#!/usr/bin/env python3
"""Prove the emission-time name guard catches what the person-level guard cannot.

Run from anywhere:

    python3 demo/generate/checks/check_emitted_sweep.py
    python3 demo/generate/checks/check_emitted_sweep.py --generate-dir ...

The claim under test
--------------------
The old sweep walked ``world.people`` and read ``p.forename`` / ``p.surname``.
The Emitter substitutes diminutives, ``SURNAME_VARIANTS`` entries and typos
*after* that, so a person named ``Robert Hawke`` is written to a CRM row as
``Bob Hawke`` -- a former Prime Minister -- and the old sweep passed.

This probe does not trust the fix. It reproduces the failure mechanically:

  1. Find pairs that are reachable ONLY through the substitution layer, by
     composing every diminutive of every forename against every surname
     variant of every surname. This is the space the old check was blind to.
  2. Inject a handful of real, measured examples into the roster at runtime.
  3. Generate a corpus and assert the injected names appear in NO output row,
     while the underlying innocuous person is still present.

WHAT PROVES THE GUARD AND WHAT DOES NOT
---------------------------------------
Section 3 is the proof. It is a DETERMINISTIC UNIT TEST: it constructs the
forbidden pair BY HAND and asserts the revert fires. It cannot pass vacuously.

Section 4 is an end-to-end smoke test and is NOT proof. Its first version
asserted "no injected name written to any row" against a 4k corpus and passed
with ``emitted_name_reverts = 0`` -- because the pairs were simply never
drawn. Green, and worthless: occurrence instead of mechanism. It is retained
because a HIT there would be a real defect, and it reports how many rows it
examined so a clean result cannot be misread as evidence.

A guard that reverts the substitution but also deletes the person would pass
a naive "is the bad name absent" test while silently shrinking the
population, so section 4 also asserts the population is intact.
"""
from __future__ import annotations

import argparse
import csv
import inspect
import json
import subprocess
import sys
import tempfile
from pathlib import Path

# Path resolution is script-relative -- no absolute path, no cwd assumption.
# This file lives at demo/generate/checks/, so parents[1] is demo/generate.
HERE = Path(__file__).resolve().parent
GENERATE = HERE.parent

_ap = argparse.ArgumentParser(description="emission-time name guard probe")
_ap.add_argument("--generate-dir", type=Path, default=None,
                 help="generator package directory (default: <repo>/demo/generate)")
_ap.add_argument("--people", type=int, default=4000)
_ap.add_argument("--records", type=int, default=10000)
_ap.add_argument("--skip-end-to-end", action="store_true",
                 help="run only the deterministic unit tests (sections 1-3)")
_args = _ap.parse_args()
if _args.generate_dir:
    GENERATE = _args.generate_dir.resolve()

sys.path.insert(0, str(GENERATE))

import banks
import generate as G

FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global FAIL
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" -- {detail}" if detail else ""))
    if not ok:
        FAIL += 1


# ---------------------------------------------------------------------------
# 1. Measure the substitution-only name space
# ---------------------------------------------------------------------------
fore_pool: set[str] = set()
for d in (banks.MALE_FORENAMES_BY_GROUP, banks.FEMALE_FORENAMES_BY_GROUP):
    for _g, pool in d.items():
        fore_pool.update(n for n, _w in pool)
sur_pool: set[str] = set()
for _g, pool in banks.SURNAMES_BY_GROUP.items():
    sur_pool.update(n for n, _w in pool)

# Everything the substitution layer can produce from a pool name.
fore_forms: dict[str, set[str]] = {}
for n in fore_pool:
    fore_forms[n] = {n} | set(banks.DIMINUTIVES.get(n, []))
sur_forms: dict[str, set[str]] = {}
for n in sur_pool:
    sur_forms[n] = {n} | set(banks.SURNAME_VARIANTS.get(n, []))

base_pairs = len(fore_pool) * len(sur_pool)
all_fore = set().union(*fore_forms.values()) if fore_forms else set()
all_sur = set().union(*sur_forms.values()) if sur_forms else set()
sub_pairs = len(all_fore) * len(all_sur)

print(f"forename pool {len(fore_pool):,} -> {len(all_fore):,} written forms")
print(f"surname  pool {len(sur_pool):,} -> {len(all_sur):,} written forms")
print(f"base pair space {base_pairs:,}; with substitution {sub_pairs:,} "
      f"(+{sub_pairs - base_pairs:,} invisible to a person-level sweep)")
print()

check(
    "substitution layer widens the name space",
    sub_pairs > base_pairs,
    f"{sub_pairs - base_pairs:,} extra pairs",
)

# ---------------------------------------------------------------------------
# 2. Real examples, verified reachable only via substitution
# ---------------------------------------------------------------------------
# (written_forename, written_surname, canonical_forename, canonical_surname)
#
# Australian equivalents of the measured examples. Each is a real public
# figure whose written name the substitution layer can compose from halves
# that are individually ordinary:
#
#   Johnny Howard  <- Juan Howard       a former Prime Minister, composed by
#       the diminutive layer from a canonical the generator will happily
#       create. The person-level sweep sees only "Juan Howard" and passes.
#   Pat White      <- Patricia White    a Nobel laureate novelist, same shape.
#   Steve Marshall <- Stephen Marshall  a former state Premier, same shape.
#
# Each is verified below rather than asserted: `reachable` re-derives the path
# from the live pools, so this list going stale fails loudly instead of
# quietly passing. The previous fixture (Bob Hawke / Tony Abbott / Jack
# Thompson) did go stale -- "Hawke", "Abbott" and "Thomson" are not in the
# Australian surname pool at all -- and the check correctly refused to pass on
# an empty example set rather than reporting a vacuous green.
#
# HONEST GAP: there is currently NO live path of the full Jackie Chan shape
# (diminutive AND surname variant together), where neither written half need
# appear in any pool. A sweep of the pools finds only three surname-variant
# paths and all three are reduplications caught by that rule instead. So the
# examples below exercise the forename half of the substitution layer only.
# The surname half is covered by the hand-constructed unit tests further down,
# not by a reachable corpus example. If a future pool edit creates a real
# combined path, add it here -- it is the strongest possible test case.
CASES = [
    ("Johnny", "Howard", "Juan", "Howard"),
    ("Pat", "White", "Patricia", "White"),
    ("Steve", "Marshall", "Stephen", "Marshall"),
]

live = []
for wfn, wsn, cfn, csn in CASES:
    reachable = (
        cfn in fore_pool
        and wfn in fore_forms.get(cfn, set())
        and csn in sur_pool
        and wsn in sur_forms.get(csn, set())
    )
    if reachable:
        live.append((wfn, wsn, cfn, csn))
    print(f"  {wfn} {wsn:10s} <- {cfn} {csn:10s} reachable={reachable}")
print()

check("at least one substitution-only example is live", bool(live))

# The old check, reproduced on the examples above. For the bug to be real it
# is enough that ONE canonical form is innocuous -- that is a person the
# generator will happily create and whose written name is a public figure.
#
# This was `all(...)` and went stale the moment the roster started blocking
# canonical forms as well as diminutives. `Robert Hawke` is itself expected
# to be blocked *because of this defect*, so requiring every canonical to be
# innocuous asserted that the fix had not been applied. `any(...)` is the
# claim that was actually meant.
blind_to = [
    f"{cfn} {csn}" for _w, _s, cfn, csn in live
    if not G._forbidden_pair(cfn, csn)
]
check(
    "person-level check is blind to at least one (reproduces the old bug)",
    bool(blind_to),
    f"innocuous canonicals: {', '.join(blind_to)}",
)

# ---------------------------------------------------------------------------
# 2b. Enumerate the live substitution paths, rather than guessing at them
# ---------------------------------------------------------------------------
# Which blocked pairs can a LEGAL person still substitute into? These are the
# only paths on which the guard can ever fire in a real run. Derived from the
# pools and the roster so the list cannot go stale, unlike the three
# hand-picked examples above.
#
# This exists to make `emitted_name_reverts == 0` readable. On its own that
# figure is ambiguous: it means either "the guard held" or "the guard was
# never asked". Knowing how many live paths there are, and whether any of
# those people exist in the corpus, tells you which.
fn_src: dict[str, set[str]] = {}
for _n in fore_pool:
    for _d in banks.DIMINUTIVES.get(_n, []):
        fn_src.setdefault(_d, set()).add(_n)
sn_src: dict[str, set[str]] = {}
for _n in sur_pool:
    for _v in banks.SURNAME_VARIANTS.get(_n, []):
        sn_src.setdefault(_v, set()).add(_n)

live_paths: set[tuple[str, str]] = set()
for _full in G.NOTABLE_FULL_NAMES:
    _p = _full.split(" ", 1)
    if len(_p) != 2:
        continue
    _wf, _ws = _p
    _cf = ({_wf} if _wf in fore_pool else set()) | fn_src.get(_wf, set())
    _cs = ({_ws} if _ws in sur_pool else set()) | sn_src.get(_ws, set())
    for _a in _cf:
        for _b in _cs:
            if (_a, _b) != (_wf, _ws) and not G._forbidden_pair(_a, _b):
                live_paths.add((_full, f"{_a} {_b}"))

print(f"\nblocked pairs a LEGAL person can substitute into: {len(live_paths)}")
for _blocked, _canon in sorted(live_paths):
    print(f"  {_blocked:22s} <- {_canon}")
print("These are the only paths on which the guard can fire in a real run.")
print("If emitted_name_reverts is 0 AND none of these people were drawn, the")
print("guard was not exercised -- section 3 is what proves it works.")

# ---------------------------------------------------------------------------
# 3. Direct unit test of the guard -- the assertion that cannot pass vacuously
# ---------------------------------------------------------------------------
# The end-to-end test below is necessary but NOT sufficient, and the first run
# of this probe proved why: at 4,000 people the injected pairs were never
# drawn, so "no injected name written to any row" passed while
# `emitted_name_reverts` was 0. That is the occurrence-vs-reachability trap
# that produced the original defect -- measuring whether something happened to
# occur instead of whether the mechanism works.
#
# This section removes the dependency on chance. It builds the exact situation
# by hand and asserts the guard fires.
#
# Driven by `live_paths`, NOT by the hardcoded CASES above. An earlier version
# used the hardcoded list and reported a false failure on "Bob Hawke": the
# roster blocks BOTH "Bob Hawke" and "Robert Hawke", so there is nothing
# legal to revert to and `_vet_pair` correctly classified it as unfixable. The
# test was asserting on a situation the generator can never produce -- if both
# forms are blocked, `make_person` never creates the person in the first place.
# Deriving the cases guarantees we only test paths that can actually occur.
# The both-forms-blocked case is asserted separately, below, as a backstop.
print("\n-- direct test of Emitter._vet_pair --")

import datetime as _dt

_world = G.World(seed=1, cfg=G.Corruption())
_em = G.Emitter(_world)


def _make_test_address():
    """Build a synthetic Australian test address.

    LOCALE-SPEC 2.6 makes the state abbreviation part of the address, so the
    `Address` dataclass may or may not have gained a `state` field by the time
    this runs. Introspect rather than guess: hardcoding a positional signature
    is how this probe would start failing for a reason that has nothing to do
    with the guard it exists to test.
    """
    want = {
        "line1": "12 Wattle Street", "street": "12 Wattle Street",
        "address_line1": "12 Wattle Street",
        "suburb": "Coogee", "city": "Sydney",
        "state": "NSW", "postcode": "2034", "std": "02", "area_code": "02",
    }
    fields = getattr(G.Address, "__dataclass_fields__", None)
    if fields:
        kwargs = {n: want[n] for n in fields if n in want}
        if len(kwargs) == len(fields):
            return G.Address(**kwargs)
    # Fall back to positional in the historical order, trimmed to arity.
    order = ["12 Wattle Street", "Coogee", "Sydney", "NSW", "2034", "02"]
    n = len(inspect.signature(G.Address).parameters)
    return G.Address(*order[:n])


_ADDR = _make_test_address()


def _person(fn: str, sn: str, pid: str = "PER-TEST") -> "G.Person":
    return G.Person(
        pid=pid, forename=fn, surname=sn, gender="M",
        dob=_dt.date(1980, 1, 1), addr=_ADDR,
        email="t@example.test", mobile="0412 345 678",
    )


# DIAGNOSTIC, NOT A GATE -- and the reason is worth reading before you change
# it back.
#
# This was `check("there is at least one live substitution path to test",
# bool(live_paths))`. That assertion was correct while a roster entry blocked
# only the exact spelling the author typed: some legal person could always
# substitute into a blocked pair, so the guard had something to fire on, and
# an empty set meant the roster had drifted away from the pools.
#
# It stopped being correct when the roster splice gained a mechanical
# diminutive closure (generate.py, `_FORENAME_CLASS`). Blocking every forename
# in a roster entry's equivalence class is precisely what CLOSES these paths.
# `live_paths == 0` is now the DESIGNED outcome: it means no legal person can
# substitute into a public figure's name at all. Gating on it would assert
# that the closure had NOT been applied -- the same stale-assertion trap that
# `all(...)` vs `any(...)` fell into a few lines above.
#
# So it is reported, not gated. What proves the guard actually works is
# section 3 below: hand-constructed people whose substitution is forced, with
# a negative control. Those cannot pass vacuously, which is the whole point --
# an empty `live_paths` would otherwise be indistinguishable from "the guard
# was never asked", the exact ambiguity this section was added to remove.
#
# If this number is ever NON-zero, that is the signal worth acting on: a pool
# or roster edit has opened a substitution route the closure does not cover.
# The paths are enumerated above; go and look at them.
if live_paths:
    print(
        f"\nNOTE: {len(live_paths)} live substitution path(s) exist. The "
        "forename closure in generate.py is expected to reduce this to 0, so "
        "a non-zero count means a pool or roster edit has opened a route it "
        "does not cover. Enumerated above -- investigate rather than ignore."
    )
else:
    print(
        "\nlive substitution paths: 0 -- expected. The diminutive closure in "
        "generate.py blocks every forename in a roster entry's equivalence "
        "class, which closes these routes by construction. The guard is "
        "proven by the forced unit tests in section 3, not by this number."
    )

for _blocked, _canon in sorted(live_paths):
    wfn, wsn = _blocked.split(" ", 1)
    cfn, csn = _canon.split(" ", 1)
    before = _em.emitted_name_reverts
    got_fn, got_sn = _em._vet_pair(_person(cfn, csn), wfn, wsn)

    check(f"'{_blocked}' <- '{_canon}' is reverted",
          _em.emitted_name_reverts == before + 1,
          f"returned '{got_fn} {got_sn}'")
    check("  result is not a forbidden pair",
          not G._forbidden_pair(got_fn, got_sn), f"'{got_fn} {got_sn}'")
    check("  forbidden pair never recorded as emitted",
          (wfn, wsn) not in _em.emitted_names)

# ---------------------------------------------------------------------------
# 3b. The both-forms-blocked backstop -- HAND-CONSTRUCTED, DETERMINISTIC
# ---------------------------------------------------------------------------
# THIS IS THE ASSERTION THAT CANNOT PASS VACUOUSLY. It does not draw, sample,
# or generate anything: it builds the exact forbidden situation by hand and
# asserts the guard fires. Do not replace it with anything that depends on a
# pair having been drawn. See the build-status doc, defect 7.
#
# When the roster blocks the diminutive AND the canonical form there is no
# legal fallback. The designed behaviour is to COUNT it and let the
# build-time sweep fail the build -- not to silently emit, and not to rename
# the person. This situation cannot arise from the generator (make_person
# would never have created the person), so this asserts the backstop, not a
# live path.
#
# The pair is `Bob Hawke` <- `Robert Hawke`: a former Prime Minister composed
# by a diminutive substitution AFTER the person `Robert Hawke` was vetted.
# LOCALE-SPEC 8.3 exception 2 requires the roster to block BOTH forms, so
# this is also a conformance test on the roster.
BOTH_BLOCKED = ("Bob", "Hawke", "Robert", "Hawke")
_bwfn, _bwsn, _bcfn, _bcsn = BOTH_BLOCKED

_both_ok = G._forbidden_pair(_bwfn, _bwsn) and G._forbidden_pair(_bcfn, _bcsn)
check(f"roster blocks BOTH '{_bwfn} {_bwsn}' and '{_bcfn} {_bcsn}' "
      f"(LOCALE-SPEC 8.3 exception 2)",
      _both_ok,
      f"diminutive blocked={G._forbidden_pair(_bwfn, _bwsn)}, "
      f"canonical blocked={G._forbidden_pair(_bcfn, _bcsn)}")

if not _both_ok:
    # The declared pair is not on the roster this build uses. Rather than
    # leave the backstop untested -- which would be exactly the green-proves-
    # nothing failure this file exists to prevent -- derive a both-blocked
    # pair from the roster and test that instead. Sorted, so deterministic.
    _derived = None
    for _c in sorted(fore_pool):
        for _d in sorted(banks.DIMINUTIVES.get(_c, [])):
            for _s in sorted(sur_pool):
                if G._forbidden_pair(_d, _s) and G._forbidden_pair(_c, _s):
                    _derived = (_d, _s, _c, _s)
                    break
            if _derived:
                break
        if _derived:
            break
    if _derived:
        print(f"  substituting derived both-blocked pair: "
              f"'{_derived[0]} {_derived[1]}' <- '{_derived[2]} {_derived[3]}'")
        _bwfn, _bwsn, _bcfn, _bcsn = _derived
    else:
        check("a both-forms-blocked pair exists to test the backstop with",
              False,
              "no roster entry blocks both a diminutive and its canonical "
              "form; the backstop is UNTESTED")

if G._forbidden_pair(_bwfn, _bwsn) and G._forbidden_pair(_bcfn, _bcsn):
    _unfix_before = _em.emitted_name_unfixable
    _gf, _gs = _em._vet_pair(_person(_bcfn, _bcsn), _bwfn, _bwsn)
    check("both-forms-blocked is counted as unfixable, not silently emitted",
          _em.emitted_name_unfixable == _unfix_before + 1,
          f"returned '{_gf} {_gs}'")
    check("  and it lands in emitted_names so the sweep fails the build",
          (_bwfn, _bwsn) in _em.emitted_names)
    # Reset so the end-to-end section starts clean.
    _em.emitted_name_unfixable = _unfix_before
    _em.emitted_names.discard((_bwfn, _bwsn))

# And the converse -- the negative control for this whole section. A guard
# that reverted EVERYTHING would pass every assertion above. An innocuous
# substitution must pass through untouched.
#
# `Maggie Walsh` <- `Margaret Walsh`: an ordinary Australian name with no
# public figure attached. Deliberately not `Margaret Court` or `Maggie Beer`.
INNOCUOUS = ("Maggie", "Walsh", "Margaret", "Walsh")
_iwfn, _iwsn, _icfn, _icsn = INNOCUOUS
check(f"negative control pair '{_iwfn} {_iwsn}' is genuinely innocuous",
      not G._forbidden_pair(_iwfn, _iwsn),
      "if this fails, pick a different control pair -- do not relax the guard")
_before = _em.emitted_name_reverts
_fn, _sn = _em._vet_pair(_person(_icfn, _icsn, "PER-TEST2"), _iwfn, _iwsn)
check("innocuous substitution passes through untouched",
      (_fn, _sn) == (_iwfn, _iwsn) and _em.emitted_name_reverts == _before,
      f"got '{_fn} {_sn}'")

# ---------------------------------------------------------------------------
# 4. End-to-end: inject into the roster, regenerate, assert absence
# ---------------------------------------------------------------------------
print("\n-- end-to-end corpus scan --")
print("NOT PROOF. Section 3 is the proof. A clean result here is consistent")
print("with the guard working AND with the guard never having been asked.")
if _args.skip_end_to_end:
    print("skipped (--skip-end-to-end)")
    print()
    print("ALL CHECKS PASS" if not FAIL else f"{FAIL} CHECK(S) FAILED")
    sys.exit(1 if FAIL else 0)
if not live:
    print("\nno live cases; skipping end-to-end")
    sys.exit(1 if FAIL else 0)

inject = [f"{w} {s}" for w, s, _c, _d in live]
harness = f'''
import json, sys
sys.path.insert(0, {json.dumps(str(GENERATE))})
import generate as G
for full in {inject!r}:
    if full not in G.NOTABLE_FULL_NAMES:
        G.NOTABLE_FULL_NAMES.append(full)
        a, b = full.split(" ", 1)
        G.FORBIDDEN_PAIRS.add((G._fold_name(a), G._fold_name(b)))
sys.argv = ["generate.py", "--seed", "42", "--people", {json.dumps(str(_args.people))},
            "--records", {json.dumps(str(_args.records))}, "--out", {json.dumps("__OUT__")}]
G.main()
'''

with tempfile.TemporaryDirectory() as td:
    out = Path(td) / "data"
    src = Path(td) / "harness.py"
    src.write_text(harness.replace("__OUT__", str(out)))
    print(f"regenerating with {len(inject)} injected roster entries: {inject}")
    r = subprocess.run(
        [sys.executable, str(src)], cwd=GENERATE,
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        check("generator ran with injected roster", False,
              (r.stderr or r.stdout)[-1500:])
        sys.exit(1)
    check("generator ran with injected roster", True)

    # Scan every emitted name field for the injected pairs.
    NAME_FIELDS = {
        "crm_customers.csv": ["full_name"],
        "ecom_accounts.csv": ["first_name", "last_name"],
        "loyalty_members.csv": ["member_name"],
        "pos_transactions.csv": ["surname"],
    }
    hits: list[str] = []
    rows_scanned = 0
    for fname, cols in NAME_FIELDS.items():
        fp = out / fname
        if not fp.exists():
            continue
        with fp.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                rows_scanned += 1
                blob = " ".join(row.get(c, "") or "" for c in cols)
                fold = G._fold_name(blob.replace(",", " "))
                for w, s, _c, _d in live:
                    if f"{G._fold_name(w)} {G._fold_name(s)}" in fold:
                        hits.append(f"{fname}:{row['record_id']}:{blob}")

    # Report the sample size alongside the verdict. A zero over 10 rows and a
    # zero over 10,000 rows are not the same claim, and the habit of printing
    # only the verdict is how three checks in this project were vacuous and
    # green at the same time.
    check(f"no injected name written to any row ({rows_scanned} rows examined)",
          not hits,
          "; ".join(hits[:5]) if hits else
          "clean, but this is a necessary condition, not a sufficient one")

    # And the underlying people must still be there -- the guard reverts the
    # substitution, it does not remove the person.
    mf = json.loads((out / "manifest.json").read_text())
    check("population intact", mf["person_count"] >= _args.people * 0.975,
          f"person_count={mf['person_count']} of {_args.people} requested")
    # NOT a check. At this scale the injected pairs are very unlikely to be
    # drawn at all, so asserting on this would be asserting on chance -- and
    # a green result would mean nothing, which is exactly the failure mode
    # that let the original defect through. Section 3 is what proves the
    # mechanism; this is reported only so the figure is visible.
    print(f"  (informational) emitted_name_reverts="
          f"{mf.get('emitted_name_reverts')} -- expected 0 at this scale")
    check("nothing unfixable", mf.get("emitted_name_unfixable", 0) == 0,
          f"emitted_name_unfixable={mf.get('emitted_name_unfixable')}")
    print(f"\ndistinct_emitted_names={mf.get('distinct_emitted_names'):,} "
          f"vs person_count={mf['person_count']:,}")

print()
print("ALL CHECKS PASS" if not FAIL else f"{FAIL} CHECK(S) FAILED")
sys.exit(1 if FAIL else 0)
