# Composable CDP · Agents (`demo/agents/`)

This directory contains two complementary agents built on top of the **Composable CDP** BigQuery tables and native Property Graphs (`cdp.cdp_identity_graph` and `cdp.cdp_semantic_graph`):

## 1 · BigQuery Conversational Analytics Data Agent (`semantic_agent.py`)

Configured against the declarative Semantic Property Graph (`cdp.cdp_semantic_graph`) and **BigQuery Knowledge Catalog** business glossary definitions. Translates natural-language analytical questions into fan-out-free `FROM GRAPH_EXPAND("all-things-cdp.cdp.cdp_semantic_graph")` + `AGG()` queries.

```bash
# Dump the Data Agent context payload (system instructions, Knowledge Catalog glossary, Golden Queries)
python3 demo/agents/semantic_agent.py --dump-config

# Ask a natural-language question against BigQuery
python3 demo/agents/semantic_agent.py \
  --ask "Compare profile counts, cluster counts, and hairballs by brand"
```

## 2 · Google ADK Identity Resolution Explainer Agent (`explainer_agent/`)

An interactive **Google Agent Development Kit (ADK)** agent (`cdp_explainer`) equipped with 5 deterministic BigQuery SQL/GQL tools for data stewards, privacy officers, and customer-care teams:

| Tool | Purpose |
|---|---|
| `lookup_profile(record_id)` | Inspects a source record, its attached identifiers & IDF rarity weights (`cdp.identifier`), and its resolved person ID across `baseline_cc`, `weighted_cc`, and `composable_cdp`. |
| `explain_link(record_id_a, record_id_b)` | Returns the 1-hop/2-hop graph features (`idf_weight_sum`, `unshared_email_both`, `forename_conflict`), RRF hybrid search ranks, Gemini 3.5 Flash rationale, and Pass-2 Contradiction Pruning status. |
| `explain_component(person_id)` | Explains a resolved Golden Person (`cdp.golden_person`), all member source records, contested field survivorship (`cdp.field_survivorship`), and Australian Privacy Act 1988 Intersection Consent (`cdp.person_consent`). |
| `identifier_report(identifier_id)` | Audits a Bipartite Identifier Graph node (`degree`, `idf_weight`, `is_promiscuous`) and lists current vs historical superseded records (`cdp.has_identifier_history`). |
| `resolution_runs()` | Returns the side-by-side 3-method benchmark (`cdp.resolution_runs` and `cdp.v_method_comparison`). |

### Running the ADK Explainer Agent

```bash
# Run interactively in the ADK Web UI
adk web demo/agents

# Or invoke the deterministic tools directly from the CLI
python3 demo/agents/explainer_agent/agent.py --explain-component PER-1cdfdb9f52ddb25a
python3 demo/agents/explainer_agent/agent.py --explain-link ECOM-9af071da LOY-4baf0bfb
python3 demo/agents/explainer_agent/agent.py --identifier-report "EM:kiosk.mel@store-checkout.com.au"
```
