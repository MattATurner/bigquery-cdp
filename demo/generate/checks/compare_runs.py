#!/usr/bin/env python3
"""Determinism gate: compare two generator output directories byte-for-byte.

Usage: compare_runs.py DIR_A DIR_B

Rationale for the design:

  * The previous gate run reported a single FAIL on support_tickets.parquet and
    nothing else. A bare "files differ" verdict is not diagnosable -- Parquet is
    a compressed container, so a one-character change in one of 10,052 ticket
    bodies and a wholesale reordering of every row produce the same verdict.
    So when a Parquet file differs we decode it and report WHICH rows and WHICH
    columns differ, and how many.

  * manifest.json legitimately contains a wall-clock timestamp, so it is
    compared with that key removed rather than being excluded outright --
    excluding it entirely would hide a real change in row counts.

  * call_transcripts/ is a directory of thousands of small files; compared as a
    name->sha256 map so an added/removed file is distinguishable from a changed
    one.

WHAT THIS PROVES: two generator runs at the same seed produced byte-identical
output, which is LOCALE-SPEC rule 0.1.
WHAT IT DOES NOT PROVE: that the output is correct, or that determinism holds
at a different seed or scale. It also cannot see a non-determinism that
happens to be stable within a single machine and Python build. Run the two
generations SERIALLY -- the one historical failure of this gate was a
concurrent-edit race between two runs sharing a tree, not a generator defect.

This file is locale-neutral. It compares bytes and never reads a name, an
address or a currency amount, so the delocalisation does not touch it.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parquet_diff(pa: Path, pb: Path) -> list[str]:
    """Decode both Parquet files and localise the difference."""
    out: list[str] = []
    try:
        import pyarrow.parquet as pq
    except ImportError:
        return ["  (pyarrow unavailable -- cannot decode)"]

    ta = pq.read_table(pa)
    tb = pq.read_table(pb)

    if ta.schema != tb.schema:
        out.append("  SCHEMA DIFFERS")
        out.append(f"    A: {ta.schema}")
        out.append(f"    B: {tb.schema}")
        return out
    if ta.num_rows != tb.num_rows:
        out.append(f"  ROW COUNT DIFFERS: A={ta.num_rows} B={tb.num_rows}")
        return out

    da = ta.to_pydict()
    db = tb.to_pydict()
    for col in ta.schema.names:
        ca, cb = da[col], db[col]
        bad = [i for i, (x, y) in enumerate(zip(ca, cb)) if x != y]
        if bad:
            out.append(f"  column {col!r}: {len(bad)} of {len(ca)} rows differ")
            for i in bad[:3]:
                out.append(f"    row {i}:")
                out.append(f"      A: {str(ca[i])[:300]}")
                out.append(f"      B: {str(cb[i])[:300]}")
    if not out:
        out.append("  DECODED CONTENT IS IDENTICAL -- difference is container"
                   " bytes only (compression/metadata), not data.")
    return out


def main() -> int:
    a, b = Path(sys.argv[1]), Path(sys.argv[2])
    if not a.is_dir() or not b.is_dir():
        print(f"missing directory: {a if not a.is_dir() else b}")
        return 2

    names_a = {p.relative_to(a).as_posix() for p in a.rglob("*") if p.is_file()}
    names_b = {p.relative_to(b).as_posix() for p in b.rglob("*") if p.is_file()}

    only_a, only_b = sorted(names_a - names_b), sorted(names_b - names_a)
    failures = 0

    if only_a or only_b:
        failures += len(only_a) + len(only_b)
        print(f"FILE SET DIFFERS: only in A: {len(only_a)}  only in B: {len(only_b)}")
        for n in (only_a + only_b)[:10]:
            print(f"  {n}")

    common = sorted(names_a & names_b)
    transcripts = [n for n in common if n.startswith("call_transcripts/")]
    others = [n for n in common if not n.startswith("call_transcripts/")]

    for n in others:
        pa, pb = a / n, b / n
        if n.endswith("manifest.json"):
            ja = json.loads(pa.read_text())
            jb = json.loads(pb.read_text())
            ja.pop("generated_at", None)
            jb.pop("generated_at", None)
            for d in (ja, jb):
                if isinstance(d.get("generator"), dict):
                    d["generator"].pop("generated_at", None)
                    d["generator"].pop("timestamp", None)
            same = json.dumps(ja, sort_keys=True) == json.dumps(jb, sort_keys=True)
            print(f"{'OK  ' if same else 'FAIL'}  {n}  (timestamp-insensitive)")
            if not same:
                failures += 1
                ka = {k: json.dumps(v, sort_keys=True) for k, v in ja.items()}
                kb = {k: json.dumps(v, sort_keys=True) for k, v in jb.items()}
                for k in sorted(set(ka) | set(kb)):
                    if ka.get(k) != kb.get(k):
                        print(f"    key {k!r}:")
                        print(f"      A: {ka.get(k, '<absent>')[:300]}")
                        print(f"      B: {kb.get(k, '<absent>')[:300]}")
            continue

        ha, hb = sha(pa), sha(pb)
        if ha == hb:
            print(f"OK    {n}")
            continue
        failures += 1
        print(f"FAIL  {n}")
        if n.endswith(".parquet"):
            for line in parquet_diff(pa, pb):
                print(line)
        else:
            la = pa.read_text(errors="replace").splitlines()
            lb = pb.read_text(errors="replace").splitlines()
            if len(la) != len(lb):
                print(f"  line count differs: A={len(la)} B={len(lb)}")
            diffs = [i for i, (x, y) in enumerate(zip(la, lb)) if x != y]
            print(f"  {len(diffs)} of {min(len(la), len(lb))} common lines differ")
            for i in diffs[:3]:
                print(f"    line {i + 1}:")
                print(f"      A: {la[i][:300]}")
                print(f"      B: {lb[i][:300]}")

    tdiff = [n for n in transcripts if sha(a / n) != sha(b / n)]
    if tdiff:
        failures += len(tdiff)
        print(f"FAIL  call_transcripts/  {len(tdiff)} of {len(transcripts)} files differ")
        for n in tdiff[:3]:
            print(f"    {n}")
    else:
        print(f"OK    call_transcripts/  ({len(transcripts)} files identical)")

    print()
    print("DETERMINISM GATE: " + ("PASS" if failures == 0 else f"FAIL ({failures} differing objects)"))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
