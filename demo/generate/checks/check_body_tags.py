#!/usr/bin/env python3
"""Validate the declared constraints on the risk banks against the prose.

This checks the TAGS, not the filter. `_body_fits` trivially honours whatever
`gender` a body declares -- testing that would be near-tautological. The open
risk after the migration is a body whose declared tag disagrees with its own
text, which the filter cannot detect and which reintroduces the exact defect
the tags were added to remove.

THE REFERENT PROBLEM
--------------------
A first version of this script looked for gendered words and compared them to
the tag. It reported 10 failures, every one of them wrong: "my mum", "my dad",
"my nan", "my brother", "my daughter" are gendered THIRD PARTIES, not the
account holder. That is the identical blind spot to the defect this whole
exercise is about -- detecting the presence of a value without binding it to
a person.

The rule used here binds the referent from the shape of the body:

  * If the body contains ``{name}``, the holder is being written ABOUT by
    somebody else. Gendered words then attach to the holder, including
    kinship terms -- "my mother, {name}, died" asserts the holder is female.

  * If the body does NOT contain ``{name}``, the writer IS the holder. Any
    "my <kinship>" is therefore someone else, and third-person pronouns refer
    to that someone else, so neither says anything about the holder's gender.

Anything the rule cannot resolve is reported as ADJUDICATE rather than being
silently counted either way. This is a recall-oriented screen, not a gate.

WHAT THIS PROVES: every declared gender/age tag on a risk body is consistent
with the body's own prose, for the subset of bodies whose holder-scope
referent this rule can resolve.
WHAT IT DOES NOT PROVE: that the tags are complete, that `_body_fits` honours
them (near-tautological, and not tested here), or that any of these bodies
reaches the corpus. It reads text_banks.py, not demo/data. Use
check_holder_gender.py for the end-to-end claim.

Run from anywhere:
    python3 demo/generate/checks/check_body_tags.py [--verbose]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Script-relative: this file lives at demo/generate/checks/, so parents[1] is
# demo/generate. No absolute path, no cwd assumption.
_ap = argparse.ArgumentParser(description="risk-bank tag-vs-prose validator")
_ap.add_argument("--generate-dir", type=Path, default=None,
                 help="generator package directory (default: <repo>/demo/generate)")
_ap.add_argument("--verbose", action="store_true")
_args = _ap.parse_args()
GEN = (_args.generate_dir.resolve() if _args.generate_dir
       else Path(__file__).resolve().parents[1])
sys.path.insert(0, str(GEN))
import text_banks as tb  # noqa: E402

VERBOSE = _args.verbose

MALE_KIN = r"husband|father|dad|son|brother|grandfather|grandad|granddad|pop|widower"
FEMALE_KIN = r"wife|mother|mum|daughter|sister|grandmother|nan|nana|gran|widow"
MALE_PRON = r"he|him|his|himself"
FEMALE_PRON = r"she|her|hers|herself"

MALE = re.compile(rf"\b({MALE_KIN}|{MALE_PRON}|mr)\b", re.I)
FEMALE = re.compile(rf"\b({FEMALE_KIN}|{FEMALE_PRON}|mrs|ms|miss)\b", re.I)

# "my mum", "my late father", "my younger brother"
MY_KIN = re.compile(rf"\bmy\s+(?:\w+\s+){{0,2}}({MALE_KIN}|{FEMALE_KIN})\b", re.I)
PRONOUN = re.compile(rf"\b({MALE_PRON}|{FEMALE_PRON})\b", re.I)

# Age-implying language. Australian aged-care vocabulary: "aged care",
# "nursing home", "retirement village". "age pension" and "superannuation"
# are both Australian and both age-implying. The previous locale's term for
# residential aged care has been dropped from this pattern.
OLD = re.compile(
    r"\b(aged care|nursing home|retirement village|dementia|elderly|"
    r"pension|superannuation|retired|stroke|care home|nursing|"
    r"Seniors Card)\b",
    re.I,
)

BANKS = [
    ("DECEASED", tb.DECEASED_BODIES),
    ("MINOR", tb.MINOR_BODIES),
    ("VULNERABLE", tb.VULNERABLE_BODIES),
]


SIGNATURE = re.compile(r"\{name\}\s*$")
# "Mum said I should let you know" -- kinship as a proper noun, with no "my".
BARE_KIN = re.compile(
    rf"\b(Mum|Mummy|Dad|Daddy|Nan|Nana|Pop|Poppy|Mother|Father|Gran|Grandad)\b"
)


def holder_gendered_terms(text: str) -> tuple[list[str], list[str], str]:
    """Gendered terms that refer to the ACCOUNT HOLDER.

    Returns (male_terms, female_terms, mode).

    Deciding whether the holder is the writer or the subject is the whole
    problem, and two things make it harder than it looks:

      * A first-person body often ends with ``{name}`` as a SIGNATURE. The
        mere presence of ``{name}`` therefore does not mean the holder is
        being written about -- a first version of this check assumed it did
        and produced six false failures.
      * Kinship terms appear as bare proper nouns ("Mum said I should let you
        know"), so stripping only "my <kin>" leaves them behind.
    """
    occurrences = text.count("{name}")
    signature_only = occurrences > 0 and occurrences == len(
        SIGNATURE.findall(text)
    )
    holder_named = occurrences > 0 and not signature_only

    if holder_named:
        scope = text
        mode = "named"
    else:
        # The writer is the holder. Strip third-party references: kinship
        # phrases with and without "my", and every third-person pronoun,
        # which can only refer to that third party since the holder is "I".
        scope = MY_KIN.sub(" ", text)
        scope = BARE_KIN.sub(" ", scope)
        scope = PRONOUN.sub(" ", scope)
        mode = "writer"

    m = sorted({w.lower() for w in MALE.findall(scope)})
    f = sorted({w.lower() for w in FEMALE.findall(scope)})
    return m, f, mode


fails = adjudicate = 0

for bank_name, bank in BANKS:
    print(f"=== {bank_name} ({len(bank)} bodies) ===")
    clean = 0
    for i, entry in enumerate(bank):
        subject, body = entry[0], entry[1]
        text = f"{subject} {body}"
        declared = getattr(entry, "gender", None)
        min_age = getattr(entry, "min_age", None)
        max_age = getattr(entry, "max_age", None)

        m, f, mode = holder_gendered_terms(text)
        problems = []

        if m and f:
            problems.append(("ADJUDICATE", f"holder-scope has both: male={m} female={f}"))
        elif m and declared != "M":
            problems.append(("FAIL", f"holder male language {m} but gender={declared!r}"))
        elif f and declared != "F":
            problems.append(("FAIL", f"holder female language {f} but gender={declared!r}"))
        elif declared is not None and not m and not f:
            problems.append(
                ("ADJUDICATE", f"gender={declared!r} declared, no holder-scope evidence")
            )

        if OLD.search(text) and min_age is None:
            problems.append(
                ("ADJUDICATE",
                 f"age-implying language {sorted({w.lower() for w in OLD.findall(text)})}"
                 " but no min_age")
            )

        for level, msg in problems:
            if level == "FAIL":
                fails += 1
            else:
                adjudicate += 1
            print(f"  [{i:>2}] {level}  {msg}")
            print(f"        {subject[:70]}")

        if not problems:
            clean += 1
            if VERBOSE:
                tag = f"gender={declared!r}"
                if min_age or max_age:
                    tag += f" age=[{min_age},{max_age}]"
                ref = mode
                print(f"  [{i:>2}] ok    {ref:<6} {tag:<24} {subject[:52]}")
    print(f"  -- {clean} of {len(bank)} clean")
    print()

total_bodies = sum(len(b) for _n, b in BANKS)
print(f"bodies examined: {total_bodies}")
print(f"VERDICT: {fails} failures, {adjudicate} needing adjudication")

# --- negative control ------------------------------------------------------
# "0 failures" is only meaningful if this comparison CAN fail. Re-run it with
# every declared gender inverted (M <-> F) and count how many bodies are then
# reported as mismatched. That number must equal the number of bodies that
# carry unambiguous holder-scope gender evidence AND a declared gender --
# i.e. every body the check is actually able to judge.
#
# This is the same control that reported "38 / 38 detected" for
# check_holder_gender.py. A check that cannot fail proves nothing.
print()
print("--- negative control: invert every declared gender ---")

judgeable = 0
detected = 0
for _bank_name, _bank in BANKS:
    for _entry in _bank:
        _text = f"{_entry[0]} {_entry[1]}"
        _declared = getattr(_entry, "gender", None)
        if _declared not in ("M", "F"):
            continue
        _m, _f, _mode = holder_gendered_terms(_text)
        if bool(_m) == bool(_f):
            continue          # ambiguous or silent: not judgeable either way
        judgeable += 1
        _inverted = "F" if _declared == "M" else "M"
        if (_m and _inverted != "M") or (_f and _inverted != "F"):
            detected += 1

print(f"  bodies the check can judge : {judgeable}")
print(f"  detected when inverted     : {detected}")
nc_ok = judgeable > 0 and detected == judgeable
print(f"  negative control: {detected}/{judgeable} "
      f"-> {'PASS' if nc_ok else 'FAIL'}")
if not nc_ok:
    if judgeable == 0:
        print("  the check judged ZERO bodies. Its clean verdict above is "
              "vacuous -- it is not detecting gendered language at all.")
    else:
        print("  the comparison did not detect every inverted tag, so a clean "
              "verdict above is not evidence the tags are right.")

sys.exit(1 if (fails or not nc_ok) else 0)
