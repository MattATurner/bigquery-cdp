#!/usr/bin/env python3
"""Google ADK Identity Resolution Explainer Agent (`cdp_explainer`).

Provides data stewards, privacy officers, and customer-care teams with
deterministic, auditable explanations of why two customer records were merged
or kept separate across `baseline_cc`, `weighted_cc`, and `composable_cdp`.

Can be run via `adk web demo/agents` or invoked directly from the CLI:
  python3 demo/agents/explainer_agent/agent.py --explain-component PER-1cdfdb9f52ddb25a
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

PROJECT = os.environ.get("CDP_PROJECT", "all-things-cdp")
DATASET = os.environ.get("CDP_DS", "cdp")
MODEL = os.environ.get("CDP_ADK_MODEL", "gemini-2.5-flash")


def _run_query(sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    from google.cloud import bigquery

    client = bigquery.Client(project=PROJECT)
    job_config = bigquery.QueryJobConfig(query_parameters=params or [])
    rows = client.query(sql, job_config=job_config).result()
    return [dict(row.items()) for row in rows]


def lookup_profile(record_id: str) -> dict[str, Any]:
    """Look up a source profile, its attached identifiers & IDF weights, and its cluster IDs across all 3 methods."""
    from google.cloud import bigquery

    sql_profile = f"""
    SELECT
      p.record_id,
      p.sources AS source_system,
      pr.raw_name AS full_name,
      CAST(pr.dob AS STRING) AS dob,
      pr.raw_address AS address,
      p.baseline_wesid,
      p.weighted_wesid,
      p.composable_wesid,
      p.baseline_hairball_flag,
      p.weighted_hairball_flag,
      p.composable_hairball_flag
    FROM `{PROJECT}.{DATASET}.sem_profile` AS p
    LEFT JOIN `{PROJECT}.{DATASET}.party_records` AS pr USING (record_id)
    WHERE p.record_id = @record_id
    """
    sql_ids = f"""
    SELECT
      i.identifier_id,
      i.identifier_type,
      i.degree,
      ROUND(i.idf_weight, 3) AS idf_weight,
      i.is_promiscuous
    FROM `{PROJECT}.{DATASET}.has_identifier` AS h
    JOIN `{PROJECT}.{DATASET}.identifier` AS i USING (identifier_id)
    WHERE h.record_id = @record_id
    ORDER BY i.idf_weight DESC
    """
    param = [bigquery.ScalarQueryParameter("record_id", "STRING", record_id)]
    profile_rows = _run_query(sql_profile, param)
    id_rows = _run_query(sql_ids, param)
    return {
        "record_id": record_id,
        "profile": profile_rows[0] if profile_rows else None,
        "identifiers": id_rows,
    }


def explain_link(record_id_a: str, record_id_b: str) -> dict[str, Any]:
    """Explain why two source records were linked, rejected, or pruned by the Pass-2 Contradiction Guard."""
    from google.cloud import bigquery

    a, b = sorted([record_id_a, record_id_b])
    sql = f"""
    SELECT
      t.record_id_a,
      t.record_id_b,
      t.a_name,
      t.b_name,
      t.retrieved_by,
      t.strong_signals,
      ROUND(t.idf_weight_sum, 3) AS idf_weight_sum,
      t.min_shared_degree,
      t.via_hub,
      t.hub_only,
      t.unshared_email_both,
      t.unshared_phone_both,
      t.unshared_acct_both,
      t.forename_conflict,
      t.dob_conflict,
      ROUND(t.rule_score, 3) AS rule_score,
      ROUND(t.similarity, 3) AS semantic_similarity,
      ROUND(t.combined_score, 3) AS combined_score,
      t.tier,
      t.tier_reason,
      d.decision AS pair_decision,
      d.decided_by,
      ROUND(d.confidence, 3) AS decision_confidence,
      d.rationale AS llm_rationale,
      e.suppressed_by_contradiction
    FROM `{PROJECT}.{DATASET}.pair_tiers` AS t
    LEFT JOIN `{PROJECT}.{DATASET}.match_decisions` AS d USING (record_id_a, record_id_b)
    LEFT JOIN `{PROJECT}.{DATASET}.resolution_edges` AS e USING (record_id_a, record_id_b)
    WHERE t.record_id_a = @a AND t.record_id_b = @b
    """
    params = [
        bigquery.ScalarQueryParameter("a", "STRING", a),
        bigquery.ScalarQueryParameter("b", "STRING", b),
    ]
    rows = _run_query(sql, params)
    return {"record_id_a": a, "record_id_b": b, "pair_explanation": rows[0] if rows else None}


def explain_component(person_id: str) -> dict[str, Any]:
    """Explain a resolved Golden Person cluster: member records, edges, field survivorship, and consent state."""
    from google.cloud import bigquery

    param = [bigquery.ScalarQueryParameter("pid", "STRING", person_id)]
    golden = _run_query(
        f"SELECT * FROM `{PROJECT}.{DATASET}.golden_person` WHERE person_id = @pid",
        param,
    )
    members = _run_query(
        f"""
        SELECT pr.record_id, pr.source_system, pr.source_trust,
               pr.raw_name, pr.email_norm, pr.phone_e164, pr.postcode_norm, pr.account_number
        FROM `{PROJECT}.{DATASET}.person_assignment` AS pa
        JOIN `{PROJECT}.{DATASET}.party_records` AS pr USING (record_id)
        WHERE pa.person_id = @pid
        ORDER BY pr.source_trust DESC, pr.record_id
        """,
        param,
    )
    contested = _run_query(
        f"""
        SELECT field, surviving_value, won_from_source, source_trust,
               distinct_values, was_contested, provenance
        FROM `{PROJECT}.{DATASET}.field_survivorship`
        WHERE person_id = @pid
        ORDER BY was_contested DESC, field
        """,
        param,
    )
    consent = _run_query(
        f"""
        SELECT channel, purpose, effective_status, naive_union_status, suppressed, explanation
        FROM `{PROJECT}.{DATASET}.person_consent`
        WHERE person_id = @pid
        ORDER BY channel, purpose
        """,
        param,
    )
    return {
        "person_id": person_id,
        "golden_person": golden[0] if golden else None,
        "member_records": members,
        "field_survivorship": contested,
        "person_consent": consent,
    }


def identifier_report(identifier_id: str) -> dict[str, Any]:
    """Inspect a Bipartite Graph identifier node (degree, IDF weight, promiscuity) and attached records."""
    from google.cloud import bigquery

    param = [bigquery.ScalarQueryParameter("iid", "STRING", identifier_id)]
    node = _run_query(
        f"""
        SELECT identifier_id, identifier_type, degree, degree_all_time,
               ROUND(idf_weight, 3) AS idf_weight, is_promiscuous, sources
        FROM `{PROJECT}.{DATASET}.identifier`
        WHERE identifier_id = @iid
        """,
        param,
    )
    attached = _run_query(
        f"""
        SELECT h.record_id, h.sources, h.is_current,
               CAST(h.from_ts AS STRING) AS valid_from,
               CAST(h.to_ts AS STRING) AS valid_to,
               pr.raw_name, pa.person_id
        FROM `{PROJECT}.{DATASET}.has_identifier_history` AS h
        JOIN `{PROJECT}.{DATASET}.party_records` AS pr USING (record_id)
        LEFT JOIN `{PROJECT}.{DATASET}.person_assignment` AS pa USING (record_id)
        WHERE h.identifier_id = @iid
        ORDER BY h.is_current DESC, h.record_id
        LIMIT 25
        """,
        param,
    )
    return {
        "identifier_id": identifier_id,
        "identifier_node": node[0] if node else None,
        "attached_records_sample": attached,
    }


def resolution_runs() -> dict[str, Any]:
    """Return the 3-method graph topology summary and pairwise precision/recall scorecard."""
    runs = _run_query(
        f"""
        SELECT method, threshold, n_profiles, n_components,
               largest_component, n_hairballs, profiles_in_hairballs
        FROM `{PROJECT}.{DATASET}.resolution_runs`
        ORDER BY CASE method WHEN 'baseline_cc' THEN 1 WHEN 'weighted_cc' THEN 2 ELSE 3 END
        """
    )
    scorecard = _run_query(
        f"""
        SELECT pair_class AS pathology, method, tp, fp, fn,
               ROUND(precision, 4) AS precision,
               ROUND(recall, 4) AS recall,
               ROUND(f1, 4) AS f1
        FROM `{PROJECT}.{DATASET}.v_method_comparison`
        WHERE pair_class IN ('ALL', 'hub', 'household', 'supersession', 'semantic_fuzzy')
        ORDER BY pair_class, method
        """
    )
    return {"resolution_runs": runs, "method_comparison": scorecard}


AGENT_INSTRUCTION = """You are the Composable CDP Identity Resolution Explainer Agent (`cdp_explainer`).
Your job is to give data stewards, privacy officers, and engineers exact, evidence-backed explanations
of how customer identity records were resolved in BigQuery.

Always follow these rules:
1. Never guess or hallucinate record IDs, scores, or rationales — always call one of your deterministic tools:
   - `lookup_profile(record_id)`
   - `explain_link(record_id_a, record_id_b)`
   - `explain_component(person_id)`
   - `identifier_report(identifier_id)`
   - `resolution_runs()`
2. Explain clearly how Composable CDP combines:
   - 1-hop Bipartite Identifier Graph Rarity (`idf_weight = LN(1 + N / degree)`, `is_promiscuous` for degree > 25)
   - 2-hop Neighbourhood Features (`unshared_email_both`, `unshared_phone_both`, `forename_conflict`)
   - Hybrid Search (`AI.SEARCH` / `VECTOR_SEARCH` + Reciprocal Rank Fusion)
   - Gemini 2.5 Flash grey-zone adjudication (`AI.GENERATE`)
   - Pass-2 Transitive Contradiction Pruning (`suppressed_by_contradiction`)
3. Always refer to governance metadata and business glossaries as BigQuery Knowledge Catalog.
"""

try:
    from google.adk.agents import Agent

    root_agent = Agent(
        name="cdp_explainer",
        model=MODEL,
        description="Explains Composable CDP identity resolution links, clusters, survivorship, and consent.",
        instruction=AGENT_INSTRUCTION,
        tools=[
            lookup_profile,
            explain_link,
            explain_component,
            identifier_report,
            resolution_runs,
        ],
    )
except ImportError:
    root_agent = None


def main() -> None:
    parser = argparse.ArgumentParser(description="Composable CDP ADK Explainer Agent CLI")
    parser.add_argument("--lookup-profile", type=str, help="Inspect a profile_id / record_id")
    parser.add_argument("--explain-link", nargs=2, metavar=("REC_A", "REC_B"), help="Explain a candidate pair")
    parser.add_argument("--explain-component", type=str, help="Explain a resolved person_id")
    parser.add_argument("--identifier-report", type=str, help="Inspect an identifier_id (e.g. EM:...)")
    parser.add_argument("--resolution-runs", action="store_true", help="Compare all 3 resolution methods")
    args = parser.parse_args()

    if args.lookup_profile:
        print(json.dumps(lookup_profile(args.lookup_profile), indent=2, default=str))
    elif args.explain_link:
        print(json.dumps(explain_link(args.explain_link[0], args.explain_link[1]), indent=2, default=str))
    elif args.explain_component:
        print(json.dumps(explain_component(args.explain_component), indent=2, default=str))
    elif args.identifier_report:
        print(json.dumps(identifier_report(args.identifier_report), indent=2, default=str))
    else:
        print(json.dumps(resolution_runs(), indent=2, default=str))


if __name__ == "__main__":
    main()
