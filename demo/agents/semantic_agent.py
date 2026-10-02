#!/usr/bin/env python3
"""BigQuery Conversational Analytics Data Agent for Composable CDP.

Configures and queries a Conversational Analytics Data Agent grounded on the
declarative Semantic Property Graph (`cdp.cdp_semantic_graph`) and the 3-method
evaluation views (`v_scorecard`, `v_method_comparison`, `v_case_results`,
`v_consent_impact`, `v_cost_model`).

Business terminology is aligned with BigQuery Knowledge Catalog glossaries so
natural-language questions automatically compile into fan-out-free
`FROM GRAPH_EXPAND("...")` + `AGG()` queries.

Usage:
  python3 demo/agents/semantic_agent.py --project all-things-cdp --dataset cdp \
    --ask "Compare baseline_cc, weighted_cc, and composable_cdp cluster counts and hairballs by brand"
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class GlossaryEntry:
    term: str
    definition: str
    canonical_sql_expression: str


@dataclass(frozen=True)
class GoldenQuery:
    question: str
    sql: str


def build_knowledge_catalog_glossary(project: str, dataset: str) -> list[GlossaryEntry]:
    """Return Knowledge Catalog business glossary terms for the CDP Semantic Graph."""
    return [
        GlossaryEntry(
            term="Composable ID (person_id / composable_wesid)",
            definition=(
                "The resolved customer entity ID produced by Composable CDP "
                "(2-Hop Bipartite Graph Rarity + Hybrid Search + Gemini 3.5 Flash "
                "Adjudication + Pass-2 Contradiction Guard)."
            ),
            canonical_sql_expression="AGG(Profile_composable_wesid_count)",
        ),
        GlossaryEntry(
            term="Hairball",
            definition=(
                "A pathological connected component containing more than 30 source "
                "profiles, caused by transitive bridging across promiscuous store-kiosk "
                "or service-desk hub identifiers."
            ),
            canonical_sql_expression="AGG(Profile_profiles_in_baseline_hairballs)",
        ),
        GlossaryEntry(
            term="Promiscuous Hub Identifier",
            definition=(
                "An email, phone, or device identifier shared by more than 25 source "
                "profiles (e.g., store checkout kiosks or contact-centre fallback numbers) "
                "with low Inverse Document Frequency weight."
            ),
            canonical_sql_expression="AGG(Identifier_promiscuous_identifier_count)",
        ),
        GlossaryEntry(
            term="Intersection Consent",
            definition=(
                "Australian Privacy Act 1988 compliance rule (Stage 85) where any explicit "
                "WITHDRAWN assertion across a resolved person's source records overrides "
                "all GRANTED assertions on that channel and purpose."
            ),
            canonical_sql_expression=f"`{project}.{dataset}.v_consent_impact`",
        ),
    ]


def build_golden_queries(project: str, dataset: str) -> list[GoldenQuery]:
    """Return verified Golden Queries using GRAPH_EXPAND + AGG() and scorecard views."""
    fq_graph = f"{project}.{dataset}.cdp_semantic_graph"
    return [
        GoldenQuery(
            question="Compare profile counts, distinct identifiers, cluster counts, and hairball membership by brand/source.",
            sql=f"""SELECT
  Profile_sources AS brand,
  AGG(Profile_profile_count)                    AS profiles,
  AGG(Membership_link_count)                    AS links,
  AGG(Identifier_identifier_count)              AS distinct_identifiers,
  AGG(Profile_profiles_touching_hubs)           AS touching_hubs,
  AGG(Profile_baseline_wesid_count)             AS baseline_clusters,
  AGG(Profile_weighted_wesid_count)             AS weighted_clusters,
  AGG(Profile_composable_wesid_count)           AS composable_clusters,
  AGG(Profile_profiles_in_baseline_hairballs)   AS in_baseline_hairballs,
  AGG(Profile_profiles_in_weighted_hairballs)   AS in_weighted_hairballs,
  AGG(Profile_profiles_in_composable_hairballs) AS in_composable_hairballs
FROM GRAPH_EXPAND("{fq_graph}")
GROUP BY brand
ORDER BY profiles DESC;""",
        ),
        GoldenQuery(
            question="How do baseline_cc, weighted_cc, and composable_cdp compare on precision, recall, and F1 across pathology classes?",
            sql=f"""SELECT
  pair_class          AS pathology,
  method,
  tp,
  fp,
  fn,
  ROUND(precision, 4) AS precision,
  ROUND(recall, 4)    AS recall,
  ROUND(f1, 4)        AS f1
FROM `{project}.{dataset}.v_method_comparison`
ORDER BY
  CASE pair_class
    WHEN 'ALL' THEN 0 WHEN 'hub' THEN 1 WHEN 'household' THEN 2
    WHEN 'supersession' THEN 3 WHEN 'semantic_fuzzy' THEN 4 ELSE 5
  END,
  CASE method WHEN 'baseline_cc' THEN 1 WHEN 'weighted_cc' THEN 2 ELSE 3 END;""",
        ),
        GoldenQuery(
            question="How many marketing contacts would have been unlawfully contacted under a Union consent rule vs Intersection consent?",
            sql=f"""SELECT
  channel,
  purpose,
  people_with_a_stated_preference,
  audience_union_rule,
  audience_intersection_rule,
  contacts_the_union_rule_would_add,
  of_which_explicitly_withdrawn,
  suppressed_for_risk,
  pct_of_union_audience_unlawful
FROM `{project}.{dataset}.v_consent_impact`
WHERE purpose = 'MARKETING'
ORDER BY people_with_a_stated_preference DESC;""",
        ),
    ]


def build_agent_context_payload(project: str, dataset: str) -> dict[str, Any]:
    """Build the Conversational Analytics Data Agent system instructions and context."""
    glossary = [asdict(g) for g in build_knowledge_catalog_glossary(project, dataset)]
    golden = [asdict(q) for q in build_golden_queries(project, dataset)]
    system_instruction = (
        "You are the Composable CDP Semantic Graph Data Agent in BigQuery. "
        "Always use BigQuery Knowledge Catalog terminology. "
        f"When aggregating across Profile, Membership, and Identifier in `{project}.{dataset}.cdp_semantic_graph`, "
        f'always use `FROM GRAPH_EXPAND("{project}.{dataset}.cdp_semantic_graph")` and wrap declared '
        "measures in `AGG(...)` so metrics are evaluated at their native entity grain without join fan-out."
    )
    return {
        "agent_name": "composable_cdp_semantic_agent",
        "project": project,
        "dataset": dataset,
        "semantic_graph": f"{project}.{dataset}.cdp_semantic_graph",
        "identity_graph": f"{project}.{dataset}.cdp_identity_graph",
        "system_instruction": system_instruction,
        "knowledge_catalog_glossary": glossary,
        "golden_queries": golden,
    }


def execute_golden_query(project: str, dataset: str, question: str) -> None:
    """Match a natural-language question to the closest Golden Query and execute in BigQuery."""
    from google.cloud import bigquery

    q_lower = question.lower()
    golden = build_golden_queries(project, dataset)
    if "consent" in q_lower or "privacy" in q_lower or "unlawful" in q_lower:
        chosen = golden[2]
    elif "precision" in q_lower or "recall" in q_lower or "pathology" in q_lower or "f1" in q_lower:
        chosen = golden[1]
    else:
        chosen = golden[0]

    print(f"Matched Question : {chosen.question}")
    print(f"Compiled SQL     :\n{chosen.sql}\n")
    client = bigquery.Client(project=project)
    df = client.query(chosen.sql).to_dataframe()
    print(df.to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Composable CDP Semantic Graph Data Agent")
    parser.add_argument("--project", default=os.environ.get("CDP_PROJECT", "all-things-cdp"))
    parser.add_argument("--dataset", default=os.environ.get("CDP_DS", "cdp"))
    parser.add_argument("--dump-config", action="store_true", help="Print the Data Agent JSON context payload")
    parser.add_argument("--ask", type=str, help="Run a natural-language query against the Semantic Graph")
    args = parser.parse_args()

    if args.dump_config or not args.ask:
        payload = build_agent_context_payload(args.project, args.dataset)
        print(json.dumps(payload, indent=2))
    if args.ask:
        execute_golden_query(args.project, args.dataset, args.ask)


if __name__ == "__main__":
    main()
