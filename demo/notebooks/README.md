# Composable CDP · 5-Act Notebook Suite & BigQuery Studio Visual Editions

Every notebook in this directory is **pre-executed against `all-things-cdp.cdp`** (`20,000` source records, `8,000` true people, `15` planted hard-case types) so tables and outputs render immediately in GitHub, VS Code, or Colab Enterprise.

## 1 · Standard 5-Act Walkthrough Suite (`demo/notebooks/`)

| Notebook | Act | What It Proves |
|---|---|---|
| [`01_identity_resolution_story.ipynb`](01_identity_resolution_story.ipynb) | **Executive Story** | 15-minute end-to-end narrative: 3-method benchmark (`baseline_cc` vs `weighted_cc` vs `composable_cdp`) + following **one customer (`Abby Noland`, `PER-1cdfdb9f52ddb25a`)** from 5 raw records to 1 golden person. |
| [`02_graph_pathology_and_rarity.ipynb`](02_graph_pathology_and_rarity.ipynb) | **Act 1 · Graph Pathology & Rarity** | How 7 promiscuous store-kiosk/call-centre hubs (`degree = 419..575`) collapse 5,195 profiles into a single hairball (`0.06%` precision), and how Bipartite Identifier Graph IDF Rarity (`LN(1 + N / degree)`) breaks the hairball in pure SQL. |
| [`03_hybrid_search_and_2hop_features.ipynb`](03_hybrid_search_and_2hop_features.ipynb) | **Act 2 · Hybrid Search + 2-Hop Features** | Why closed-form 1-hop/2-hop SQL graph features (`idf_weight_sum`, `unshared_email_both`, `unshared_phone_both`) + BigQuery Hybrid Search (`AI.SEARCH` / `VECTOR_SEARCH` + RRF) outperform standalone PyTorch GraphSAGE link predictors without GPU training pipelines. |
| [`04_llm_adjudicator_and_contradiction_guard.ipynb`](04_llm_adjudicator_and_contradiction_guard.ipynb) | **Act 3 · Gemini Adjudication & Contradiction Guard** | How Gemini 3.5 Flash adjudicates the `0.39%` grey-zone pairs, blocks adversarial prompt injection, and works with Stage 70's **Pass-2 Transitive Contradiction Guard** to hold false merges to **`4`** in the planted hard-case set (only 2 of the 15 types pass outright). |
| [`05_semantic_graph_governance_and_roi.ipynb`](05_semantic_graph_governance_and_roi.ipynb) | **Act 4 & 5 · Semantic Graph, Consent & ROI** | Fan-out-free multi-hop aggregation via `FROM GRAPH_EXPAND("cdp.cdp_semantic_graph")` + `AGG()`, Australian Privacy Act 1988 Intersection Consent, `3x` attributed spend lift, `12.85%` direct-mail household waste reduction, and the cost model (`$6.58` of model spend per 1,000 records per rebuild). |

## 2 · BigQuery Studio Interactive Graph Editions (`demo/notebooks/bigquery_studio/`)

Open these two notebooks inside **BigQuery Studio** in the Google Cloud Console to render interactive force-directed property graphs via `%%bigquery --graph`:

- [`bigquery_studio/act1_bipartite_graph_and_hairball.ipynb`](bigquery_studio/act1_bipartite_graph_and_hairball.ipynb) — Visualises promiscuous kiosk hubs (`EM:kiosk.mel@store-checkout.com.au`), shared household emails (`EM:thegills@gmail.com`) resolving to separate `Person` nodes inside a shared `Household`, and call-transcript `RELATED_TO` edges.
- [`bigquery_studio/act2_hybrid_search_llm_and_scorecard.ipynb`](bigquery_studio/act2_hybrid_search_llm_and_scorecard.ipynb) — Visualises the complete multi-hop Customer 360 subgraph for `Abby Noland` (`PER-1cdfdb9f52ddb25a`), runs `GRAPH_EXPAND` + `AGG()`, and queries the 3-method scorecard.

## 3 · Rebuilding the Notebooks Deterministically

Two steps. The builder writes the notebook structure; the refresher re-runs every `%%bigquery` cell against live BigQuery and rewrites its output, so no figure in these notebooks is hand-typed:

```bash
python3 demo/notebooks/builders/build_all.py
demo/.venv-nb/bin/python demo/notebooks/builders/refresh_outputs.py
```

`refresh_outputs.py` also writes `builders/live_snapshot.json` — the exact rows behind every table — so narrative figures can be checked against it.
