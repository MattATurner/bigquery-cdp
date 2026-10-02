#!/usr/bin/env python3
"""Refresh every notebook's pre-populated outputs from LIVE BigQuery.

build_all.py generates the notebook structure (markdown + code). This script
then re-executes every `%%bigquery` cell's SQL against the configured project
and rewrites that cell's output table, so the figures shown in GitHub / VS Code
are always the figures the pipeline actually produced -- never hand-typed.

    python3 demo/notebooks/builders/build_all.py
    demo/.venv-nb/bin/python demo/notebooks/builders/refresh_outputs.py

`%%bigquery --graph` cells are skipped (they only render inside BigQuery
Studio). Plain Python cells keep their generated output, except the subject
announcement in notebook 01, which is regenerated from the live subject row.

Writes a summary of the headline figures to builders/live_snapshot.json so the
narrative text can be checked against the same numbers.

    --dry-run   validate every cell's SQL with a BigQuery dry run (free) and
                report failures, without touching the notebooks.

Any cell whose SQL fails keeps its previous output; failures are listed at
the end and the script exits non-zero.
"""

from __future__ import annotations

import datetime as dt
import decimal
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NOTEBOOKS_DIR = HERE.parent
DEMO_DIR = NOTEBOOKS_DIR.parent
sys.path.insert(0, str(HERE))

from build_all import df_to_output  # noqa: E402

TARGETS = [
    NOTEBOOKS_DIR / "01_identity_resolution_story.ipynb",
    NOTEBOOKS_DIR / "02_graph_pathology_and_rarity.ipynb",
    NOTEBOOKS_DIR / "03_hybrid_search_and_2hop_features.ipynb",
    NOTEBOOKS_DIR / "04_llm_adjudicator_and_contradiction_guard.ipynb",
    NOTEBOOKS_DIR / "05_semantic_graph_governance_and_roi.ipynb",
    NOTEBOOKS_DIR / "bigquery_studio" / "act2_hybrid_search_llm_and_scorecard.ipynb",
]
MAX_ROWS = 30
CAPTION_RE = re.compile(r"<div style='font-weight:600[^>]*>(.*?)</div>", re.S)


def load_config() -> dict[str, str]:
    cfg: dict[str, str] = {}
    path = DEMO_DIR / "config.env"
    if not path.exists():
        return cfg
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.split("#", 1)[0].strip().strip('"').strip("'")
    return cfg


def fmt(v: object) -> object:
    if v is None:
        return None
    if isinstance(v, float):
        return round(v, 4)
    if isinstance(v, decimal.Decimal):
        return str(v)
    if isinstance(v, (dt.date, dt.datetime, dt.time)):
        return v.isoformat()
    if isinstance(v, (list, dict)):
        return json.dumps(v, default=str)
    return v


def old_caption(cell: dict) -> str | None:
    for out in cell.get("outputs", []):
        html = "".join(out.get("data", {}).get("text/html", []))
        m = CAPTION_RE.search(html)
        if m:
            return m.group(1)
    return None


def main() -> int:
    from google.cloud import bigquery

    cfg = load_config()
    project = cfg.get("CDP_PROJECT", "all-things-cdp")
    dataset = cfg.get("CDP_DS", "cdp")
    location = cfg.get("CDP_LOCATION", "US")
    client = bigquery.Client(project=project, location=location)

    dry_run = "--dry-run" in sys.argv
    state: dict[str, object] = {}
    snapshot: dict[str, list[dict]] = {}
    failures: list[str] = []

    targets = TARGETS + ([NOTEBOOKS_DIR / "bigquery_studio" / "act1_bipartite_graph_and_hairball.ipynb"]
                         if dry_run else [])
    for nb_path in targets:
        nb = json.loads(nb_path.read_text(encoding="utf-8"))
        refreshed = 0
        for cell in nb["cells"]:
            if cell["cell_type"] != "code":
                continue
            src = "".join(cell["source"])
            first, _, sql = src.partition("\n")

            if cell.get("id") == "nb01-subject-params" and "subject" in state:
                s = state["subject"]
                text = (f"Following {s['full_name']} ({s['person_id']}) across "
                        f"{s['n_records']} records in {s['sources']}\n")
                cell["outputs"] = [{"output_type": "stream", "name": "stdout",
                                    "text": [text]}]
                continue

            if not first.startswith("%%bigquery"):
                continue
            # Graph cells only render in BigQuery Studio, but their SQL can
            # still be validated.
            if "--graph" in first and not dry_run:
                continue

            parts = first.split()
            var = parts[1] if len(parts) > 1 and not parts[1].startswith("--") else None
            params = []
            if "--params" in parts:
                pid = state.get("pid", "PER-0000000000000000")
                params = [bigquery.ScalarQueryParameter("pid", "STRING", pid)]

            sql = sql.replace("`cdp.", f"`{project}.{dataset}.")
            label = f"{nb_path.name}:{cell.get('id')}"
            try:
                job = client.query(sql, job_config=bigquery.QueryJobConfig(
                    query_parameters=params, dry_run=dry_run))
                if dry_run:
                    refreshed += 1
                    continue
                result = job.result()
            except Exception as exc:  # noqa: BLE001 -- report every failing cell
                msg = getattr(exc, "message", None) or str(exc).splitlines()[0]
                failures.append(f"{label}: {msg}")
                continue
            headers = [f.name for f in result.schema]
            rows = [dict(r.items()) for r in result]

            if var == "df_subject" and rows:
                state["subject"] = rows[0]
                state["pid"] = rows[0]["person_id"]

            snapshot[f"{nb_path.stem}:{var or cell.get('id')}"] = [
                {k: fmt(v) for k, v in r.items()} for r in rows
            ]
            table = [[fmt(r[h]) for h in headers] for r in rows[:MAX_ROWS]]
            plain, html = df_to_output(headers, table, caption=old_caption(cell))
            ec = cell.get("execution_count") or 1
            cell["outputs"] = [{
                "output_type": "execute_result",
                "execution_count": ec,
                "data": {"text/plain": [plain], "text/html": [html]},
                "metadata": {},
            }]
            refreshed += 1

        if not dry_run:
            nb_path.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        verb = "validated" if dry_run else "refreshed"
        print(f"  {verb} {refreshed:>2} cells  {nb_path.relative_to(DEMO_DIR.parent)}")

    if failures:
        print(f"\n  {len(failures)} cell(s) FAILED:")
        for f in failures:
            print(f"    - {f}")
    if dry_run:
        return 1 if failures else 0

    out = HERE / "live_snapshot.json"
    out.write_text(json.dumps(snapshot, indent=1, default=str), encoding="utf-8")
    print(f"  wrote {out.relative_to(DEMO_DIR.parent)}")
    if "subject" in state:
        s = state["subject"]
        print(f"  subject: {s['full_name']} ({s['person_id']})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
