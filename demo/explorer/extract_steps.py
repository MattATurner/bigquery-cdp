#!/usr/bin/env python3
"""Capture WHAT EACH STAGE ACTUALLY RAN in BigQuery, and the volumes in and out.

The results views tell you the outcome of a stage but not the work it did. This
adds, per stage:

  steps    every statement the stage executes, in order, with the object it
           targets and what kind of operation it is
  inputs   the objects the stage READS that it did not create, with live row
           counts -- the "before" side
  outputs  the objects the stage CREATES, with live row counts, bytes and last
           modified time -- the "after" side

Plus a pipeline-level funnel: records in, pairs considered, pairs surviving each
tier, verdicts, clusters out.

Writes demo/explorer/steps.json. Read-only against BigQuery.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent
SQL = DEMO / "sql"
CONFIG = DEMO / "config.env"

# Statement forms this pipeline uses, in the order we try them.
STMT = [
    (r"CREATE\s+SCHEMA\s+IF\s+NOT\s+EXISTS\s+`([^`]+)`", "create schema", "schema"),
    (r"CREATE\s+OR\s+REPLACE\s+TABLE\s+FUNCTION\s+`([^`]+)`", "create table function", "routine"),
    (r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+`([^`]+)`", "create function", "routine"),
    (r"CREATE\s+OR\s+REPLACE\s+PROCEDURE\s+`([^`]+)`", "create procedure", "routine"),
    (r"CREATE\s+OR\s+REPLACE\s+VIEW\s+`([^`]+)`", "create view", "view"),
    (r"CREATE\s+OR\s+REPLACE\s+EXTERNAL\s+TABLE\s+`([^`]+)`", "create external table", "table"),
    (r"CREATE\s+OR\s+REPLACE\s+TABLE\s+`([^`]+)`", "create table", "table"),
    (r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+`([^`]+)`", "create table if absent", "table"),
    (r"CREATE\s+OR\s+REPLACE\s+TEMP\s+TABLE\s+(\w+)", "create temp table", "temp"),
    (r"LOAD\s+DATA\s+OVERWRITE\s+`([^`]+)`", "load data", "table"),
    (r"CREATE\s+VECTOR\s+INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)", "create vector index", "index"),
    (r"CREATE\s+SEARCH\s+INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)", "create search index", "index"),
    (r"INSERT\s+INTO\s+`([^`]+)`", "insert into", "table"),
    (r"MERGE\s+(?:INTO\s+)?`([^`]+)`", "merge into", "table"),
    (r"CALL\s+`([^`]+)`", "call procedure", "routine"),
]
ASSERT_RE = re.compile(r"^\s*ASSERT\s", re.M | re.I)
REF_RE = re.compile(r"(?:FROM|JOIN)\s+`([^`]+)`", re.I)


def cfg() -> dict:
    out = {}
    p = CONFIG if CONFIG.exists() else CONFIG.with_name("config.env.example")
    if not p.exists():
        return out
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r'^([A-Z_]+)=["\']?([^"\'#]*)["\']?(?:\s*#.*)?$', line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


_TOKEN_RE = re.compile(
    r"""('''[\s\S]*?'''|\"\"\"[\s\S]*?\"\"\"|'[^'\\]*(?:\\.[^'\\]*)*'|"[^"\\]*(?:\\.[^"\\]*)*"|`[^`]*`|--[^\n]*)""",
    re.S,
)


def strip_comments(sql: str) -> str:
    return _TOKEN_RE.sub(lambda m: "" if m.group(0).startswith("--") else m.group(0), sql)


def split_statements(sql: str) -> list[str]:
    stmts = []
    start = 0
    in_quote = None
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        if in_quote:
            if ch == "\\" and in_quote in ("'", '"'):
                i += 2
                continue
            if sql.startswith(in_quote, i):
                i += len(in_quote)
                in_quote = None
                continue
            i += 1
        else:
            if sql.startswith("'''", i) or sql.startswith('"""', i):
                in_quote = sql[i:i+3]
                i += 3
            elif ch in ("'", '"', "`"):
                in_quote = ch
                i += 1
            elif ch == ";":
                frag = sql[start:i+1].strip()
                if frag:
                    stmts.append(frag)
                start = i + 1
                i += 1
            else:
                i += 1
    tail = sql[start:].strip()
    if tail:
        stmts.append(tail)
    return stmts


def short(name: str) -> str:
    return name.split(".")[-1]


def main() -> int:
    c = cfg()
    proj = c.get("CDP_PROJECT", "")
    ds = c.get("CDP_DS", "cdp")
    dst = c.get("CDP_DS_TRUTH", "cdp_truth")
    loc = c.get("CDP_LOCATION", "US")

    # Live table metadata for both datasets.
    meta = {}
    if proj:
        for d in (ds, dst):
            p = subprocess.run(
                ["bq", "query", f"--project_id={proj}", f"--location={loc}",
                 "--use_legacy_sql=false", "--format=prettyjson", "--quiet", "--max_rows", "500",
                 f"SELECT table_id, row_count, size_bytes, "
                 f"CAST(TIMESTAMP_MILLIS(last_modified_time) AS STRING) AS modified "
                 f"FROM `{proj}.{d}.__TABLES__`"],
                capture_output=True, text=True, timeout=300)
            if p.returncode == 0:
                for r in json.loads(p.stdout or "[]"):
                    meta[r["table_id"]] = {
                        "rows": int(r["row_count"]), "bytes": int(r["size_bytes"]),
                        "modified": r["modified"], "dataset": d,
                    }
            else:
                print(f"warn: bq query for {proj}.{d} exited {p.returncode}: {p.stderr.strip()}", file=sys.stderr)

    stages = []
    for f in sorted(SQL.glob("[0-9]*.sql")):
        raw = f.read_text(encoding="utf-8")
        body = strip_comments(raw)

        steps, created = [], set()
        for frag in split_statements(body):
            matched = False
            for pat, label, kind in STMT:
                mm = re.search(pat, frag, re.I)
                if mm:
                    obj = short(mm.group(1))
                    steps.append({"op": label, "object": obj, "kind": kind,
                                  "rows": meta.get(obj, {}).get("rows")})
                    if kind in ("table", "view", "temp"):
                        created.add(obj)
                    matched = True
                    break
            if not matched and ASSERT_RE.search(frag):
                steps.append({"op": "assert", "object": "—", "kind": "assert",
                              "rows": None})

        refs = {short(r) for r in REF_RE.findall(body)}
        inputs = sorted(r for r in refs - created if r in meta)

        stages.append({
            "id": f.stem,
            "num": f.stem.split("_")[0],
            "statements": len(steps),
            "steps": steps,
            "inputs": [{"object": i, **meta[i]} for i in inputs],
            "outputs": [{"object": o, **meta[o]} for o in sorted(created) if o in meta],
        })
        print(f"  {f.stem:22} {len(steps):>3} statements  "
              f"{len(inputs):>2} in  {len([o for o in created if o in meta]):>2} out")

    # ---- pipeline funnel, assembled only from figures that exist ----
    def scalar(sql):
        p = subprocess.run(
            ["bq", "query", f"--project_id={proj}", f"--location={c['CDP_LOCATION']}",
             "--use_legacy_sql=false", "--format=csv", "--quiet", sql],
            capture_output=True, text=True, timeout=300)
        if p.returncode != 0:
            return None
        lines = [l for l in p.stdout.strip().splitlines() if l]
        try:
            return int(lines[-1])
        except (ValueError, IndexError):
            return None

    funnel = []
    for label, sql, note in [
        ("Source records landed", f"SELECT COUNT(*) FROM `{proj}.{ds}.party_records`",
         "every row from the eight sources, normalised"),
        ("Pairs considered", f"SELECT COUNT(*) FROM `{proj}.{ds}.pair_tiers`",
         "after blocking cut the full cross product"),
        ("Auto-matched on rules", f"SELECT COUNT(*) FROM `{proj}.{ds}.pair_tiers` WHERE tier='AUTO_MATCH'",
         "no LLM involved"),
        ("Sent to the adjudicator", f"SELECT COUNT(*) FROM `{proj}.{ds}.pair_tiers` WHERE tier='GREY_ZONE'",
         "the only pairs that cost model spend"),
        ("Rejected before the LLM", f"SELECT COUNT(*) FROM `{proj}.{ds}.pair_tiers` WHERE tier='REJECT'",
         "scored or ruled out"),
        ("Adjudicated MATCH", f"SELECT COUNT(*) FROM `{proj}.{ds}.v_adjudications_current` WHERE verdict='MATCH'",
         "LLM agreed they are the same person"),
        ("Resolved people", f"SELECT COUNT(DISTINCT person_id) FROM `{proj}.{ds}.person_assignment`",
         "clusters published"),
        ("True people (ground truth)", f"SELECT COUNT(DISTINCT true_person_id) FROM `{proj}.{dst}.person_truth`",
         "what the answer should have been"),
    ]:
        v = scalar(sql)
        if v is not None:
            funnel.append({"label": label, "value": v, "note": note})
            print(f"  funnel: {label:28} {v:>12,}")

    out = {"stages": stages, "funnel": funnel}
    (HERE / "steps.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\n  wrote {HERE / 'steps.json'} "
          f"({(HERE / 'steps.json').stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
