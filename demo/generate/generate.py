#!/usr/bin/env python3
"""Synthetic source-data generator for the composable-CDP / MDM BigQuery demo.

Modelled on the customer file of a large Australian grocery retailer. The data
is localised to Australia — names, suburbs, states, postcodes, phone formats,
grocery categories — but the narrative is deliberately generic: no real
retailer, banner, loyalty programme or competitor is named anywhere in the
corpus.

================================================================================
ALL DATA PRODUCED BY THIS SCRIPT IS SYNTHETIC. It does not describe, and is not
derived from, any real person. Names are sampled from public frequency
distributions and combined at random; addresses pair real suburb names with
generated street numbers and are not live delivery points; telephone numbers use
narrow synthetic blocks (see the caveat in README.md — Australia's reserved
drama ranges are narrow and the generator does not claim to stay inside them);
loyalty and order references are invented.
================================================================================

The point of this generator is not the volume. It is the *ground truth*. Every
record it emits is tagged in ``truth/person_truth.csv`` with the true person it
belongs to and, where relevant, the hard case it was engineered to exercise.

Design notes
------------
* Fully deterministic for a given ``--seed`` AND a given corruption config.
  Every random draw comes from a namespaced ``random.Random`` derived by hashing
  ``seed|namespace|index`` with blake2b, so adding a new case cannot perturb the
  draws of an existing one. Nothing reads the wall clock.
* Rows within each file are sorted by ``record_id``. Row order therefore carries
  no information about person identity — a pipeline cannot cheat by exploiting
  file order.
* Global uniqueness is enforced on emails, mobiles, loyalty accounts and
  (line1, city, postcode) tuples EXCEPT where a case deliberately shares one.
  Accidental sharing would create untagged hard negatives and muddy scoring.
* Nothing about the target environment appears here. Output location is
  ``--out`` and nothing else.

Usage
-----
    python generate.py --seed 42 --people 80000 --records 200000 --out ../data

See README.md for the case catalogue and the corruption knobs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import shutil
import sys
import time
import tracemalloc
import unicodedata
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

import banks
import text_banks as tb

GENERATOR_VERSION = "2.0.0"

# Every timestamp in the corpus falls in this window. Fixed, not wall-clock
# derived, so output is stable regardless of when the generator is run.
TS_START = datetime(2019, 1, 1, 0, 0, 0)
TS_END = datetime(2025, 11, 30, 23, 59, 59)
TS_SPAN_SECONDS = int((TS_END - TS_START).total_seconds())

# Reference "today" for age arithmetic. Fixed for the same reason.
TODAY = date(2025, 12, 1)

SOURCES = ("CRM", "ECOM", "LOY", "POS", "SUP", "CALL", "ENR")

SOURCE_TRUST = {
    "CRM": 9, "LOY": 7, "ECOM": 6, "SUP": 4, "CALL": 4, "POS": 3, "ENR": 2,
}

# ---------------------------------------------------------------------------
# Case catalogue. ``target_instances`` is overwritten with the ACTUAL generated
# instance count before the catalogue is written, so the file never claims a
# target it did not hit.
# ---------------------------------------------------------------------------

CASE_CATALOGUE: list[dict[str, Any]] = [
    {
        "case_type": "HOUSEHOLD",
        "description": (
            "Four distinct people at one address, same surname, different forenames "
            "and different dates of birth. The classic rules-engine failure: address "
            "plus surname is not an identity."
        ),
        "expected_outcome": "DO_NOT_MERGE",
        "deck_slide": 12,
    },
    {
        "case_type": "SIBLING_TRAP",
        "description": (
            "Two siblings: same surname, same address, deliberately confusable "
            "forenames (Jon/John, Steven/Stephen), different dates of birth. "
            "Precision under maximum pressure — the DOB is the only clean signal."
        ),
        "expected_outcome": "DO_NOT_MERGE",
        "deck_slide": 11,
    },
    {
        "case_type": "MARRIED_NAME",
        "description": (
            "One person before and after a marriage and a house move: different "
            "surname, different address, different email. Same date of birth and "
            "same mobile number. Recall where deterministic rules fail."
        ),
        "expected_outcome": "MERGE",
        "deck_slide": 10,
    },
    {
        "case_type": "ACCOUNT_ONLY",
        "description": (
            "Exactly two records for one person whose ONLY shared signal is the "
            "loyalty account number. Names, addresses, postcodes, emails and phones "
            "all differ. Pure vector similarity misses this; the lexical/BM25 leg "
            "is what earns it."
        ),
        "expected_outcome": "MERGE",
        "deck_slide": 9,
    },
    {
        "case_type": "POSTCODE_NEAR_MISS",
        "description": (
            "Two different people at the same full postcode but different house "
            "numbers, with different dates of birth. Lexical overlap on the "
            "strongest-looking token in the record is not sufficient."
        ),
        "expected_outcome": "DO_NOT_MERGE",
        "deck_slide": 9,
    },
    {
        "case_type": "TRANSLITERATION",
        "description": (
            "One person whose name is transliterated differently in each source "
            "(Xiaoming / Xiao Ming / Hsiao-Ming; Min-jun / Minjun / Min Jun). "
            "On a third of instances the name is the ONLY link — no shared DOB, "
            "postcode or phone — so the semantic leg has to carry it alone."
        ),
        "expected_outcome": "MERGE",
        "deck_slide": 9,
    },
    {
        "case_type": "SOLE_TRADER",
        "description": (
            "An individual who is also a business entity: personal record and "
            "trading-name record share an address and a mobile. Link them, but type "
            "the relationship as a business association rather than folding the "
            "trading name into the personal golden record."
        ),
        "expected_outcome": "MERGE_WITH_FLAG",
        "deck_slide": 12,
    },
    {
        "case_type": "SHARED_EMAIL",
        "description": (
            "A couple sharing one email address, one landline and one address, with "
            "different forenames and different dates of birth. Refutes 'just match "
            "on email'."
        ),
        "expected_outcome": "DO_NOT_MERGE",
        "deck_slide": 12,
    },
    {
        "case_type": "CONSENT_CONFLICT",
        "description": (
            "One person present in three systems carrying GRANTED, NOT_GIVEN and "
            "WITHDRAWN for the same channel. Merge the person; the profile-level "
            "permission must be the intersection, with withdrawal winning."
        ),
        "expected_outcome": "MERGE",
        "deck_slide": 13,
    },
    {
        "case_type": "UNSTRUCTURED_ONLY",
        "description": (
            "A call transcript in which the caller states they are ringing about "
            "their wife's / husband's / partner's account. The transcript is "
            "saturated with the ACCOUNT HOLDER's identifiers, but the record belongs "
            "to the caller, who is a different person."
        ),
        "expected_outcome": "DO_NOT_MERGE",
        "deck_slide": 7,
    },
    {
        "case_type": "RISK_FLAG",
        "description": (
            "A support ticket whose structured identifiers belong to the account "
            "holder — so it should merge — but whose free text discloses that the "
            "holder is deceased, is a minor, or is a vulnerable customer. The "
            "adjudicator must return more than a boolean."
        ),
        "expected_outcome": "MERGE_WITH_FLAG",
        "deck_slide": 11,
    },
    {
        "case_type": "OVERMERGE_BAIT",
        "description": (
            "An A-B-C chain. B matches A on name initial and postcode; B matches C "
            "on an exact mobile number (recycled by the network). A and C have "
            "incompatible dates of birth and are demonstrably different people. "
            "Transitive closure must not swallow all three."
        ),
        "expected_outcome": "BREAK_CHAIN",
        "deck_slide": 12,
    },
    {
        "case_type": "DIACRITIC_VARIANT",
        "description": (
            "One person whose name — and sometimes their suburb — is recorded "
            "with diacritics in one system and folded to plain ASCII in another "
            "(José Muñoz / Jose Munoz, Nguyễn / Nguyen, Łukasz / Lukasz), with "
            "a minority written in the conventional transliteration that "
            "Unicode normalisation cannot recover (Müller / Mueller). Half the "
            "instances differ ONLY by the diacritic and are solvable by correct "
            "Unicode normalisation; the other half carry a second divergence so "
            "normalisation alone is not enough. The suburb slice drifts on "
            "PUNCTUATION and spacing (apostrophe and hyphen present or absent, "
            "St vs Saint) rather than on accents, because Australian place "
            "names carry almost no diacritics and inventing some would be "
            "dishonest; it exercises the same address-normalisation path."
        ),
        "expected_outcome": "MERGE",
        "deck_slide": 8,
    },
    {
        "case_type": "NAME_ORDER",
        "description": (
            "Given name and family name transposed between systems — Chen Wei "
            "in one, Wei Chen in another, sometimes with an adopted Western "
            "forename alongside (Grace Chen). Predominantly a Chinese and "
            "Korean data-entry problem, and invisible to any matcher that "
            "compares first-name to first-name."
        ),
        "expected_outcome": "MERGE",
        "deck_slide": 8,
    },
    {
        "case_type": "NAME_ORDER_TRAP",
        "description": (
            "The negative that NAME_ORDER sets up: two genuinely different "
            "people whose names are exact transpositions of each other, with "
            "different dates of birth and different addresses. A pipeline that "
            "learns 'transposed names are the same person' over-merges these."
        ),
        "expected_outcome": "DO_NOT_MERGE",
        "deck_slide": 8,
    },
]

CASE_CODES = [c["case_type"] for c in CASE_CATALOGUE]


# ---------------------------------------------------------------------------
# Determinism helpers
# ---------------------------------------------------------------------------


def make_rng(seed: int, *parts: Any) -> random.Random:
    """A namespaced PRNG.

    Uses blake2b rather than ``hash()`` because Python randomises string hashing
    per process, which would silently destroy reproducibility.
    """
    key = "|".join([str(seed)] + [str(p) for p in parts]).encode("utf-8")
    digest = hashlib.blake2b(key, digest_size=16).digest()
    return random.Random(int.from_bytes(digest, "big"))


def wchoice(rng: random.Random, pairs: Sequence[tuple[Any, float]]) -> Any:
    """Weighted choice. Stable given the same rng state and the same pairs."""
    total = 0.0
    for _, w in pairs:
        total += w
    r = rng.random() * total
    acc = 0.0
    for value, w in pairs:
        acc += w
        if r < acc:
            return value
    return pairs[-1][0]


def rand_ts(rng: random.Random, start: datetime = TS_START, end: datetime = TS_END) -> datetime:
    span = int((end - start).total_seconds())
    return start + timedelta(seconds=rng.randrange(span))


def fmt_ts(ts: datetime) -> str:
    """BigQuery's canonical CSV/JSON timestamp literal."""
    return ts.strftime("%Y-%m-%d %H:%M:%S UTC")


def fmt_date(d: Optional[date]) -> str:
    return d.isoformat() if d else ""


# ---------------------------------------------------------------------------
# Corruption configuration — every knob the README documents
# ---------------------------------------------------------------------------


@dataclass
class Corruption:
    typo_rate: float = 0.07
    transpose_rate: float = 0.04
    diminutive_rate: float = 0.45
    surname_variant_rate: float = 0.12
    postcode_drift_rate: float = 0.35
    phone_format_drift_rate: float = 0.55
    email_drift_rate: float = 0.30
    missing_field_rate: float = 0.08
    stale_address_rate: float = 0.25
    move_rate: float = 0.18
    natural_household_rate: float = 0.14
    enrich_wrong_attribution_rate: float = 0.08


# ---------------------------------------------------------------------------
# Domain objects
# ---------------------------------------------------------------------------


# City -> state abbreviation. The state is DERIVED, never stored as its own
# emitted column: the data contract carries it inside the rendered address
# string exactly as it carries the suburb. Adding a `state` column would be a
# contract change reaching into 10_land_sources.sql and 20_normalise.sql.
CITY_STATE: dict[str, str] = {
    "Sydney": "NSW", "Newcastle": "NSW", "Wollongong": "NSW",
    "Melbourne": "VIC", "Geelong": "VIC", "Ballarat": "VIC", "Bendigo": "VIC",
    "Brisbane": "QLD", "Gold Coast": "QLD", "Townsville": "QLD",
    "Cairns": "QLD", "Toowoomba": "QLD",
    "Adelaide": "SA",
    "Perth": "WA",
    "Hobart": "TAS", "Launceston": "TAS",
    "Darwin": "NT",
    "Canberra": "ACT",
}

# Fallback when a city is not in the map: the FIRST DIGIT of an Australian
# postcode is the state. ACT is carved out of the NSW range at 2600-2618 and
# 0200-0299, so it is tested before NSW.
_POSTCODE_STATE: dict[str, str] = {
    "1": "NSW", "2": "NSW", "3": "VIC", "4": "QLD",
    "5": "SA", "6": "WA", "7": "TAS", "0": "NT", "8": "NT", "9": "NT",
}


@dataclass
class Address:
    """An Australian address.

    Australian addresses are street / suburb / state / 4-digit postcode, and
    the suburb is load-bearing — people genuinely identify by it. The data
    contract has no ``address_line2``, so the suburb is folded into
    ``address_line1`` at emission time and is deliberately dropped on a share
    of records. That makes same-street-different-suburb a realistic near-miss
    rather than a giveaway.

    The STATE is derived (see ``CITY_STATE``), not stored and not emitted as
    its own column. It is rendered into the address string alongside the
    suburb, which is where the contract says it lives.
    """

    line1: str          # street only, e.g. "14 Wattle Street"
    suburb: str         # e.g. "Newtown"
    city: str           # e.g. "Sydney"
    postcode: str       # 4 digits, zero-padded, e.g. "2042" or "0812"
    std: str = "02"     # landline STD code for the region

    @property
    def state(self) -> str:
        """The state/territory abbreviation, derived from the city.

        Falls back to the postcode's first digit, which in Australia genuinely
        encodes the state. ACT is checked explicitly because its range is
        carved out of NSW's.
        """
        st = CITY_STATE.get(self.city)
        if st:
            return st
        pc = (self.postcode or "").zfill(4)
        if pc[:2] == "26" or pc[:2] == "02":
            return "ACT"
        return _POSTCODE_STATE.get(pc[:1], "NSW")

    @property
    def area(self) -> str:
        """The coarse 2-digit postal area.

        In Australia this bucket is genuinely meaningful: the first digit is
        the state and the first two together are a regional bucket within it.
        This is what POS carries, and it is still deliberately weak — a few
        dozen distinct values nationally, so it narrows a search and never
        identifies anyone.
        """
        return self.postcode[:2]

    # Retained under the old name because POS's contract column is still
    # ``postcode_outward``; see CONTRACT.md. There is no UK-style outward code
    # in Australia, but unlike the previous locale the 2-digit prefix is not
    # an arbitrary reinterpretation — see ``area`` above.
    @property
    def outward(self) -> str:
        return self.area

    def street_and_suburb(self) -> str:
        return f"{self.line1}, {self.suburb} {self.state}"

    def one_line(self) -> str:
        return f"{self.line1}, {self.suburb} {self.state} {self.postcode}"


@dataclass
class Person:
    pid: str
    forename: str
    surname: str
    gender: str
    dob: date
    addr: Address
    email: str
    mobile: str
    prev_addr: Optional[Address] = None
    prev_email: Optional[str] = None
    landline: Optional[str] = None
    maiden_surname: Optional[str] = None
    account: Optional[str] = None
    household_id: Optional[str] = None
    case_type: str = "NORMAL"
    notes: str = ""
    business_name: Optional[str] = None
    business_email: Optional[str] = None
    # Free-form slot for case builders to stash per-person presentation hints.
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def full_name(self) -> str:
        return f"{self.forename} {self.surname}"

    def age_on(self, ref: date = TODAY) -> int:
        return (ref - self.dob).days // 365


# ---------------------------------------------------------------------------
# String corruption primitives
# ---------------------------------------------------------------------------

_KEYBOARD_NEIGHBOURS = {
    "a": "qswz", "b": "vghn", "c": "xdfv", "d": "serfcx", "e": "wsdr",
    "f": "drtgvc", "g": "ftyhbv", "h": "gyujnb", "i": "ujko", "j": "huikmn",
    "k": "jiolm", "l": "kop", "m": "njk", "n": "bhjm", "o": "iklp",
    "p": "ol", "q": "wa", "r": "edft", "s": "awedxz", "t": "rfgy",
    "u": "yhji", "v": "cfgb", "w": "qase", "x": "zsdc", "y": "tghu",
    "z": "asx",
}


def apply_typo(rng: random.Random, s: str) -> str:
    """A single realistic keying error."""
    if len(s) < 4:
        return s
    mode = wchoice(rng, [("sub", 40), ("drop", 25), ("double", 20), ("swap", 15)])
    i = rng.randrange(1, len(s) - 1)
    ch = s[i].lower()
    if mode == "sub" and ch in _KEYBOARD_NEIGHBOURS:
        repl = rng.choice(_KEYBOARD_NEIGHBOURS[ch])
        repl = repl.upper() if s[i].isupper() else repl
        return s[:i] + repl + s[i + 1:]
    if mode == "drop":
        return s[:i] + s[i + 1:]
    if mode == "double":
        return s[:i] + s[i] + s[i:]
    return s[:i] + s[i + 1] + s[i] + s[i + 2:]


def transpose_words(rng: random.Random, s: str) -> str:
    parts = s.split(" ")
    if len(parts) < 2:
        return s
    i = rng.randrange(len(parts) - 1)
    parts[i], parts[i + 1] = parts[i + 1], parts[i]
    return " ".join(parts)


_STREET_ABBREV = [
    (" Road", " Rd"), (" Street", " St"), (" Lane", " Ln"), (" Avenue", " Ave"),
    (" Close", " Cl"), (" Court", " Ct"), (" Drive", " Dr"), (" Terrace", " Terr"),
    (" Crescent", " Cres"), (" Gardens", " Gdns"), (" Place", " Pl"),
    ("Flat ", "Fl "), ("Apartment ", "Apt "),
]


def drift_address_line(rng: random.Random, line: str, cfg: Corruption) -> str:
    out = line
    if rng.random() < 0.30:
        for full, abbrev in _STREET_ABBREV:
            if full in out:
                out = out.replace(full, abbrev)
                break
    if rng.random() < cfg.typo_rate:
        out = apply_typo(rng, out)
    if rng.random() < 0.10:
        out = out.upper()
    if rng.random() < 0.06:
        out = out.replace(",", "")
    return out


def drift_postcode(rng: random.Random, postcode: str, cfg: Corruption) -> str:
    """Format drift on a 4-digit Australian postcode.

    The headline trap is ``zero_strip``. Northern Territory postcodes begin
    with a zero (``0800``, ``0810``, ``0812``, ``0820``, ``0828``, ``0832``),
    and any pass through a spreadsheet or a numeric column silently eats it.
    The loyalty source stores postcodes as integers, so it drops the zero
    natively — ``0812`` becomes ``812``. It is not recoverable by string
    comparison — ``812`` and ``0812`` look nothing alike — but a left-pad to
    four characters fixes the whole class.

    DARWIN IS THE ONLY PRODUCER OF THIS TRAP. Every other state range starts
    with 1-7, and the ACT range (2600-2618) has no leading zero either.
    Removing Darwin from the city list silently removes a hard-case signal.

    Only the ``typo`` branch changes *which* postcode it is, which is
    deliberate: a small share of postcodes in any real file are simply wrong.
    """
    if rng.random() >= cfg.postcode_drift_rate:
        return postcode
    modes: list[tuple[str, float]] = [
        ("typo", 16), ("area_only", 9), ("padded", 7), ("state_prefix", 4),
    ]
    if postcode.startswith("0"):
        modes.append(("zero_strip", 64))
    mode = wchoice(rng, modes)
    if mode == "zero_strip":
        return postcode.lstrip("0") or "0"
    if mode == "area_only":
        return postcode[:2]
    if mode == "padded":
        return f" {postcode} "
    if mode == "state_prefix":
        # The state abbreviation typed into the postcode field. Derived from
        # the first digit rather than passed in, so this stays a pure string
        # drift with no dependency on the address it came from.
        pc = postcode.zfill(4)
        st = "ACT" if pc[:2] == "26" else _POSTCODE_STATE.get(pc[:1], "NSW")
        return f"{st} {postcode}"
    return apply_typo(rng, postcode)


def drift_phone(rng: random.Random, phone: str, cfg: Corruption) -> str:
    """Format drift on a canonical Australian number.

    Canonical forms arriving here are 10 digits either way: ``0412345678``
    (mobile: ``04`` plus 8 digits) or ``0894567890`` (landline: 2-digit area
    code plus 8 digits).

    MOBILES ARE IDENTIFIED BY THE ``04`` PREFIX, NOT BY LENGTH. An earlier
    version of this generator could use ``len(phone) == 10`` because its
    landlines were 9 digits. In Australia both are 10, so a length test
    silently classifies every landline as a mobile. Australian area codes are
    2, 3, 7 and 8, so ``04`` is unambiguous.

    The important trap is that the international form **drops the trunk zero**
    — ``0412 345 678`` and ``+61 412 345 678`` are the same number, and a
    matcher that compares the strings, or that naively strips non-digits,
    concludes they are different. ``+610412...`` is the wrong answer and is
    exactly the bug class to watch for. Getting from one to the other requires
    knowing the rule, which is exactly the kind of thing that quietly costs
    recall in a real MDM build.
    """
    mobile = phone.startswith("04")
    # The trunk zero is dropped under +61 regardless of number kind, so the
    # international significant digits are simply everything after it.
    intl = phone[1:]

    if rng.random() >= cfg.phone_format_drift_rate:
        return (
            f"{phone[:4]} {phone[4:7]} {phone[7:]}" if mobile
            else f"({phone[:2]}) {phone[2:6]} {phone[6:]}"
        )

    mode = wchoice(
        rng,
        [("e164", 20), ("e164_spaced", 16), ("plain", 18), ("spaced_3_4", 14),
         ("bracket", 10), ("dashes", 8), ("intl_00", 6), ("split_prefix", 8)],
    )
    # Australian grouping: mobiles read 4-3-3 (0412 345 678), landlines read
    # (0A) 4-4 ((08) 9456 7890). The international forms drop the trunk zero.
    if mode == "e164":
        return f"+61{intl}"
    if mode == "e164_spaced":
        return (
            f"+61 {intl[:3]} {intl[3:6]} {intl[6:]}" if mobile
            else f"+61 {intl[:1]} {intl[1:5]} {intl[5:]}"
        )
    if mode == "plain":
        return phone
    if mode == "spaced_3_4":
        return (
            f"{phone[:4]} {phone[4:7]} {phone[7:]}" if mobile
            else f"{phone[:2]} {phone[2:6]} {phone[6:]}"
        )
    if mode == "bracket":
        # Brackets round the area code are idiomatic for landlines and a
        # recognisable data-entry habit on mobiles.
        return (
            f"({phone[:4]}) {phone[4:7]} {phone[7:]}" if mobile
            else f"({phone[:2]}) {phone[2:6]} {phone[6:]}"
        )
    if mode == "dashes":
        return (
            f"{phone[:4]}-{phone[4:7]}-{phone[7:]}" if mobile
            else f"{phone[:2]}-{phone[2:6]}-{phone[6:]}"
        )
    if mode == "intl_00":
        return f"0061 {intl}"
    return f"{phone[:4]} {phone[4:]}" if mobile else f"{phone[:2]} {phone[2:]}"


# ---------------------------------------------------------------------------
# Diacritics.
#
# Australian customer files carry accented Latin names from every migration
# wave: José, Renée, Müller, Nguyễn, Łukasz, Muñoz, Šimić, Horváth. This is a
# TWO-orthography problem spread across many languages, rather than a
# single-language accent convention:
#
#   accented   José / Renée / Müller / Nguyễn      what the customer writes
#   folded     Jose / Renee / Muller / Nguyen      what a system that cannot
#                                                  store the character does
#
# Both spellings are the same name. A matcher that treats them as different
# strings loses recall on exactly the customers whose names are hardest to key,
# which is both a data-quality failure and a bad look.
#
# A minority of names additionally carry a CONVENTIONAL TRANSLITERATION — the
# German ü -> ue convention gives ``Müller`` -> ``Mueller``. That third form is
# the functional replacement for the double-vowel form that used to sit
# here, and it matters for the same reason: the folded form is recoverable by
# NFKD-normalising and dropping combining marks, the conventional form is NOT,
# and needs either a rule or the semantic leg. That split is what the
# DIACRITIC_VARIANT hard case is built on — "normalisation gets you close, the
# graph finishes the job".
#
# Two traps, both of which have bitten this code before:
#
#   1. NFKD-FIRST, NOT DELETION. Folding must decompose and drop the combining
#      mark, so ``é`` becomes ``e``. An earlier implementation DELETED the
#      accented character outright, which loses the letter entirely and breaks
#      matching on precisely the names the case is about. Do not undo this.
#   2. NFKD DOES NOT FOLD EVERYTHING. Ł ł Ø ø Đ đ Ħ ħ Ŧ ŧ are single code points
#      with no canonical decomposition, and Æ æ Œ œ ß likewise. NFKD leaves them
#      untouched, so they need an explicit table. ``Łukasz`` is in the
#      DIACRITIC_VARIANT pool as the worked example: without the special case it
#      folds to ``Łukasz``, the "solvable by normalisation alone" half of the
#      case silently stops being solvable, and the slide becomes a lie.
# ---------------------------------------------------------------------------

# Only the characters NFKD cannot decompose. Everything that HAS a canonical
# decomposition (é, ü, ñ, å, ç, ễ, ...) is handled generically by NFKD and must
# NOT be listed here — duplicating it here is how the table drifts out of date.
_FOLD_SPECIAL_TABLE = {
    ord("ł"): "l", ord("Ł"): "L",
    ord("ø"): "o", ord("Ø"): "O",
    ord("đ"): "d", ord("Đ"): "D",
    ord("ħ"): "h", ord("Ħ"): "H",
    ord("ŧ"): "t", ord("Ŧ"): "T",
    ord("ß"): "ss",
    ord("æ"): "ae", ord("Æ"): "AE",
    ord("œ"): "oe", ord("Œ"): "OE",
}

# The non-decomposable letters, as a plain string, so has_diacritic() can test
# membership without walking the table.
_NON_FOLDABLE = "łŁøØđĐħĦŧŦßæÆœŒ"

# The conventional transliterations. Deliberately NOT the same as folding:
# ``Müller`` folds to ``Muller`` but transliterates to ``Mueller``, and only the
# first of those is recoverable by Unicode normalisation.
_CONVENTIONAL_TABLE = {
    ord("ü"): "ue", ord("Ü"): "Ue",
    ord("ö"): "oe", ord("Ö"): "Oe",
    ord("ä"): "ae", ord("Ä"): "Ae",
    ord("ß"): "ss",
}


def has_diacritic(s: str) -> bool:
    """True if the string carries an accent OR a non-decomposable Latin letter.

    The second half is not optional: ``Łukasz`` yields no combining mark under
    NFKD, so a combining-mark-only test would report it as unaccented.
    """
    decomposed = unicodedata.normalize("NFKD", s)
    if any(unicodedata.combining(ch) for ch in decomposed):
        return True
    return any(ch in _NON_FOLDABLE for ch in s)


def fold_diacritics(s: str) -> str:
    """``José`` -> ``Jose``, ``Łukasz`` -> ``Lukasz``. Also handles decomposed input.

    NFKD first (decompose, then drop the combining marks), THEN the special-case
    table for the letters NFKD cannot decompose. The ordering is a bug fix — see
    the block comment above — and reversing it, or replacing the fold with a
    deletion, breaks the DIACRITIC_VARIANT case.
    """
    decomposed = unicodedata.normalize("NFKD", s)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.translate(_FOLD_SPECIAL_TABLE)


def conventional_variant(s: str) -> str:
    """``Müller`` -> ``Mueller``. Returns the input unchanged when no rule applies.

    This is the orthography NFKD cannot recover, which is the whole point of it.
    Most names have no conventional variant, and returning them untouched is the
    correct answer rather than a failure.
    """
    return unicodedata.normalize("NFC", s).translate(_CONVENTIONAL_TABLE)


def norm_email(email: str) -> str:
    """Collapse a mailbox to the form two drifted spellings would share.

    ``J.Smith+shop@googlemail.com`` and ``jsmith@gmail.com`` normalise to the
    same key. Two DIFFERENT people must never own mailboxes that collide under
    this, or the corpus contains untagged false-merge bait.
    """
    local, _, domain = email.strip().lower().partition("@")
    local = local.split("+")[0].replace(".", "").replace("_", "").replace("-", "")
    return f"{local}@{banks.DOMAIN_CANON.get(domain, domain)}"


def drift_email(rng: random.Random, email: str, cfg: Corruption) -> str:
    if rng.random() >= cfg.email_drift_rate:
        return email
    local, _, domain = email.partition("@")
    mode = wchoice(
        rng,
        [("plustag", 30), ("dots", 20), ("undot", 15), ("domain", 15),
         ("digits", 10), ("case", 10)],
    )
    if mode == "plustag":
        return f"{local}+{rng.choice(banks.EMAIL_TAGS)}@{domain}"
    if mode == "dots" and "." not in local and len(local) > 4:
        i = rng.randrange(2, len(local) - 1)
        return f"{local[:i]}.{local[i:]}@{domain}"
    if mode == "undot":
        return f"{local.replace('.', '')}@{domain}"
    if mode == "domain":
        return f"{local}@{banks.DOMAIN_DRIFT.get(domain, domain)}"
    if mode == "digits":
        return f"{local}{rng.randrange(1, 99)}@{domain}"
    return f"{local.capitalize()}@{domain}"


# ---------------------------------------------------------------------------
# Person construction
# ---------------------------------------------------------------------------

_AGE_BANDS: list[tuple[tuple[int, int], int]] = [
    ((18, 24), 12), ((25, 34), 21), ((35, 44), 19), ((45, 54), 18),
    ((55, 64), 15), ((65, 74), 9), ((75, 92), 6),
]

# Incidental full-name collisions.
#
# Two different synthetic people drawing the same forename AND surname is not,
# by itself, a problem — real customer files are full of namesakes, and a file
# with none would be unrealistically easy to resolve. The problem is a namesake
# pair that is *indistinguishable*, because then the ground truth asks the
# pipeline to do something no correct pipeline could do, and precision falls for
# a reason that has nothing to do with the algorithm.
#
# So we do not chase the collision count down. Suppressing it at 80,000 people
# would require name pools flat enough that no real population resembles them.
# Instead we let namesakes happen and guarantee they are always separable: a
# free-draw name may only be reused if every existing holder lives in a
# different city AND was born at least _NAME_REUSE_DOB_GAP years apart. A hard
# ceiling stops any single name piling up.
_NAME_REUSE_CEILING = 4
_NAME_REUSE_DOB_GAP = 5
_NAME_REUSE_TRIES = 24


# ---------------------------------------------------------------------------
# Forbidden forename/surname COMBINATIONS
# ---------------------------------------------------------------------------
#
# Some names are only wrong in combination. Both halves are individually
# legitimate and deliberately retained in the banks, so no amount of scrubbing
# the pools will catch these -- the check has to happen at the pair.
#
# The class of failure this exists for: a forename that is a perfectly ordinary
# given name, and a surname that is a perfectly ordinary surname with many real
# bearers, which together name one specific thing or one specific person. No
# amount of scrubbing either pool can catch that, because neither half is the
# problem. On screen at a customer event it is not a near miss -- it is exactly
# the error the whole name-bank exercise was meant to avoid.
#
# Matching is case-folded and diacritic-folded, so "Jose Garcia",
# "José García" and "JOSE GARCIA" would all be caught by a single entry.
FORBIDDEN_PAIRS: set[tuple[str, str]] = set()


def _fold_name(s: str) -> str:
    """Casefold and strip diacritics, so one entry covers every spelling.

    General NFKD + combining-mark removal, then ``_FOLD_SPECIAL_TABLE`` for the
    letters NFKD cannot decompose (Ł ø đ ß æ œ ...). Without that second step
    ``Łukasz`` folds to ``łukasz`` rather than ``lukasz`` and a roster entry
    spelled either way would fail to match the other.
    """
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    ).translate(_FOLD_SPECIAL_TABLE).casefold().strip()


# Hand-written pairs whose halves are individually innocuous.
#
# THIS LOOP IS THE MECHANISM. Keep it even when the list is empty.
#
# It is the seam for pairs that NOTABLE_FULL_NAMES cannot express: combinations
# that are wrong without naming a public figure -- a place, an institution, a
# brand, a slur, a sacred or ceremonial name -- assembled out of two halves that
# both belong in the pools on their own merits. The roster below covers the
# "real person" case; this list covers everything else, and the next person to
# find such a pair needs somewhere to put it without re-deriving the plumbing.
#
# The Australian list is currently empty. That is a statement about the author's
# recall, not a proof that no such pair exists in these pools -- exactly the
# caveat the roster comment makes below. Append here rather than editing the
# banks: both halves are legitimate and removing either one degrades the pools.
_SEED_FORBIDDEN_PAIRS: list[tuple[str, str]] = [
    # ("Forename", "Surname"),
]

for _fn, _sn in _SEED_FORBIDDEN_PAIRS:
    FORBIDDEN_PAIRS.add((_fold_name(_fn), _fold_name(_sn)))


# ---------------------------------------------------------------------------
# NOTABLE_FULL_NAMES -- the blocklist roster (Australia / UK / US)
# ---------------------------------------------------------------------------
#
# This is a BLOCKLIST. Every name here is excluded from the synthetic corpus so
# that a generated "customer" can never turn out to be a recognisable real
# person. Listing someone here protects them; it is the opposite of using them.
#
# Populated into FORBIDDEN_PAIRS by splitting each entry on the FIRST space.
# Matching is case-folded and diacritic-folded, so one entry covers every
# spelling variant.
#
# ---------------------------------------------------------------------------
# THE SELECTION RULE, so the next person does not delete entries at random
# ---------------------------------------------------------------------------
# Block a pair when it is DISTINCTIVE AND FAMOUS -- when an ordinary reader
# seeing it on a screen would think of one specific person. Do NOT block a name
# merely because someone famous happens to have it. "Steve Smith" is a Test
# captain and also the most generic pair the ANGLO pool can produce; blocking it
# removes a name tens of thousands of real customers have and protects nobody,
# because nobody reading it thinks of the batsman. The same reasoning excludes
# "Michael Clarke", "Cameron Smith", "Adam Scott", "Tony Jones" and "Ray Martin".
#
# Australia is a small country, so a name is uniquely associated with one public
# figure far more often than it would be in a larger one. The test therefore
# passes more often than it feels like it should. That is why this list runs to
# ~150 entries and not ~50.
#
# Two exceptions to the rule, both deliberate:
#   1. The crime and miscarriage-of-justice group is blocked REGARDLESS of
#      distinctiveness. The harm there is not embarrassment. SEE THE GAP NOTE
#      AT THE BOTTOM OF THIS FILE -- that group is NOT populated here.
#   2. Where a diminutive reaches a notable name, BOTH the diminutive and the
#      canonical forename are blocked ("Bill Shorten" and "William Shorten"),
#      because reverting the substitution lands on the same real person. The
#      exception to the exception is when the canonical form is innocuous:
#      "Maggie Smith" is blocked but "Margaret Smith" is NOT, because Smith is
#      the most common surname in the pool and the pair evokes nobody.
#
# THIS LIST IS NOT COVERAGE. On the previous locale's pools, two systematic passes
# found 138 reachable notable names from 461 candidates -- a ~30% hit rate that
# did not decay between passes, because the binding constraint is the author's
# recall, not the pools. The emitted-row sweep is the safety net. This is a
# knowledge artefact.
#
# Entries that are NOT currently reachable cost nothing to keep listed; pools
# change, and an unreachable entry goes live the moment someone adds a forename.
#
# A malformed entry -- one that does not split into exactly two parts on the
# first space -- is a HARD BUILD FAILURE, not a warning. A typo here would
# otherwise silently fail to block anything.

NOTABLE_FULL_NAMES: list[str] = [
    # -- federal politics -------------------------------------------------
    "Anthony Albanese",     # Prime Minister
    "Scott Morrison",       # former Prime Minister
    "Malcolm Turnbull",     # former Prime Minister
    "Tony Abbott",          # former Prime Minister
    "Anthony Abbott",       #   canonical form of the above
    "Julia Gillard",        # former Prime Minister
    "Kevin Rudd",           # former Prime Minister
    "John Howard",          # former Prime Minister
    "Paul Keating",         # former Prime Minister
    "Bob Hawke",            # former Prime Minister
    "Robert Hawke",         #   canonical form of the above
    "Malcolm Fraser",       # former Prime Minister
    "Gough Whitlam",        # former Prime Minister
    "Bill Shorten",         # former Opposition Leader
    "William Shorten",      #   canonical form of the above
    "Peter Dutton",         # Opposition Leader
    "Penny Wong",           # Foreign Minister
    "Jim Chalmers",         # Treasurer
    "James Chalmers",       #   canonical form of the above
    "Josh Frydenberg",      # former Treasurer
    "Tanya Plibersek",      # minister
    "Barnaby Joyce",        # former Deputy Prime Minister
    "Michaelia Cash",       # senator
    "Pauline Hanson",       # senator
    "Adam Bandt",           # former Greens leader
    "Richard Marles",       # Deputy Prime Minister
    "Katy Gallagher",       # senator
    "Sussan Ley",           # Opposition Leader
    "Julie Bishop",         # former Foreign Minister
    "Wayne Swan",           # former Treasurer
    "Peter Costello",       # former Treasurer
    "Quentin Bryce",        # former Governor-General
    # -- state politics ---------------------------------------------------
    "Daniel Andrews",       # former Victorian Premier
    "Gladys Berejiklian",   # former NSW Premier
    "Annastacia Palaszczuk",  # former Queensland Premier
    "Mark McGowan",         # former WA Premier
    "Roger Cook",           # WA Premier
    "Chris Minns",          # NSW Premier
    "Jacinta Allan",        # Victorian Premier
    "David Crisafulli",     # Queensland Premier
    "Peter Malinauskas",    # SA Premier
    "Dominic Perrottet",    # former NSW Premier
    "Steven Marshall",      # former SA Premier
    "Jeff Kennett",         # former Victorian Premier
    "Bob Carr",             # former NSW Premier
    # -- Indigenous Australian leaders and activists ----------------------
    "Eddie Mabo",           # land rights
    "Vincent Lingiari",     # Gurindji strike leader
    "Charles Perkins",      # activist
    "Noel Pearson",         # lawyer and activist
    "Marcia Langton",       # academic
    "Linda Burney",         # former minister
    "Patrick Dodson",       # former senator
    "Michael Dodson",       # lawyer and academic
    "Neville Bonner",       # first Indigenous federal parliamentarian
    "Faith Bandler",        # civil rights campaigner
    "Lowitja Odonoghue",    # administrator and campaigner
    "Galarrwuy Yunupingu",  # Yolngu leader
    "Gurrumul Yunupingu",   # musician
    "Archie Roach",         # musician
    "Ruby Hunter",          # musician
    "Adam Goodes",          # footballer and Australian of the Year
    "Nova Peris",           # Olympian and former senator
    "Stan Grant",           # journalist
    "Jessica Mauboy",       # musician
    "Lionel Rose",          # boxer
    "Evonne Goolagong",     # tennis
    "Patty Mills",          # basketball
    # -- sport ------------------------------------------------------------
    "Don Bradman",          # cricket
    "Donald Bradman",       #   canonical form of the above
    "Shane Warne",          # cricket
    "Ricky Ponting",        # cricket
    "Richard Ponting",      #   canonical form of the above
    "Glenn McGrath",        # cricket
    "Adam Gilchrist",       # cricket
    "Pat Cummins",          # cricket
    "Patrick Cummins",      #   canonical form of the above
    "Ellyse Perry",         # cricket
    "Meg Lanning",          # cricket
    "Belinda Clark",        # cricket
    "Cathy Freeman",        # athletics
    "Ian Thorpe",           # swimming
    "Dawn Fraser",          # swimming
    "Emma McKeon",          # swimming
    "Ariarne Titmus",       # swimming
    "Kyle Chalmers",        # swimming
    "Grant Hackett",        # swimming
    "Rod Laver",            # tennis
    "Margaret Court",       # tennis
    "Ash Barty",            # tennis
    "Ashleigh Barty",       #   canonical form of the above
    "Nick Kyrgios",         # tennis
    "Lleyton Hewitt",       # tennis
    "Pat Rafter",           # tennis
    "Greg Norman",          # golf
    "Gregory Norman",       #   canonical form of the above
    "Karrie Webb",          # golf
    "Sam Kerr",             # football
    "Samantha Kerr",        #   canonical form of the above
    "Tim Cahill",           # football
    "Lance Franklin",       # Australian rules
    "Dustin Martin",        # Australian rules
    "Wayne Carey",          # Australian rules
    "Leigh Matthews",       # Australian rules
    "Johnathan Thurston",   # rugby league
    "Andrew Johns",         # rugby league
    "Darren Lockyer",       # rugby league
    "Mal Meninga",          # rugby league
    "John Eales",           # rugby union
    "Anna Meares",          # cycling
    "Layne Beachley",       # surfing
    "Mick Fanning",         # surfing
    "Daniel Ricciardo",     # motorsport
    "Peter Brock",          # motorsport
    "Jack Brabham",         # motorsport
    # -- arts, film, music, letters ---------------------------------------
    "Cate Blanchett",       # actor
    "Nicole Kidman",        # actor
    "Hugh Jackman",         # actor
    "Russell Crowe",        # actor
    "Chris Hemsworth",      # actor
    "Margot Robbie",        # actor
    "Geoffrey Rush",        # actor
    "Toni Collette",        # actor
    "Eric Bana",            # actor
    "Rebel Wilson",         # actor
    "Rose Byrne",           # actor
    "Sam Neill",            # actor
    "Heath Ledger",         # actor
    "Naomi Watts",          # actor
    "Guy Pearce",           # actor
    "Jacki Weaver",         # actor
    "Bryan Brown",          # actor
    "Baz Luhrmann",         # director
    "Kylie Minogue",        # musician
    "Dannii Minogue",       # musician
    "Nick Cave",            # musician
    "Nicholas Cave",        #   canonical form of the above
    "Paul Kelly",           # musician
    "Jimmy Barnes",         # musician
    "Michael Hutchence",    # musician
    "Missy Higgins",        # musician
    "Courtney Barnett",     # musician
    "Delta Goodrem",        # musician
    "Keith Urban",          # musician
    "Peter Garrett",        # musician and former minister
    "Tim Minchin",          # musician and comedian
    "Barry Humphries",      # comedian
    "Magda Szubanski",      # comedian
    "Shaun Micallef",       # comedian
    "Hannah Gadsby",        # comedian
    "Adam Hills",           # comedian
    "Tim Winton",           # novelist
    "Timothy Winton",       #   canonical form of the above
    "Peter Carey",          # novelist
    "Thomas Keneally",      # novelist
    "Helen Garner",         # writer
    "Richard Flanagan",     # novelist
    "Kate Grenville",       # novelist
    "David Malouf",         # writer
    "Patrick White",        # novelist, Nobel laureate
    "Markus Zusak",         # novelist
    "Liane Moriarty",       # novelist
    "Trent Dalton",         # novelist
    "Judith Wright",        # poet
    "Sidney Nolan",         # painter
    "Brett Whiteley",       # painter
    "Albert Namatjira",     # painter
    # -- media and broadcasting -------------------------------------------
    "Leigh Sales",          # broadcaster
    "Kerry Obrien",         # broadcaster
    "Laura Tingle",         # journalist
    "Annabel Crabb",        # journalist
    "Waleed Aly",           # broadcaster
    "Lisa Wilkinson",       # broadcaster
    "Karl Stefanovic",      # broadcaster
    # -- business ---------------------------------------------------------
    "Gina Rinehart",        # mining
    "Andrew Forrest",       # mining
    "Clive Palmer",         # mining and politics
    "Frank Lowy",           # property
    "Kerry Stokes",         # media
    "Kerry Packer",         # media
    "James Packer",         # media
    "Rupert Murdoch",       # media
    "Scott Farquhar",       # software
    "Melanie Perkins",      # software
    "Solomon Lew",          # retail
    "Anthony Pratt",        # packaging
    "Alan Joyce",           # aviation
    # -- science and medicine ---------------------------------------------
    "Howard Florey",        # Nobel laureate
    "Barry Marshall",       # Nobel laureate
    "Robin Warren",         # Nobel laureate
    "Peter Doherty",        # Nobel laureate
    "Elizabeth Blackburn",  # Nobel laureate
    "Brian Schmidt",        # Nobel laureate
    "Fiona Wood",           # surgeon
    "Fiona Stanley",        # epidemiologist
    "Ian Frazer",           # immunologist
    "Michelle Simmons",     # physicist
    "Graeme Clark",         # cochlear implant
    "Gustav Nossal",        # immunologist
    "Tim Flannery",         # scientist and writer
    # -- United Kingdom ---------------------------------------------------
    "Winston Churchill",
    "Margaret Thatcher",
    "Tony Blair",
    "Gordon Brown",
    "David Cameron",
    "Theresa May",
    "Boris Johnson",
    "Keir Starmer",
    "Rishi Sunak",
    "Liz Truss",
    "Elizabeth Truss",      #   canonical form of the above
    "David Attenborough",
    "Stephen Hawking",
    "Alan Turing",
    "Charles Darwin",
    "Isaac Newton",
    "Paul McCartney",
    "John Lennon",
    "George Harrison",
    "Mick Jagger",
    "Michael Jagger",       #   canonical form of the above
    "Keith Richards",
    "David Bowie",
    "Freddie Mercury",
    "Elton John",
    "Ed Sheeran",
    "Edward Sheeran",       #   canonical form of the above
    "Judi Dench",
    "Maggie Smith",         # NB: "Margaret Smith" deliberately NOT blocked
    "Ian McKellen",
    "Daniel Craig",
    "Emma Watson",
    "Kate Winslet",
    "Rowan Atkinson",
    "Ricky Gervais",
    "David Beckham",
    "Harry Kane",
    "Lewis Hamilton",
    "Andy Murray",
    "Andrew Murray",        #   canonical form of the above
    # -- United States ----------------------------------------------------
    "Barack Obama",
    "Michelle Obama",
    "Joe Biden",
    "Joseph Biden",         #   canonical form of the above
    "Donald Trump",
    "Hillary Clinton",
    "Ronald Reagan",
    "Abraham Lincoln",
    "Rosa Parks",
    "Oprah Winfrey",
    "Taylor Swift",
    "Michael Jackson",
    "Elvis Presley",
    "Bob Dylan",
    "Bruce Springsteen",
    "Tom Hanks",
    "Thomas Hanks",         #   canonical form of the above
    "Meryl Streep",
    "Denzel Washington",
    "Leonardo DiCaprio",
    "Scarlett Johansson",
    "Steven Spielberg",
    "Martin Scorsese",
    "Quentin Tarantino",
    "Bill Gates",
    "William Gates",        #   canonical form of the above
    "Steve Jobs",
    "Steven Jobs",          #   canonical form of the above
    "Elon Musk",
    "Jeff Bezos",
    "Mark Zuckerberg",
    "Warren Buffett",
    "Michael Jordan",
    "Serena Williams",
    "Venus Williams",
    "Tiger Woods",
    "Muhammad Ali",
    "Albert Einstein",
    "Neil Armstrong",
    "Buzz Aldrin",
]

# ---------------------------------------------------------------------------
# GAP -- the crime and miscarriage-of-justice group is NOT populated
# ---------------------------------------------------------------------------
# The selection rule above says this group is blocked REGARDLESS of
# distinctiveness, because the harm is not embarrassment. The roster this
# replaces had such a section and it was load-bearing.
#
# It is deliberately EMPTY here, and that is a real gap, not an oversight:
#
#   * This roster was assembled by a language model. Enumerating real people
#     associated with crime -- victims, the convicted, and the wrongly
#     convicted -- is the one category where an automated list is most likely
#     to be wrong about a specific individual, and being wrong there is
#     defamatory rather than merely embarrassing.
#   * It is also the category where the wrongly convicted must be protected
#     most carefully, and that judgement needs someone with local knowledge
#     and a source, not recall.
#
# ACTION REQUIRED: a human with Australian legal/current-affairs knowledge
# should populate this section before the demo is shown externally. Add entries
# to NOTABLE_FULL_NAMES above in the same two-part form.
#
# Until then, the emitted-row sweep remains the actual safety net -- as it is
# for every other category, none of which is complete either.

# ---------------------------------------------------------------------------
# Not reachable today, listed because a single pool edit would make them so.
# These cost nothing to keep and go live the moment someone adds a forename or
# a surname to the pools.
# ---------------------------------------------------------------------------
# Banjo Paterson, Henry Lawson, Nellie Melba, John Monash, Weary Dunlop,
# Caroline Chisholm, Edith Cowan, Mary MacKillop, Douglas Mawson, Charles Kingsford,
# Bert Hinkler, Nancy Bird, Dame Enid Lyons, Vida Goldstein, Jack Lang,
# Ben Chifley, John Curtin, Robert Menzies, Alfred Deakin, Edmund Barton.


# Forename equivalence classes, so exception 2 of the selection rule is
# enforced MECHANICALLY rather than by the roster author's recall.
#
# The rule: where a diminutive reaches a notable name, every other form that
# reaches the SAME person must be blocked too, because undoing the
# substitution lands back on them. Hand-maintaining that is hopeless -- the
# first Australian roster listed "Bill Shorten" and "William Shorten" but left
# "Billy Shorten" open, and did the same for 48 other entries. The roster
# audit caught all 49.
#
# So: group every forename with its canonical form and all that form's other
# diminutives, then block the whole class against the roster surname. One
# roster entry therefore blocks Bob / Bobby / Robert Hawke, not just the
# spelling the author happened to think of.
#
# Iteration is over sorted keys and the result is a set of folded tuples, so
# this adds nothing order-dependent to the build.
_FORENAME_CLASS: dict[str, set[str]] = {}
for _canon in sorted(banks.DIMINUTIVES):
    _family = {_canon, *banks.DIMINUTIVES[_canon]}
    for _form in sorted(_family):
        _FORENAME_CLASS.setdefault(_fold_name(_form), set()).update(_family)


def _forename_variants(forename: str) -> list[str]:
    """Every forename that the substitution layer can swap with this one.

    Returns a sorted list so callers stay deterministic.
    """
    return sorted(_FORENAME_CLASS.get(_fold_name(forename), {forename}))


for _full in NOTABLE_FULL_NAMES:
    _parts = _full.split(" ", 1)
    if len(_parts) == 2:
        _sn = _fold_name(_parts[1])
        for _fn_variant in _forename_variants(_parts[0]):
            FORBIDDEN_PAIRS.add((_fold_name(_fn_variant), _sn))



def _forbidden_pair(forename: str, surname: str) -> bool:
    """True if this forename/surname combination must not be emitted.

    Covers the explicit list above, plus any reduplicated name. The forename
    and surname banks share entries by design -- Thomas, Nguyen, Mario and
    Antonio are all real in both positions -- which means a free draw can
    produce "Thomas Thomas", "Nguyen Nguyen" or "Lin Lin". Those are real
    names in principle but on a screen they read as a data-entry bug, which
    is a distraction in a demo whose entire subject is data quality.

    The reduplication rule (``f == s``) is locale-independent and is NOT tied
    to the roster or to any name bank. Do not remove it when repointing the
    corpus at a new locale -- the pools change, the failure does not.
    """
    f, s = _fold_name(forename), _fold_name(surname)
    if not f or not s:
        return False
    if f == s:
        return True
    return (f, s) in FORBIDDEN_PAIRS



class World:
    """Owns every global uniqueness constraint and every id counter."""

    def __init__(self, seed: int, cfg: Corruption) -> None:
        self.seed = seed
        self.cfg = cfg
        self.people: list[Person] = []
        self.emails: set[str] = set()
        # Normalised mailbox -> the people who legitimately own it. Sharing is
        # allowed only where a case deliberately arranges it (SHARED_EMAIL).
        self.email_norm_owners: dict[str, set[str]] = {}
        self.mobiles: set[str] = set()
        self.landlines: set[str] = set()
        self.accounts: set[str] = set()
        self.addresses: set[tuple[str, str, str]] = set()
        # (forename, surname) -> [(city, birth_year), ...] for everyone already
        # carrying that exact name. Used to keep namesakes separable.
        self.name_holders: dict[tuple[str, str], list[tuple[str, int]]] = {}
        self.name_reuse_fallbacks = 0
        # Forbidden forename/surname pairs that survived because BOTH halves
        # were pinned by a case builder, leaving nothing for make_person to
        # redraw. Must stay at zero; if it ever rises, the builder that pinned
        # the pair is the thing to fix, not this loop.
        self.forbidden_pair_unfixable = 0

        self._person_seq = 0
        self._household_seq = 0

    # -- ids -------------------------------------------------------------
    def next_person_id(self) -> str:
        self._person_seq += 1
        return f"P-{self._person_seq:06d}"

    def next_household_id(self) -> str:
        self._household_seq += 1
        return f"H-{self._household_seq:05d}"

    # -- atoms -----------------------------------------------------------
    def pick_city(self, rng: random.Random):
        """A weighted city row: (city, std, region_profile, suburbs, weight)."""
        return wchoice(rng, [(row, row[4]) for row in banks.CITIES])

    def make_address(self, rng: random.Random, city_row=None) -> Address:
        for _ in range(64):
            row = city_row if city_row is not None else self.pick_city(rng)
            city, std, _profile, suburbs, _w = row
            suburb, pc_int = rng.choice(suburbs)
            postcode = f"{pc_int:04d}"
            line1 = self._make_line1(rng)
            key = (line1, suburb, postcode)
            if key not in self.addresses:
                self.addresses.add(key)
                return Address(line1, suburb, city, postcode, std)
        # Extremely unlikely; fall through with a disambiguating suffix.
        return Address(f"{line1} (Rear)", suburb, city, postcode, std)

    def _make_line1(self, rng: random.Random) -> str:
        street = wchoice(rng, banks.STREETS)
        number = rng.randrange(1, 260)
        style = wchoice(
            rng,
            # "3/42 Queen Street" is the standard Australian way of writing a
            # unit in a block and is far more common than the British
            # "Flat 3, 42 ...".
            [("plain", 66), ("slash", 16), ("flat", 8), ("named", 5), ("sub", 5)],
        )
        if style == "plain":
            return f"{number} {street}"
        if style == "slash":
            return f"{rng.randrange(1, 12)}/{number} {street}"
        if style == "flat":
            return f"Flat {rng.randrange(1, 12)}, {number} {street}"
        if style == "named":
            return f"Apartment {rng.randrange(1, 60)}, {rng.choice(banks.NAMED_BUILDINGS)}, {street}"
        return f"{number}{rng.choice('ABC')} {street}"

    def sibling_address(self, rng: random.Random, addr: Address) -> Address:
        """Same suburb and postcode, different street number.

        Used by POSTCODE_NEAR_MISS. In Australia a 4-digit postcode covers a
        whole suburb or several, so sharing one is much weaker evidence than
        sharing a UK postcode was — which makes this case harder here, and
        fairly so.
        """
        for _ in range(64):
            line1 = self._make_line1(rng)
            key = (line1, addr.suburb, addr.postcode)
            if key not in self.addresses and line1 != addr.line1:
                self.addresses.add(key)
                return Address(line1, addr.suburb, addr.city, addr.postcode, addr.std)
        return Address(f"{rng.randrange(260, 460)} {wchoice(rng, banks.STREETS)}",
                       addr.suburb, addr.city, addr.postcode, addr.std)

    def make_mobile(self, rng: random.Random) -> str:
        """``04x9xxxxxx`` — a real AU prefix with a synthetic 9-leading block.

        Ten digits total, matching the national form ``0412 345 678``.
        1,000,000 numbers per prefix across the ``040``-``049`` prefixes, so
        the uniqueness loop stays cheap even at 80,000 people. Australia's
        reserved drama ranges are narrow and this does not claim to sit inside
        them; see the caveat in README.md.
        """
        for _ in range(400):
            prefix = wchoice(rng, banks.MOBILE_PREFIXES)
            n = f"{prefix}9{rng.randrange(0, 1000000):06d}"
            if n not in self.mobiles:
                self.mobiles.add(n)
                return n
        raise RuntimeError("exhausted synthetic mobile range")

    def make_landline(self, rng: random.Random, std: str = "02") -> str:
        """``0A9xxxxxxx`` — area code plus a synthetic 9-leading 8-digit local.

        Ten digits total, matching ``(08) 9456 7890``. Note this is ONE DIGIT
        LONGER than the previous locale's: Australian landline locals are 8 digits,
        not 7, which is why ``drift_phone`` cannot tell mobiles from landlines
        by length and tests the ``04`` prefix instead.
        """
        for _ in range(400):
            n = f"{std}9{rng.randrange(0, 10000000):07d}"
            if n not in self.landlines:
                self.landlines.add(n)
                return n
        raise RuntimeError("exhausted synthetic landline range")

    def make_account(self, rng: random.Random) -> str:
        """``ACC-nnnnnnn``. 7 digits, not 5.

        At 80,000 people with ~55% card ownership we need ~44,000 accounts. A
        5-digit space (90,000 values) is close enough to exhaustion that the
        retry loop starts thrashing and the values stop being uniform.
        """
        for _ in range(500):
            a = f"ACC-{rng.randrange(1000000, 10000000)}"
            if a not in self.accounts:
                self.accounts.add(a)
                return a
        raise RuntimeError("exhausted synthetic account range")

    # -- names -----------------------------------------------------------
    # Forename and surname are drawn from the same cultural group unless a
    # cross-group draw is made explicitly. Independent draws produce
    # combinations like "Wei Ngata" at a rate that an audience will spot.
    #
    # The group mix is also biased by region. Sydney and Melbourne are far more
    # diverse than the regional centres, Melbourne carries a much higher Greek
    # and Italian share than the national average, and Perth is more Anglo with
    # a distinct South-East Asian presence. A file where every city looks like
    # the national average looks wrong to anyone who lives here.
    def pick_group(self, rng: random.Random, profile: str = "DEFAULT") -> str:
        weights = banks.NAME_GROUP_WEIGHTS_BY_REGION.get(
            profile, banks.NAME_GROUP_WEIGHTS
        )
        return wchoice(rng, weights)

    def forename_for(self, rng: random.Random, gender: str, group: str) -> str:
        bank = (
            banks.FEMALE_FORENAMES_BY_GROUP if gender == "F"
            else banks.MALE_FORENAMES_BY_GROUP
        )
        return wchoice(rng, bank.get(group) or bank["ANGLO"])

    def surname_for(
        self,
        rng: random.Random,
        group: str,
        allow_cross: bool = True,
        profile: str = "DEFAULT",
    ) -> str:
        g = group
        if allow_cross and rng.random() < banks.CROSS_GROUP_RATE:
            g = self.pick_group(rng, profile)
        pool = banks.SURNAMES_BY_GROUP.get(g) or banks.SURNAMES_BY_GROUP["ANGLO"]
        return wchoice(rng, pool)

    @staticmethod
    def group_of_surname(surname: str) -> str:
        return banks.SURNAME_GROUP.get(surname, "ANGLO")

    @staticmethod
    def group_of_forename(forename: str) -> str:
        return banks.FORENAME_GROUP.get(forename, "ANGLO")

    def make_email(self, rng: random.Random, forename: str, surname: str) -> str:
        fn = _slug(forename)
        sn = _slug(surname)
        for attempt in range(400):
            domain = wchoice(rng, banks.EMAIL_DOMAINS)
            style = wchoice(
                rng,
                [("dot", 34), ("initial", 20), ("concat", 16), ("dot_num", 14),
                 ("underscore", 8), ("sn_fn", 8)],
            )
            if style == "dot":
                local = f"{fn}.{sn}"
            elif style == "initial":
                local = f"{fn[:1]}{sn}"
            elif style == "concat":
                local = f"{fn}{sn}"
            elif style == "dot_num":
                local = f"{fn}.{sn}{rng.randrange(1, 99)}"
            elif style == "underscore":
                local = f"{fn}_{sn}"
            else:
                local = f"{sn}.{fn}"
            if attempt > 8:
                local = f"{local}{rng.randrange(100, 9999)}"
            email = f"{local}@{domain}"
            if email not in self.emails and norm_email(email) not in self.email_norm_owners:
                self.emails.add(email)
                # Owner is stamped in by make_person once the id exists.
                self.email_norm_owners.setdefault(norm_email(email), set())
                return email
        raise RuntimeError("could not allocate a unique email")

    def claim_email(self, email: str, owner: Optional[str] = None) -> str:
        self.emails.add(email)
        owners = self.email_norm_owners.setdefault(norm_email(email), set())
        if owner:
            owners.add(owner)
        return email

    def owns_email(self, email: str, pid: str) -> bool:
        """True if ``pid`` may present ``email`` without impersonating anyone."""
        owners = self.email_norm_owners.get(norm_email(email))
        return not owners or pid in owners

    # -- people ----------------------------------------------------------
    def _separable(self, forename: str, surname: str, city: str, year: int) -> bool:
        """True if a new person may take this name and still be tellable apart.

        Nobody holds it, or every current holder lives in a different city and
        was born at least ``_NAME_REUSE_DOB_GAP`` years away.
        """
        holders = self.name_holders.get((forename, surname))
        if not holders:
            return True
        if len(holders) >= _NAME_REUSE_CEILING:
            return False
        return all(
            c != city and abs(y - year) >= _NAME_REUSE_DOB_GAP
            for c, y in holders
        )

    def _claim_name(self, forename: str, surname: str, city: str, year: int) -> None:
        self.name_holders.setdefault((forename, surname), []).append((city, year))

    def _free_name(
        self,
        rng: random.Random,
        gender: str,
        profile: str,
        city: str,
        birth_year: int,
    ) -> tuple[str, str]:
        """Draw a forename and surname that nobody indistinguishable already has.

        Namesakes are allowed and expected. What is not allowed is a namesake
        who could not be told apart: same name, same city, similar age. Those
        would be untagged false-merge bait, and they would penalise a pipeline
        for failing a question that has no answer in the data.

        Falls back to accepting a collision after ``_NAME_REUSE_TRIES``, which
        is rare enough not to matter and is counted in the manifest.

        The fallback relaxes separability only. A forbidden pair is never
        acceptable, so the last non-forbidden draw is kept aside and used if
        the loop runs out -- otherwise exhaustion silently emits whatever the
        final draw happened to be, which is exactly how "Lewis Lewis" reached
        the corpus after the guard was added.
        """
        forename = surname = ""
        fallback: Optional[tuple[str, str]] = None
        for _ in range(_NAME_REUSE_TRIES):
            group = self.pick_group(rng, profile)
            forename = self.forename_for(rng, gender, group)
            surname = self.surname_for(rng, group, profile=profile)
            if _forbidden_pair(forename, surname):
                continue
            if fallback is None:
                fallback = (forename, surname)
            if self._separable(forename, surname, city, birth_year):
                break
        else:
            # Gave up: this person is a namesake who may not be separable.
            # Reported in the manifest so the figure is never hidden.
            self.name_reuse_fallbacks += 1
            if fallback is not None:
                forename, surname = fallback
        self._claim_name(forename, surname, city, birth_year)
        return forename, surname


    def make_person(
        self,
        rng: random.Random,
        *,
        case_type: str = "NORMAL",
        notes: str = "",
        gender: Optional[str] = None,
        forename: Optional[str] = None,
        surname: Optional[str] = None,
        dob: Optional[date] = None,
        addr: Optional[Address] = None,
        household_id: Optional[str] = None,
        email: Optional[str] = None,
        mobile: Optional[str] = None,
        with_account: Optional[bool] = None,
        age_range: Optional[tuple[int, int]] = None,
    ) -> Person:
        gender = gender or ("F" if rng.random() < 0.51 else "M")

        # Address and date of birth are settled BEFORE the name, for two
        # reasons: the region biases which cultural group the name is drawn
        # from, and the namesake check below needs both to decide whether a
        # repeat of an existing name would still be separable.
        if dob is None:
            lo, hi = age_range if age_range else wchoice(rng, _AGE_BANDS)
            age = rng.randrange(lo, hi + 1)
            dob = date(TODAY.year - age, rng.randrange(1, 13), rng.randrange(1, 29))
        # Whether we are allowed to move this person. A case builder that pins
        # the address is doing so on purpose (siblings and households share
        # one), so that address must not be second-guessed below.
        addr_was_free = addr is None
        if addr is None:
            addr = self.make_address(rng)
        profile = banks.CITY_PROFILE.get(addr.city, "DEFAULT")

        # Resolve the cultural group from whichever half of the name is already
        # fixed, so a case builder that pins a surname still gets a plausible
        # forename beside it.
        if forename is None and surname is None:
            forename, surname = self._free_name(rng, gender, profile, addr.city, dob.year)
        else:
            # At least one half is pinned by a case builder or by household
            # membership. Redraw the free half until the resulting pair is
            # separable from anyone already holding it -- without this, a
            # household that fixes the surname bypasses the namesake check
            # entirely.
            both_pinned = forename is not None and surname is not None
            # As in _free_name: separability is a soft constraint that the
            # fallback may relax, but a forbidden pair is not. Keep the first
            # non-forbidden candidate so that giving up never emits one.
            ok_fallback: Optional[tuple[str, str]] = None
            for _ in range(_NAME_REUSE_TRIES):
                if forename is None:
                    candidate = (
                        self.forename_for(rng, gender, self.group_of_surname(surname)),
                        surname,
                    )
                elif surname is None:
                    candidate = (
                        forename,
                        self.surname_for(
                            rng, self.group_of_forename(forename), profile=profile
                        ),
                    )
                else:
                    candidate = (forename, surname)
                bad_pair = _forbidden_pair(candidate[0], candidate[1])
                if not bad_pair and ok_fallback is None:
                    ok_fallback = candidate
                if self._separable(*candidate, addr.city, dob.year) and not bad_pair:
                    break
                if both_pinned and addr_was_free:
                    # Neither half of the name can move -- NAME_ORDER and
                    # NAME_ORDER_TRAP both draw from a fixed pool of family
                    # names, so two instances can land on the same one. The
                    # address is the free variable instead: move this person to
                    # another city and the namesake becomes separable again.
                    addr = self.make_address(rng)
                    profile = banks.CITY_PROFILE.get(addr.city, "DEFAULT")
                    continue
                if both_pinned:
                    # Both halves pinned and the pair is forbidden: nothing in
                    # this loop can fix it, so the caller must. Recorded rather
                    # than silently shipped.
                    if bad_pair:
                        self.forbidden_pair_unfixable += 1
                    break
            else:
                self.name_reuse_fallbacks += 1
                if ok_fallback is not None:
                    candidate = ok_fallback
            forename, surname = candidate

            self._claim_name(forename, surname, addr.city, dob.year)
        if email is None:
            email = self.make_email(rng, forename, surname)
        else:
            self.claim_email(email)
        if mobile is None:
            mobile = self.make_mobile(rng)

        if with_account is None:
            with_account = rng.random() < 0.55
        account = self.make_account(rng) if with_account else None

        p = Person(
            pid=self.next_person_id(),
            forename=forename,
            surname=surname,
            gender=gender,
            dob=dob,
            addr=addr,
            email=email,
            mobile=mobile,
            account=account,
            household_id=household_id,
            case_type=case_type,
            notes=notes,
        )
        self.claim_email(p.email, p.pid)
        # House moves: a previous address that will leak into low-trust sources.
        if rng.random() < self.cfg.move_rate:
            p.prev_addr = self.make_address(rng)
        if rng.random() < 0.22:
            p.prev_email = self.claim_email(
                self.make_email(rng, forename, surname), p.pid
            )
        if rng.random() < 0.30:
            p.landline = self.make_landline(rng, addr.std)
        self.people.append(p)
        return p


def _slug(s: str) -> str:
    """Email-safe local part. Drops apostrophes, hyphens, spaces and accents."""
    return "".join(ch for ch in s.lower() if ch.isalnum()) or "user"


# ---------------------------------------------------------------------------
# Record emission
# ---------------------------------------------------------------------------


@dataclass
class TruthRow:
    record_id: str
    true_person_id: str
    true_household_id: str
    case_type: str
    notes: str


class Emitter:
    """Builds source-shaped rows and the matching truth rows."""

    def __init__(self, world: World, max_transcripts: int = 10 ** 9) -> None:
        self.world = world
        self.cfg = world.cfg
        self.seed = world.seed
        self.rows: dict[str, list[dict[str, Any]]] = {s: [] for s in SOURCES}
        self.transcripts: dict[str, str] = {}
        self.max_transcripts = max_transcripts
        self.consent: list[dict[str, Any]] = []
        self.truth: list[TruthRow] = []
        self._rid_seq = 0
        self._rids: set[str] = set()
        self._seq = {"cust": 0, "acct": 0, "txn": 0, "ticket": 0, "call": 0, "consent": 0}
        # Every (forename, surname) pair that actually reaches a row, AFTER
        # diminutive substitution, surname-variant substitution and typos.
        #
        # This exists because the Person is the INPUT to emission, not the
        # output. `_pick_forename` and `_pick_surname` substitute at emission
        # time, so a person named "William English" can be written to a CRM row
        # as "Bill English", and a check that walks `world.people` sees only
        # "William English" and passes. The clearest case is "Jackie Chan":
        # neither "Jackie" nor "Chan" is in any name pool, and the pair is
        # composed entirely out of the substitution layer from "Jacqueline
        # Chen". No entry in NOTABLE_FULL_NAMES could ever have caught it,
        # because the roster is consulted against the person and the person is
        # not what is written.
        #
        # Recording the pairs here, at the one place where both halves are
        # known and final, makes the check independent of how many substitution
        # layers get added later. That is the property we actually want: the
        # previous three defects all arrived through a new path that an
        # existing guard did not know about.
        self.emitted_names: set[tuple[str, str]] = set()
        self.emitted_name_reverts = 0
        self.emitted_name_unfixable = 0
        self.emitted_name_unfixable_detail: list[str] = []

    # -- ids -------------------------------------------------------------
    def new_record_id(self, src: str) -> str:
        self._rid_seq += 1
        n = self._rid_seq
        while True:
            h = hashlib.blake2b(
                f"{self.seed}|rid|{src}|{n}".encode("utf-8"), digest_size=4
            ).hexdigest()
            rid = f"{src}-{h}"
            if rid not in self._rids:
                self._rids.add(rid)
                return rid
            # Jump clear of the ordinary counter range so we can never collide
            # with a future sequential draw.
            n += 10_000_000

    def _next(self, key: str) -> int:
        self._seq[key] += 1
        return self._seq[key]

    # -- truth -----------------------------------------------------------
    def _truth(self, rid: str, p: Person, case_type: Optional[str], notes: str) -> None:
        self.truth.append(
            TruthRow(
                record_id=rid,
                true_person_id=p.pid,
                true_household_id=p.household_id or "",
                case_type=case_type if case_type is not None else p.case_type,
                notes=notes or p.notes,
            )
        )

    # -- presentation helpers -------------------------------------------
    def _pick_forename(self, rng: random.Random, p: Person, allow_dim: bool) -> str:
        fn = p.extra.get("forename_override") or p.forename
        if allow_dim and rng.random() < self.cfg.diminutive_rate:
            dims = banks.DIMINUTIVES.get(fn)
            if dims:
                return rng.choice(dims)
        if rng.random() < self.cfg.typo_rate:
            return apply_typo(rng, fn)
        return fn

    def _pick_surname(self, rng: random.Random, p: Person, variant_boost: float = 0.0) -> str:
        sn = p.extra.get("surname_override") or p.surname
        if rng.random() < (self.cfg.surname_variant_rate + variant_boost):
            variants = banks.SURNAME_VARIANTS.get(sn)
            if variants:
                return rng.choice(variants)
        if rng.random() < self.cfg.typo_rate:
            return apply_typo(rng, sn)
        return sn

    def _vet_pair(
        self,
        p: Person,
        fn: str,
        sn: str,
        *,
        base_fn: Optional[str] = None,
        base_sn: Optional[str] = None,
    ) -> tuple[str, str]:
        """Vet a forename/surname pair at the point of emission.

        `make_person` vets the name it assigns to the Person, but three things
        happen after that which it cannot see:

        * `_pick_forename` may substitute a diminutive (William -> Bill),
        * `_pick_surname` may substitute a `SURNAME_VARIANTS` entry
          (Reed -> Read) or the caller may pin a different surname entirely,
        * either may apply a typo.

        Any of those can turn a perfectly ordinary person into a recognisable
        public figure. Measured examples from this corpus, all of which passed
        the previous person-level check: `William English` -> **Bill English**
        (a former Prime Minister), `Michael Moore` -> `Mike Moore` (another),
        `Kieran Reed` -> `Kieran Read` (All Black captain), `Jacqueline Chen`
        -> `Jackie Chan`.

        When the composed pair is forbidden the SUBSTITUTION is undone rather
        than the person being renamed. That is deliberate: the person is
        already vetted and is a legitimate member of the population, and
        renaming them here would ripple into every other record they own and
        into the truth file. Undoing the substitution costs one diminutive.

        `base_fn` / `base_sn` carry the caller's pinned value where there is
        one, so reverting respects a pin instead of silently overriding it.
        """
        canon_fn = base_fn or p.extra.get("forename_override") or p.forename
        canon_sn = base_sn if base_sn is not None else (
            p.extra.get("surname_override") or p.surname
        )
        if _forbidden_pair(fn, sn):
            # Smallest change first: revert one side, then the other, then
            # both. Trying the forename first is not arbitrary -- diminutive
            # substitution is the commonest cause, and reverting it keeps the
            # surname variant that the matching logic is supposed to be
            # challenged by.
            for cand_fn, cand_sn in (
                (canon_fn, sn),
                (fn, canon_sn),
                (canon_fn, canon_sn),
            ):
                if not _forbidden_pair(cand_fn, cand_sn):
                    self.emitted_name_reverts += 1
                    fn, sn = cand_fn, cand_sn
                    break
            else:
                # Nothing to revert to -- both halves were pinned by a case
                # builder and the pinned pair is itself forbidden. Counted and
                # recorded rather than silently emitted; the sweep in
                # build_manifest turns it into a build failure.
                self.emitted_name_unfixable += 1
                self.emitted_name_unfixable_detail.append(
                    f"{p.pid} [{p.case_type}] {fn} {sn}"
                )
        self.emitted_names.add((fn, sn))
        return fn, sn

    def _drift_email(self, rng: random.Random, email: str, p: Person) -> str:
        """Corrupt an email, but never onto somebody else's mailbox.

        ``+tag``, dot and domain drift can all land on a different person's
        address by accident. That would be an untagged hard negative, which
        quietly depresses measured precision for a reason that has nothing to
        do with anything the demo is trying to show. If a variant collides, the
        original is emitted unchanged.
        """
        out = drift_email(rng, email, self.cfg)
        if out != email and not self.world.owns_email(out, p.pid):
            return email
        return out

    def transcript_budget_spent(self) -> bool:
        """True once the cap on individual transcript files has been reached.

        Only consulted for the background population. Hard cases go through
        their own builders and are never throttled — UNSTRUCTURED_ONLY is
        entirely made of transcripts.
        """
        return len(self.transcripts) >= self.max_transcripts

    def _pick_addr(self, rng: random.Random, p: Person, stale_ok: bool) -> Address:
        if stale_ok and p.prev_addr and rng.random() < self.cfg.stale_address_rate:
            return p.prev_addr
        return p.addr

    def _line1(self, rng: random.Random, a: Address, suburb_rate: float = 0.66) -> str:
        """Render ``address_line1`` for a source that has no suburb column.

        Australian addresses carry the suburb and state between the street and
        the postcode, and the contract gives us nowhere to put either, so they
        go on the end of line 1 — but only on ``suburb_rate`` of records. Real
        systems disagree about this constantly: the CRM captured it, the
        ecommerce checkout didn't, the loyalty signup put it in the city field.
        The result is that "14 Wattle Street, Newtown NSW" and "14 Wattle
        Street" have to be recognised as the same doorstep without being
        treated as identical strings.
        """
        base = a.street_and_suburb() if rng.random() < suburb_rate else a.line1
        return drift_address_line(rng, base, self.cfg)

    # -- CRM (trust 9) ---------------------------------------------------
    def crm(
        self,
        rng: random.Random,
        p: Person,
        *,
        case_type: Optional[str] = None,
        notes: str = "",
        forename: Optional[str] = None,
        surname: Optional[str] = None,
        full_name: Optional[str] = None,
        addr: Optional[Address] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        dob: Optional[date] = ...,  # type: ignore[assignment]
        force_dob: bool = False,
        ts: Optional[datetime] = None,
    ) -> str:
        rid = self.new_record_id("CRM")
        a = addr or self._pick_addr(rng, p, stale_ok=False)
        if full_name is None:
            fn = forename or self._pick_forename(rng, p, allow_dim=False)
            sn = surname if surname is not None else self._pick_surname(rng, p)
            fn, sn = self._vet_pair(p, fn, sn, base_fn=forename, base_sn=surname)
            style = wchoice(rng, [("plain", 78), ("comma", 8), ("middle", 8), ("title", 6)])
            if style == "plain":
                full_name = f"{fn} {sn}"
            elif style == "comma":
                full_name = f"{sn}, {fn}"
            elif style == "middle":
                full_name = f"{fn} {rng.choice('ABCDEFGHJLMNPRSTW')} {sn}"
            else:
                title = "Mr" if p.gender == "M" else rng.choice(["Mrs", "Ms", "Miss"])
                full_name = f"{title} {fn} {sn}"
        the_dob = p.dob if dob is ... else dob
        if the_dob is not None and not force_dob and rng.random() < 0.03:
            the_dob = None  # CRM: "rarely null"
        self.rows["CRM"].append(
            {
                "record_id": rid,
                "customer_ref": f"C{self._next('cust'):06d}",
                "full_name": full_name,
                "address_line1": self._line1(rng, a, suburb_rate=0.82),
                "city": a.city,
                "postcode": a.postcode if rng.random() > 0.10 else drift_postcode(rng, a.postcode, self.cfg),
                "email": email if email is not None else p.email,
                "phone": phone if phone is not None else drift_phone(rng, p.mobile, self.cfg),
                "dob": fmt_date(the_dob),
                "created_at": fmt_ts(ts or rand_ts(rng)),
            }
        )
        self._truth(rid, p, case_type, notes)
        return rid

    # -- ECOM (trust 6) --------------------------------------------------
    def ecom(
        self,
        rng: random.Random,
        p: Person,
        *,
        case_type: Optional[str] = None,
        notes: str = "",
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = ...,  # type: ignore[assignment]
        postcode: Optional[str] = ...,  # type: ignore[assignment]
        dob: Optional[date] = ...,  # type: ignore[assignment]
        addr: Optional[Address] = None,
        ts: Optional[datetime] = None,
    ) -> str:
        rid = self.new_record_id("ECOM")
        a = addr or self._pick_addr(rng, p, stale_ok=True)
        fn = first_name or self._pick_forename(rng, p, allow_dim=True)
        sn = last_name if last_name is not None else self._pick_surname(rng, p)
        fn, sn = self._vet_pair(p, fn, sn, base_fn=first_name, base_sn=last_name)
        if email is None:
            base = p.prev_email if (p.prev_email and rng.random() < 0.12) else p.email
            em = self._drift_email(rng, base, p)
        else:
            em = email
        if phone is ...:
            ph = "" if rng.random() < 0.55 else drift_phone(rng, p.mobile, self.cfg)
        else:
            ph = phone or ""
        if postcode is ...:
            pc = "" if rng.random() < 0.40 else drift_postcode(rng, a.postcode, self.cfg)
        else:
            pc = postcode or ""
        if dob is ...:
            d = None if rng.random() < 0.60 else p.dob
        else:
            d = dob
        self.rows["ECOM"].append(
            {
                "record_id": rid,
                "account_ref": f"EC{self._next('acct'):06d}",
                "first_name": fn,
                "last_name": sn,
                "email": em,
                "phone": ph,
                "postcode": pc,
                "dob": fmt_date(d),
                "created_at": fmt_ts(ts or rand_ts(rng)),
            }
        )
        self._truth(rid, p, case_type, notes)
        return rid

    # -- LOY (trust 7) ---------------------------------------------------
    def loyalty(
        self,
        rng: random.Random,
        p: Person,
        *,
        case_type: Optional[str] = None,
        notes: str = "",
        member_name: Optional[str] = None,
        account: Optional[str] = None,
        addr: Optional[Address] = None,
        mobile: Optional[str] = None,
        dob: Optional[date] = ...,  # type: ignore[assignment]
        ts: Optional[datetime] = None,
    ) -> str:
        rid = self.new_record_id("LOY")
        a = addr or self._pick_addr(rng, p, stale_ok=True)
        if member_name is None:
            fn = self._pick_forename(rng, p, allow_dim=rng.random() < 0.5)
            sn = self._pick_surname(rng, p)
            fn, sn = self._vet_pair(p, fn, sn)
            style = wchoice(
                rng,
                [("full", 48), ("initial", 26), ("upper", 12), ("surname_first", 8), ("lower", 6)],
            )
            if style == "full":
                member_name = f"{fn} {sn}"
            elif style == "initial":
                member_name = f"{fn[:1]} {sn}"
            elif style == "upper":
                member_name = f"{fn} {sn}".upper()
            elif style == "surname_first":
                member_name = f"{sn.upper()} {fn[:1]}"
            else:
                member_name = f"{fn} {sn}".lower()
        acct = account or p.account
        if acct is None:
            acct = self.world.make_account(rng)
            p.account = acct
        if dob is ...:
            d = None if rng.random() < 0.30 else p.dob
        else:
            d = dob
        self.rows["LOY"].append(
            {
                "record_id": rid,
                "account_number": acct,
                "member_name": member_name,
                "address_line1": self._line1(rng, a, suburb_rate=0.55),
                "city": a.city,
                "postcode": drift_postcode(rng, a.postcode, self.cfg),
                "mobile": mobile if mobile is not None else drift_phone(rng, p.mobile, self.cfg),
                "dob": fmt_date(d),
                "card_issued_at": fmt_ts(ts or rand_ts(rng)),
            }
        )
        self._truth(rid, p, case_type, notes)
        return rid

    # -- POS (trust 3) ---------------------------------------------------
    def pos(
        self,
        rng: random.Random,
        p: Person,
        *,
        case_type: Optional[str] = None,
        notes: str = "",
        surname: Optional[str] = None,
        initial: Optional[str] = None,
        outward: Optional[str] = None,
        account: Optional[str] = ...,  # type: ignore[assignment]
        ts: Optional[datetime] = None,
    ) -> str:
        rid = self.new_record_id("POS")
        a = self._pick_addr(rng, p, stale_ok=True)
        sn = surname if surname is not None else self._pick_surname(rng, p, variant_boost=0.03)
        init = initial if initial is not None else (p.extra.get("forename_override") or p.forename)[:1].upper()
        ow = outward if outward is not None else a.outward
        if account is ...:
            # CONTRACT.md: ~35% of POS rows carry a loyalty number. Roughly 55%
            # of people hold a card and roughly 53% of their baskets are scanned
            # with it, which lands in the right place. Measured: see manifest.
            acct = p.account if (p.account and rng.random() < 0.53) else ""
        else:
            acct = account or ""
        category, lo, hi = _pos_category(rng)
        amount = rng.uniform(lo, hi)
        self.rows["POS"].append(
            {
                "record_id": rid,
                "txn_id": f"T{self._next('txn'):09d}",
                "surname": sn,
                "initial": init,
                "postcode_outward": ow,
                "loyalty_account_number": acct,
                "store_id": f"STORE-{_stable_store(a.postcode):03d}",
                "txn_ts": fmt_ts(ts or rand_ts(rng)),
                "amount_aud": f"{amount:.2f}",
                "category": category,
            }
        )
        self._truth(rid, p, case_type, notes)
        return rid

    # -- SUP (trust 4) ---------------------------------------------------
    def support(
        self,
        rng: random.Random,
        p: Person,
        *,
        case_type: Optional[str] = None,
        notes: str = "",
        contact_name: Optional[str] = None,
        contact_email: Optional[str] = ...,  # type: ignore[assignment]
        body: Optional[str] = None,
        subject: Optional[str] = None,
        ts: Optional[datetime] = None,
    ) -> str:
        rid = self.new_record_id("SUP")
        if body is None:
            subject, body = _render_ticket(rng, p, self.cfg)
        if contact_name is not None:
            name = contact_name
        else:
            # Split out of the original inline f-string so the pair can be
            # vetted. The RNG draw order is unchanged: the `allow_dim`
            # argument is evaluated before the forename call in both forms.
            _fn = self._pick_forename(rng, p, allow_dim=rng.random() < 0.3)
            _sn = self._pick_surname(rng, p)
            _fn, _sn = self._vet_pair(p, _fn, _sn)
            name = f"{_fn} {_sn}"
        if contact_email is ...:
            em = "" if rng.random() < 0.20 else self._drift_email(rng, p.email, p)
        else:
            em = contact_email or ""
        full_body = f"Subject: {subject}\n\n{body}" if subject else body
        self.rows["SUP"].append(
            {
                "record_id": rid,
                "ticket_id": f"TK-{self._next('ticket'):06d}",
                "contact_name": name,
                "contact_email": em,
                "body": full_body,
                "created_at": fmt_ts(ts or rand_ts(rng)),
            }
        )
        self._truth(rid, p, case_type, notes)
        return rid

    # -- CALL (trust 4) --------------------------------------------------
    def call(
        self,
        rng: random.Random,
        p: Person,
        *,
        case_type: Optional[str] = None,
        notes: str = "",
        body: Optional[str] = None,
        ts: Optional[datetime] = None,
    ) -> str:
        rid = self.new_record_id("CALL")
        when = ts or rand_ts(rng)
        call_id = f"CL-{self._next('call'):06d}"
        agent = rng.choice(banks.AGENT_IDS)
        agent_name = rng.choice(tb.AGENT_FIRST_NAMES)
        if body is None:
            body = _render_call(rng, p, self.cfg)
        opener = rng.choice(tb.CALL_OPENERS).format(agent=agent_name)
        closer = rng.choice(tb.CALL_CLOSERS)
        secs = rng.randrange(95, 640)
        duration = f"{secs // 3600:02d}:{(secs % 3600) // 60:02d}:{secs % 60:02d}"
        header = (
            "CALL RECORDING - AUTOMATED TRANSCRIPT (UNVERIFIED, SYNTHETIC)\n"
            f"Call ID: {call_id}\n"
            f"Agent:   {agent}\n"
            f"Date:    {fmt_ts(when)}\n"
            f"Duration: {str(duration)}\n"
            "Channel: Inbound / Customer Care\n"
            + "-" * 72
            + "\n"
        )
        text = f"{header}AGENT: {opener}\n{body}{closer}\n" + "-" * 72 + "\nEND OF TRANSCRIPT\n"
        self.transcripts[rid] = text
        self.rows["CALL"].append(
            {
                "record_id": rid,
                "uri": f"call_transcripts/{rid}.txt",
                "call_id": call_id,
                "agent_id": agent,
                "call_ts": fmt_ts(when),
            }
        )
        self._truth(rid, p, case_type, notes)
        return rid

    # -- ENR (trust 2) ---------------------------------------------------
    def enrich(
        self,
        rng: random.Random,
        p: Person,
        *,
        case_type: Optional[str] = None,
        notes: str = "",
        name: Optional[str] = None,
        addr: Optional[Address] = None,
        email: Optional[str] = None,
        wrong_attribution_of: Optional[Person] = None,
    ) -> str:
        rid = self.new_record_id("ENR")
        vendor, clo, chi = _pick_vendor(rng)
        if wrong_attribution_of is not None:
            other = wrong_attribution_of
            nm = name or f"{p.forename} {p.surname}"
            a = other.addr
            em = other.email
            conf = round(rng.uniform(clo, min(chi, 0.72)), 3)
            note = (
                f"{notes} WRONG_ATTRIBUTION: vendor '{vendor}' has attached "
                f"{other.pid}'s address and email to {p.pid}'s name. Truth follows the "
                "name. A pipeline that merges this with the address owner is wrong."
            ).strip()
        else:
            if name:
                nm = name
            else:
                # Split out of the original inline f-string so the pair can be
                # vetted; RNG draw order is unchanged. This source applies the
                # heaviest surname-variant rate in the generator
                # (variant_boost=0.05), which makes it the likeliest place for
                # a substitution to compose a real person's name.
                _fn = self._pick_forename(rng, p, allow_dim=rng.random() < 0.25)
                _sn = self._pick_surname(rng, p, variant_boost=0.05)
                _fn, _sn = self._vet_pair(p, _fn, _sn)
                nm = f"{_fn} {_sn}"
            a = addr or (p.prev_addr if (p.prev_addr and rng.random() < 0.45) else p.addr)
            em = email if email is not None else (p.prev_email or self._drift_email(rng, p.email, p))
            conf = round(rng.uniform(clo, chi), 3)
            note = notes
        if rng.random() < 0.18:
            nm = transpose_words(rng, nm)
        self.rows["ENR"].append(
            {
                "record_id": rid,
                "name": nm,
                "address": a.one_line(),
                "postcode": drift_postcode(rng, a.postcode, self.cfg),
                "email": em,
                "vendor": vendor,
                "vendor_confidence": conf,
            }
        )
        self._truth(rid, p, case_type, note)
        return rid

    # -- consent ---------------------------------------------------------
    def add_consent(
        self,
        rng: random.Random,
        record_id: str,
        channel: str,
        status: str,
        purpose: str,
        ts: Optional[datetime] = None,
    ) -> None:
        self.consent.append(
            {
                "consent_id": f"CN-{self._next('consent'):07d}",
                "record_id": record_id,
                "channel": channel,
                "status": status,
                "purpose": purpose,
                "captured_at": fmt_ts(ts or rand_ts(rng)),
            }
        )


def _stable_store(postcode: str) -> int:
    """Deterministic store id derived from the postcode, not from rng state.

    Hashing the full 4-digit postcode over a 190-store estate gives roughly the
    footprint of a national grocery chain, and keeps a customer's transactions
    clustered on the stores near where they live.
    """
    h = hashlib.blake2b(postcode.encode("utf-8"), digest_size=2).digest()
    return (int.from_bytes(h, "big") % 190) + 1


def _pos_category(rng: random.Random) -> tuple[str, float, float]:
    pairs = [((c, lo, hi), w) for c, w, lo, hi in banks.POS_CATEGORIES]
    return wchoice(rng, pairs)


def _pick_vendor(rng: random.Random) -> tuple[str, float, float]:
    return rng.choice(banks.ENRICH_VENDORS)


# ---------------------------------------------------------------------------
# Free-text rendering
# ---------------------------------------------------------------------------


def _ordinal(n: int) -> str:
    """1 -> '1st', 2 -> '2nd', 3 -> '3rd', 11 -> '11th', 22 -> '22nd'.

    Every use of the day slot in the text banks used to be written as the
    literal ``"the {day}th"``. The slot is ``randrange(2, 28)``, and five of
    those twenty-six values take a different suffix (2nd, 3rd, 21st, 22nd,
    23rd), so 19.2% of each occurrence rendered "the 22th" or "the 3th".

    That defect is worth more than its frequency. It is not a domain error
    that only a local would catch -- every reader in the room parses
    "the 22th" as a bug, and it appeared inside free text that the pipeline is
    supposed to be extracting facts from.
    """
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return f"{n}" + {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def _dob_for_age(target_age: int, month: int, day: int) -> date:
    """A date of birth that yields EXACTLY ``target_age`` under ``age_on``.

    ``Person.age_on`` is
    ``TODAY.year - b.year - ((TODAY.month, TODAY.day) < (b.month, b.day))``,
    so the birth year depends on whether the birthday has already fallen this
    year. Solving for it rather than assuming keeps the result exact for a
    December birthday as well as a January one.

    The month and day are carried over from the person's real date of birth so
    the fabricated value does not stand out as a fixed pattern.

    Exactness matters more here than it looks. ``MINOR 12`` says *"Your system
    thinks I'm {younger}"* -- it NAMES the value the record is supposed to
    hold. A dob that is merely wrong, rather than wrong by precisely the
    rendered amount, would leave the body contradicting the row it sits on:
    a quieter version of the defect this change exists to remove, and one that
    would survive any check asking only "is the dob wrong?".
    """
    if day == 29 and month == 2:
        day = 28  # the target year may not be a leap year
    birthday_passed = (TODAY.month, TODAY.day) >= (month, day)
    year = TODAY.year - target_age - (0 if birthday_passed else 1)
    return date(year, month, day)


def _body_template(entry: Any) -> tuple[str, str]:
    """Return ``(subject, body)`` from either bank entry shape.

    The risk banks are migrating from a plain ``(subject, body)`` tuple to a
    ``text_banks.Body`` named tuple carrying the constraints the body places
    on the holder (gender, age). Accepting both shapes means neither this file
    nor ``text_banks.py`` blocks the other, and there is no window in which
    the build is broken.
    """
    return entry[0], entry[1]


def _body_fits(entry: Any, p: Person) -> bool:
    """Is this body compatible with the person it would be rendered against?

    Two kinds of constraint, and they are deliberately sourced differently:

    * **Declared** -- ``gender`` / ``min_age`` / ``max_age`` attributes on a
      ``Body``. These cannot be inferred from the text, so the bank author has
      to state them. 23 of the 46 risk bodies assert a holder gender ("my
      wife", "she lived at"), and nothing used to check it, so roughly 29 of
      100 risk tickets rendered a gender that contradicted the name on the
      same row.

    * **Derived** -- read out of the template string itself. A body quoting
      ``{account}`` used to fall back to a freshly invented number when the
      person had none (``with_account = rng.random() < 0.55``, so ~45% of
      people), which put a loyalty account in the text that was invented on
      the spot and belonged to nobody. A derived constraint is used here in
      preference to a declared one because it cannot go stale: add a body
      quoting an account tomorrow and it is covered automatically.

      Be precise about what this does **not** guarantee. It ensures the
      quoted number is the person's real ``p.account``. It does **not**
      ensure that person also has a row in ``loyalty_members.csv`` -- holding
      an account number and being emitted to the loyalty source are separate
      things, and the record mix decides the second. So some tickets still
      quote an account that resolves to no loyalty row. That residue is
      counted in the manifest as ``tickets_quoting_unlinked_account`` rather
      than asserted away: it is defensible (a customer quoting a card the
      loyalty extract does not carry is a real situation, and an MDM demo is
      the right place for it) but it was not designed, and an uncounted
      "probably fine" is how the other defects in this file started.
    """
    subject, body = _body_template(entry)

    if p.account is None and ("{account}" in subject or "{account}" in body):
        return False

    gender = getattr(entry, "gender", None)
    if gender is not None and gender != p.gender:
        return False

    min_age = getattr(entry, "min_age", None)
    max_age = getattr(entry, "max_age", None)
    if min_age is not None or max_age is not None:
        age = p.age_on()
        if min_age is not None and age < min_age:
            return False
        if max_age is not None and age > max_age:
            return False

    return True


def _choose_body(rng: random.Random, bank: list, p: Person, label: str) -> Any:
    """Pick a body from ``bank`` that is compatible with ``p``.

    Raises rather than falling back to the unfiltered bank. A silent fallback
    is exactly how the gender mismatch would come back: it would restore the
    old behaviour for whichever person the filter happened to exclude, and
    produce no error to notice.
    """
    eligible = [e for e in bank if _body_fits(e, p)]
    if not eligible:
        raise RuntimeError(
            f"no {label} body is compatible with person {p.pid} "
            f"(gender={p.gender}, age={p.age_on()}, account={p.account!r}). "
            f"Widen the bank or relax the constraints -- do not fall back to "
            f"an incompatible body."
        )
    return rng.choice(eligible)


def _risk_bank_state() -> dict[str, Any]:
    """Report how many bodies in each risk bank declare a constraint.

    This exists so the migration state is a fact in the manifest rather than
    an assumption in someone's head. Two failure modes it makes visible:

    * A bank that has not been converted to ``Body`` yet reports zero
      gendered bodies -- which is indistinguishable, from the output alone,
      from a bank whose bodies genuinely make no gender claim.
    * A body added later without declaring its assumptions silently lowers
      these counts, and the drop is the signal.
    """
    out: dict[str, Any] = {}
    for name, bank in (
        ("DECEASED", tb.DECEASED_BODIES),
        ("MINOR", tb.MINOR_BODIES),
        ("VULNERABLE", tb.VULNERABLE_BODIES),
    ):
        out[name] = {
            "bodies": len(bank),
            "gender_constrained": sum(
                1 for e in bank if getattr(e, "gender", None) is not None
            ),
            "age_constrained": sum(
                1
                for e in bank
                if getattr(e, "min_age", None) is not None
                or getattr(e, "max_age", None) is not None
            ),
            "quote_account": sum(
                1 for e in bank if "{account}" in e[0] or "{account}" in e[1]
            ),
        }
    return out


def _ticket_slots(rng: random.Random, p: Person, cfg: Corruption) -> dict[str, Any]:
    a = p.addr
    day = rng.randrange(2, 28)
    # `day2` is a SECOND, LATER day, so a body can narrate two events in
    # sequence. DECEASED 12 ("on the Nth I told your call centre ... on the
    # Nth an email still arrived") previously rendered one slot twice and
    # collapsed the before/after structure the body is built around.
    #
    # Derived, not drawn: an extra RNG call here would shift the stream for
    # every ticket in the corpus, not just the ones using it.
    #
    # `day` is 2..27 and this is `min(28, day + 6)`, so `day2 > day` holds for
    # all 26 inputs and never exceeds the 28th, which is a valid date in every
    # month. An earlier version of this used a wrap-around that could put the
    # second event BEFORE the first for day > 21 -- the same defect the slot
    # was added to fix, reintroduced in the fix itself.
    day2 = min(28, day + 6)
    return {
        "name": f"{p.forename} {p.surname}",
        "first": p.forename,
        "order": f"ORD-{rng.randrange(1000000, 9999999)}",
        "product": rng.choice(tb.PRODUCTS),
        "city": a.city,
        "line1": a.line1,
        "postcode": a.postcode,
        # 7 digits, matching World.make_account. The fallback was left at 5 by
        # the rename. Note that _body_fits now stops an accountless person
        # being given a body that quotes this at all, so the fallback should
        # be unreachable for any body that names it -- it is kept correct
        # rather than removed so that it cannot reintroduce the mismatch if a
        # future caller reaches it another way.
        "account": p.account or f"ACC-{rng.randrange(1000000, 10000000)}",
        "date": f"{rng.randrange(1, 28)} {rng.choice(tb.MONTHS)}",
        "month": rng.choice(tb.MONTHS),
        "amount": f"{rng.uniform(6, 340):.2f}",
        "email": p.email,
        "phone": f"{p.mobile[:5]} {p.mobile[5:]}",
        "last4": f"{rng.randrange(0, 10000):04d}",
        "day": day,
        "day_ord": _ordinal(day),
        "day2_ord": _ordinal(day2),
        "age": rng.randrange(14, 18),
        "younger": rng.randrange(9, 13),
    }


def _render_ticket(rng: random.Random, p: Person, cfg: Corruption) -> tuple[str, str]:
    # Filtered even though this bank declares no gender or age constraints:
    # the derived {account} rule in _body_fits applies here too, and ordinary
    # tickets are where it bites. ~45% of people hold no loyalty card, and a
    # body quoting {account} for one of them asserts a row that is not in
    # loyalty_members.csv.
    entry = _choose_body(rng, tb.TICKET_SUBJECTS_AND_BODIES, p, "ticket")
    subject, body = _body_template(entry)
    slots = _ticket_slots(rng, p, cfg)
    return subject.format(**slots), body.format(**slots)


def _render_risk_ticket(
    rng: random.Random, p: Person, kind: str, cfg: Corruption
) -> tuple[str, str, Any, dict[str, Any]]:
    """Render a risk ticket, returning the chosen body and the slots used.

    The entry and slots come back because the caller has to emit a date of
    birth that agrees with what the text ended up saying. ``MINOR 12`` names
    the age the record supposedly holds, and that value is drawn here.
    """
    bank = {
        "DECEASED": tb.DECEASED_BODIES,
        "MINOR": tb.MINOR_BODIES,
        "VULNERABLE": tb.VULNERABLE_BODIES,
    }[kind]
    entry = _choose_body(rng, bank, p, kind)
    subject, body = _body_template(entry)
    slots = _ticket_slots(rng, p, cfg)
    if kind == "MINOR":
        # The holder IS the minor. {age} must always refer to the person named
        # in contact_name -- several bodies used to be written from a parent's
        # or older sibling's point of view, which bound {age} to a third party
        # and produced a 14-year-old with a son aged 14. Worse than the prose:
        # the truth note asserts the HOLDER disclosed being a minor, so a model
        # that correctly read "my son is 14" as an adult holder was graded wrong.
        slots["age"] = p.age_on()
        slots["younger"] = max(8, p.age_on() - rng.randrange(3, 6))
    return subject.format(**slots), body.format(**slots), entry, slots


def _dob_spoken(d: date) -> str:
    return d.strftime("%d/%m/%Y").lstrip("0")


def _call_slots(rng: random.Random, p: Person, cfg: Corruption) -> dict[str, Any]:
    s = _ticket_slots(rng, p, cfg)
    s["caller"] = f"{p.forename} {p.surname}"
    s["dob_spoken"] = _dob_spoken(p.dob)
    if p.prev_addr:
        s["old_postcode"] = p.prev_addr.postcode
    else:
        # A plausible nearby postcode: same 2-digit area, different suffix.
        s["old_postcode"] = f"{p.addr.area}{rng.randrange(10, 100):02d}"
    s["business"] = p.business_name or ""
    s["neighbour"] = rng.randrange(2, 90)
    s["holder"] = ""
    return s


def _render_call(rng: random.Random, p: Person, cfg: Corruption) -> str:
    return rng.choice(tb.CALL_BODIES).format(**_call_slots(rng, p, cfg))


# ---------------------------------------------------------------------------
# Hard case builders
# ---------------------------------------------------------------------------

# CONFUSABLE_FORENAMES — the SIBLING_TRAP pool.
#
# Pairs of forenames that are similar enough to fool a matcher but belong
# to two different people. The builder calls group_of_forename(fn_a) and
# draws the shared surname from that group, so FN_A MUST EXIST IN ONE OF
# THE GROUP POOLS IN banks_names.py or the surname silently falls back to
# ANGLO.
#
# ORDER EACH PAIR SO THE GROUP-DISTINCTIVE NAME IS FIRST. This is not
# cosmetic. The reverse index resolves a name to its HEAVIEST group, and
# ANGLO is by far the heaviest, so a pair written generic-name-first
# resolves to ANGLO and draws an Anglo surname for a non-Anglo person.
# Four pairs were wrong this way in a previous pass because the generic
# half was common in the Anglo pool too; the fix was to swap the order,
# not to remove the pair. A probe asserts each pair against the section
# comment it sits under, so a pair filed in the wrong section fails the
# build rather than quietly producing a mismatched surname.
#
# The same fallback was a live defect of a second kind: the pool once
# carried Mohammed, Aisha, Imran and Yusuf with no Arabic group to resolve
# them to, and the corpus contained "Muhammad Anderson", "Ayesha Becker"
# and "Yousef Mccoy". They were removed rather than given a group, because
# adding a group properly -- matching surnames, regional weights -- was a
# bigger change than this case justified, and a half-done version would
# have been worse than the omission.
#
# An ARABIC group now exists, so that particular omission is reversible;
# it has deliberately NOT been reversed here, because a pair may only be
# added once its first name is confirmed present in that group's pool, and
# that confirmation belongs with whoever owns banks_names.py. Adding a pair
# on the assumption that the pool contains it reintroduces exactly the
# defect described above. The same applies to the VIETNAMESE, GREEK and
# ITALIAN groups: sections for them are worth adding, but only pool-first.
#
# The pairs below are chosen so that BOTH names sit in the same group's
# pool wherever possible, and they deliberately span the orthographic
# problems an Australian retailer actually has:
#
#   · Anglo near-homographs    Jon / John, Steven / Stephen, Sean / Shaun
#   · -y / -ey / -ie endings   Tracy / Tracey, Lesley / Leslie
#   · doubled consonants       Philip / Phillip, Alan / Allan
#   · silent-letter drift      Catherine / Katherine, Clare / Claire
#   · romanisation hyphenation Min-jun / Minjun, Ji-woo / Jiwoo
#   · vowel-cluster drift      Xiaoli / Xiaoling, Sunita / Sarita
#
# Every one of these is a real pair of distinct people in a real customer
# base, and every one is a DO_NOT_MERGE.

CONFUSABLE_FORENAMES: list[tuple[str, str, str]] = [
    # -- Anglo ----------------------------------------------------------
    # Both halves are Anglo, so pair order carries no group signal here and
    # the reverse index resolves either half to ANGLO correctly.
    ("Jon", "John", "M"), ("Steven", "Stephen", "M"),
    ("Catherine", "Katherine", "F"), ("Sean", "Shaun", "M"),
    ("Brian", "Bryan", "M"), ("Geoffrey", "Jeffrey", "M"),
    ("Alan", "Allan", "M"), ("Ann", "Anne", "F"),
    ("Lesley", "Leslie", "F"), ("Mark", "Marc", "M"),
    ("Neil", "Neal", "M"), ("Philip", "Phillip", "M"),
    ("Rachel", "Rachael", "F"), ("Sara", "Sarah", "F"),
    ("Tracy", "Tracey", "F"), ("Clare", "Claire", "F"),
    ("Marion", "Marian", "F"), ("Gail", "Gayle", "F"),
    ("Kristen", "Kirsten", "F"),
    ("Katherine", "Kathryn", "F"), ("Jayne", "Jane", "F"),
    # Was ("Nicola", "Nichola", "F") -- withdrawn. `Nicola` is a MALE Italian
    # given name and is in the ITALIAN male pool, so the reverse index
    # resolved it to ITALIAN/M against a section comment claiming ANGLO/F.
    # That is Defect 1 exactly: the pair would have drawn an Italian surname
    # for a name the comment calls Anglo, and asserted the wrong gender.
    # Replaced with a pair whose first element resolves unambiguously.
    ("Diane", "Dianne", "F"), ("Ashley", "Ashleigh", "F"),
    ("Francis", "Frances", "M"), ("Alexander", "Alexandra", "M"),
    ("Danielle", "Daniella", "F"), ("Stuart", "Stewart", "M"),
    ("Lyndsey", "Lindsay", "F"), ("Zoe", "Zoey", "F"),
    ("Connor", "Conor", "M"), ("Aaron", "Arron", "M"),
    ("Isabel", "Isobel", "F"), ("Elliot", "Elliott", "M"),
    ("Karen", "Karyn", "F"), ("Terri", "Terry", "F"),
    # -- Chinese --------------------------------------------------------
    ("Hua", "Hui", "M"), ("Jian", "Jie", "M"),
    ("Xiaoli", "Xiaoling", "F"), ("Xiaomin", "Xiaomei", "F"),
    # -- Korean ---------------------------------------------------------
    ("Min-jun", "Minjun", "M"), ("Ji-ho", "Ji-hu", "M"),
    ("Seo-yeon", "Seo-yun", "F"), ("Ji-woo", "Jiwoo", "F"),
    ("Eun-ji", "Eun-ju", "F"),
    # -- Indian ---------------------------------------------------------
    ("Dinesh", "Ramesh", "M"), ("Mahesh", "Suresh", "M"),
    ("Pradeep", "Pramod", "M"), ("Sunita", "Sarita", "F"),
    ("Neha", "Nisha", "F"), ("Priya", "Preeya", "F"),
    # -- Filipino -------------------------------------------------------
    # "Rosa" is common in the Anglo pool too, so "Rosario" leads. Same for
    # "Renato" ahead of the more generic "Ricardo".
    ("Ricardo", "Renato", "M"), ("Estela", "Estrella", "F"),
    ("Rosario", "Rosa", "F"),
]


class CaseBuilder:
    def __init__(self, world: World, em: Emitter, instances: int) -> None:
        self.w = world
        self.em = em
        self.n = instances
        self.cfg = world.cfg
        self.seed = world.seed
        self.instance_counts: dict[str, int] = {c: 0 for c in CASE_CODES}
        self.injection_record_ids: list[str] = []

    def _rng(self, case: str, i: int, tag: str = "") -> random.Random:
        return make_rng(self.seed, "case", case, i, tag)

    # -- 1 ---------------------------------------------------------------
    def household(self) -> None:
        case = "HOUSEHOLD"
        for i in range(self.n):
            rng = self._rng(case, i)
            hid = self.w.next_household_id()
            addr = self.w.make_address(rng)
            group = self.w.pick_group(rng)
            surname = self.w.surname_for(rng, group, allow_cross=False)
            landline = self.w.make_landline(rng, addr.std)
            # Two adults and two adult children, spanning generations. Forename
            # initials are forced distinct so the POS records (surname + initial
            # + outward only) remain in principle separable — a trap that cannot
            # be solved is not a fair test.
            used_initials: set[str] = set()
            members: list[Person] = []
            plan = [("M", (46, 68)), ("F", (44, 66)), (None, (19, 28)), (None, (18, 26))]
            for j, (gender, ages) in enumerate(plan):
                fn = self._distinct_forename(rng, gender, used_initials, group)
                used_initials.add(fn[0].upper())
                sn = (
                    surname
                    if (j < 2 and rng.random() < 0.85) or j >= 2
                    else self.w.surname_for(rng, group)
                )
                p = self.w.make_person(
                    rng,
                    case_type=case,
                    gender=gender or ("F" if rng.random() < 0.5 else "M"),
                    forename=fn,
                    surname=sn,
                    addr=addr,
                    household_id=hid,
                    age_range=ages,
                    with_account=rng.random() < 0.5,
                )
                p.landline = landline
                members.append(p)
            roster = ", ".join(f"{m.pid}={m.forename} ({m.dob.year})" for m in members)
            for m in members:
                m.notes = (
                    f"HOUSEHOLD {hid}: four distinct people at {addr.line1}, "
                    f"{addr.postcode}. Roster: {roster}. Shared address and mostly shared "
                    "surname; different forenames and different DOBs. Must NOT merge."
                )
                for src in self._household_sources(rng):
                    self._emit(rng, m, src, case)
            self.instance_counts[case] += 1

    def _distinct_forename(self, rng, gender, used_initials, group="ANGLO") -> str:
        for _ in range(80):
            g = gender or ("F" if rng.random() < 0.5 else "M")
            fn = self.w.forename_for(rng, g, group)
            if fn[0].upper() not in used_initials:
                return fn
        return fn

    def _household_sources(self, rng) -> list[str]:
        k = wchoice(rng, [(1, 30), (2, 50), (3, 20)])
        pool = [("CRM", 30), ("ECOM", 22), ("LOY", 22), ("POS", 26)]
        out: list[str] = []
        for _ in range(k):
            s = wchoice(rng, pool)
            while s != "POS" and s in out:
                s = wchoice(rng, pool)
            out.append(s)
        return out

    # -- 2 ---------------------------------------------------------------
    def sibling_trap(self) -> None:
        case = "SIBLING_TRAP"
        for i in range(self.n):
            rng = self._rng(case, i)
            hid = self.w.next_household_id()
            addr = self.w.make_address(rng)
            fn_a, fn_b, gender = CONFUSABLE_FORENAMES[i % len(CONFUSABLE_FORENAMES)]
            if i >= len(CONFUSABLE_FORENAMES):
                fn_a, fn_b = fn_b, fn_a
            base_age = rng.randrange(21, 46)
            gap = rng.randrange(2, 8)
            yr_a = TODAY.year - base_age
            yr_b = TODAY.year - base_age - gap

            # Both siblings pin forename, surname AND address, so by the time
            # make_person sees them it has no free variable left and its
            # namesake guard cannot act -- it just breaks and accepts. The
            # shared surname is the last free choice, so the check belongs
            # here. Without it a sibling can land on a name a HOUSEHOLD member
            # in the same city already holds, producing two DO_NOT_MERGE people
            # with the same name, same city and near-identical ages: a question
            # the data cannot answer, which the scorecard would still mark.
            group = self.w.group_of_forename(fn_a)
            surname = self.w.surname_for(rng, group, allow_cross=False)
            for _ in range(40):
                if (
                    self.w._separable(fn_a, surname, addr.city, yr_a)
                    and self.w._separable(fn_b, surname, addr.city, yr_b)
                    and not _forbidden_pair(fn_a, surname)
                    and not _forbidden_pair(fn_b, surname)
                ):
                    break
                surname = self.w.surname_for(rng, group, allow_cross=False)

            a = self.w.make_person(
                rng, case_type=case, gender=gender, forename=fn_a, surname=surname,
                addr=addr, household_id=hid,
                dob=date(yr_a, rng.randrange(1, 13), rng.randrange(1, 29)),
                with_account=rng.random() < 0.5,
            )
            b = self.w.make_person(
                rng, case_type=case, gender=gender, forename=fn_b, surname=surname,
                addr=addr, household_id=hid,
                dob=date(yr_b, rng.randrange(1, 13), rng.randrange(1, 29)),
                with_account=rng.random() < 0.5,
            )

            note = (
                f"SIBLING_TRAP {hid}: {a.pid}={fn_a} (b.{a.dob.year}) and {b.pid}={fn_b} "
                f"(b.{b.dob.year}) are siblings at {addr.line1}, {addr.postcode}. Same "
                "surname, same address, near-identical forenames, similar email patterns. "
                "The ONLY clean discriminator is the DOB, which both carry on at least one "
                "record. Must NOT merge."
            )
            a.notes = b.notes = note
            for person in (a, b):
                # CRM always carries the DOB so the case stays solvable.
                self.em.crm(rng, person, case_type=case, dob=person.dob, force_dob=True)
                second = wchoice(rng, [("ECOM", 40), ("LOY", 35), ("POS", 25)])
                self._emit(rng, person, second, case)
            # Two of the three prompt injections ride on this case: a hard
            # negative, so obeying the injected instruction is provably wrong.
            if i < 2:
                self._inject(rng, b, case, i, note)
            self.instance_counts[case] += 1

    # -- 3 ---------------------------------------------------------------
    def married_name(self) -> None:
        case = "MARRIED_NAME"
        for i in range(self.n):
            rng = self._rng(case, i)
            group = self.w.pick_group(rng)
            maiden = self.w.surname_for(rng, group, allow_cross=False)
            married = self.w.surname_for(rng, group)
            while married == maiden:
                married = self.w.surname_for(rng, group)
            old_addr = self.w.make_address(rng)
            new_addr = self.w.make_address(rng)
            p = self.w.make_person(
                rng, case_type=case, gender="F" if rng.random() < 0.86 else "M",
                surname=married, addr=new_addr, age_range=(26, 52), with_account=True,
            )
            # The pre-marriage CRM record is emitted under the MAIDEN surname,
            # which make_person never saw -- it vetted (forename, married).
            # That leaves a second pinned half nothing has checked, which is
            # the shape of every name defect this generator has had: a builder
            # pins a half, make_person has nothing to redraw, and the Emitter
            # cannot revert an explicit override. Re-vet the maiden pair here.
            #
            # Found by the output-side sweep on the first Australian build:
            # "Giang Giang" (MARRIED_NAME), because Giang is genuinely both a
            # Vietnamese given name and a surname and the pools rightly carry
            # it in both. The overlap is correct; the missing vet was not.
            #
            # Stepping is deterministic -- rng is seeded per (case, i) -- so
            # the corpus stays byte-reproducible.
            _tries = 0
            while _forbidden_pair(p.forename, maiden) or maiden == married:
                maiden = self.w.surname_for(rng, group, allow_cross=False)
                _tries += 1
                if _tries > 200:
                    raise SystemExit(
                        f"MARRIED_NAME: no legal maiden surname for forename "
                        f"'{p.forename}' in group {group} after 200 draws. "
                        f"The group's surname pool is probably too small or "
                        f"too heavily overlapped with its forename pool."
                    )
            p.maiden_surname = maiden
            p.prev_addr = old_addr
            maiden_email = self.w.make_email(rng, p.forename, maiden)
            p.prev_email = maiden_email
            p.notes = (
                f"MARRIED_NAME: {p.pid} appears as '{p.forename} {maiden}' at "
                f"{old_addr.postcode} before the marriage and as '{p.forename} {married}' at "
                f"{new_addr.postcode} after it. Surname, address and email all change; the "
                f"DOB ({p.dob.isoformat()}) and the mobile ({p.mobile}) do not. MUST merge."
            )
            marriage = rand_ts(rng, datetime(2021, 1, 1), datetime(2024, 6, 1))
            # Pre-marriage record
            self.em.crm(
                rng, p, case_type=case, surname=maiden, addr=old_addr,
                email=maiden_email, dob=p.dob, force_dob=True,
                phone=drift_phone(rng, p.mobile, self.cfg),
                ts=rand_ts(rng, TS_START, marriage),
            )
            # Post-marriage records
            self.em.loyalty(
                rng, p, case_type=case, addr=new_addr, dob=p.dob,
                ts=rand_ts(rng, marriage, TS_END),
            )
            self.em.ecom(
                rng, p, case_type=case, last_name=married, postcode=new_addr.postcode,
                dob=None, phone="", ts=rand_ts(rng, marriage, TS_END),
            )
            self.instance_counts[case] += 1

    # -- 4 ---------------------------------------------------------------
    def account_only(self) -> None:
        case = "ACCOUNT_ONLY"
        for i in range(self.n):
            rng = self._rng(case, i)
            p = self.w.make_person(rng, case_type=case, with_account=True, age_range=(24, 64))
            group = self.w.group_of_surname(p.surname)
            alt_surname = self.w.surname_for(rng, group)
            while alt_surname == p.surname:
                alt_surname = self.w.surname_for(rng, group)
            # A second address in a different city so even the outward code differs.
            work_addr = self.w.make_address(rng)
            while work_addr.outward == p.addr.outward:
                work_addr = self.w.make_address(rng)
            alt_mobile = self.w.make_mobile(rng)
            middle_initial = rng.choice("ABDEHJLMNPRSTW")
            while middle_initial == p.forename[0].upper():
                middle_initial = rng.choice("ABDEHJLMNPRSTW")
            p.notes = (
                f"ACCOUNT_ONLY: {p.pid} has exactly two records. The loyalty record is "
                f"'{p.forename} {p.surname}' at {p.addr.postcode} on mobile {alt_mobile}; the "
                f"POS record is '{middle_initial} {alt_surname}' at {work_addr.outward}. "
                f"Name, address, postcode, phone and DOB all differ or are absent. The ONLY "
                f"shared signal is loyalty account {p.account}. MUST merge — this is the "
                "lexical/BM25 leg's case."
            )
            self.em.loyalty(
                rng, p, case_type=case,
                member_name=f"{p.forename} {p.surname}",
                addr=p.addr, mobile=drift_phone(rng, alt_mobile, self.cfg), dob=None,
            )
            self.em.pos(
                rng, p, case_type=case, surname=alt_surname, initial=middle_initial,
                outward=work_addr.outward, account=p.account,
            )
            self.instance_counts[case] += 1

    # -- 5 ---------------------------------------------------------------
    def postcode_near_miss(self) -> None:
        case = "POSTCODE_NEAR_MISS"
        common = ["Patel", "Smith", "Khan", "Jones", "Singh", "Begum", "Taylor",
                  "Ahmed", "Williams", "Nowak"]
        for i in range(self.n):
            rng = self._rng(case, i)
            same_surname = rng.random() < 0.40
            addr_a = self.w.make_address(rng)
            addr_b = self.w.sibling_address(rng, addr_a)
            group_a = self.w.pick_group(rng)
            group_b = self.w.pick_group(rng)
            sn_a = rng.choice(common) if same_surname else self.w.surname_for(rng, group_a)
            sn_b = sn_a if same_surname else self.w.surname_for(rng, group_b)
            while sn_b == sn_a and not same_surname:
                sn_b = self.w.surname_for(rng, group_b)
            a = self.w.make_person(rng, case_type=case, surname=sn_a, addr=addr_a,
                                   age_range=(24, 70))
            b = self.w.make_person(rng, case_type=case, surname=sn_b, addr=addr_b,
                                   age_range=(24, 70))
            # This overwrites a forename that make_person already vetted, so
            # the replacement has to be re-checked against the surname here.
            while (
                b.forename[0].upper() == a.forename[0].upper()
                or _forbidden_pair(b.forename, sn_b)
            ):
                b.forename = self.w.forename_for(
                    rng, b.gender, self.w.group_of_surname(sn_b)
                )

            note = (
                f"POSTCODE_NEAR_MISS: {a.pid} at {addr_a.line1} and {b.pid} at "
                f"{addr_b.line1} share postcode {addr_a.postcode} but are unrelated people "
                f"({'same' if same_surname else 'different'} surname, DOBs {a.dob.year} vs "
                f"{b.dob.year}, different emails and mobiles). Postcode overlap is not "
                "identity. Must NOT merge."
            )
            a.notes = b.notes = note
            for person in (a, b):
                self.em.crm(rng, person, case_type=case, dob=person.dob, force_dob=True)
                self._emit(rng, person, wchoice(rng, [("POS", 45), ("ECOM", 30), ("LOY", 25)]), case)
            # The third and final prompt injection.
            if i == 0:
                self._inject(rng, b, case, 2, note)
            self.instance_counts[case] += 1

    # -- 6 ---------------------------------------------------------------
    def transliteration(self) -> None:
        case = "TRANSLITERATION"
        used_surnames: set[str] = set()
        for i in range(self.n):
            rng = self._rng(case, i)
            fam_f = banks.TRANSLITERATION_FORENAMES[i % len(banks.TRANSLITERATION_FORENAMES)]
            fam_s = banks.TRANSLITERATION_SURNAMES[i % len(banks.TRANSLITERATION_SURNAMES)]
            # Not every family has three distinct spellings; cycle so index 1
            # and 2 are always safe, rather than assuming a minimum length.
            spellings_s = list(fam_s)
            if spellings_s[0] in used_surnames:
                spellings_s = [f"{s}-{wchoice(rng, banks.SURNAMES)}" for s in fam_s]
            used_surnames.add(spellings_s[0])
            spellings_f = list(fam_f)
            while len(spellings_s) < 3:
                spellings_s.append(spellings_s[len(spellings_s) % len(fam_s)])
            while len(spellings_f) < 3:
                spellings_f.append(spellings_f[len(spellings_f) % len(fam_f)])
            gender = "F" if spellings_f[0] in {
                "Aisha", "Zainab", "Khadija", "Fatima", "Nadia", "Rania",
                "Siobhan", "Aleksandra", "Malia", "Lupe", "Ana", "Mele",
                "Thi Mai", "Priya", "Xiaoli", "Ji-woo", "Seo-yeon",
            } else "M"
            p = self.w.make_person(
                rng, case_type=case, gender=gender, forename=spellings_f[0],
                surname=spellings_s[0], age_range=(22, 66), with_account=True,
            )
            name_only = (i % 3 == 0)
            p.notes = (
                f"TRANSLITERATION: {p.pid} is written "
                + " / ".join(f"'{f} {s}'" for f, s in zip(spellings_f[:3], spellings_s[:3]))
                + " across three sources. "
                + (
                    "On this instance the ecom record shares NO postcode, NO DOB and a "
                    "different email, so the transliterated name is the only link — the "
                    "semantic leg has to carry it alone. "
                    if name_only else
                    "Address, mobile and DOB are consistent; only the name string moves. "
                )
                + "MUST merge."
            )
            self.em.crm(
                rng, p, case_type=case,
                full_name=f"{spellings_f[0]} {spellings_s[0]}", dob=p.dob,
            )
            self.em.loyalty(
                rng, p, case_type=case,
                member_name=f"{spellings_f[1]} {spellings_s[1]}",
                dob=p.dob if rng.random() > 0.35 else None,
            )
            if name_only:
                self.em.ecom(
                    rng, p, case_type=case,
                    first_name=spellings_f[2], last_name=spellings_s[2],
                    email=self.w.make_email(rng, spellings_f[2], spellings_s[2]),
                    postcode="", dob=None, phone="",
                )
            else:
                self.em.ecom(
                    rng, p, case_type=case,
                    first_name=spellings_f[2], last_name=spellings_s[2],
                    postcode=p.addr.postcode, dob=p.dob,
                )
            self.instance_counts[case] += 1

    # -- 7 ---------------------------------------------------------------
    def sole_trader(self) -> None:
        case = "SOLE_TRADER"
        for i in range(self.n):
            rng = self._rng(case, i)
            p = self.w.make_person(rng, case_type=case, age_range=(28, 62), with_account=True)
            _, forms = rng.choice(banks.BUSINESS_TRADES)
            form = rng.choice(forms)
            suffix = rng.choice(banks.BUSINESS_SUFFIXES)
            style = wchoice(rng, [("initial", 40), ("full", 35), ("surname", 25)])
            if style == "initial":
                stem = f"{p.forename[0].upper()} {p.surname}"
            elif style == "full":
                stem = f"{p.forename} {p.surname}"
            else:
                stem = p.surname
            business = " ".join(x for x in [stem, form, suffix] if x).strip()
            p.business_name = business
            domain_stem = _slug(stem) + _slug(form.split(" ")[0])
            biz_email = f"info@{domain_stem[:28]}.co.uk"
            bump = 0
            while not self.w.owns_email(biz_email, p.pid):
                bump += 1
                biz_email = f"info@{domain_stem[:26]}{bump}.co.uk"
            p.business_email = self.w.claim_email(biz_email, p.pid)
            p.notes = (
                f"SOLE_TRADER: {p.pid} trades as '{business}' from the home address "
                f"{p.addr.line1}, {p.addr.postcode}, on the same mobile. The business record "
                "should be LINKED to the person and typed as a business association, not "
                "folded into the personal golden record. Expect risk_flag / entity_type = "
                "BUSINESS."
            )
            self.em.crm(rng, p, case_type=case, dob=p.dob)
            self.em.loyalty(
                rng, p, case_type=case, member_name=business, addr=p.addr, dob=None,
            )
            if i % 2 == 0:
                body = rng.choice(tb.SOLE_TRADER_CALL_BODIES).format(**_call_slots(rng, p, self.cfg))
                self.em.call(rng, p, case_type=case, body=body)
            else:
                self.em.support(
                    rng, p, case_type=case, contact_name=business,
                    contact_email=p.business_email,
                    subject="VAT receipts for trade purchases",
                    body=(
                        f"Hello,\n\nI'm a sole trader — I trade as {business} but the account "
                        f"is in my own name, {p.forename} {p.surname}. Both are at "
                        f"{p.addr.line1}, {p.addr.city}, {p.addr.postcode}.\n\n"
                        f"I need VAT invoices for everything on loyalty card {p.account} for "
                        "the last quarter, made out to the business rather than to me "
                        "personally. My accountant has been fairly clear about this.\n\n"
                        f"Best regards,\n{p.forename} {p.surname}\n{business}"
                    ),
                )
            self.instance_counts[case] += 1

    # -- 8 ---------------------------------------------------------------
    def shared_email(self) -> None:
        case = "SHARED_EMAIL"
        for i in range(self.n):
            rng = self._rng(case, i)
            hid = self.w.next_household_id()
            addr = self.w.make_address(rng)
            landline = self.w.make_landline(rng, addr.std)
            same_surname = rng.random() < 0.60
            group = self.w.pick_group(rng)
            sn_a = self.w.surname_for(rng, group, allow_cross=False)
            sn_b = sn_a if same_surname else self.w.surname_for(rng, group)
            # Both halves are pinned when these reach make_person, so its
            # forbidden-pair guard has nothing it can redraw. Do it here,
            # where the surname is already fixed. This produced "Hekau Hekau":
            # Hekau is genuine as both a forename and a surname.
            fn_a = self.w.forename_for(rng, "M", group)
            for _ in range(24):
                if not _forbidden_pair(fn_a, sn_a):
                    break
                fn_a = self.w.forename_for(rng, "M", group)
            fn_b = self.w.forename_for(rng, "F", group)
            for _ in range(24):
                # fn_b must also differ from fn_a. Unisex names (Lin, Ari, Kim)
                # appear in both the male and female pools, so the couple could
                # draw the same one and end up as two people with an identical
                # name at one address, two years apart -- which contradicts
                # this case's own note ("Different forenames, different DOBs")
                # and asks the pipeline a question with no answer in the data.
                if not _forbidden_pair(fn_b, sn_b) and _fold_name(fn_b) != _fold_name(fn_a):
                    break
                fn_b = self.w.forename_for(rng, "F", group)


            style = wchoice(rng, [("the_x", 34), ("a_and_b", 33), ("household", 33)])
            domain = wchoice(rng, banks.EMAIL_DOMAINS)
            if style == "the_x":
                local = f"the{_slug(sn_a)}s"
            elif style == "a_and_b":
                local = f"{_slug(fn_a)}and{_slug(fn_b)}"
            else:
                local = f"{_slug(sn_a)}.household{rng.randrange(1, 99)}"
            shared = f"{local}@{domain}"
            if shared in self.w.emails:
                shared = f"{local}{rng.randrange(100, 999)}@{domain}"
            self.w.claim_email(shared)
            a = self.w.make_person(
                rng, case_type=case, gender="M", forename=fn_a, surname=sn_a,
                addr=addr, household_id=hid, email=shared, age_range=(30, 72),
            )
            b = self.w.make_person(
                rng, case_type=case, gender="F", forename=fn_b, surname=sn_b,
                addr=addr, household_id=hid, email=shared, age_range=(28, 70),
            )
            a.landline = b.landline = landline
            note = (
                f"SHARED_EMAIL {hid}: {a.pid}={fn_a} {sn_a} (b.{a.dob.year}) and "
                f"{b.pid}={fn_b} {sn_b} (b.{b.dob.year}) are a couple sharing the single "
                f"mailbox {shared}, the address {addr.line1}, {addr.postcode} and the "
                f"landline {landline}. Different forenames, different DOBs, different "
                "mobiles. Email equality is not identity. Must NOT merge."
            )
            a.notes = b.notes = note
            for person in (a, b):
                self.em.crm(rng, person, case_type=case, email=shared, dob=person.dob, force_dob=True)
                self.em.ecom(rng, person, case_type=case, email=shared,
                             postcode=addr.postcode, dob=None)
            self.instance_counts[case] += 1

    # -- 9 ---------------------------------------------------------------
    def consent_conflict(self) -> None:
        case = "CONSENT_CONFLICT"
        for i in range(self.n):
            rng = self._rng(case, i)
            p = self.w.make_person(rng, case_type=case, age_range=(22, 70), with_account=True)
            channel = wchoice(rng, [("EMAIL", 60), ("SMS", 25), ("POST", 15)])
            p.notes = (
                f"CONSENT_CONFLICT: {p.pid} exists in CRM, ecom and loyalty. For channel "
                f"{channel} the three source records carry GRANTED, NOT_GIVEN and WITHDRAWN "
                "respectively. The person MUST merge; the profile-level permission must be "
                "the intersection, with the WITHDRAWN record winning, so this person must "
                "NOT appear in a contactable audience."
            )
            t0 = rand_ts(rng, datetime(2019, 6, 1), datetime(2021, 6, 1))
            t1 = rand_ts(rng, datetime(2021, 7, 1), datetime(2023, 6, 1))
            t2 = rand_ts(rng, datetime(2023, 7, 1), TS_END)
            crm_id = self.em.crm(rng, p, case_type=case, dob=p.dob, ts=t0)
            ecom_id = self.em.ecom(rng, p, case_type=case, postcode=p.addr.postcode,
                                   dob=p.dob, ts=t1)
            loy_id = self.em.loyalty(rng, p, case_type=case, dob=p.dob, ts=t2)
            self.em.add_consent(rng, crm_id, channel, "GRANTED", "MARKETING", t0)
            self.em.add_consent(rng, ecom_id, channel, "NOT_GIVEN", "MARKETING", t1)
            self.em.add_consent(rng, loy_id, channel, "WITHDRAWN", "MARKETING", t2)
            # Service consent is uncontested, so the suppression is provably
            # channel- and purpose-specific rather than a blanket block.
            self.em.add_consent(rng, crm_id, channel, "GRANTED", "SERVICE", t0)
            self.instance_counts[case] += 1

    # -- 10 --------------------------------------------------------------
    def unstructured_only(self) -> None:
        case = "UNSTRUCTURED_ONLY"
        for i in range(self.n):
            rng = self._rng(case, i)
            hid = self.w.next_household_id()
            addr = self.w.make_address(rng)
            group = self.w.pick_group(rng)
            surname = self.w.surname_for(rng, group, allow_cross=False)
            holder_female = (i % 4) != 2
            holder = self.w.make_person(
                rng, case_type=case, gender="F" if holder_female else "M",
                surname=surname, addr=addr, household_id=hid, age_range=(28, 66),
                with_account=True,
            )
            caller_surname = (
                surname if rng.random() < 0.70 else self.w.surname_for(rng, group)
            )
            caller = self.w.make_person(
                rng, case_type=case, gender="M" if holder_female else "F",
                surname=caller_surname, addr=addr, household_id=hid, age_range=(28, 68),
                with_account=False,
            )
            note = (
                f"UNSTRUCTURED_ONLY: the call transcript belongs to the CALLER {caller.pid} "
                f"({caller.forename} {caller.surname}), who states on the call that they are "
                f"ringing about their spouse's/partner's account. The transcript is saturated "
                f"with the ACCOUNT HOLDER {holder.pid}'s identifiers — name "
                f"'{holder.forename} {holder.surname}', postcode {addr.postcode}, loyalty "
                f"account {holder.account}. The caller and the holder share an address and "
                f"often a surname. The call must NOT be merged with {holder.pid}."
            )
            holder.notes = (
                f"UNSTRUCTURED_ONLY: {holder.pid} is the ACCOUNT HOLDER named inside a call "
                f"transcript placed by {caller.pid}. The transcript record must not resolve "
                "to this person."
            )
            caller.notes = note
            # Holder's own records
            self.em.crm(rng, holder, case_type=case, dob=holder.dob)
            self.em.loyalty(rng, holder, case_type=case, dob=holder.dob)
            # Caller's own record, so a correct merge is available for the caller too
            self._emit(rng, caller, wchoice(rng, [("CRM", 55), ("ECOM", 45)]), case)
            slots = _call_slots(rng, caller, self.cfg)
            slots["holder"] = f"{holder.forename} {holder.surname}"
            slots["postcode"] = addr.postcode
            slots["line1"] = addr.line1
            slots["city"] = addr.city
            slots["account"] = holder.account or ""
            template_pool = (
                tb.PROXY_CALL_BODIES_FEMALE_HOLDER if holder_female
                else tb.PROXY_CALL_BODIES_MALE_HOLDER
            )
            body = rng.choice(template_pool).format(**slots)
            self.em.call(rng, caller, case_type=case, body=body, notes=note)
            self.instance_counts[case] += 1

    # -- 11 --------------------------------------------------------------
    #
    # VULNERABLE age range. The original range was (74, 92), which had two
    # problems. The visible one: bodies describing age-agnostic vulnerabilities
    # -- job loss, wheelchair use, Deafness, ESL, mental health, a protection
    # order, post-surgical recovery -- rendered against 74-to-92-year-olds, so
    # the corpus emitted a 91-year-old who had "lost my job" and an 86-year-old
    # worried about "my flatmates".
    #
    # The less visible and more serious one: with that range the dataset
    # asserts that *vulnerable means elderly*. In a demo whose subject is how
    # an organisation treats its customers' data, that is a claim we do not
    # want the data making on our behalf, and it is the kind of thing an
    # audience notices.
    #
    # So the range widens to the full adult span and the bodies that genuinely
    # need an older holder (advanced dementia, rest-home resident, "she's
    # elderly") carry an explicit `min_age`, which `_body_fits` enforces.
    #
    # The widening is CONDITIONAL on those tags existing. Widening before the
    # bank declares them would let a 30-year-old draw the advanced-dementia
    # body -- trading a mild implausibility for a worse one, silently. The
    # state actually used is recorded in the manifest rather than merely
    # warned about, so it is observable instead of assumed.
    VULNERABLE_AGES_WIDE = (28, 92)
    VULNERABLE_AGES_NARROW = (74, 92)

    @staticmethod
    def _vulnerable_bank_is_tagged() -> bool:
        return any(
            getattr(e, "min_age", None) is not None for e in tb.VULNERABLE_BODIES
        )

    def risk_flag(self) -> None:
        case = "RISK_FLAG"
        kinds = (["DECEASED"] * 9 + ["MINOR"] * 8 + ["VULNERABLE"] * 5)
        tagged = self._vulnerable_bank_is_tagged()
        vulnerable_ages = (
            self.VULNERABLE_AGES_WIDE if tagged else self.VULNERABLE_AGES_NARROW
        )
        self.vulnerable_age_range = vulnerable_ages
        self.vulnerable_bank_tagged = tagged
        for i in range(self.n):
            rng = self._rng(case, i)
            kind = kinds[i % len(kinds)]
            if kind == "MINOR":
                age_range = (14, 17)
            elif kind == "VULNERABLE":
                age_range = vulnerable_ages
            else:
                age_range = (58, 90)
            p = self.w.make_person(rng, case_type=case, age_range=age_range, with_account=True)

            # Body selection happens BEFORE emission, because a body may
            # dictate what the emitted date of birth has to be. Two MINOR
            # bodies complain that the record holds the wrong age; rather than
            # reword them, the record is made wrong so the text is true.
            subject, body, entry, slots = _render_risk_ticket(rng, p, kind, self.cfg)

            # The direction matters, and a boolean would have been wrong. The
            # two bodies are mistaken in OPPOSITE directions:
            #
            #   MINOR 08  "I put my birth year in wrong because it wouldn't let
            #             me register otherwise"  -> the record must show an ADULT
            #   MINOR 12  "Your system thinks I'm {younger}"
            #                                     -> the record must show {younger}
            #
            # Emitting an adult dob for MINOR 12 would leave the body saying
            # "your system thinks I'm 11" beside a record implying 34 -- the
            # same cross-field defect, reintroduced by its own fix.
            misstated = getattr(entry, "dob_misstated", None)
            emit_dob = p.dob
            dob_note = ""
            if misstated == "adult":
                # Just over the gate they were trying to clear, not wildly old.
                fake_age = rng.randrange(18, 26)
                emit_dob = _dob_for_age(fake_age, p.dob.month, p.dob.day)
                dob_note = (
                    f" NOTE: the dob on the CRM and loyalty records is WRONG -- it "
                    f"implies age {fake_age}, because the customer overstated their "
                    f"age at signup to pass an 18+ gate. The free text is "
                    f"authoritative. A dob-only rule will NOT flag this person."
                )
            elif misstated == "younger":
                # Must imply EXACTLY the age the body names, not merely a wrong one.
                fake_age = slots["younger"]
                emit_dob = _dob_for_age(fake_age, p.dob.month, p.dob.day)
                dob_note = (
                    f" NOTE: the dob on the CRM and loyalty records is WRONG -- it "
                    f"implies age {fake_age}, which is the value the ticket says the "
                    f"system holds. The free text is authoritative."
                )

            p.notes = (
                f"RISK_FLAG ({kind}): the support ticket's structured identifiers "
                f"(contact_name, contact_email) are {p.pid}'s, so it MUST merge with "
                f"{p.pid}. The free text discloses a {kind} condition"
                + (f" (stated age {p.age_on()})" if kind == "MINOR" else "")
                + ". Expect merge plus risk_flag=" + kind + "."
                + dob_note
            )
            # The SAME wrong value goes to both sources deliberately: a
            # divergent dob would create an intra-person dob_conflict and push
            # the pair down the REJECT/GREY_ZONE rails, changing the merge
            # outcome this case is supposed to be testing.
            self.em.crm(rng, p, case_type=case, dob=emit_dob)
            self.em.loyalty(rng, p, case_type=case, dob=emit_dob)
            self.em.support(
                rng, p, case_type=case, subject=subject, body=body,
                contact_name=f"{p.forename} {p.surname}", contact_email=p.email,
            )
            self.instance_counts[case] += 1

    # -- 12 --------------------------------------------------------------
    def overmerge_bait(self) -> None:
        case = "OVERMERGE_BAIT"
        for i in range(self.n):
            rng = self._rng(case, i)
            group = self.w.pick_group(rng)
            surname = self.w.surname_for(rng, group, allow_cross=False)
            # Same first initial, different forename, radically different DOBs.
            # The initial has to be one the group actually supplies two distinct
            # forenames for, or the bait degenerates into one name.
            initial = self._shared_initial(rng, group)
            fn_a = self._forename_with_initial(rng, initial, "M", group=group)
            fn_c = self._forename_with_initial(rng, initial, "M", exclude=fn_a, group=group)
            addr_a = self.w.make_address(rng)
            # Put C in the same city as A, so the chain is geographically
            # plausible and the DOB is doing all the discriminating work.
            city_row = None
            for row in banks.CITIES:
                if row[0] == addr_a.city:
                    city_row = row
                    break
            addr_c = self.w.make_address(rng, city_row=city_row)
            older = rng.randrange(56, 74)
            younger = rng.randrange(20, 32)
            a = self.w.make_person(
                rng, case_type=case, gender="M", forename=fn_a, surname=surname,
                addr=addr_a,
                dob=date(TODAY.year - older, rng.randrange(1, 13), rng.randrange(1, 29)),
                with_account=True,
            )
            c = self.w.make_person(
                rng, case_type=case, gender="M", forename=fn_c, surname=surname,
                addr=addr_c,
                dob=date(TODAY.year - younger, rng.randrange(1, 13), rng.randrange(1, 29)),
                with_account=True,
            )
            # Which of the two the bridging record genuinely belongs to alternates,
            # so a pipeline cannot learn "the bridge is always the older one".
            owner, other = (a, c) if i % 2 == 0 else (c, a)
            note = (
                f"OVERMERGE_BAIT: chain {a.pid} <-> BRIDGE <-> {c.pid}. {a.pid}="
                f"{fn_a} {surname} b.{a.dob.year}; {c.pid}={fn_c} {surname} b.{c.dob.year}. "
                f"The bridging loyalty record reads '{initial} {surname}' at "
                f"{owner.addr.postcode} (matching {owner.pid} on initial + postcode) but "
                f"carries {other.pid}'s mobile {other.mobile}, which the network recycled. "
                f"It truly belongs to {owner.pid}. {a.pid} and {c.pid} have incompatible "
                f"DOBs ({a.dob.year} vs {c.dob.year}) and different forenames, so the chain "
                "MUST be broken rather than closed transitively."
            )
            a.notes = c.notes = note
            self.em.crm(rng, a, case_type=case, dob=a.dob, force_dob=True)
            self.em.crm(rng, c, case_type=case, dob=c.dob, force_dob=True)
            self.em.loyalty(
                rng, owner, case_type=case, notes=note,
                member_name=f"{initial} {surname}",
                addr=owner.addr, mobile=drift_phone(rng, other.mobile, self.cfg), dob=None,
            )
            self.em.pos(rng, other, case_type=case, surname=surname, initial=initial,
                        outward=other.addr.outward)
            self.instance_counts[case] += 1

    def _shared_initial(self, rng, group: str) -> str:
        """An initial for which this group supplies at least two male forenames."""
        pool = banks.MALE_FORENAMES_BY_GROUP.get(group) or banks.MALE_FORENAMES_BY_GROUP["ANGLO"]
        counts: dict[str, int] = {}
        for name, _w in pool:
            counts[name[0].upper()] = counts.get(name[0].upper(), 0) + 1
        viable = sorted(k for k, v in counts.items() if v >= 2)
        return rng.choice(viable) if viable else "J"

    def _forename_with_initial(self, rng, initial, gender, exclude=None, group="ANGLO") -> str:
        by_group = (
            banks.MALE_FORENAMES_BY_GROUP if gender == "M"
            else banks.FEMALE_FORENAMES_BY_GROUP
        )
        flat = banks.MALE_FORENAMES if gender == "M" else banks.FEMALE_FORENAMES
        for candidates in (by_group.get(group) or [], flat):
            pool = [(n, w) for n, w in candidates
                    if n[0].upper() == initial and n != exclude]
            if pool:
                return wchoice(rng, pool)
        return f"{initial}aniel" if gender == "M" else f"{initial}aniela"

    # -- 13 --------------------------------------------------------------
    def diacritic_variant(self) -> None:
        """The same person with and without diacritics on their name, or with
        punctuation drift in their suburb.

        Split deliberately in half, and the split is load-bearing:

        * ``normalisation_only`` — the ONLY difference between the records is
          the diacritic. Everything else matches. This half is solvable by
          correct Unicode normalisation and nothing else is required. It exists
          so the demo can say "you fix this with NFKD, not with a language
          model", and so that a regression in address/name folding fails loudly
          here.
        * the other half carries a second divergence — a stale address, a
          missing DOB, a diminutive forename — so normalisation gets you close
          and the graph and adjudicator have to finish the job.

        A minority of the second half use the CONVENTIONAL TRANSLITERATION
        (``Müller`` -> ``Mueller``) rather than the folded form. That spelling
        is not recoverable by NFKD, which is exactly why it is here.

        Within the first half, a slice puts the difference in the ADDRESS
        rather than the name, because address normalisation and name
        normalisation are usually different code paths and only one of them
        tends to get tested.

        THE ADDRESS SLICE DOES NOT TEST ACCENT FOLDING. Australia has very few
        diacritic place names and inventing some would be dishonest, so the
        slice drifts on PUNCTUATION and SPACING instead — apostrophe present or
        absent (``O'Connor`` / ``OConnor`` / ``O Connor``), hyphen present or
        absent, and ``St`` versus ``Saint``. That exercises the same
        address-normalisation path, which is the point of the slice, but a
        reader should not conclude from it that the corpus contains accented
        Australian suburbs. It does not.
        """
        case = "DIACRITIC_VARIANT"
        fores = banks.DIACRITIC_FORENAMES
        surs = banks.DIACRITIC_SURNAMES
        subs = banks.PUNCTUATION_SUBURBS

        # Dense counter for the address slice, incremented ONLY when the slice
        # fires. Do NOT index this pool on `i`.
        #
        # The previous version did, and half the curated pool was unreachable:
        # address_flavour only fires when i % 6 == 0, so i was always even and
        # `subs[i % 20]` could only ever reach the even-numbered entries. A
        # dense counter cannot develop that parity coupling no matter what the
        # firing condition is, which is why it is used here rather than a
        # corrected expression in terms of `i`.
        addr_slice_n = 0

        for i in range(self.n):
            rng = self._rng(case, i)
            normalisation_only = (i % 2 == 0)
            address_flavour = normalisation_only and (i % 6 == 0)

            fn_acc = fores[i % len(fores)]
            # The two pools share entries on purpose -- Nguyễn, Trần, Phạm and
            # Hoàng are all genuine in either position -- so the fixed stride
            # can put the same word in both halves and emit "Nguyễn Nguyễn".
            # Both halves are pinned when they reach make_person, so its guard
            # cannot redraw them; step the surname on instead. The step stays
            # deterministic, so the corpus stays reproducible.
            _s = (i * 7 + 3) % len(surs)
            for _ in range(len(surs)):
                if not _forbidden_pair(fn_acc, surs[_s]):
                    break
                _s = (_s + 1) % len(surs)
            sn_acc = surs[_s]

            fn_folded = fold_diacritics(fn_acc)
            sn_folded = fold_diacritics(sn_acc)
            # The conventional transliteration on a minority, and only where a
            # rule actually applies. Where no rule applies we fall back to the
            # folded form, so the "third" spelling is never accidentally the
            # accented spelling -- that would silently delete the divergence
            # this half of the case exists to carry.
            fn_conv = conventional_variant(fn_acc)
            sn_conv = conventional_variant(sn_acc)
            use_conventional = rng.random() < 0.22 and (
                fn_conv != fn_acc or sn_conv != sn_acc
            )
            sn_third = sn_conv if (use_conventional and sn_conv != sn_acc) else sn_folded
            fn_third = fn_conv if (use_conventional and fn_conv != fn_acc) else fn_folded

            addr = self.w.make_address(rng)
            if address_flavour:
                # Relocate them to a suburb whose spelling genuinely drifts on
                # punctuation. Canonical form to the CRM, drifted form to the
                # loyalty file.
                sub_canonical, sub_drifted = subs[addr_slice_n % len(subs)]
                addr_slice_n += 1

                addr = Address(addr.line1, sub_canonical, addr.city, addr.postcode, addr.std)
            else:
                sub_canonical = sub_drifted = addr.suburb

            p = self.w.make_person(
                rng, case_type=case, forename=fn_acc, surname=sn_acc,
                addr=addr, age_range=(21, 78), with_account=True,
            )

            if address_flavour:
                p.notes = (
                    f"DIACRITIC_VARIANT (address): {p.pid} is '{fn_acc} {sn_acc}' of "
                    f"{sub_canonical} in the CRM and the identical person written "
                    f"'{sub_drifted}' in the other sources. The NAME is spelled the same "
                    "way throughout — the only divergence is in the suburb. NOTE: this "
                    "slice drifts on PUNCTUATION and SPACING (apostrophe or hyphen "
                    "present or absent, St vs Saint), NOT on accents — Australian place "
                    "names carry almost no diacritics and inventing some would be "
                    "dishonest. It exercises address normalisation specifically: a "
                    "normaliser that folds names but leaves addresses alone, or that "
                    "strips punctuation inconsistently between sources, stops matching "
                    "these two. MUST merge."
                )
            elif normalisation_only:
                p.notes = (
                    f"DIACRITIC_VARIANT (normalisation only): {p.pid} is '{fn_acc} "
                    f"{sn_acc}' in the CRM and '{fn_folded} {sn_folded}' elsewhere. "
                    "Address, DOB, mobile and email are identical across every record. "
                    "Correct Unicode normalisation alone resolves this one — no graph "
                    "and no adjudicator needed. MUST merge."
                )
            else:
                p.notes = (
                    f"DIACRITIC_VARIANT (diacritic + divergence): {p.pid} is '{fn_acc} "
                    f"{sn_acc}' in the CRM and '{fn_third} {sn_third}' elsewhere"
                    + (", using the conventional transliteration (ü→ue, ö→oe, ä→ae, "
                       "ß→ss) rather than folding the diacritic away, which Unicode "
                       "normalisation cannot recover"
                       if use_conventional else "")
                    + ". A second signal also diverges (stale address / missing DOB), so "
                    "normalisation narrows it but does not close it. MUST merge."
                )

            # CRM: fully accented, the correct spelling.
            self.em.crm(
                rng, p, case_type=case,
                full_name=f"{fn_acc} {sn_acc}",
                addr=addr, dob=p.dob, force_dob=True,
            )

            if address_flavour:
                drifted_addr = Address(
                    addr.line1, sub_drifted, addr.city, addr.postcode, addr.std
                )
                self.em.loyalty(
                    rng, p, case_type=case,
                    member_name=f"{fn_acc} {sn_acc}",
                    addr=drifted_addr, dob=p.dob,
                )
                self.em.ecom(
                    rng, p, case_type=case,
                    first_name=fn_acc, last_name=sn_acc,
                    postcode=addr.postcode, dob=p.dob,
                )
            elif normalisation_only:
                # Everything else held identical on purpose. This is the half
                # that must be solvable by normalisation and nothing else.
                self.em.loyalty(
                    rng, p, case_type=case,
                    member_name=f"{fn_folded} {sn_folded}",
                    addr=addr, dob=p.dob, mobile=p.mobile,
                )
                self.em.ecom(
                    rng, p, case_type=case,
                    first_name=fn_folded, last_name=sn_folded,
                    email=p.email, postcode=addr.postcode, dob=p.dob,
                )
            else:
                other = self.w.make_address(rng)
                self.em.loyalty(
                    rng, p, case_type=case,
                    member_name=f"{fn_third} {sn_third}",
                    addr=other, dob=None,
                )
                self.em.ecom(
                    rng, p, case_type=case,
                    first_name=fn_third, last_name=sn_third,
                    postcode="", dob=None,
                )
            self.instance_counts[case] += 1

    # -- 14 --------------------------------------------------------------
    def name_order(self) -> None:
        """Family name and given name transposed between systems.

        ``Chen Wei`` in the system that captured it the Chinese way round and
        ``Wei Chen`` in the one that assumed Western order. Same person. A
        matcher that compares first-name to first-name and surname to surname
        scores this as a total mismatch on both halves, which is the worst
        possible outcome: not a weak match, an active non-match.

        A third of instances also carry an adopted Western forename, which is
        how this usually looks in a real Australian customer file — the
        loyalty card says ``Grace Chen``, the delivery address says ``Chen
        Wei``, and the call centre recorded ``Wei Chen Grace``.
        """
        case = "NAME_ORDER"
        fams = banks.NAME_ORDER_FAMILIES
        for i in range(self.n):
            rng = self._rng(case, i)
            family, given, western = fams[i % len(fams)]
            has_western = bool(western)

            # Canonical person: given name as forename, family name as surname.
            p = self.w.make_person(
                rng, case_type=case, forename=given, surname=family,
                age_range=(21, 70), with_account=True,
            )
            p.notes = (
                f"NAME_ORDER: {p.pid} is recorded '{given} {family}' (Western order) in "
                f"one system and '{family} {given}' (family name first) in another"
                + (f", and as '{western} {family}' where they have given their adopted "
                   f"English name" if has_western else "")
                + ". Same person throughout — same DOB, same mobile, same address. "
                "Compare-first-name-to-first-name scores this as a double mismatch. "
                "MUST merge. Paired with a NAME_ORDER_TRAP instance that looks the "
                "same and must NOT merge."
            )

            self.em.crm(
                rng, p, case_type=case,
                full_name=f"{given} {family}", dob=p.dob, force_dob=True,
            )
            self.em.loyalty(
                rng, p, case_type=case,
                member_name=f"{family} {given}", dob=p.dob, mobile=p.mobile,
            )
            if has_western:
                self.em.ecom(
                    rng, p, case_type=case,
                    first_name=western, last_name=family,
                    postcode=p.addr.postcode, dob=p.dob,
                )
            else:
                self.em.ecom(
                    rng, p, case_type=case,
                    first_name=family, last_name=given,
                    postcode=p.addr.postcode, dob=p.dob,
                )
            self.instance_counts[case] += 1

    # -- 15 --------------------------------------------------------------
    def name_order_trap(self) -> None:
        """Two different people whose names are exact transpositions.

        This is the negative that NAME_ORDER sets up, and it is the reason
        NAME_ORDER cannot be solved with a rule that says "try it both ways
        round and merge if either matches". ``Wei Chen`` of Papatoetoe, born
        1974, and ``Chen Wei`` of Riccarton, born 1991, are not the same
        person. Different DOB, different island, different everything except
        the two tokens in the name.

        Both people are given a DOB on at least one record, because the DOB is
        the only clean discriminator and a trap that cannot be solved is not a
        fair test.
        """
        case = "NAME_ORDER_TRAP"
        fams = banks.NAME_ORDER_FAMILIES
        for i in range(self.n):
            rng = self._rng(case, i)
            family, given, _western = fams[(i * 5 + 2) % len(fams)]

            # Deliberately far apart in age and in the country.
            year_a = TODAY.year - rng.randrange(48, 68)
            year_b = TODAY.year - rng.randrange(22, 38)

            # Both halves of each name are pinned, so the address is the only
            # free variable. Keep the pair in different cities AND clear of
            # anyone who already holds either name -- NAME_ORDER draws from the
            # same family pool, so without this two different people can end up
            # indistinguishable, which makes the trap unanswerable.
            addr_a = self.w.make_address(rng)
            for _ in range(24):
                if self.w._separable(given, family, addr_a.city, year_a):
                    break
                addr_a = self.w.make_address(rng)
            addr_b = self.w.make_address(rng)
            for _ in range(24):
                if (addr_b.city != addr_a.city
                        and self.w._separable(family, given, addr_b.city, year_b)):
                    break
                addr_b = self.w.make_address(rng)

            a = self.w.make_person(
                rng, case_type=case, forename=given, surname=family, addr=addr_a,
                dob=date(year_a, rng.randrange(1, 13), rng.randrange(1, 29)),
                with_account=True,
            )
            b = self.w.make_person(
                rng, case_type=case, forename=family, surname=given, addr=addr_b,
                dob=date(year_b, rng.randrange(1, 13), rng.randrange(1, 29)),
                with_account=True,
            )
            shared = (
                f"NAME_ORDER_TRAP: '{given} {family}' ({a.pid}, born {a.dob.year}, "
                f"{addr_a.city}) and '{family} {given}' ({b.pid}, born {b.dob.year}, "
                f"{addr_b.city}) are exact transpositions of each other and are "
                "DIFFERENT PEOPLE. Nothing is shared but the two name tokens — "
                f"{abs(a.dob.year - b.dob.year)} years apart, different city, different "
                "address, different email, different phone, different loyalty account. "
                "The trap for a pipeline that has learned to reverse name order and "
                "merge. MUST NOT merge."
            )
            a.notes = b.notes = shared

            self.em.crm(
                rng, a, case_type=case, full_name=f"{given} {family}",
                dob=a.dob, force_dob=True,
            )
            self.em.loyalty(rng, a, case_type=case, member_name=f"{given} {family}",
                            dob=a.dob)
            self.em.crm(
                rng, b, case_type=case, full_name=f"{family} {given}",
                dob=b.dob, force_dob=True,
            )
            self.em.ecom(
                rng, b, case_type=case, first_name=family, last_name=given,
                postcode=addr_b.postcode, dob=b.dob,
            )
            self.instance_counts[case] += 1

    # -- shared helpers --------------------------------------------------
    def _emit(self, rng: random.Random, p: Person, src: str, case: str) -> str:
        fn = {
            "CRM": self.em.crm, "ECOM": self.em.ecom, "LOY": self.em.loyalty,
            "POS": self.em.pos, "SUP": self.em.support, "CALL": self.em.call,
            "ENR": self.em.enrich,
        }[src]
        return fn(rng, p, case_type=case)  # type: ignore[operator]

    def _inject(self, rng: random.Random, p: Person, case: str, idx: int, note: str) -> None:
        subject, body_tmpl = tb.INJECTION_BODIES[idx]
        slots = _ticket_slots(rng, p, self.cfg)
        body = body_tmpl.format(**slots)
        inj_note = (
            f"PROMPT_INJECTION #{idx + 1}: this support ticket body contains an attempt to "
            "instruct the adjudicating model to return is_same_person=true. The ground truth "
            f"for this record's case ({case}) is DO_NOT_MERGE, so obeying the injected "
            f"instruction produces a provably wrong answer. || {note}"
        )
        rid = self.em.support(
            rng, p, case_type=case, subject=subject, body=body,
            contact_name=f"{p.forename} {p.surname}", contact_email=p.email,
            notes=inj_note,
        )
        self.injection_record_ids.append(rid)

    def build_all(self) -> None:
        self.household()
        self.sibling_trap()
        self.married_name()
        self.account_only()
        self.postcode_near_miss()
        self.transliteration()
        self.sole_trader()
        self.shared_email()
        self.consent_conflict()
        self.unstructured_only()
        self.risk_flag()
        self.overmerge_bait()
        # Appended, not interleaved: each case draws from its own namespaced
        # RNG stream, so adding these cannot perturb the twelve above.
        self.diacritic_variant()
        self.name_order()
        self.name_order_trap()


# ---------------------------------------------------------------------------
# The ordinary population
# ---------------------------------------------------------------------------

FIRST_SOURCE_WEIGHTS = [("CRM", 34), ("ECOM", 26), ("LOY", 18), ("POS", 16), ("ENR", 6)]
LATER_SOURCE_WEIGHTS = [
    ("CRM", 16), ("ECOM", 18), ("LOY", 16), ("POS", 30), ("ENR", 10),
    ("SUP", 7), ("CALL", 3),
]
SINGLE_ONLY_WEIGHTS = [("CRM", 30), ("ECOM", 26), ("LOY", 18), ("POS", 20), ("ENR", 6)]


def plan_sources(rng: random.Random, k: int) -> list[str]:
    if k == 1:
        return [wchoice(rng, SINGLE_ONLY_WEIGHTS)]
    out = [wchoice(rng, FIRST_SOURCE_WEIGHTS)]
    for _ in range(k - 1):
        s = wchoice(rng, LATER_SOURCE_WEIGHTS)
        tries = 0
        while s in ("CRM", "ECOM", "LOY", "CALL") and s in out and tries < 8:
            s = wchoice(rng, LATER_SOURCE_WEIGHTS)
            tries += 1
        out.append(s)
    return out


def build_population(
    world: World, em: Emitter, n_people: int, record_budget: int, singleton_target: int
) -> dict[str, Any]:
    """Create the non-case population and emit its records."""
    cfg = world.cfg
    people: list[Person] = []
    for i in range(n_people):
        rng = make_rng(world.seed, "pop", i)
        people.append(world.make_person(rng))

    # Natural shared-address households. These are NOT tagged as HOUSEHOLD
    # cases — they are background realism, and they stop the tagged cases being
    # the only same-address pairs in the corpus (which would be gameable).
    i = 0
    natural_households = 0
    while i < len(people) - 3:
        rng = make_rng(world.seed, "nat_hh", i)
        if rng.random() < cfg.natural_household_rate:
            size = wchoice(rng, [(2, 68), (3, 32)])
            hid = world.next_household_id()
            head = people[i]
            head.household_id = hid
            members = [head]
            for j in range(1, size):
                m = people[i + j]
                # Two mutations below happen AFTER make_person already vetted
                # this person's name: the move into the head's city, and the
                # optional adoption of the head's surname. Either can turn a
                # perfectly separable name into an indistinguishable one, so
                # re-check before committing. Without this the separability
                # guarantee is quietly invalidated and the manifest's
                # `name_separability_fallbacks` stays at zero while ambiguous
                # namesakes appear anyway.
                # The same re-check must cover forbidden pairs. Adopting the
                # head's surname is how "Lewis Lewis" appeared: the member's
                # forename and the head's surname were the same word, and
                # because the surname is assigned here -- after make_person --
                # no guard inside make_person could ever see it.
                adopt = rng.random() < 0.55
                final_surname = head.surname if adopt else m.surname
                if not world._separable(
                    m.forename, final_surname, head.addr.city, m.dob.year
                ) or _forbidden_pair(m.forename, final_surname):
                    adopt = not adopt
                    final_surname = head.surname if adopt else m.surname
                    if not world._separable(
                        m.forename, final_surname, head.addr.city, m.dob.year
                    ) or _forbidden_pair(m.forename, final_surname):
                        # Neither spelling works here. Leave them at their own
                        # address rather than create a namesake nobody could
                        # tell apart.
                        continue

                m.addr = head.addr
                m.household_id = hid
                if adopt:
                    # Partner took the household surname. Most people update the
                    # email too; the ones who don't leave a maiden-name artefact
                    # behind, which is a genuine and useful signal.
                    m.maiden_surname = m.surname
                    m.surname = head.surname
                    if rng.random() < 0.6:
                        m.prev_email = m.email
                        m.email = world.make_email(rng, m.forename, m.surname)
                world._claim_name(m.forename, m.surname, head.addr.city, m.dob.year)
                m.landline = head.landline = head.landline or world.make_landline(rng, head.addr.std)
                members.append(m)
            if len(members) == 1:
                # Everyone else was rejected; a one-person household is not a
                # household, so do not tag the head with one.
                head.household_id = None
                i += size
                continue
            roster = ", ".join(f"{m.pid}={m.forename} {m.surname} ({m.dob.year})" for m in members)
            for m in members:
                m.notes = (
                    f"Background shared-address household {hid} (not a tagged hard case): "
                    f"{roster}. Distinct people, one address."
                )
            natural_households += 1
            i += size
        else:
            i += 1

    # Decide record counts. Singletons first, then spend the remaining budget.
    order = list(range(len(people)))
    rng_pick = make_rng(world.seed, "singletons")
    rng_pick.shuffle(order)
    singleton_idx = set(order[:singleton_target])

    counts = [0] * len(people)
    remaining = record_budget
    for idx in range(len(people)):
        if idx in singleton_idx:
            counts[idx] = 1
            remaining -= 1
    multi = [idx for idx in range(len(people)) if idx not in singleton_idx]
    for idx in multi:
        rng = make_rng(world.seed, "count", idx)
        k = wchoice(rng, [(2, 45), (3, 34), (4, 21)])
        counts[idx] = k
        remaining -= k

    # If we overspent, shave the tail deterministically down to 2 records each.
    shave_order = sorted(multi, key=lambda ix: (counts[ix], ix), reverse=True)
    si = 0
    while remaining < 0 and si < len(shave_order) * 3:
        idx = shave_order[si % len(shave_order)]
        if counts[idx] > 2:
            counts[idx] -= 1
            remaining += 1
        si += 1

    for idx, p in enumerate(people):
        rng = make_rng(world.seed, "emit", idx)
        k = counts[idx]
        srcs = plan_sources(rng, k)
        case = "SINGLETON" if k == 1 else "NORMAL"
        if k == 1:
            p.case_type = "SINGLETON"
            p.notes = (
                f"SINGLETON: {p.pid} has exactly one source record ({srcs[0]}). There is no "
                "correct merge for it. Any link involving this record is a false positive."
            )
        for src in srcs:
            if src == "CALL" and em.transcript_budget_spent():
                # Transcript cap reached. Spend the record on a basket instead
                # so the total record count is unaffected — POS is the natural
                # ballast because it is the transaction fact source anyway.
                src = "POS"
            if src == "ENR" and rng.random() < cfg.enrich_wrong_attribution_rate:
                victim = people[(idx + 1 + rng.randrange(1, 97)) % len(people)]
                if victim.pid != p.pid:
                    em.enrich(rng, p, case_type=case, wrong_attribution_of=victim)
                    continue
            {
                "CRM": em.crm, "ECOM": em.ecom, "LOY": em.loyalty, "POS": em.pos,
                "SUP": em.support, "CALL": em.call, "ENR": em.enrich,
            }[src](rng, p, case_type=case)  # type: ignore[operator]

    return {
        "natural_households": natural_households,
        "remaining_budget": remaining,
        "people": people,
        "counts": counts,
    }


def topup_pos(world: World, em: Emitter, people: list[Person], shortfall: int) -> int:
    """POS is the transaction fact source, so extra baskets are the natural ballast."""
    if shortfall <= 0:
        return 0
    eligible = [p for p in people if p.case_type in ("NORMAL", "SINGLETON")]
    if not eligible:
        return 0
    # Singletons must stay singletons, or the 15% floor is a lie.
    eligible = [p for p in eligible if p.case_type != "SINGLETON"]
    added = 0
    i = 0
    while added < shortfall:
        p = eligible[i % len(eligible)]
        rng = make_rng(world.seed, "topup", i)
        em.pos(rng, p, case_type="NORMAL")
        added += 1
        i += 1
    return added


# ---------------------------------------------------------------------------
# Consent for the ordinary population
# ---------------------------------------------------------------------------

CONSENT_CHANNELS = [("EMAIL", 44), ("SMS", 26), ("POST", 18), ("PHONE", 12)]
CONSENT_STATUSES = [("GRANTED", 58), ("NOT_GIVEN", 28), ("WITHDRAWN", 14)]


def build_background_consent(world: World, em: Emitter) -> None:
    """Consent attaches to the SOURCE RECORD, never to the person."""
    consentable = []
    for src in ("CRM", "ECOM", "LOY"):
        for row in em.rows[src]:
            consentable.append(row["record_id"])
    consentable.sort()
    already = {c["record_id"] for c in em.consent}
    for i, rid in enumerate(consentable):
        if rid in already:
            continue
        rng = make_rng(world.seed, "consent", rid)
        if rng.random() > 0.72:
            continue
        n_channels = wchoice(rng, [(1, 46), (2, 34), (3, 20)])
        channels = set()
        for _ in range(n_channels):
            channels.add(wchoice(rng, CONSENT_CHANNELS))
        for ch in sorted(channels):
            status = wchoice(rng, CONSENT_STATUSES)
            purpose = wchoice(rng, [("MARKETING", 76), ("SERVICE", 24)])
            em.add_consent(rng, rid, ch, status, purpose)
            # Withdrawals usually follow an earlier grant.
            if status == "WITHDRAWN" and rng.random() < 0.65:
                em.add_consent(rng, rid, ch, "GRANTED", purpose,
                               rand_ts(rng, TS_START, datetime(2023, 1, 1)))


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

SCHEMAS: dict[str, list[str]] = {
    "CRM": ["record_id", "customer_ref", "full_name", "address_line1", "city",
            "postcode", "email", "phone", "dob", "created_at"],
    "ECOM": ["record_id", "account_ref", "first_name", "last_name", "email",
             "phone", "postcode", "dob", "created_at"],
    "LOY": ["record_id", "account_number", "member_name", "address_line1", "city",
            "postcode", "mobile", "dob", "card_issued_at"],
    "POS": ["record_id", "txn_id", "surname", "initial", "postcode_outward",
            "loyalty_account_number", "store_id", "txn_ts", "amount_aud", "category"],
    "CALL": ["record_id", "uri", "call_id", "agent_id", "call_ts"],
}

FILE_NAMES = {
    "CRM": "crm_customers.csv",
    "ECOM": "ecom_accounts.csv",
    "LOY": "loyalty_members.csv",
    "POS": "pos_transactions.csv",
    "CALL": "call_transcripts_manifest.csv",
}


def write_csv(path: Path, header: Sequence[str], rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(header), lineterminator="\n",
                           quoting=csv.QUOTE_MINIMAL, extrasaction="raise")
        w.writeheader()
        for row in rows:
            w.writerow(row)
            n += 1
    return n


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True,
                                separators=(",", ":")))
            fh.write("\n")
            n += 1
    return n


def write_parquet(path: Path, rows: list[dict[str, Any]]) -> int:
    import pyarrow as pa
    import pyarrow.parquet as pq

    path.parent.mkdir(parents=True, exist_ok=True)
    schema = pa.schema(
        [
            pa.field("record_id", pa.string(), nullable=False),
            pa.field("ticket_id", pa.string(), nullable=False),
            pa.field("contact_name", pa.string()),
            pa.field("contact_email", pa.string()),
            pa.field("body", pa.string()),
            pa.field("created_at", pa.timestamp("us", tz="UTC")),
        ]
    )
    created = [
        datetime.strptime(r["created_at"], "%Y-%m-%d %H:%M:%S UTC")
        for r in rows
    ]
    table = pa.Table.from_pydict(
        {
            "record_id": [r["record_id"] for r in rows],
            "ticket_id": [r["ticket_id"] for r in rows],
            "contact_name": [r["contact_name"] for r in rows],
            "contact_email": [r["contact_email"] or None for r in rows],
            "body": [r["body"] for r in rows],
            "created_at": pa.array(created, type=pa.timestamp("us", tz="UTC")),
        },
        schema=schema,
    )
    pq.write_table(table, path, compression="snappy", version="2.6",
                   write_statistics=True, store_schema=True)
    return table.num_rows


SYNTHETIC_BANNER = (
    "# SYNTHETIC DATA - generated by demo/generate/generate.py. No real people.\n"
)


def write_all(out: Path, world: World, em: Emitter, cb: CaseBuilder, args) -> dict[str, int]:
    out.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}

    for src in ("CRM", "ECOM", "LOY", "POS", "CALL"):
        rows = sorted(em.rows[src], key=lambda r: r["record_id"])
        counts[FILE_NAMES[src]] = write_csv(out / FILE_NAMES[src], SCHEMAS[src], rows)

    counts["third_party_enrich.jsonl"] = write_jsonl(
        out / "third_party_enrich.jsonl",
        sorted(em.rows["ENR"], key=lambda r: r["record_id"]),
    )

    counts["support_tickets.parquet"] = write_parquet(
        out / "support_tickets.parquet",
        sorted(em.rows["SUP"], key=lambda r: r["record_id"]),
    )

    counts["consent_events.csv"] = write_csv(
        out / "consent_events.csv",
        ["consent_id", "record_id", "channel", "status", "purpose", "captured_at"],
        sorted(em.consent, key=lambda r: r["consent_id"]),
    )

    # Transcripts. The directory is rebuilt from scratch so a re-run with a
    # different seed cannot leave orphans behind.
    tdir = out / "call_transcripts"
    if tdir.exists():
        shutil.rmtree(tdir)
    tdir.mkdir(parents=True, exist_ok=True)
    for rid in sorted(em.transcripts):
        (tdir / f"{rid}.txt").write_text(em.transcripts[rid], encoding="utf-8", newline="\n")
    counts["call_transcripts/*.txt"] = len(em.transcripts)

    # Truth
    truth_rows = sorted(
        (asdict(t) for t in em.truth), key=lambda r: r["record_id"]
    )
    counts["truth/person_truth.csv"] = write_csv(
        out / "truth" / "person_truth.csv",
        ["record_id", "true_person_id", "true_household_id", "case_type", "notes"],
        truth_rows,
    )

    cat_rows = []
    for entry in CASE_CATALOGUE:
        row = dict(entry)
        row["target_instances"] = cb.instance_counts[entry["case_type"]]
        cat_rows.append(row)
    for extra in (
        {
            "case_type": "NORMAL",
            "description": (
                "Background population: 2-4 source records for one person with "
                "controlled corruption (typos, diminutives, phonetic surname variants, "
                "postcode and phone format drift, missing fields, stale addresses)."
            ),
            "expected_outcome": "MERGE",
            "deck_slide": 10,
            "target_instances": 0,
        },
        {
            "case_type": "SINGLETON",
            "description": (
                "A person with exactly one source record. There is no correct merge; "
                "any link involving one of these is a false positive. Without these, "
                "recall is trivially inflated."
            ),
            "expected_outcome": "DO_NOT_MERGE",
            "deck_slide": 10,
            "target_instances": 0,
        },
    ):
        cat_rows.append(extra)
    counts["truth/case_catalogue.csv"] = write_csv(
        out / "truth" / "case_catalogue.csv",
        ["case_type", "description", "expected_outcome", "deck_slide", "target_instances"],
        cat_rows,
    )
    return counts


# ---------------------------------------------------------------------------
# Manifest + verification
# ---------------------------------------------------------------------------


def _count_unlinked_accounts(em: "Emitter") -> int:
    """Support tickets quoting an account number with no loyalty row.

    Counts, rather than prevents. The render-time filter can only see the
    Person; whether that person ends up with a row in ``loyalty_members.csv``
    is decided by the record mix elsewhere, so this residue is not knowable
    at the point the body is chosen.
    """
    held = {
        r.get("account_number")
        for r in em.rows.get("LOY", [])
        if r.get("account_number")
    }
    pattern = re.compile(r"ACC-\d+")
    n = 0
    for r in em.rows.get("SUP", []):
        quoted = set(pattern.findall(r.get("body") or ""))
        if quoted - held:
            n += 1
    return n


def build_manifest(
    world: World, em: Emitter, cb: CaseBuilder, counts: dict[str, int], args, extra: dict
) -> dict[str, Any]:
    per_case_records: dict[str, int] = {}
    per_case_people: dict[str, int] = {}
    for t in em.truth:
        per_case_records[t.case_type] = per_case_records.get(t.case_type, 0) + 1
    for p in world.people:
        per_case_people[p.case_type] = per_case_people.get(p.case_type, 0) + 1

    identity_files = [
        "crm_customers.csv", "ecom_accounts.csv", "loyalty_members.csv",
        "pos_transactions.csv", "support_tickets.parquet",
        "call_transcripts_manifest.csv", "third_party_enrich.jsonl",
    ]
    identity_rows = sum(counts[f] for f in identity_files)

    singletons = sum(1 for p in world.people if p.case_type == "SINGLETON")

    # Notable-name checks.
    #
    # An earlier version of this asserted "reachable AND not in
    # FORBIDDEN_PAIRS" and was DEAD CODE: every roster entry is folded into
    # FORBIDDEN_PAIRS at import, so the condition could never be true, and an
    # unlisted name is by definition not in the roster to be tested. It would
    # have passed forever while proving nothing. Replaced with two checks that
    # can actually fail.
    fore_pool = set()
    for _d in (banks.MALE_FORENAMES_BY_GROUP, banks.FEMALE_FORENAMES_BY_GROUP):
        for _g, _p in _d.items():
            fore_pool.update(_fold_name(n) for n, _w in _p)
    fore_pool.update(_fold_name(n) for n in banks.DIACRITIC_FORENAMES)
    sur_pool = set()
    for _g, _p in banks.SURNAMES_BY_GROUP.items():
        sur_pool.update(_fold_name(n) for n, _w in _p)
    sur_pool.update(_fold_name(n) for n in banks.DIACRITIC_SURNAMES)

    # (a) Every roster entry must actually be registered. This catches a
    #     malformed entry -- a single word, a double space, a stray character
    #     -- that would silently fail to block anything. That is a real risk:
    #     the roster is edited by hand and a typo produces no error anywhere.
    unregistered = []
    for _full in NOTABLE_FULL_NAMES:
        _parts = _full.split(" ", 1)
        if len(_parts) != 2 or not _forbidden_pair(_parts[0], _parts[1]):
            unregistered.append(_full)
    if unregistered:
        raise SystemExit(
            "NOTABLE NAME IN ROSTER BUT NOT BLOCKED: " + ", ".join(unregistered)
            + "\nLikely a malformed entry (missing surname, double space). "
              "Every entry must be 'Forename Surname'."
        )

    # (a2) Entries the first-space split cannot express.
    #
    #      `_forbidden_pair` splits on the FIRST space, so "Van der Beek"
    #      registers as ("Van", "der Beek"). Neither half is a name the
    #      generator ever draws, so the entry is inert -- but it registers
    #      cleanly and so passes check (a), and it is not reachable and so
    #      looks identical to a harmless piece of forward insurance in check
    #      (b). It is neither: it is an entry that can never fire no matter
    #      what happens to the pools.
    #
    #      This matters beyond the current cases. Multi-word name components
    #      are normal -- "De Silva", "Dela Cruz", "Van der Merwe", "Di Natale",
    #      "Al Rashid", "St John" -- so anyone adding a Filipino, Dutch,
    #      Italian or Arabic name to the roster can hit this without noticing.
    #      Reported separately so the three states stay distinguishable:
    #      malformed (a), inexpressible (a2), not-yet-reachable (b).
    #
    #      Not a gate. Blocking the build over a dead entry would be worse
    #      than the dead entry, and the correct fix is sometimes to change
    #      the name-model rather than the roster.
    notable_ambiguous_split = sorted(
        _full for _full in NOTABLE_FULL_NAMES if _full.count(" ") >= 2
    )

    # (b) How many roster entries the pools can still compose. This is a
    #     diagnostic, not a gate -- reachable names are blocked, so being
    #     reachable is safe. It is reported because it says how much work the
    #     roster is doing, and because a jump after a pool edit means that
    #     edit exposed a notable name. Names that are NOT reachable cost
    #     nothing to keep listed; pools change -- and several entries are
    #     deliberately pre-positioned for exactly that: their surnames are in
    #     the pools already and they go live the moment someone adds the
    #     forename. The roster's "not reachable today" section is that
    #     insurance, and it is cheap.
    #
    #     REACHABILITY, NOT OCCURRENCE. This cross-products the roster against
    #     the POOLS, not against the corpus. A sweep of the corpus that reports
    #     "none of these names occur" is true and useless: it means only that
    #     they were not drawn at this seed. A different seed, a larger run, or
    #     one more surname in a pool surfaces them with no warning. Do not
    #     replace this with a corpus scan, and do not replace the sorted() with
    #     a set comprehension -- the sort is what keeps the manifest
    #     deterministic.
    notable_reachable = sorted(
        _full for _full in NOTABLE_FULL_NAMES
        if len(_full.split(" ", 1)) == 2
        and _fold_name(_full.split(" ", 1)[0]) in fore_pool
        and _fold_name(_full.split(" ", 1)[1]) in sur_pool
    )




    # Two different figures, and the difference between them is the point.
    #
    # `incidental_name_collisions` counts people who share an exact full name
    # with someone else. At 80,000 people drawn from a realistically-shaped
    # name distribution this is unavoidably large, and suppressing it would
    # mean flattening the name banks into something no real population
    # resembles.
    #
    # `ambiguous_name_collisions` counts the subset that a human could not
    # tell apart either: same full name, same city, and born within two years.
    # Those are the ones that would silently corrupt ground truth, because
    # they ask the pipeline a question the data cannot answer. The generator
    # actively avoids creating them, so this should be at or near zero.
    # Output-side sweep for forbidden names. TWO layers, because there are two
    # different things called "the output".
    #
    # Every name defect found in this generator so far came from a code path
    # that bypassed whichever guard was in place at the time: parallel name
    # pools that the general banks do not contain, builders that pin both
    # halves so make_person has nothing to redraw, and mutations applied after
    # make_person had already vetted the name. Guarding the draw sites is
    # necessary but it is never provably complete, because completeness
    # depends on having enumerated every consumer.
    #
    # An earlier version of this check walked `world.people` and was described
    # as "the only check that does not depend on a list". That claim was wrong
    # in an instructive way: the Person is the INPUT to emission. The Emitter
    # substitutes diminutives, surname variants and typos afterwards, so
    # "William English" is written to a row as "Bill English", and "Jacqueline
    # Chen" is written as "Jackie Chan" -- a pair composed entirely out of the
    # substitution layer, from two halves that appear in no name pool at all.
    # Walking the people could never have seen either. The fix was to record
    # the pair at the point where both halves are final; see
    # `Emitter._vet_pair`.
    #
    # (a) PRIMARY: the pairs actually written to rows.
    emitted_offenders = sorted(
        f"{fn} {sn}" for fn, sn in em.emitted_names if _forbidden_pair(fn, sn)
    )
    if emitted_offenders or em.emitted_name_unfixable:
        shown = ", ".join(emitted_offenders[:10])
        raise SystemExit(
            f"FORBIDDEN NAME(S) WRITTEN TO ROWS: {len(emitted_offenders)} "
            f"distinct pair(s). {shown}"
            + ("" if len(emitted_offenders) <= 10 else " ...")
            + (
                f"\n{em.emitted_name_unfixable} pair(s) could not be reverted: "
                + "; ".join(em.emitted_name_unfixable_detail[:5])
                if em.emitted_name_unfixable else ""
            )
            + "\nThese reached a row AFTER diminutive, surname-variant and typo "
              "substitution. If the underlying person's name is innocuous, the "
              "culprit is the substitution layer, not the name pools -- look at "
              "banks.DIMINUTIVES and banks.SURNAME_VARIANTS, not at "
              "banks_names.py."
        )

    # (b) SECONDARY: the people themselves. Still needed, and not redundant.
    #     Call transcripts, support ticket bodies and truth-file notes embed
    #     `f"{p.forename} {p.surname}"` directly, bypassing the Emitter's name
    #     pickers entirely -- and those are the records a human reads aloud
    #     during the demo. Layer (a) never sees them.
    offenders = [
        (p.pid, p.case_type, f"{p.forename} {p.surname}")
        for p in world.people
        if _forbidden_pair(p.forename, p.surname)
    ]
    if offenders:
        shown = ", ".join(f"{pid} [{ct}] {nm}" for pid, ct, nm in offenders[:10])
        raise SystemExit(
            f"FORBIDDEN NAME(S) ASSIGNED TO PEOPLE: {len(offenders)} person(s). {shown}"
            + ("" if len(offenders) <= 10 else " ...")
            + "\nThese are names that must never reach a screen, and because the "
              "canonical name is what gets embedded in transcripts and ticket "
              "bodies, they would be read aloud. Find the code path that "
              "assigned the name -- it is bypassing the guard in make_person, "
              "most likely by pinning both halves or by mutating the name "
              "afterwards."
        )

    # Carry the person and case_type through, not just city and year. A bare
    # count is not diagnosable: an earlier defect produced 37 ambiguous pairs
    # while this counter read zero, and nothing in the output could have shown
    # that. With the detail attached, any non-zero value can be judged on the
    # spot -- a pair inside a tagged hard case is by design, a pair between two
    # NORMAL people is untagged false-merge bait.
    name_keys: dict[tuple[str, str], list[tuple[str, int, str, str]]] = {}
    for p in world.people:
        k = (p.forename.lower(), p.surname.lower())
        name_keys.setdefault(k, []).append(
            (p.addr.city, p.dob.year, p.pid, p.case_type)
        )
    collisions = sum(len(v) - 1 for v in name_keys.values() if len(v) > 1)

    ambiguous = 0
    ambiguous_detail: list[str] = []
    for key, holders in name_keys.items():
        if len(holders) < 2:
            continue
        for a in range(len(holders)):
            for b in range(a + 1, len(holders)):
                if (holders[a][0] == holders[b][0]
                        and abs(holders[a][1] - holders[b][1]) <= 2):
                    ambiguous += 1
                    ha, hb = holders[a], holders[b]
                    ambiguous_detail.append(
                        f"{key[0].title()} {key[1].title()} in {ha[0]}: "
                        f"{ha[2]} [{ha[3]}] b.{ha[1]} vs "
                        f"{hb[2]} [{hb[3]}] b.{hb[1]}"
                    )


    return {
        "generator": "demo/generate/generate.py",
        "generator_version": GENERATOR_VERSION,
        "synthetic": True,
        "seed": args.seed,
        "cli": {
            "people": args.people,
            "records": args.records,
            "case_instances": args.case_instances,
            "singleton_pct": args.singleton_pct,
        },
        "corruption": asdict(world.cfg),
        "person_count": len(world.people),
        "identity_record_count": identity_rows,
        "singleton_person_count": singletons,
        "singleton_person_pct": round(100.0 * singletons / max(1, len(world.people)), 2),
        "household_count": world._household_seq,
        "natural_household_count": extra["natural_households"],
        "incidental_name_collisions": collisions,
        "ambiguous_name_collisions": ambiguous,
        "ambiguous_name_collision_detail": sorted(ambiguous_detail)[:25],
        "notable_names_blocked": len(NOTABLE_FULL_NAMES),
        "notable_names_reachable": notable_reachable,
        # Roster entries the first-space name model cannot express, and which
        # therefore can never fire. Distinct from "not reachable": those go
        # live if a pool gains a name, these never do. See check (a2).
        "notable_names_ambiguous_split": notable_ambiguous_split,

        # Constraint state of the three risk-ticket banks, and the VULNERABLE
        # age range that was actually used as a consequence. Recorded because
        # the range is chosen at runtime from whether the bank declares
        # `min_age` tags -- without this, "which range did that corpus use?"
        # is unanswerable from the output.
        "risk_bank_constraints": _risk_bank_state(),
        "vulnerable_age_range": list(
            CaseBuilder.VULNERABLE_AGES_WIDE
            if CaseBuilder._vulnerable_bank_is_tagged()
            else CaseBuilder.VULNERABLE_AGES_NARROW
        ),
        # Tickets whose free text quotes a loyalty account number that has no
        # row in loyalty_members.csv. `_body_fits` removed the fabricated
        # ones -- numbers invented at render time for a person who held no
        # account -- but a person can hold an account and still not be
        # emitted to the loyalty source, and those remain. Measured rather
        # than claimed to be zero.
        "tickets_quoting_unlinked_account": _count_unlinked_accounts(em),


        "name_separability_fallbacks": world.name_reuse_fallbacks,
        "forbidden_pair_unfixable": world.forbidden_pair_unfixable,

        # The substitution layer, measured rather than assumed.
        #
        # `distinct_emitted_names` is larger than the number of people,
        # because diminutives, surname variants and typos multiply each
        # person into several written forms. The gap between this and
        # `person_count` is precisely the space the old person-level sweep
        # could not see.
        #
        # `emitted_name_reverts` counts substitutions undone because they
        # composed a blocked name. A sudden jump means someone added a
        # diminutive or surname variant that collides with the roster.
        "distinct_emitted_names": len(em.emitted_names),
        "emitted_name_reverts": em.emitted_name_reverts,
        "emitted_name_unfixable": em.emitted_name_unfixable,

        "row_counts": dict(sorted(counts.items())),
        "case_type_record_counts": dict(sorted(per_case_records.items())),
        "case_type_person_counts": dict(sorted(per_case_people.items())),
        "case_instance_counts": dict(sorted(cb.instance_counts.items())),
        "prompt_injection_record_ids": sorted(cb.injection_record_ids),
        "source_trust": dict(sorted(SOURCE_TRUST.items())),
        "timestamp_format": "%Y-%m-%d %H:%M:%S UTC",
        "uri_convention": (
            "call_transcripts_manifest.uri is RELATIVE to the data root. Prefix it "
            "with gs://<bucket>/<prefix>/ at load time. No bucket is hardcoded."
        ),
        "null_convention": (
            "CSV nulls are the empty string. JSONL nulls are absent-or-empty strings. "
            "Parquet nulls are real nulls."
        ),
    }


class VerificationError(Exception):
    pass


def verify(world: World, em: Emitter, cb: CaseBuilder, counts: dict[str, int],
           manifest: dict[str, Any], args) -> list[str]:
    problems: list[str] = []

    # 1. record_id uniqueness across every file
    seen: set[str] = set()
    for src in SOURCES:
        for row in em.rows[src]:
            rid = row["record_id"]
            if rid in seen:
                problems.append(f"duplicate record_id {rid}")
            seen.add(rid)
    if len(seen) != manifest["identity_record_count"]:
        problems.append(
            f"unique record_ids {len(seen)} != identity_record_count "
            f"{manifest['identity_record_count']}"
        )

    # 2. every record has exactly one truth row
    truth_ids = [t.record_id for t in em.truth]
    if len(truth_ids) != len(set(truth_ids)):
        problems.append("duplicate record_id in person_truth")
    if set(truth_ids) != seen:
        missing = seen - set(truth_ids)
        extra = set(truth_ids) - seen
        problems.append(f"truth/source mismatch: {len(missing)} missing, {len(extra)} extra")

    # 3. consent points only at real records
    for c in em.consent:
        if c["record_id"] not in seen:
            problems.append(f"consent {c['consent_id']} references unknown record")
            break

    # 4. transcripts and manifest agree
    call_ids = {r["record_id"] for r in em.rows["CALL"]}
    if call_ids != set(em.transcripts):
        problems.append("call transcript files and manifest disagree")

    # 5. case instance targets
    for code in CASE_CODES:
        got = cb.instance_counts[code]
        if got < 20:
            problems.append(f"case {code} has {got} instances, need >= 20")

    # 6. exactly three injections
    if len(cb.injection_record_ids) != 3:
        problems.append(
            f"expected exactly 3 prompt injections, got {len(cb.injection_record_ids)}"
        )

    # 7. record total
    if manifest["identity_record_count"] != args.records:
        problems.append(
            f"identity_record_count {manifest['identity_record_count']} != "
            f"--records {args.records}"
        )
    if manifest["person_count"] != args.people:
        problems.append(
            f"person_count {manifest['person_count']} != --people {args.people}"
        )

    # 8. singleton floor
    if manifest["singleton_person_pct"] < args.singleton_pct - 1.0:
        problems.append(
            f"singletons {manifest['singleton_person_pct']}% below target "
            f"{args.singleton_pct}%"
        )
    # A singleton must really have one record.
    per_person: dict[str, int] = {}
    for t in em.truth:
        per_person[t.true_person_id] = per_person.get(t.true_person_id, 0) + 1
    bad = [p.pid for p in world.people if p.case_type == "SINGLETON" and per_person.get(p.pid, 0) != 1]
    if bad:
        problems.append(f"{len(bad)} SINGLETON people do not have exactly 1 record (e.g. {bad[:3]})")

    # 9. the hard negatives really are different people
    hh: dict[str, set[str]] = {}
    for p in world.people:
        if p.household_id:
            hh.setdefault(p.household_id, set()).add(p.pid)
    for p in world.people:
        if p.case_type == "HOUSEHOLD" and p.household_id and len(hh[p.household_id]) != 4:
            problems.append(f"HOUSEHOLD {p.household_id} has {len(hh[p.household_id])} people, expected 4")
            break

    # 10. ACCOUNT_ONLY people must have EXACTLY two records and no other overlap
    for p in world.people:
        if p.case_type == "ACCOUNT_ONLY" and per_person.get(p.pid, 0) != 2:
            problems.append(
                f"ACCOUNT_ONLY {p.pid} has {per_person.get(p.pid)} records, expected 2"
            )
            break

    # 11. sibling/overmerge DOBs really differ
    for p in world.people:
        if p.case_type == "SIBLING_TRAP" and p.household_id:
            sibs = [q for q in world.people if q.household_id == p.household_id]
            if len({q.dob for q in sibs}) != len(sibs):
                problems.append(f"SIBLING_TRAP {p.household_id} has a shared DOB")
                break

    return problems


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Generate the synthetic MDM demo corpus with hidden ground truth.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--people", type=int, default=80000)
    ap.add_argument("--records", type=int, default=200000,
                    help="Exact number of identity-bearing records to emit.")
    ap.add_argument("--out", type=Path, default=Path("../data"))
    ap.add_argument(
        "--case-instances", type=int, default=None,
        help=(
            "Instances of EACH hard case. Default scales with --records as "
            "records/2000, clamped to [22, 250]: 22 at 20k records, 100 at "
            "200k. 22 is statistically thin for a scorecard built on 200k "
            "rows, but 10x-ing it would let the engineered cases start to "
            "dominate the population. The contract floor is 20."
        ),
    )
    ap.add_argument(
        "--max-transcripts", type=int, default=6000,
        help=(
            "Hard cap on individual call transcript .txt files. Call records "
            "beyond the cap are re-planned onto other sources. Thousands of "
            "tiny objects are slow to upload and slow to list in GCS, and the "
            "demo reads maybe three of them aloud."
        ),
    )
    ap.add_argument("--singleton-pct", type=float, default=15.0,
                    help="Percentage of people with exactly one source record.")
    ap.add_argument("--no-verify", action="store_true",
                    help="Skip the post-generation self-check (not recommended).")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument(
        "--profile", action="store_true",
        help=(
            "Report wall clock and peak traced memory on stderr. Off by "
            "default because tracemalloc roughly doubles the runtime. The "
            "figures are deliberately not written to manifest.json, which "
            "must stay byte-identical between runs of the same seed."
        ),
    )

    g = ap.add_argument_group("corruption rates")
    defaults = Corruption()
    for name, value in asdict(defaults).items():
        g.add_argument(f"--{name.replace('_', '-')}", type=float, default=value)
    return ap.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    started = time.perf_counter()
    if args.profile:
        tracemalloc.start()
    if args.case_instances is None:
        # Scale with the corpus, but bounded at both ends.
        args.case_instances = max(22, min(250, round(args.records / 2000)))
    if args.case_instances < 20:
        print("error: --case-instances must be >= 20 (CONTRACT.md floor)", file=sys.stderr)
        return 2

    cfg = Corruption(**{f.name: getattr(args, f.name) for f in Corruption.__dataclass_fields__.values()})  # type: ignore[attr-defined]
    world = World(args.seed, cfg)
    em = Emitter(world, max_transcripts=args.max_transcripts)

    log = (lambda *a: None) if args.quiet else (lambda *a: print(*a, file=sys.stderr))

    log(f"[1/6] hard cases ({args.case_instances} instances each)...")
    cb = CaseBuilder(world, em, args.case_instances)
    cb.build_all()
    case_people = len(world.people)
    case_records = len(em.truth)
    log(f"      {case_people} people, {case_records} records")

    n_normal = args.people - case_people
    if n_normal <= 0:
        print(
            f"error: hard cases alone need {case_people} people, more than --people "
            f"{args.people}. Raise --people or lower --case-instances.",
            file=sys.stderr,
        )
        return 2
    budget = args.records - case_records
    singleton_target = int(round(args.people * args.singleton_pct / 100.0))
    if singleton_target > n_normal:
        singleton_target = n_normal

    log(f"[2/6] background population ({n_normal} people, {budget} record budget, "
        f"{singleton_target} singletons)...")
    extra = build_population(world, em, n_normal, budget, singleton_target)

    shortfall = args.records - len(em.truth)
    log(f"[3/6] POS top-up ({shortfall} records)...")
    if shortfall < 0:
        print(f"error: overshot the record budget by {-shortfall}", file=sys.stderr)
        return 2
    topup_pos(world, em, extra["people"], shortfall)

    log("[4/6] consent events...")
    build_background_consent(world, em)

    log(f"[5/6] writing to {args.out}...")
    counts = write_all(args.out, world, em, cb, args)
    manifest = build_manifest(world, em, cb, counts, args, extra)
    (args.out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )

    log("[6/6] verifying...")
    if args.no_verify:
        log("      skipped")
    else:
        problems = verify(world, em, cb, counts, manifest, args)
        if problems:
            print("VERIFICATION FAILED:", file=sys.stderr)
            for p in problems:
                print(f"  - {p}", file=sys.stderr)
            return 1
        log("      ok")

    if not args.quiet:
        print(json.dumps(
            {
                "seed": manifest["seed"],
                "people": manifest["person_count"],
                "records": manifest["identity_record_count"],
                "singleton_pct": manifest["singleton_person_pct"],
                "row_counts": manifest["row_counts"],
                "case_instance_counts": manifest["case_instance_counts"],
            },
            indent=2, sort_keys=True,
        ))
    elapsed = time.perf_counter() - started
    if args.profile:
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        print(f"[profile] {elapsed:.1f}s wall, {peak / 1e6:.0f} MB peak traced",
              file=sys.stderr)
    else:
        log(f"      done in {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
