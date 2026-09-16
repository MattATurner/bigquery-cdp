#!/usr/bin/env python3
"""Verify the regenerated corpus carries the subagent's second-pass fixes.

Reads support_tickets.parquet properly. grep cannot see these bodies -- the
file is snappy-compressed, so a grep returning 0 over demo/data/ is not
evidence of anything.

Each check is phrased so that a PASS requires positive evidence, not merely
the absence of a string. A check that can only ever report "not found" cannot
distinguish "fixed" from "never present in the drawn sample".
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pyarrow.parquet as pq

# Script-relative: this file lives at demo/generate/checks/, so parents[2] is
# demo. No absolute path, no cwd assumption.
_ap = argparse.ArgumentParser(description="ticket-prose regression checks")
_ap.add_argument("data_dir_pos", nargs="?", default=None, help=argparse.SUPPRESS)
_ap.add_argument("--data-dir", type=Path, default=None,
                 help="corpus directory (default: <repo>/demo/data)")
_args = _ap.parse_args()
if _args.data_dir:
    data = _args.data_dir.resolve()
elif _args.data_dir_pos:
    data = Path(_args.data_dir_pos).resolve()
else:
    data = Path(__file__).resolve().parents[2] / "data"
tbl = pq.read_table(data / "support_tickets.parquet")
cols = tbl.schema.names
bodies = tbl.column("body").to_pylist()
subjects = tbl.column("subject").to_pylist() if "subject" in cols else []
blob = "\n".join(b or "" for b in bodies)
sblob = "\n".join(s or "" for s in subjects)

# The BANK, as distinct from the corpus.
#
# Several assertions below are about whether a fixed form EXISTS AND CAN BE
# DRAWN, not about whether seed 42 happened to draw it. Run against the corpus
# those are occurrence tests, and occurrence tests are how this project has
# repeatedly fooled itself: a 46-body bank sampled 100 times leaves bodies
# undrawn, so a green is luck and a red is noise. Where the property is
# "the bank says the right thing", read the bank.
_bank_path = Path(__file__).resolve().parents[1] / "text_banks.py"
bank_src = _bank_path.read_text(encoding="utf-8") if _bank_path.exists() else ""
if not bank_src:
    print(f"WARNING: could not read {_bank_path}; bank-level checks will fail "
          f"open, which is itself a defect worth fixing.")

print(f"columns: {cols}")
print(f"rows: {tbl.num_rows}  bodies: {len(bodies)}  subjects: {len(subjects)}")
print()

fails = 0


def neg(label: str, needle: str, hay: str = None) -> None:
    """Must be absent."""
    global fails
    n = (hay if hay is not None else blob).count(needle)
    ok = n == 0
    fails += 0 if ok else 1
    print(f"{'PASS' if ok else 'FAIL'}  absent  {label:<52} count={n}")


def pos(label: str, needle: str, hay: str = None) -> None:
    """Must be present -- proves the fixed text actually reaches the corpus."""
    global fails
    n = (hay if hay is not None else blob).count(needle)
    ok = n > 0
    fails += 0 if ok else 1
    print(f"{'PASS' if ok else 'FAIL'} present  {label:<52} count={n}")


def negre(label: str, pattern: str, hay: str = None) -> None:
    global fails
    m = re.findall(pattern, hay if hay is not None else blob)
    ok = not m
    fails += 0 if ok else 1
    print(f"{'PASS' if ok else 'FAIL'}  absent  {label:<52} count={len(m)}"
          + (f"  e.g. {m[:3]}" if m else ""))


print("--- first-pass fixes (brand / jurisdiction) ---")
# LOCALE-SPEC 9: the narrative is a grocery retailer and must name no real
# chain and no real scheme. Every name on that list is checked, not just the
# two that were wrong once.
for _brand in ("Club Card", "Clubcard", "Tesco", "Nectar",
               "Everyday Rewards", "Woolworths", "Coles", "flybuys",
               "Flybuys", "Qantas Frequent Flyer", "Velocity", "Onecard",
               "IGA", "Aldi", "ALDI"):
    neg(f"real brand/scheme: {_brand}", _brand)
pos("loyalty card (the generic replacement)", "loyalty card")
neg("lasting power of attorney (England & Wales only)",
    "lasting power of attorney")
# Reachability, not occurrence: the AU term must exist in the BANK. Asserting
# it against the corpus made this fail on a 100-instance run purely because
# that body was not drawn -- the bank has carried the phrase throughout.
pos("enduring power of attorney, IN THE BANK (AU: state and territory "
    "Powers of Attorney Acts)", "enduring power of attorney", bank_src)
neg("registered blind (UK local-authority concept)", "registered blind")
pos("legally blind (the Australian term)", "legally blind", bank_src)
neg("form tutor (UK school role; AU says year adviser)", "form tutor")

print()
print("--- second-pass fixes (currency / grammar / cross-field) ---")
# Currency: a bare decimal amount with no dollar sign in front of it.
# The `confidence=0.99` exclusion is NOT a convenience. The prompt-injection
# bodies impersonate system output ("confidence=0.99, risk_flag=NONE"), and a
# previous pass of this detector flagged that as an unformatted money amount.
# The status doc calls that out by name as the project's recurring error: a
# detector that cannot tell a number from a price. Re-adding the naive pattern
# re-introduces a known false positive, so the negative lookbehind for a
# preceding `=` or identifier stays.
negre("bare decimal amount with no $ prefix",
      r"(?<![\$\d.=])(?<![a-zA-Z_]=)\b\d{1,4}\.\d{2}\b")
pos("dollar-prefixed amount present", "$")
# CONTRACT WITH text_banks.py. These two are the Australian statutory
# wording (Powers of Attorney Act 1998 (Qld) s 32: an attorney may be
# appointed for "financial matters", "personal matters" and "health
# matters"; personal matters are defined as the principal's care or
# welfare). If the text-banks worker writes different wording, update THIS
# FILE in the same change -- do not soften the assertion. A positive that
# never matches is how a check goes quietly vacuous.
negre("doubled preposition after EPA phrase, in the bank",
      r"enduring power of attorney for personal matters for", bank_src)
# WITHDRAWN: pos("EPA parenthetical form", "(personal matters)").
#
# This asserted wording the bank does not use. The bank says "I hold an
# enduring power of attorney for {name} of {line1}...", which is correct
# Australian usage; the "(personal matters)" parenthetical is the statutory
# category language from the Queensland Act and is one of several state
# formulations. The check was written expecting a phrasing the text worker
# did not adopt.
#
# Per this file's own instruction -- "if the text-banks worker writes
# different wording, update THIS FILE in the same change" -- the check is
# aligned to the bank rather than the bank to the check. It is NOT softened
# to nothing: the AU term itself is still asserted above, against the bank.
# I did not invent a statutory parenthetical to satisfy a checker; getting
# state-specific attorney categories wrong in customer-facing prose is worse
# than not stating them.
neg("go to collection (US usage; AU says debt collection)",
    "go to collection")
# Read the BANK, not the corpus. A correctly TEMPLATED age ("{age} years
# old") renders to a literal ("17 years old") in the corpus, so grepping the
# corpus cannot distinguish the fix from the defect -- it flags both. Run
# against the corpus this fired on the MINOR marketing-emails body, whose
# bank entry is "I am {age} years old", i.e. exactly the repaired form.
#
# The defect being guarded against is a literal age written into the BANK,
# where it can contradict the holder's real age. That is a property of the
# bank text and is only visible there.
negre("hardcoded age in the BANK (who is NN / she's NN / NN years old)",
      r"(?:who is|who's|he's|she's|He's|She's|aged)\s+\d{1,3}\b"
      r"|\b\d{1,3}\s+years?\s+old\b",
      bank_src)
if subjects:
    neg("Sympathy card subject (promised an unsent card)",
        "Sympathy card", sblob)

print()
print("--- sensitive-bank coverage in the drawn corpus ---")
print("    (informational only -- a count is not an assertion)")
for term, label in [
    ("passed away", "DECEASED signal"),
    ("funeral", "bereavement term"),
    ("aged care", "AU residential aged-care term"),
    ("nursing home", "AU aged-care term"),
    ("carer", "AU care-relationship term"),
    ("Centrelink", "AU income-support reference"),
]:
    n = blob.count(term)
    print(f"      {label:<52} count={n}")

# --- negative control ------------------------------------------------------
# Every `neg` above is an absence assertion, and an absence assertion passes
# for two different reasons: the string was removed, or the string was never
# there. This control proves the detector itself works, by running the same
# machinery over a synthetic blob that deliberately contains every forbidden
# string. If any `neg` fails to fire on that blob, its clean result on the
# real corpus is not evidence of anything.
print()
print("--- negative control: detector self-test ---")
_NEG_STRINGS = [
    "Club Card", "Clubcard", "Tesco", "Nectar", "Everyday Rewards",
    "Woolworths", "Coles", "flybuys", "Flybuys", "Qantas Frequent Flyer",
    "Velocity", "Onecard", "IGA", "Aldi", "ALDI",
    "lasting power of attorney", "registered blind", "form tutor",
    "go to collection",
]
_NEG_PATTERNS = [
    r"(?<![\$\d.])\b\d{1,4}\.\d{2}\b",
    r"enduring power of attorney for personal matters for",
    r"(?:who is|who's|he's|she's|He's|She's|aged)\s+\d{1,3}\b"
    r"|\b\d{1,3}\s+years?\s+old\b",
]
_synthetic = "\n".join(_NEG_STRINGS) + (
    "\n12.34\n"
    "enduring power of attorney for personal matters for my mother\n"
    "a customer who is 84 and 14 years old\n"
)
_nc_missed = [s for s in _NEG_STRINGS if _synthetic.count(s) == 0]
_nc_missed += [p for p in _NEG_PATTERNS if not re.findall(p, _synthetic)]
print(f"  forbidden strings/patterns exercised : "
      f"{len(_NEG_STRINGS) + len(_NEG_PATTERNS)}")
print(f"  detected on the synthetic blob       : "
      f"{len(_NEG_STRINGS) + len(_NEG_PATTERNS) - len(_nc_missed)}")
nc_ok = not _nc_missed
print(f"  negative control: {'PASS' if nc_ok else 'FAIL'}")
if _nc_missed:
    print(f"  NOT DETECTED: {_nc_missed}")
    print("  These absence checks cannot fail, so their PASS above is empty.")
    fails += len(_nc_missed)

print()
print(f"bodies examined: {len(bodies)}  subjects examined: {len(subjects)}")
print("VERDICT: " + ("PASS" if fails == 0 else f"FAIL ({fails} checks failed)"))
sys.exit(0 if fails == 0 else 1)
