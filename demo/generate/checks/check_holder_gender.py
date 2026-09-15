#!/usr/bin/env python3
"""End-to-end check: does the gender asserted in a risk ticket match the holder?

This is the check the whole `Body` migration exists to satisfy, and it is
deliberately independent of the mechanism that implements it. `_body_fits`
honouring a `gender` attribute is near-tautological; what matters is whether
the text that reached the corpus agrees with the person it was written about.

Holder gender is derived from the FORENAME via the generator's own pools,
not from the CRM title. An earlier version used the title and checked exactly
one ticket out of 45, because titles survive on very few records -- a clean
result that measured almost nothing.

Only DECEASED and VULNERABLE bodies are checked, and only where the holder is
the SUBJECT of the body. MINOR bodies are first-person from the minor and
their gendered language refers to third parties (a mum, a dad), so they carry
no holder-gender claim to verify.

WHAT THIS PROVES: for every RISK_FLAG DECEASED/VULNERABLE ticket where the
holder's gender is resolvable from their forename AND the body carries an
unambiguous gender signal, the two agree.
WHAT IT DOES NOT PROVE: anything about MINOR tickets (deliberately skipped --
they are first-person from the minor and their gendered language refers to
third parties), anything about the bodies it could not resolve, and nothing
at all if `checked` is small. The count of assertions actually made is
printed alongside the verdict for exactly that reason.

Run from anywhere:
    python3 demo/generate/checks/check_holder_gender.py [--data-dir DIR]
    python3 demo/generate/checks/check_holder_gender.py --negative-control
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

# Script-relative: this file lives at demo/generate/checks/.
HERE = Path(__file__).resolve().parent
GENERATE = HERE.parent
DEMO = GENERATE.parent

_ap = argparse.ArgumentParser(description="end-to-end holder-gender check")
_ap.add_argument("data_dir_pos", nargs="?", default=None,
                 help=argparse.SUPPRESS)
_ap.add_argument("--data-dir", type=Path, default=None,
                 help="corpus directory (default: <repo>/demo/data)")
_ap.add_argument("--generate-dir", type=Path, default=None,
                 help="generator package directory (default: <repo>/demo/generate)")
_ap.add_argument("--negative-control", action="store_true",
                 help="invert the gender lookup and assert every assertion "
                      "flips to a mismatch; a check that cannot fail proves "
                      "nothing")
_args = _ap.parse_args()

if _args.generate_dir:
    GENERATE = _args.generate_dir.resolve()
sys.path.insert(0, str(GENERATE))
import banks  # noqa: E402

import pyarrow.parquet as pq  # noqa: E402

if _args.data_dir:
    data = _args.data_dir.resolve()
elif _args.data_dir_pos:
    data = Path(_args.data_dir_pos).resolve()
else:
    data = DEMO / "data"

INVERT = _args.negative_control

# The flattened banks are lists of (name, weight), not bare strings.
MALE_F = {n.lower() for n, _w in banks.MALE_FORENAMES}
FEMALE_F = {n.lower() for n, _w in banks.FEMALE_FORENAMES}
AMBIG = MALE_F & FEMALE_F

MALE = re.compile(
    r"\b(he|him|his|husband|father|dad|son|brother|grandfather|widower)\b", re.I
)
FEMALE = re.compile(
    r"\b(she|her|hers|wife|mother|mum|daughter|sister|grandmother|widow)\b", re.I
)


def gender_of(forename: str) -> str | None:
    """Resolve holder gender from the forename via the generator's own pools.

    Under --negative-control the answer is INVERTED. Every assertion that
    passes on the real lookup must then fail, and the run reports N/N
    detected. If it reports fewer, the check is not actually comparing the
    two things it claims to compare.
    """
    f = (forename or "").strip().lower()
    if not f or f in AMBIG:
        return None
    if f in MALE_F:
        return "F" if INVERT else "M"
    if f in FEMALE_F:
        return "M" if INVERT else "F"
    return None


truth: dict[str, dict] = {}
with (data / "truth" / "person_truth.csv").open() as fh:
    for r in csv.DictReader(fh):
        truth[r["record_id"]] = r

# Holder forename, taken from any identity source carrying a name.
forename: dict[str, str] = {}


def harvest(fn: str, col: str, split: bool) -> None:
    with (data / fn).open() as fh:
        for r in csv.DictReader(fh):
            t = truth.get(r["record_id"])
            if not t:
                continue
            v = (r.get(col) or "").strip()
            if not v:
                continue
            if split:
                parts = v.split()
                if parts and parts[0] in {"Mr", "Mrs", "Ms", "Miss", "Dr"}:
                    parts = parts[1:]
                if not parts:
                    continue
                v = parts[0]
            forename.setdefault(t["true_person_id"], v)


harvest("ecom_accounts.csv", "first_name", False)
harvest("crm_customers.csv", "full_name", True)

tbl = pq.read_table(data / "support_tickets.parquet")
rows = list(
    zip(tbl.column("record_id").to_pylist(), tbl.column("body").to_pylist())
)

stats = Counter()
mismatches = []

for rid, body in rows:
    t = truth.get(rid)
    if not t or t["case_type"] != "RISK_FLAG":
        continue
    notes = t["notes"]
    kind = (
        "DECEASED" if "DECEASED" in notes
        else "VULNERABLE" if "VULNERABLE" in notes
        else "MINOR" if "MINOR" in notes
        else "?"
    )
    stats[f"{kind}_total"] += 1
    if kind == "MINOR":
        stats["MINOR_skipped_first_person"] += 1
        continue

    g = gender_of(forename.get(t["true_person_id"], ""))
    if g is None:
        stats[f"{kind}_no_gender_resolved"] += 1
        continue

    b = body or ""
    has_m, has_f = bool(MALE.search(b)), bool(FEMALE.search(b))
    if has_m == has_f:
        stats[f"{kind}_no_single_signal"] += 1
        continue

    said = "F" if has_f else "M"
    stats[f"{kind}_checked"] += 1
    if said != g:
        stats[f"{kind}_MISMATCH"] += 1
        mismatches.append((rid, kind, forename.get(t["true_person_id"]), g, said, b))

print(f"corpus: {data}")
for k in sorted(stats):
    print(f"  {k:<34} {stats[k]}")
print()

checked = stats["DECEASED_checked"] + stats["VULNERABLE_checked"]
bad = stats["DECEASED_MISMATCH"] + stats["VULNERABLE_MISMATCH"]
print(f"holder-gender assertions checked : {checked}")
print(f"mismatches                       : {bad}")

for rid, kind, fn, g, said, b in mismatches[:8]:
    print(f"\n  {rid} [{kind}] holder forename={fn!r} -> {g}, body asserts {said}")
    print("    " + b.replace("\n", " ")[:200])

if checked < 20:
    print(
        "\nWARNING: fewer than 20 assertions checked. A zero here would not be "
        "evidence of anything -- this check has been vacuous twice already."
    )

if INVERT:
    # Negative control. Every assertion that passes on the real lookup must
    # fail here, so the expected result is bad == checked.
    print("\n--- NEGATIVE CONTROL (gender lookup inverted) ---")
    print(f"  assertions checked : {checked}")
    print(f"  detected           : {bad}")
    ok = checked >= 20 and bad == checked
    print(f"  {bad}/{checked} detected -> {'PASS' if ok else 'FAIL'}")
    if not ok:
        print("  The check does not detect a deliberately wrong answer, so "
              "its clean result on the real lookup means nothing.")
    print("\nVERDICT: " + ("PASS" if ok else "FAIL"))
    sys.exit(0 if ok else 1)

print("\nVERDICT: " + ("PASS" if bad == 0 and checked >= 20 else
                       "FAIL" if bad else "INCONCLUSIVE"))
print("Re-run with --negative-control before believing a zero.")
sys.exit(1 if bad else 0)
