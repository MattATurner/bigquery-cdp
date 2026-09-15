#!/usr/bin/env python3
"""Post-regeneration checks on demo/data.

Verifies the things the CONFUSABLE_FORENAMES and PUNCTUATION_SUBURBS work was
supposed to change, plus a banned-token sweep that reads BOTH the name banks
and the emitted corpus. Bank-walking alone is blind to anything the emitter
composes after the draw; corpus-walking alone is blind to anything that simply
was not drawn at this seed. Neither is sufficient, so this does both and says
which is which.

WHAT THIS PROVES AND WHAT IT DOES NOT
-------------------------------------
Reachability assertions (load-bearing, cannot pass by luck):
  * check 1a -- no banned token is present in any name pool
  * check 7  -- every roster name the pools can COMPOSE is in FORBIDDEN_PAIRS

Occurrence observations (a hit is a real defect; a miss proves nothing):
  * check 1b -- no banned token appears in an emitted name field
  * check 7b -- no roster name appears in an emitted name field

The occurrence halves exist as an independent second opinion that reads the
files on disk rather than the objects in memory, so they would catch a defect
in the writer as well as one in the generator. They are reported with the
number of rows examined, and a clean result is explicitly labelled as not
evidence. See LOCALE-SPEC section 0 rule 3.

Usage (no absolute paths anywhere -- everything is resolved from __file__):

    python3 demo/generate/checks/check_corpus.py
    python3 demo/generate/checks/check_corpus.py --data-dir /path/to/data
"""
import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


def strip_acc(s: str) -> str:
    """Remove diacritics but keep case, so 'Nguyễn' -> 'Nguyen'."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )


def fold(s: str) -> str:
    return strip_acc(s).upper()


# --- path resolution: script-relative, never absolute ----------------------
# This file lives at demo/generate/checks/, so:
#   parents[0] = demo/generate/checks
#   parents[1] = demo/generate
#   parents[2] = demo
HERE = Path(__file__).resolve().parent
GENERATE = HERE.parent
ROOT = GENERATE.parent

_ap = argparse.ArgumentParser(description=__doc__)
_ap.add_argument("--data-dir", type=Path, default=None,
                 help="corpus directory (default: <repo>/demo/data)")
_ap.add_argument("--generate-dir", type=Path, default=None,
                 help="generator package directory (default: <repo>/demo/generate)")
_args = _ap.parse_args()

if _args.generate_dir:
    GENERATE = _args.generate_dir.resolve()
DATA = (_args.data_dir.resolve() if _args.data_dir else ROOT / "data")
csv.field_size_limit(10_000_000)

# Tokens that must never appear as a component of a person's name.
#
# Three kinds, and the reason differs for each:
#
#   1. Aboriginal and Torres Strait Islander nation, language-group and
#      sacred/Dreaming terms. These are peoples and cosmology, not personal
#      names. Attaching one to a synthetic shopper with an address and a
#      support ticket is the failure class this whole guard exists for, and
#      it is the one the pools are most likely to reach by accident because
#      the words look like plausible surnames.
#   2. Ordinary-language and place tokens that read as a data-entry bug.
#   3. Surnames so uniquely associated with one public figure that the pair
#      rule in NOTABLE_FULL_NAMES is not enough -- the surname alone is the
#      identification. Kept deliberately short: an ordinary surname belongs
#      in the roster as a PAIR, not here. "Abbott", "Howard", "Hawke" and
#      "Smith" are ordinary surnames and are NOT in this list.
#
# NOTE ON A DELETION. The previous locale's list banned "Mohammed",
# "Muhammad", "Aisha", "Imran", "Yusuf" and similar, because those forenames
# were landing on surnames from the dominant Anglo group. That was a
# cross-group drawing defect, not a property of the names. LOCALE-SPEC
# section 1.1 makes ARABIC a first-class group with its own
# surname pool, so banning its forenames outright would now be both wrong and
# discriminatory. They are deliberately absent. If cross-group pairing
# misbehaves, fix CROSS_GROUP_RATE and the group pools -- not this list.
BANNED = [
    # -- nations / language groups -------------------------------------
    "Wiradjuri", "Noongar", "Nyoongar", "Yolngu", "Arrernte", "Gadigal",
    "Bundjalung", "Kaurna", "Palawa", "Anangu", "Gunditjmara",
    "Ngarrindjeri", "Wurundjeri", "Boonwurrung", "Pitjantjatjara",
    "Yorta Yorta", "Larrakia", "Kamilaroi", "Gamilaraay", "Whadjuk",
    # -- sacred / Dreaming ----------------------------------------------
    "Bunjil", "Baiame", "Daramulum", "Wandjina", "Tjukurpa", "Jukurrpa",
    "Dreaming", "Dreamtime",
    # -- place tokens that read as a data-entry bug ----------------------
    "Uluru", "Kata Tjuta", "Kakadu", "Kosciuszko", "Woomera",
    # -- surnames uniquely identifying one public figure -----------------
    "Albanese", "Whitlam", "Gillard", "Turnbull", "Bradman",
]

NAME_FIELDS = {
    "crm_customers.csv": ["full_name"],
    "ecom_accounts.csv": ["first_name", "last_name"],
    "loyalty_members.csv": ["member_name"],
    "pos_transactions.csv": ["surname"],
}
ADDR_FIELDS = {
    "crm_customers.csv": ["address_line1", "city"],
    "loyalty_members.csv": ["address_line1", "city"],
}

fails: list[str] = []
warns: list[str] = []


def rows(name):
    with (DATA / name).open(newline="", encoding="utf-8") as fh:
        yield from csv.DictReader(fh)


# ---- truth index ---------------------------------------------------------
case_of: dict[str, str] = {}
person_of: dict[str, str] = {}
for r in rows("truth/person_truth.csv"):
    case_of[r["record_id"]] = r["case_type"]
    person_of[r["record_id"]] = r["true_person_id"]
print(f"truth rows: {len(case_of)}")
print(f"case types: {len(set(case_of.values()))}\n")

# ---- 1a. banned tokens in the POOLS (reachability -- load-bearing) -------
# This is the half that cannot pass by luck. A single token either is or is
# not in a pool; if it is in a pool it can be drawn, and that is the property
# we care about. Occurrence at seed 42 is not.
print("== 1a. banned tokens in the name pools (reachability) ==")
sys.path.insert(0, str(GENERATE))
pool_tokens: set[str] = set()
pool_names_read = 0
try:
    import banks as _banks  # noqa: E402

    _pools = []
    for _d in (_banks.MALE_FORENAMES_BY_GROUP,
               _banks.FEMALE_FORENAMES_BY_GROUP,
               _banks.SURNAMES_BY_GROUP):
        for _g, _p in sorted(_d.items()):
            _pools.append(_p)
    for _p in _pools:
        for _n, _w in _p:
            pool_names_read += 1
            pool_tokens.add(fold(_n))
            # A pool entry may be multi-word ("Yorta Yorta", "Te Kanawa").
            for _tok in _n.split():
                pool_tokens.add(fold(_tok))
    # Everything the substitution layer can additionally write.
    for _src in (getattr(_banks, "DIMINUTIVES", {}),
                 getattr(_banks, "SURNAME_VARIANTS", {})):
        for _k in sorted(_src):
            for _v in _src[_k]:
                pool_tokens.add(fold(_v))
                for _tok in _v.split():
                    pool_tokens.add(fold(_tok))
except Exception as exc:  # pragma: no cover - import guard
    fails.append(f"could not import banks.py to run the reachability half "
                 f"of check 1: {exc}")
    print(f"  FAIL could not import banks.py: {exc}")

if pool_tokens:
    pool_bad = sorted(b for b in BANNED if fold(b) in pool_tokens)
    print(f"  pool entries read : {pool_names_read}")
    print(f"  distinct written tokens (incl. substitutions): {len(pool_tokens)}")
    print(f"  banned tokens checked : {len(BANNED)}")
    if pool_bad:
        for b in pool_bad:
            print(f"  FAIL {b}: present in a name pool -- REACHABLE")
        fails.append(f"{len(pool_bad)} banned tokens are reachable from the "
                     f"name pools: {', '.join(pool_bad)}")
    else:
        print(f"  ok -- none of the {len(BANNED)} banned tokens is reachable")

    # Negative control. A zero above is only believable if the detector can
    # produce a non-zero. Inject a token that IS in a pool and confirm it is
    # caught. Deterministic: the sentinel is the alphabetically first token.
    _sentinel = sorted(pool_tokens)[0] if pool_tokens else ""
    _nc_hits = [b for b in [_sentinel] if fold(b) in pool_tokens]
    print(f"  negative control  : sentinel {_sentinel!r} detected="
          f"{bool(_nc_hits)} (must be True)")
    if not _nc_hits:
        fails.append("check 1a negative control failed -- the pool detector "
                     "cannot detect a token known to be in a pool, so its "
                     "clean result means nothing")

# ---- 1b. banned tokens in the emitted corpus (occurrence -- second opinion)
# Word-boundary match, accent-sensitive: a short token must not fire inside a
# longer word. A HIT here is a real defect. A MISS proves nothing on its own
# -- it may merely not have been drawn at this seed -- which is why 1a exists.
banned_re = {b: re.compile(rf"(?<!\w){re.escape(b)}(?!\w)") for b in BANNED}
hits: dict[str, list[str]] = defaultdict(list)
rows_scanned_1b = 0
for fname, fields in NAME_FIELDS.items():
    for r in rows(fname):
        rows_scanned_1b += 1
        blob = " ".join(r.get(f, "") for f in fields)
        for b, rx in banned_re.items():
            if rx.search(blob):
                if len(hits[b]) < 4:
                    hits[b].append(f"{r['record_id']}: {blob}")

print("\n== 1b. banned tokens in emitted names (occurrence) ==")
print(f"  rows examined: {rows_scanned_1b}")
if hits:
    for b, ex in sorted(hits.items()):
        print(f"  FAIL {b}: {len(ex)}+ e.g. {ex[:2]}")
    fails.append(f"{len(hits)} banned tokens present in emitted names")
else:
    print(f"  0 of {len(BANNED)} banned tokens occur in {rows_scanned_1b} rows")
    print("  NOT EVIDENCE on its own -- check 1a is the load-bearing half")

# ---- 2. SIBLING_TRAP forename spread -------------------------------------
print("\n== 2. SIBLING_TRAP name spread ==")
sib_fore: Counter = Counter()
sib_diacritic = 0
sib_total = 0


def forenames(fname, r):
    if fname == "crm_customers.csv":
        return r["full_name"].split()[:1]
    if fname == "ecom_accounts.csv":
        return [r["first_name"]]
    if fname == "loyalty_members.csv":
        return r["member_name"].split()[:1]
    return []


for fname in ("crm_customers.csv", "ecom_accounts.csv", "loyalty_members.csv"):
    for r in rows(fname):
        if case_of.get(r["record_id"]) != "SIBLING_TRAP":
            continue
        for fn in forenames(fname, r):
            if not fn:
                continue
            sib_total += 1
            sib_fore[fn] += 1
            if any(unicodedata.combining(c) for c in unicodedata.normalize("NFKD", fn)):
                sib_diacritic += 1

# The property this section exists to protect is that SIBLING_TRAP draws
# across MULTIPLE name groups -- the pre-fix symptom was the pool collapsing
# to one. Under the previous locale, "carries a diacritic" was a serviceable
# proxy for that, because the largest non-Anglo group carried macrons.
#
# It is a WORTHLESS proxy under this one. The Australian general pools are
# deliberately plain ASCII in every group (Vietnamese names appear unaccented,
# which is how they overwhelmingly appear in Australian systems); accented
# forms live only in DIACRITIC_FORENAMES/SURNAMES, which only
# DIACRITIC_VARIANT draws from. Zero accented SIBLING_TRAP forenames is the
# expected, correct state and says nothing whatever about group collapse.
#
# So measure the group spread directly. This is strictly stronger than the
# proxy it replaces and it is locale-independent.
try:
    import banks as _b2  # noqa: E402
    import generate as _gen  # noqa: E402
    _FORENAME_GROUP = _b2.FORENAME_GROUP
    _CONFUSABLES = _gen.CONFUSABLE_FORENAMES
except Exception as _exc:  # pragma: no cover
    _FORENAME_GROUP = {}
    _CONFUSABLES = []
    fails.append(f"could not import banks/generate for the SIBLING_TRAP "
                 f"group-spread check: {_exc}")
    print(f"  FAIL could not import for group-spread check: {_exc}")

groups: Counter = Counter()
for _fn in sib_fore:
    _g = _FORENAME_GROUP.get(_fn)
    if _g:
        groups[_g] += sib_fore[_fn]

print(f"  SIBLING_TRAP forename instances : {sib_total}")
print(f"  distinct forenames              : {len(sib_fore)}")
print(f"  carrying a diacritic            : {sib_diacritic} "
      f"(expected 0 -- general pools are ASCII; not a signal)")
print(f"  distinct name groups            : {len(groups)}  {dict(groups)}")
print(f"  top 10: {sib_fore.most_common(10)}")

# Sample-size honesty. SIBLING_TRAP walks CONFUSABLE_FORENAMES with a fixed
# stride (`[i % len]`), and the Anglo section is first and long, so a run with
# fewer instances than the index of the first non-Anglo pair CANNOT reach one
# however healthy the pool is. Gating regardless would fail every small run
# and teach the reader to ignore this check -- which is how a real collapse
# would get through. Below that threshold it reports and abstains.
_first_non_anglo = next(
    (i for i, _pair in enumerate(_CONFUSABLES)
     if _FORENAME_GROUP.get(_pair[0]) not in (None, "ANGLO")),
    None,
)
try:
    _instances = int(
        json.loads((DATA / "manifest.json").read_text())
        .get("case_instance_counts", {})
        .get("SIBLING_TRAP", 0)
    )
except Exception:
    _instances = 0
if _first_non_anglo is None:
    fails.append("CONFUSABLE_FORENAMES contains no non-Anglo pair at all -- "
                 "the pool really has collapsed to one group")
    print("  FAIL no non-Anglo pair exists in CONFUSABLE_FORENAMES")
elif _instances <= _first_non_anglo:
    print(f"  SKIP group-spread gate: {_instances} instances cannot reach the "
          f"first non-Anglo pair at index {_first_non_anglo}. "
          f"Re-run with --case-instances > {_first_non_anglo} to exercise it. "
          f"(At the shipped 100 this spans 6 groups.)")
elif len(groups) < 2:
    fails.append(f"SIBLING_TRAP drew from only {len(groups)} name group(s) "
                 f"across {_instances} instances -- the pool has collapsed")
    print(f"  FAIL only {len(groups)} group(s)")
else:
    print(f"  ok -- {len(groups)} groups represented")

# ---- 3. curated punctuation suburbs in DIACRITIC_VARIANT addresses -------
# Australia has very few diacritic place names, so per LOCALE-SPEC 10.1 the
# address slice of this case runs on PUNCTUATION and SPACING drift instead of
# accents: apostrophe present/absent ("O'Connor" / "OConnor" / "O Connor"),
# hyphen present/absent, and "St" / "Saint". It exercises the address
# normalisation path, which is the point of the slice -- it does NOT test
# accent folding. Say so wherever this case is described.
#
# Checking one named suburb is too brittle: with ~17 address-flavour draws
# spread over ~20 pairs, any single suburb appears about once and its written
# form is a coin flip. Pool coverage and the overall canonical/drifted split
# are what the case actually depends on.
#
# Pool coverage is also the defect-4 regression test. The old address slice
# fired only when `i % 6 == 0`, so `subs[i % 20]` could only reach even
# indices and half the curated pool was unreachable. LOCALE-SPEC 2.4 requires
# the new slice to index on its own DENSE counter. If coverage collapses to
# roughly half the pool, that bug is back.
print("\n== 3. curated punctuation suburbs in DIACRITIC_VARIANT addresses ==")
sys.path.insert(0, str(GENERATE))
try:
    from banks_places import PUNCTUATION_SUBURBS  # noqa: E402
except Exception as exc:  # pragma: no cover - import guard
    fails.append(f"could not import PUNCTUATION_SUBURBS from banks_places.py: "
                 f"{exc}")
    PUNCTUATION_SUBURBS = []

# Entries are (canonical, drifted) or (canonical, drifted, drifted2, ...).
_pairs = [(e[0], tuple(e[1:])) for e in PUNCTUATION_SUBURBS if len(e) >= 2]

canon_hits: Counter = Counter()
drift_hits: Counter = Counter()
mv_addr = 0
for fname, fields in ADDR_FIELDS.items():
    for r in rows(fname):

        if case_of.get(r["record_id"]) != "DIACRITIC_VARIANT":
            continue
        mv_addr += 1
        blob = r.get("address_line1", "") + " " + r.get("city", "")
        for canon, drifts in _pairs:
            if canon in blob:
                canon_hits[canon] += 1
            elif any(d in blob for d in drifts):
                drift_hits[canon] += 1

covered = {c for c, _d in _pairs if canon_hits[c] or drift_hits[c]}
print(f"  DIACRITIC_VARIANT address rows : {mv_addr}")
print(f"  curated pairs appearing        : {len(covered)} of {len(_pairs)}")
print(f"  canonical (punctuated) hits    : {sum(canon_hits.values())}")
print(f"  drifted hits                   : {sum(drift_hits.values())}")
if not _pairs:
    print("  FAIL PUNCTUATION_SUBURBS is empty or unimportable")
elif not canon_hits or not drift_hits:
    fails.append("DIACRITIC_VARIANT addresses carry only one written form, "
                 "so the address flavour of the case tests nothing")
    print("  FAIL only one written form across the whole case")
elif len(covered) * 2 < len(_pairs):
    warns.append(f"only {len(covered)} of {len(_pairs)} curated punctuation "
                 f"suburbs are reachable -- this is the defect-4 shape; check "
                 f"the slice indexes on a dense counter, not on i")
    print("  WARN less than half the curated pool is reachable "
          "(defect-4 shape -- check the index stride)")
else:
    print("  ok -- both forms present and most of the curated pool is used")
missing = [c for c, _d in _pairs if c not in covered]
if missing:
    print(f"  not drawn this run: {missing}")



# ---- 4. manifest sanity --------------------------------------------------
print("\n== 4. manifest ==")
man = json.loads((DATA / "manifest.json").read_text())
print(f"  seed        : {man.get('seed')}")
print(f"  people      : {man.get('people')}")
for k in ("row_counts", "case_instance_counts", "case_type_person_counts"):
    v = man.get(k)
    if isinstance(v, dict):
        print(f"  {k}: {sum(v.values())} across {len(v)} keys")
amb = man.get("ambiguous_name_collisions")
print(f"  ambiguous_name_collisions: {amb}")
if isinstance(amb, int) and amb > 1:
    warns.append(f"ambiguous_name_collisions = {amb} (was 1 after the "
                 f"household fix)")

# ---- 5. record_id uniqueness ---------------------------------------------
# Scoped to the files that MINT record ids. consent_events.csv is
# event-per-row and legitimately repeats a record_id many times, so including
# it reports ~79k "duplicates" and hides any real collision.
print("\n== 5. record_id uniqueness (record-minting files only) ==")
seen: Counter = Counter()
for fname in list(NAME_FIELDS) + ["call_transcripts_manifest.csv"]:
    for r in rows(fname):
        rid = r.get("record_id")
        if rid:
            seen[rid] += 1
dupe = [k for k, n in seen.items() if n > 1]
print(f"  ids seen: {len(seen)}  duplicated: {len(dupe)}")
if dupe:
    print(f"  FAIL e.g. {dupe[:5]}")
    fails.append(f"{len(dupe)} duplicated record_ids")
else:
    print("  ok -- all unique")

# ---- 6. reduplicated names -----------------------------------------------
# "Hōhepa Hōhepa" / "Lin Lin". Real in principle, but on screen they read as
# a data-entry bug in a demo whose whole subject is data quality.
print("\n== 6. reduplicated forename/surname ==")
redup: Counter = Counter()
for fname in ("crm_customers.csv", "loyalty_members.csv"):
    field = "full_name" if fname == "crm_customers.csv" else "member_name"
    for r in rows(fname):
        parts = r[field].split()
        if len(parts) >= 2 and fold(parts[-1]) == fold(parts[-2]):
            redup[r[field]] += 1
for r in rows("ecom_accounts.csv"):
    if r["first_name"] and fold(r["first_name"]) == fold(r["last_name"]):
        redup[f"{r['first_name']} {r['last_name']}"] += 1
print(f"  reduplicated names: {sum(redup.values())}")
if redup:
    print(f"  e.g. {list(redup)[:10]}")
    fails.append(f"{sum(redup.values())} reduplicated names still emitted")
else:
    print("  ok -- none")

# ---- 7. notable full names -----------------------------------------------
# The roster is IMPORTED, never copied. This check previously kept its own
# 22-name list, which drifted behind the generator's as soon as the roster
# grew. A drifted safety list is worse than one list: it reports clean
# against names the generator no longer agrees are the right ones, and the
# green result is read as though it covered the real roster.
#
# 7a is REACHABILITY and is the load-bearing half. 7b is occurrence and is a
# second opinion only. LOCALE-SPEC section 0 rule 3, and defect 6 in the
# build-status doc: the old version of this check reported "none of the 22
# notable names occur", which was true, and useless. All 22 were reachable;
# none happened to be drawn at seed 42.
print("\n== 7a. notable full names -- REACHABILITY (load-bearing) ==")
sys.path.insert(0, str(GENERATE))
try:
    from generate import NOTABLE_FULL_NAMES as NOTABLE  # type: ignore
    print(f"  roster imported from generate.py: {len(NOTABLE)} entries")
except Exception as exc:  # pragma: no cover - import guard
    fails.append(f"could not import NOTABLE_FULL_NAMES from generate.py: {exc}")
    NOTABLE = []

try:
    from generate import _forbidden_pair as _fp  # type: ignore
except Exception as exc:  # pragma: no cover - import guard
    fails.append(f"could not import _forbidden_pair from generate.py: {exc}")
    _fp = None

# Malformed-entry rule (LOCALE-SPEC 8.3): an entry that does not split into
# exactly two parts on the first space is a HARD failure, not a warning. A
# typo in the roster must not silently fail to block anything.
malformed = [n for n in NOTABLE if len(n.split(" ")) != 2]
if malformed:
    fails.append(f"{len(malformed)} malformed roster entries (must split into "
                 f"exactly two parts on the first space): {malformed[:5]}")
    print(f"  FAIL {len(malformed)} malformed entries: {malformed[:5]}")
else:
    print(f"  ok -- all {len(NOTABLE)} entries split into exactly two parts")

# Written forename/surname forms the pools can compose, INCLUDING the
# substitution layer. `pool_tokens` from check 1a is token-level; here we need
# whole-name forms, so rebuild them.
w_fore: set[str] = set()
w_sur: set[str] = set()
if pool_tokens:  # banks imported successfully in check 1a
    for _d in (_banks.MALE_FORENAMES_BY_GROUP, _banks.FEMALE_FORENAMES_BY_GROUP):
        for _g in sorted(_d):
            for _n, _w in _d[_g]:
                w_fore.add(fold(_n))
                for _v in getattr(_banks, "DIMINUTIVES", {}).get(_n, []):
                    w_fore.add(fold(_v))
    for _g in sorted(_banks.SURNAMES_BY_GROUP):
        for _n, _w in _banks.SURNAMES_BY_GROUP[_g]:
            w_sur.add(fold(_n))
            for _v in getattr(_banks, "SURNAME_VARIANTS", {}).get(_n, []):
                w_sur.add(fold(_v))

reachable, unreachable, unblocked = [], [], []
for n in NOTABLE:
    if len(n.split(" ")) != 2:
        continue
    fn, sn = n.split(" ", 1)
    if fold(fn) in w_fore and fold(sn) in w_sur:
        reachable.append(n)
        # THE assertion. A reachable roster name that the guard does not
        # block is a live hole, whether or not it was drawn at this seed.
        if _fp is not None and not _fp(fn, sn):
            unblocked.append(n)
    else:
        unreachable.append(n)

print(f"  forename written forms : {len(w_fore)}")
print(f"  surname  written forms : {len(w_sur)}")
print(f"  roster entries REACHABLE from the pools : {len(reachable)}")
print(f"  roster entries not reachable today      : {len(unreachable)}")
if unblocked:
    for n in sorted(unblocked):
        print(f"  FAIL {n}: reachable but NOT blocked by _forbidden_pair")
    fails.append(f"{len(unblocked)} roster names are composable from the pools "
                 f"but are not blocked: {', '.join(sorted(unblocked)[:5])}")
elif reachable:
    print(f"  ok -- all {len(reachable)} reachable roster names are blocked")
else:
    warns.append("no roster name is reachable from the pools -- either the "
                 "roster or the pools are not the ones this build uses, and "
                 "a clean result here would mean nothing")
    print("  WARN nothing reachable; this check examined 0 live pairs")

# Negative control: the detector must be able to report a hole. Compose a
# name that IS reachable and is NOT on the roster, and confirm the same
# predicate classifies it as unblocked.
if w_fore and w_sur and _fp is not None:
    _nc_fn, _nc_sn = sorted(w_fore)[0], sorted(w_sur)[0]
    _nc_detects = not _fp(_nc_fn, _nc_sn)
    print(f"  negative control : reachable non-roster pair "
          f"{_nc_fn} {_nc_sn} reported unblocked={_nc_detects} (must be True)")
    if not _nc_detects:
        warns.append("check 7a negative control did not fire -- the sentinel "
                     "pair is itself blocked; pick another sentinel before "
                     "believing the clean result")

print("\n== 7b. notable full names -- occurrence (second opinion) ==")
notable_re = {
    n: re.compile(rf"(?<!\w){re.escape(fold(n))}(?!\w)") for n in NOTABLE
}
nhits: dict[str, int] = Counter()
rows_scanned_7b = 0
for fname, fields in NAME_FIELDS.items():
    for r in rows(fname):
        rows_scanned_7b += 1
        blob = fold(" ".join(r.get(f, "") for f in fields))
        for n, rx in notable_re.items():
            if rx.search(blob):
                nhits[n] += 1
print(f"  rows examined: {rows_scanned_7b}")
if nhits:
    for n, c in sorted(nhits.items(), key=lambda kv: -kv[1]):
        print(f"  {n}: {c}")
    fails.append(f"{len(nhits)} blocked names present in the corpus "
                 f"({', '.join(sorted(nhits))}) -- the generator's guard "
                 f"did not hold")
elif NOTABLE:
    print(f"  0 of {len(NOTABLE)} roster names occur in {rows_scanned_7b} rows")
    print("  NOT EVIDENCE on its own -- 7a is the load-bearing half")


# ---- 8. Australian postcode ranges, and the NT leading-zero trap ---------
#
# LOCALE-SPEC 2.3. This was the one locale rule with no test at all.
#
# The rule is NOT "any four digits". Australian postcodes carry the state in
# the leading digit(s), and the loyalty source deliberately drifts NT `08xx`
# into a three-digit form because postcodes are stored as integers and the
# leading zero drops natively. `0812` -> `812` is a TRAP THE PIPELINE MUST
# HANDLE, not a defect, so this check must accept it -- a validator that
# rejected `812` would be asserting the trap away.
#
# Darwin is the only producer of that drift. If it stops firing, the signal
# has silently left the corpus, so a zero count warns rather than passing.
print("\n== 8. postcode state ranges + NT leading-zero drift ==")

_STATE_RANGES = [  # (state, low, high) -- inclusive, on the integer value
    ("NT", 800, 899), ("NSW", 1000, 2599), ("ACT", 2600, 2618),
    ("NSW", 2619, 2899), ("ACT", 2900, 2920), ("NSW", 2921, 2999),
    ("VIC", 3000, 3999), ("QLD", 4000, 4999), ("SA", 5000, 5799),
    ("WA", 6000, 6797), ("TAS", 7000, 7799),
]


def _postcode_state(p: str):
    """State for a postcode, tolerating the stripped leading zero."""
    s = (p or "").strip()
    if not s.isdigit() or not (3 <= len(s) <= 4):
        return None
    v = int(s)
    for st, lo, hi in _STATE_RANGES:
        if lo <= v <= hi:
            return st
    return None


# IMPORTANT: this canNOT be a postcode-validity gate, and an earlier draft of
# this check wrongly made it one -- flagging 1,099 rows as broken when every
# one was working as designed.
#
# `drift_postcode` deliberately emits non-postcodes: `area_only` ("20"),
# `padded` (" 2042 "), `state_prefix` ("NSW 2042"), `zero_strip` ("812") and
# `typo`, which changes WHICH postcode it is and so legitimately produces a
# well-formed four-digit value that is simply wrong. Asserting validity would
# assert the corruption away -- the corruption is the point of the source.
#
# What can honestly be checked from the corpus is that every value matches a
# RECOGNISED shape. An unrecognised shape means a drift mode changed, or
# something is emitting garbage that no documented mode explains.
_shapes: Counter = Counter()
_pc_unknown, _pc_total = [], 0
_ST = ("NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT")
for fname in ("crm_customers.csv", "ecom_accounts.csv", "loyalty_members.csv"):
    for raw in rows(fname):
        p0 = raw.get("postcode") or ""
        if not p0.strip():
            continue
        _pc_total += 1
        p = p0.strip()
        if p != p0:
            _shapes["padded (whitespace)"] += 1
        head = p.split()[0] if " " in p else ""
        if head in _ST and p.split()[-1].isdigit():
            _shapes["state_prefix (NSW 2042)"] += 1
        elif p.isdigit() and len(p) == 4:
            _shapes["4-digit in state range" if _postcode_state(p)
                    else "4-digit OUT of range (typo mode -- expected)"] += 1
        elif p.isdigit() and len(p) == 3 and 800 <= int(p) <= 899:
            _shapes["zero_strip NT (812 <- 0812)"] += 1
        elif p.isdigit() and len(p) == 2:
            _shapes["area_only (20)"] += 1
        elif p.isdigit() and len(p) in (3, 5, 6):
            _shapes["digit-count typo"] += 1
        else:
            _shapes["UNRECOGNISED"] += 1
            _pc_unknown.append(f"{fname}:{p0!r}")

_nt_drift = _shapes.get("zero_strip NT (812 <- 0812)", 0)
print(f"  postcodes examined        : {_pc_total}")
for _s, _c in _shapes.most_common():
    print(f"    {_s:44s} {_c}")
print(f"  NT leading-zero drift hits: {_nt_drift}  (e.g. 0812 -> 812)")

# Negative control: the validator must actually reject something.
_ctl_bad = ["0000", "9999", "12345", "abcd", "8000"]
_ctl_good = ["2042", "3000", "4000", "5000", "6000", "7000", "0812", "812", "2600"]
_nc_rej = sum(1 for c in _ctl_bad if _postcode_state(c) is None)
_nc_acc = sum(1 for c in _ctl_good if _postcode_state(c) is not None)
print(f"  negative control          : rejects {_nc_rej}/{len(_ctl_bad)} bad, "
      f"accepts {_nc_acc}/{len(_ctl_good)} good (both must be full marks)")
if _nc_rej != len(_ctl_bad) or _nc_acc != len(_ctl_good):
    fails.append("postcode validator self-test failed -- it cannot "
                 "distinguish valid Australian postcodes from invalid ones, "
                 "so its verdict on the corpus means nothing")

if _pc_unknown:
    fails.append(f"{len(_pc_unknown)} postcode(s) match no documented shape, "
                 f"e.g. {', '.join(sorted(set(_pc_unknown))[:5])} -- either a "
                 f"drift mode changed or something is emitting garbage")
    print(f"  FAIL e.g. {sorted(set(_pc_unknown))[:5]}")
elif _pc_total:
    print("  ok -- every postcode matches a documented shape")

if _pc_total and _nt_drift == 0:
    warns.append("NT leading-zero drift never fired: no 3-digit 8xx postcode "
                 "in the corpus. Darwin is its only producer -- if Darwin "
                 "left the city list, LOCALE-SPEC 2.3's trap is gone and the "
                 "loyalty source lost a deliberate signal.")
    print("  WARN NT drift never fired")


print("\n" + "=" * 60)
for f in fails:
    print(f"FAIL: {f}")
for w in warns:
    print(f"WARN: {w}")
if not fails and not warns:
    print("all checks clean")
sys.exit(1 if fails else 0)
