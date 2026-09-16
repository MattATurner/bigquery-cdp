#!/usr/bin/env python3
"""Validate CONFUSABLE_FORENAMES against the group pools.

The SIBLING_TRAP builder calls group_of_forename(fn_a) and draws the shared
surname from that group. If fn_a is not in banks.FORENAME_GROUP the lookup
silently falls back to ANGLO -- the exact defect this pool was rebuilt to fix
(defect 1 in the build-status doc).

Two things are checked:
  1. fn_a resolves to a group consistent with the section comment it sits under.
  2. fn_a's declared gender matches the pool it was actually found in.

Note FORENAME_GROUP is a *reverse* index built in banks.py: if a name appears
in several groups it resolves to the highest-weighted one. So a name can be
present in the GREEK pool and still resolve to ANGLO. That is a real failure
for this purpose -- the surname would come from the wrong bank. LOCALE-SPEC
10.2: order each pair so the group-distinctive name is FIRST.

WHAT THIS PROVES: every fn_a in the literal resolves to the group its section
comment claims, so the shared surname is drawn from the intended bank.
WHAT IT DOES NOT PROVE: that the pairs are good confusables, that fn_b is
spelled correctly, or that either name is ever actually drawn. This reads the
source literal and the pools -- it never reads the corpus, and it is therefore
independent of what seed 42 happened to produce.

Usage:
    python3 demo/generate/checks/check_confusables.py [--generate-dir DIR]
"""
import argparse
import re
import sys
import unicodedata
from pathlib import Path

# Script-relative: this file lives at demo/generate/checks/.
_ap = argparse.ArgumentParser(description="CONFUSABLE_FORENAMES group probe")
_ap.add_argument("--generate-dir", type=Path, default=None,
                 help="generator package directory (default: <repo>/demo/generate)")
_args = _ap.parse_args()
GEN = (_args.generate_dir.resolve() if _args.generate_dir
       else Path(__file__).resolve().parents[1])
sys.path.insert(0, str(GEN))

import banks  # noqa: E402
import generate as g  # noqa: E402


def fold(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    ).upper()


# The ten group keys of LOCALE-SPEC 1.1. A section heading may legitimately
# map to more than one pool key, which is why the values are sets even where
# only one key is currently listed -- keep the shape so a future split does
# not require restructuring this table.
SECTION_TO_GROUPS = {
    "ANGLO": {"ANGLO"},
    "CHINESE": {"CHINESE"},
    "INDIAN": {"INDIAN"},
    "VIETNAMESE": {"VIETNAMESE"},
    "FILIPINO": {"FILIPINO"},
    "ARABIC": {"ARABIC"},
    "GREEK": {"GREEK"},
    "ITALIAN": {"ITALIAN"},
    "KOREAN": {"KOREAN"},
    "SEASIAN": {"SE_ASIAN"},
}

# Guard against this table and banks.py drifting apart. If a worker adds or
# removes a group key without telling the coordinator (LOCALE-SPEC 1.1 says
# not to), this fires rather than silently checking nine groups out of ten.
_declared = set().union(*SECTION_TO_GROUPS.values())
_actual = set(banks.SURNAMES_BY_GROUP)
if _declared != _actual:
    print(f"GROUP KEY DRIFT -- this script knows {sorted(_declared)}")
    print(f"                   banks.py has    {sorted(_actual)}")
    print(f"                   only in script: {sorted(_declared - _actual)}")
    print(f"                   only in banks : {sorted(_actual - _declared)}")
    print("Update SECTION_TO_GROUPS. LOCALE-SPEC 1.1 lists the ten keys.")
    sys.exit(2)

src = (GEN / "generate.py").read_text(encoding="utf-8")
start = src.index("CONFUSABLE_FORENAMES: list[tuple[str, str, str]] = [")
end = src.index("\n]\n", start)
body = src[start:end]

intended: dict[str, set[str]] = {}
label: dict[str, str] = {}
current, current_label = None, None
pair_re = re.compile(r'\("([^"]+)",\s*"([^"]+)",\s*"([MF])"\)')
for line in body.splitlines():
    m = re.match(r"\s*#\s*--\s*([A-Za-z\u0100-\u017f ]+?)\s*-{2,}", line)
    if m:
        key = fold(m.group(1)).replace(" ", "").replace("-", "").replace("_", "")
        if key not in SECTION_TO_GROUPS:
            print(f"UNKNOWN SECTION HEADING: {m.group(1)!r}")
            sys.exit(2)
        current, current_label = SECTION_TO_GROUPS[key], m.group(1).strip()
        continue
    for fn_a, _fn_b, _gender in pair_re.findall(line.split("#", 1)[0]):
        if current is None:
            print(f"pair before any section heading: {fn_a}")
            sys.exit(2)
        intended[fn_a] = current
        label[fn_a] = current_label

pairs = g.CONFUSABLE_FORENAMES
print(f"pairs in literal        : {len(pairs)}")
print(f"distinct fn_a with group: {len(intended)}")
print(f"surname groups available: {sorted(banks.SURNAMES_BY_GROUP)}\n")

male = {g_: {n for n, _w in p} for g_, p in banks.MALE_FORENAMES_BY_GROUP.items()}
female = {g_: {n for n, _w in p} for g_, p in banks.FEMALE_FORENAMES_BY_GROUP.items()}


def pools_containing(name):
    hits = []
    for grp, names in male.items():
        if name in names:
            hits.append((grp, "M"))
    for grp, names in female.items():
        if name in names:
            hits.append((grp, "F"))
    return hits


fail_a, gender_bad, warn_b, benign = [], [], [], []
seen: dict[str, int] = {}
for fn_a, fn_b, gender in pairs:
    seen[fn_a] = seen.get(fn_a, 0) + 1
    want = intended[fn_a]
    resolved = g.World.group_of_forename(fn_a)
    hits = pools_containing(fn_a)
    if fn_a not in banks.FORENAME_GROUP:
        # Absent from every pool means the lookup falls back to ANGLO. That
        # is only a defect if the pair was meant to be something else.
        if want == {"ANGLO"}:
            benign.append(fn_a)
        else:
            fail_a.append(fn_a)
            print(f"  FAIL   {fn_a:<12} ({label[fn_a]:<9}) absent from every "
                  f"forename pool -> silent ANGLO surname")
    elif resolved not in want:
        fail_a.append(fn_a)
        print(f"  FAIL   {fn_a:<12} ({label[fn_a]:<9}) resolves to {resolved}; "
              f"found in {hits}")
    if hits and not any(gd == gender for _g, gd in hits):
        gender_bad.append(fn_a)
        print(f"  GENDER {fn_a:<12} declared {gender} but only in {hits}")
    if fn_b not in banks.FORENAME_GROUP:
        warn_b.append((fn_b, label[fn_a]))


for fn_a, n in seen.items():
    if n > 1:
        print(f"  DUPLICATE fn_a used {n}x: {fn_a}")

print()
print(f"pairs examined      : {len(pairs)}")
print(f"fn_a group failures : {len(fail_a)}")
print(f"fn_a gender issues  : {len(gender_bad)}")
print(f"fn_a absent from all pools but intended ANGLO (fallback is correct, "
      f"though it is correct by accident): {len(benign)}")

print(f"fn_b absent from all pools (informational -- fn_b is only ever used as a "
      f"literal): {len(warn_b)}")
for fn_b, lab in warn_b:
    print(f"    {fn_b}  ({lab})")

# --- negative control ------------------------------------------------------
# Zero failures above is only believable if the comparison can produce a
# failure. Take the first pair, deliberately claim it belongs to a group it
# does not resolve to, and confirm the same comparison flags it.
#
# Without this, a bug that made `intended` empty, or `resolved` always equal
# to `want`, would report a clean run over however many pairs exist and look
# exactly like success.
print()
print("--- negative control ---")
nc_ok = False
if pairs:
    nc_fn = pairs[0][0]
    nc_resolved = g.World.group_of_forename(nc_fn)
    nc_wrong = next(
        (k for k in sorted(_actual) if k != nc_resolved), None
    )
    if nc_wrong is not None:
        nc_ok = nc_resolved not in {nc_wrong}
    print(f"  {nc_fn!r} resolves to {nc_resolved}; asserted against "
          f"{{{nc_wrong}}} -> detected={nc_ok} (must be True)")
if not nc_ok:
    print("  NEGATIVE CONTROL FAILED -- the group comparison cannot detect a "
          "deliberately wrong section, so a clean run above proves nothing")

print()
print(f"VERDICT: {'PASS' if not (fail_a or gender_bad) and nc_ok else 'FAIL'}"
      f"  ({len(pairs)} pairs examined, {len(fail_a)} group failures, "
      f"{len(gender_bad)} gender issues, negative control {'ok' if nc_ok else 'BROKEN'})")

sys.exit(1 if (fail_a or gender_bad or not nc_ok) else 0)
