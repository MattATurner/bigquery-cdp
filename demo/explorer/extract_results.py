#!/usr/bin/env python3
"""Pull everything the stage explorer needs out of BigQuery into one JSON.

Reads config.env for the project/dataset, queries the result views each stage
produces, and pairs them with that stage's SQL source. Re-run after any
pipeline run to refresh the explorer:

    python3 demo/explorer/extract_results.py
    python3 demo/explorer/build_explorer.py

Emits demo/explorer/results.json. Every query is read-only.
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

# stage -> (title, plain-English summary, [result view or table names])
STAGES: dict[str, tuple[str, str, list[str]]] = {
    "00_setup": ("Setup", "Creates the working dataset and a separate ground-truth "
                 "dataset the pipeline is never allowed to read, plus the "
                 "normalisation UDFs everything downstream depends on.", []),
    "05_preflight": ("Preflight", "Calls each AI model once before any data is "
                     "touched, so a wrong model id or a missing IAM grant fails "
                     "in seconds instead of an hour in.", ["v_preflight"]),
    "10_land_sources": ("Land sources", "Pulls eight messy sources into BigQuery — "
                        "managed tables, external CSV/Parquet/JSONL, and an object "
                        "table over the call recordings.", ["v_source_profile"]),
    "20_normalise": ("Normalise + extract", "Standardises names, addresses and "
                     "phones, and reads the unstructured sources — call transcripts "
                     "and ticket bodies — with AI to pull identities out of free "
                     "text.", ["v_extraction_audit", "v_injection_guard"]),
    "30_embed": ("Embed", "Generates an identity vector per record via a generated "
                 "column. Embeddings are asynchronous by necessity, so run.sh waits "
                 "for them before continuing.", ["v_embedding_health"]),
    "35_embed_finalise": ("Index", "Builds the hybrid TREE_AH index for live lookup "
                          "and a separate IVF index for the bulk all-pairs join.", []),
    "40_block": ("Block", "Cuts the comparison space from every possible pair to "
                 "those sharing a blocking key.", ["v_blocking_funnel"]),
    "50_candidates": ("Candidates", "Runs both retrieval legs, fuses them with "
                      "reciprocal rank fusion, scores each pair and tiers it: "
                      "auto-match, grey zone, or reject.",
                      ["v_candidate_funnel", "v_retrieval_legs", "v_retrieval_recall"]),
    "60_adjudicate": ("Adjudicate", "Sends only grey-zone pairs to an LLM. This is "
                      "the expensive stage, which is why the tiering above it "
                      "matters so much.", ["v_adjudication_summary"]),
    "70_graph": ("Graph", "Builds the identity graph and resolves clusters, then "
                 "rechecks any cluster that contradicts itself rather than trusting "
                 "transitive closure.", ["v_graph_summary", "v_cluster_sizes"]),
    "80_survivorship": ("Survivorship", "Picks the winning value per field when "
                        "sources disagree, weighted by source trust.",
                        ["v_survivorship_by_source"]),
    "85_consent": ("Consent", "Recomputes permissions at profile level. Merging two "
                   "records never merges their consent.",
                   ["v_consent_impact", "v_consent_conflicts"]),
    "90_downstream": ("Downstream", "The outputs: segments, households, shared-"
                      "identifier risk, agent grounding and activation audiences.",
                      ["v_household_waste", "v_shared_identifiers",
                       "v_activation_before_after"]),
    "95_scorecard": ("Scorecard", "Marks its own homework against ground truth, per "
                     "hard case, with a diagnosis of where each failure occurred.",
                     ["v_scorecard", "v_case_results", "v_failures"]),
    "96_cost_model": ("Cost model", "Measured token counts and bytes billed, "
                      "extrapolated to the customer's real volume.",
                      ["v_cost_model", "v_cost_compute", "v_cost_sensitivity"]),
}

MAX_ROWS = 60


def cfg() -> dict[str, str]:
    p = CONFIG if CONFIG.exists() else CONFIG.with_name("config.env.example")
    if not p.exists():
        sys.exit("No demo/config.env — run ./setup.sh first.")
    out = {}
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r'^([A-Z_]+)=["\']?([^"\'#]*)["\']?(?:\s*#.*)?$', line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def query(c: dict[str, str], sql: str):
    p = subprocess.run(
        ["bq", "query", f"--project_id={c['CDP_PROJECT']}",
         f"--location={c['CDP_LOCATION']}", "--use_legacy_sql=false",
         "--format=prettyjson", "--quiet", "--max_rows", str(MAX_ROWS), sql],
        capture_output=True, text=True, timeout=300)
    if p.returncode != 0:
        print(f"warn: bq query failed (exit {p.returncode}): {p.stderr.strip()}", file=sys.stderr)
        return None
    try:
        return json.loads(p.stdout or "[]")
    except json.JSONDecodeError:
        return None


def main() -> int:
    c = cfg()
    ds = f"{c['CDP_PROJECT']}.{c['CDP_DS']}"
    out = {
        "project": c["CDP_PROJECT"],
        "dataset": c["CDP_DS"],
        "location": c["CDP_LOCATION"],
        "corpus": {"records": c.get("CDP_RECORDS"), "people": c.get("CDP_PEOPLE"),
                   "seed": c.get("CDP_SEED")},
        "models": {"embedding": c.get("CDP_EMBEDDING_ENDPOINT"),
                   "extraction": c.get("CDP_EXTRACTION_MODEL"),
                   "adjudicator": c.get("CDP_ADJUDICATOR_MODEL")},
        "thresholds": {k: c.get(k) for k in
                       ("CDP_TAU_HI", "CDP_TAU_LO", "CDP_TAU_LOW_IDENTITY",
                        "CDP_TAU_SINGLE_SIGNAL", "CDP_ACCEPT_CONFIDENCE",
                        "CDP_STEWARD_CONFIDENCE", "CDP_GREYZONE_CAP")},
        "stages": [],
    }

    for key, (title, blurb, views) in STAGES.items():
        src = (SQL / f"{key}.sql")
        stage = {
            "id": key,
            "num": key.split("_")[0],
            "title": title,
            "summary": blurb,
            "sql": src.read_text(encoding="utf-8") if src.exists() else "",
            "sql_lines": len(src.read_text(encoding="utf-8").splitlines()) if src.exists() else 0,
            "results": [],
        }
        for v in views:
            rows = query(c, f"SELECT * FROM `{ds}.{v}`")
            if rows is None:
                stage["results"].append({"view": v, "error": "not available"})
            else:
                stage["results"].append({
                    "view": v,
                    "columns": list(rows[0].keys()) if rows else [],
                    "rows": rows,
                    "row_count": len(rows),
                })
            print(f"  {key:22} {v:28} "
                  f"{'-' if rows is None else str(len(rows)) + ' rows'}")
        out["stages"].append(stage)

    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str),
                                       encoding="utf-8")
    size = (HERE / "results.json").stat().st_size
    print(f"\n  wrote {HERE / 'results.json'} ({size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
