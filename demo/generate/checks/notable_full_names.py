#!/usr/bin/env python3
"""Audit the NOTABLE_FULL_NAMES roster against the name pools.

WHAT THIS FILE USED TO BE, AND WHY IT IS NOT THAT ANY MORE
----------------------------------------------------------
It was a paste-able copy of the roster: a `NOTABLE_FULL_NAMES` literal plus
the rationale comments, spliced into `generate.py` by a companion script. That
shape is a second copy of a safety list, and a second copy of a safety list is
worse than one copy. The build-status doc records the same lesson from the
other direction -- the corpus verifier used to keep its own 22-name list, it
drifted behind the generator's, and the fix was noted as "roster now
IMPORTED, not a stale copy".

So this file no longer contains a roster. It **imports** the roster from
`generate.py` and audits it. The roster content itself is the
`generate.py` / `banks_names.py` worker's deliverable under LOCALE-SPEC 8.3.

WHAT THIS PROVES
----------------
  1. Every roster entry splits into exactly two parts on the first space.
     LOCALE-SPEC 8.3 makes a malformed entry a HARD BUILD FAILURE, not a
     warning: a typo in the roster must not silently fail to block anything.
  2. REACHABILITY, not occurrence. For every roster entry, whether the
     forename x surname cross product of the POOLS -- including everything
     the substitution layer can write -- can compose it. This is the property
     LOCALE-SPEC rule 0.3 says is the only one worth measuring.
  3. Every entry that IS reachable is actually blocked by `_forbidden_pair`.
     A reachable roster entry the guard does not block is a live hole whether
     or not it was drawn at seed 42.
  4. LOCALE-SPEC 8.3 exception 2: where a diminutive reaches a notable name,
     BOTH the diminutive and the canonical forename are blocked. Reverting a
     substitution must not land on the same real person. Same surname means
     same person, so this is asserted, not adjudicated.
  5. The roster has not silently shrunk (optional, --baseline).

WHAT THIS DOES NOT PROVE
------------------------
**The roster is not coverage, and this audit cannot make it one.** Two
systematic passes over the previous locale's pools found 138 reachable
notable names from 461 candidates -- a ~30% hit rate that did not decay
between passes, because the binding constraint is the author's recall of
public life, not the pools. A roster that passes every check here is still
only as complete as the person who wrote it. The emitted-row sweep
(`check_emitted_sweep.py`) is the safety net; the roster is a knowledge
artefact.

This file also never reads `demo/data`. It is a static audit of the roster
against the pools, which is exactly what makes it immune to what seed 42
happened to draw.

Usage:
    python3 demo/generate/checks/notable_full_names.py
    python3 demo/generate/checks/notable_full_names.py --candidates FILE
    python3 demo/generate/checks/notable_full_names.py --baseline roster.txt
    python3 demo/generate/checks/notable_full_names.py --write-baseline roster.txt

`--candidates FILE` takes one "Forename Surname" per line and reports which
of them the pools can compose and which of THOSE are not on the roster. That
is how the roster was built for the previous locale and how it should be
extended for this one: propose candidates, keep the reachable ones, and
record the hit rate so the next person knows the list is recall-bound.
"""
from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path

# LOCALE-SPEC 8.3 sets the floor at ~110 entries -- the size the previous
# locale's roster reached -- and says more is better. This is a floor, not a
# target: the roster is a knowledge artefact bounded by the author's recall,
# not a coverage guarantee. The emitted-row sweep is the actual safety net.
MIN_ROSTER_ENTRIES = 110


def fold(s: str) -> str:
    """NFKD fold + casefold, with the LOCALE-SPEC 5.3 special cases.

    Mirrors `generate._fold_name`. Kept local so this audit still runs if the
    generator's helper is renamed, but the generator's own function is used
    for the blocking assertions -- this one is only for pool indexing.
    """
    special = {
        "\u0142": "l", "\u0141": "L", "\u00f8": "o", "\u00d8": "O",
        "\u0111": "d", "\u0110": "D", "\u00df": "ss",
        "\u00e6": "ae", "\u00c6": "AE", "\u0153": "oe", "\u0152": "OE",
        "\u0127": "h", "\u0126": "H", "\u0167": "t", "\u0166": "T",
    }
    s = "".join(special.get(c, c) for c in s)
    return "".join(
        c for c in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(c)
    ).casefold()


# --- path resolution: script-relative, never absolute ----------------------
ap = argparse.ArgumentParser(description="NOTABLE_FULL_NAMES roster audit")
ap.add_argument("--generate-dir", type=Path, default=None,
                help="generator package directory (default: <repo>/demo/generate)")
ap.add_argument("--candidates", type=Path, default=None,
                help="file of 'Forename Surname' candidates, one per line")
ap.add_argument("--baseline", type=Path, default=None,
                help="a previously written roster snapshot; fail if entries "
                     "present in it are missing now")
ap.add_argument("--write-baseline", type=Path, default=None,
                help="write the current roster to this file and exit")
ap.add_argument("--verbose", action="store_true")
args = ap.parse_args()

GENERATE = (args.generate_dir.resolve() if args.generate_dir
            else Path(__file__).resolve().parents[1])
sys.path.insert(0, str(GENERATE))

import banks  # noqa: E402
import generate as G  # noqa: E402

FAIL = 0
WARN = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global FAIL
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" -- {detail}" if detail else ""))
    if not ok:
        FAIL += 1


def warn(label: str, detail: str = "") -> None:
    global WARN
    print(f"[WARN] {label}" + (f" -- {detail}" if detail else ""))
    WARN += 1


roster: list[str] = list(G.NOTABLE_FULL_NAMES)
print(f"roster imported from generate.py: {len(roster)} entries")

if args.write_baseline:
    args.write_baseline.write_text(
        "\n".join(sorted(roster)) + "\n", encoding="utf-8"
    )
    print(f"baseline written to {args.write_baseline} ({len(roster)} entries)")
    sys.exit(0)

# ---------------------------------------------------------------------------
# 1. Structural rules
# ---------------------------------------------------------------------------
print("\n== 1. structure ==")

malformed = [n for n in roster if len(n.split(" ")) != 2]
check("every entry splits into exactly two parts on the first space",
      not malformed,
      f"{len(malformed)} malformed: {malformed[:8]}" if malformed else
      "LOCALE-SPEC 8.3 -- a typo here silently blocks nothing")

dupes = sorted({n for n in roster if roster.count(n) > 1})
check("no duplicate entries", not dupes, f"{dupes[:8]}" if dupes else "")

check(f"roster carries at least {MIN_ROSTER_ENTRIES} entries",
      len(roster) >= MIN_ROSTER_ENTRIES,
      f"{len(roster)} entries -- LOCALE-SPEC 8.3 asks for at least "
      f"{MIN_ROSTER_ENTRIES}")

if args.baseline and args.baseline.exists():
    before = [l.strip() for l in
              args.baseline.read_text(encoding="utf-8").splitlines() if l.strip()]
    lost = [n for n in before if n not in roster]
    check("no baseline entry has been dropped", not lost,
          f"{len(lost)} lost: {lost[:8]}" if lost else
          f"{len(before)} baseline entries all still present")
    print(f"  roster: {len(before)} -> {len(roster)} "
          f"({len(roster) - len(before):+d})")

# ---------------------------------------------------------------------------
# 2. The written name space -- pools plus the substitution layer
# ---------------------------------------------------------------------------
print("\n== 2. written name space ==")

fore_pool: set[str] = set()
for _d in (banks.MALE_FORENAMES_BY_GROUP, banks.FEMALE_FORENAMES_BY_GROUP):
    for _g in sorted(_d):
        fore_pool.update(n for n, _w in _d[_g])
sur_pool: set[str] = set()
for _g in sorted(banks.SURNAMES_BY_GROUP):
    sur_pool.update(n for n, _w in banks.SURNAMES_BY_GROUP[_g])

DIMINUTIVES = getattr(banks, "DIMINUTIVES", {})
SURNAME_VARIANTS = getattr(banks, "SURNAME_VARIANTS", {})

# folded written form -> the pool name(s) it can come from
fore_src: dict[str, set[str]] = {}
for n in sorted(fore_pool):
    fore_src.setdefault(fold(n), set()).add(n)
    for v in DIMINUTIVES.get(n, []):
        fore_src.setdefault(fold(v), set()).add(n)
sur_src: dict[str, set[str]] = {}
for n in sorted(sur_pool):
    sur_src.setdefault(fold(n), set()).add(n)
    for v in SURNAME_VARIANTS.get(n, []):
        sur_src.setdefault(fold(v), set()).add(n)

base_pairs = len(fore_pool) * len(sur_pool)
written_pairs = len(fore_src) * len(sur_src)
print(f"  forename pool {len(fore_pool):,} -> {len(fore_src):,} written forms")
print(f"  surname  pool {len(sur_pool):,} -> {len(sur_src):,} written forms")
print(f"  base pairs {base_pairs:,}; written pairs {written_pairs:,} "
      f"(+{written_pairs - base_pairs:,} the substitution layer adds)")
check("the substitution layer widens the name space",
      written_pairs > base_pairs,
      "if this is 0 the audit below is only seeing half the problem")

# ---------------------------------------------------------------------------
# 3. Reachability, and the blocking assertion
# ---------------------------------------------------------------------------
print("\n== 3. reachability (LOCALE-SPEC 0.3 / 8.5) ==")

reachable: list[str] = []
unreachable: list[str] = []
unblocked: list[str] = []

for entry in roster:
    if len(entry.split(" ")) != 2:
        continue
    fn, sn = entry.split(" ", 1)
    if fold(fn) in fore_src and fold(sn) in sur_src:
        reachable.append(entry)
        if not G._forbidden_pair(fn, sn):
            unblocked.append(entry)
    else:
        unreachable.append(entry)

print(f"  entries REACHABLE from the pools : {len(reachable)}")
print(f"  entries not reachable today      : {len(unreachable)}")
print("  (an unreachable entry is not dead weight -- one pool edit can make "
      "it reachable, which is why it stays on the list)")
if args.verbose and unreachable:
    for n in sorted(unreachable):
        print(f"    not reachable: {n}")

check("every reachable roster entry is blocked by _forbidden_pair",
      not unblocked,
      f"{len(unblocked)} live holes: {sorted(unblocked)[:8]}" if unblocked
      else f"{len(reachable)} reachable entries, all blocked")

if not reachable:
    warn("no roster entry is reachable from the pools",
         "either the roster or the pools are not the ones this build uses; "
         "a clean result above would mean nothing")

# Negative control. The auditor must be able to FIND a hole, or its clean
# result is just a broken predicate. Compose a pair that is reachable by
# construction and is not on the roster, and confirm the same test that
# produced `unblocked` classifies it as unblocked.
print("\n  -- negative control --")
nc_ok = False
if fore_src and sur_src:
    nc_fn = sorted(fore_src)[0]
    nc_sn = sorted(sur_src)[0]
    nc_reachable = nc_fn in fore_src and nc_sn in sur_src
    nc_blocked = G._forbidden_pair(nc_fn, nc_sn)
    nc_ok = nc_reachable and not nc_blocked
    print(f"  sentinel pair '{nc_fn} {nc_sn}': reachable={nc_reachable}, "
          f"blocked={nc_blocked}, reported as a hole={nc_ok} (must be True)")
if not nc_ok:
    warn("negative control did not fire",
         "the sentinel pair is itself blocked, or the reachability index is "
         "empty; pick another sentinel before believing the clean result")

# ---------------------------------------------------------------------------
# 4. LOCALE-SPEC 8.3 exception 2 -- diminutive and canonical both blocked
# ---------------------------------------------------------------------------
print("\n== 4. diminutive / canonical pairing (LOCALE-SPEC 8.3 exception 2) ==")
print("  Where a diminutive reaches a notable name, BOTH the diminutive and")
print("  the canonical forename must be blocked: reverting the substitution")
print("  must not land on the same real person. Same surname means the same")
print("  person, so this is asserted rather than adjudicated. The documented")
print("  exception -- canonical innocuous because the SURNAME also differs --")
print("  does not apply here by construction.")

canon_of: dict[str, set[str]] = {}
for c in sorted(fore_pool):
    for d in sorted(DIMINUTIVES.get(c, [])):
        canon_of.setdefault(fold(d), set()).add(c)

half_blocked: list[str] = []
pairs_examined = 0
for entry in roster:
    if len(entry.split(" ")) != 2:
        continue
    d_fn, sn = entry.split(" ", 1)
    for c_fn in sorted(canon_of.get(fold(d_fn), set())):
        if fold(c_fn) == fold(d_fn):
            continue
        pairs_examined += 1
        if not G._forbidden_pair(c_fn, sn):
            half_blocked.append(f"{entry}  (canonical '{c_fn} {sn}' NOT blocked)")

print(f"  diminutive->canonical pairs examined : {pairs_examined}")
check("no roster entry blocks the diminutive but leaves the canonical open",
      not half_blocked,
      f"{len(half_blocked)}: {half_blocked[:5]}" if half_blocked else "")
if pairs_examined == 0:
    warn("this check examined 0 pairs",
         "no roster entry uses a forename that banks.DIMINUTIVES maps from, "
         "so its PASS is vacuous")

# ---------------------------------------------------------------------------
# 5. Optional candidate sweep -- how the roster gets extended
# ---------------------------------------------------------------------------
if args.candidates:
    print("\n== 5. candidate sweep ==")
    cands = [l.strip() for l in
             args.candidates.read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.startswith("#")]
    on_roster = {fold(n) for n in roster}
    hit, miss, new = [], [], []
    for c in cands:
        if len(c.split(" ")) != 2:
            warn(f"candidate is not two parts: {c!r}")
            continue
        fn, sn = c.split(" ", 1)
        if fold(fn) in fore_src and fold(sn) in sur_src:
            hit.append(c)
            if fold(c) not in on_roster:
                new.append(c)
        else:
            miss.append(c)
    rate = (100.0 * len(hit) / len(cands)) if cands else 0.0
    print(f"  candidates        : {len(cands)}")
    print(f"  reachable         : {len(hit)}  ({rate:.0f}% hit rate)")
    print(f"  not reachable     : {len(miss)}")
    print(f"  reachable and NOT already on the roster : {len(new)}")
    for c in sorted(new):
        print(f"    ADD? {c}")
    print("  A hit rate that does not decay across passes means the binding")
    print("  constraint is the author's recall, not the pools. Record it.")

# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("REMINDER: this list is NOT coverage. Passing every check above means")
print("the roster is internally consistent and correctly wired -- not that it")
print("names every public figure the pools can compose. The emitted-row sweep")
print("is the safety net; see check_emitted_sweep.py.")
print()
print(f"VERDICT: {'PASS' if not FAIL else f'FAIL ({FAIL} checks failed)'}"
      f"{f', {WARN} warning(s)' if WARN else ''}")
sys.exit(1 if FAIL else 0)
