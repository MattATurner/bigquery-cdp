-- =====================================================================
-- 96 · Cost model
--
-- Answers "what would this cost at our volume?" from MEASUREMENT, not
-- from assumption.
--
-- The distinction matters. Every cost estimate for this kind of workload
-- that you have ever been shown was built by assuming a tokens-per-record
-- figure and a grey-zone percentage, and both of those assumptions are
-- doing all the work. This stage instead reads:
--
--   · the token counts the models themselves reported (usageMetadata)
--   · the bytes and slot-time BigQuery actually billed (INFORMATION_SCHEMA)
--
-- and multiplies by unit prices held in config.env, where they can be
-- corrected in one place when they change.
--
-- Where something genuinely cannot be measured — AI.EMBED and AI.CLASSIFY
-- do not return usage metadata — it is estimated, and the output column
-- says so. Nothing here silently mixes the two.
--
-- >>> UNIT PRICES ARE LIST PRICES CAPTURED 14 SEP 2026 AND WILL GO STALE.
-- >>> Re-verify before putting a number in front of a customer.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 96a · Unit prices, stamped onto the run
--
-- Written to a table rather than inlined so that a cost figure produced
-- six months from now can still be traced to the prices it assumed.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.ref_unit_prices` AS
SELECT
  CURRENT_TIMESTAMP()                             AS captured_at,
  DATE '2026-09-14'                               AS price_list_date,
  CAST('${CDP_PRICE_EMBED_INPUT}'       AS FLOAT64) AS usd_per_1m_embed_input,
  CAST('${CDP_PRICE_EXTRACT_INPUT}'     AS FLOAT64) AS usd_per_1m_extract_input,
  CAST('${CDP_PRICE_EXTRACT_OUTPUT}'    AS FLOAT64) AS usd_per_1m_extract_output,
  CAST('${CDP_PRICE_ADJUDICATE_INPUT}'  AS FLOAT64) AS usd_per_1m_adjudicate_input,
  CAST('${CDP_PRICE_ADJUDICATE_OUTPUT}' AS FLOAT64) AS usd_per_1m_adjudicate_output,
  CAST('${CDP_PRICE_BQ_PER_TIB}'        AS FLOAT64) AS usd_per_tib_scanned,
  CAST('${CDP_PRICE_BQ_SLOT_HOUR}'      AS FLOAT64) AS usd_per_slot_hour,
  CAST('${CDP_PRICE_STORAGE_GIB_MONTH}' AS FLOAT64) AS usd_per_gib_month,
  '${CDP_EMBEDDING_ENDPOINT}'                     AS embedding_model,
  '${CDP_EXTRACTION_MODEL}'                       AS extraction_model,
  '${CDP_ADJUDICATOR_MODEL}'                      AS adjudicator_model;


-- ---------------------------------------------------------------------
-- 96b · What the run actually consumed
--
-- One row per cost component. `basis` is the honesty column: MEASURED
-- means the number came from the model or from BigQuery's own accounting,
-- ESTIMATED means it was derived from input size.
--
-- The estimate uses 4 characters per token, which is the usual English
-- rule of thumb. It is wrong for the identity strings the embedder sees —
-- names and postcodes tokenise worse than prose — so treat the embedding
-- line as the softest number here.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.cost_components` AS

WITH
-- Extraction over call transcripts.
call_extract AS (
  SELECT
    'extraction_calls'                     AS component,
    COUNT(*)                               AS calls,
    SUM(IFNULL(input_tokens, 0))           AS input_tokens,
    SUM(IFNULL(output_tokens, 0))          AS output_tokens,
    COUNTIF(input_tokens IS NULL)          AS unmeasured_calls
  FROM `${CDP_PROJECT}.${CDP_DS}.stg_call_entities`
),

-- Extraction over support ticket bodies. Covers the AI.GENERATE call only.
ticket_extract AS (
  SELECT
    'extraction_tickets'                   AS component,
    COUNT(*)                               AS calls,
    SUM(IFNULL(input_tokens, 0))           AS input_tokens,
    SUM(IFNULL(output_tokens, 0))          AS output_tokens,
    COUNTIF(input_tokens IS NULL)          AS unmeasured_calls
  FROM `${CDP_PROJECT}.${CDP_DS}.stg_support_entities`
),

-- AI.CLASSIFY on the same ticket bodies. Returns a bare STRING, so there
-- is no usage metadata to read and this is necessarily an estimate.
-- Output is a single label, so output tokens are negligible but nonzero.
ticket_classify AS (
  SELECT
    'classification_tickets'               AS component,
    COUNT(*)                               AS calls,
    CAST(SUM(CHAR_LENGTH(IFNULL(t.body, ''))) / 4 AS INT64) AS input_tokens,
    COUNT(*) * 5                           AS output_tokens,
    COUNT(*)                               AS unmeasured_calls
  FROM `${CDP_PROJECT}.${CDP_DS}.ext_support_tickets` AS t
),

-- Embeddings. AI.EMBED reports no usage metadata, so this is estimated
-- from the length of the match key that was embedded.
embedding AS (
  SELECT
    'embedding'                            AS component,
    COUNT(*)                               AS calls,
    CAST(SUM(CHAR_LENGTH(IFNULL(match_key, ''))) / 4 AS INT64) AS input_tokens,
    0                                      AS output_tokens,
    COUNT(*)                               AS unmeasured_calls
  FROM `${CDP_PROJECT}.${CDP_DS}.party_search`
),

-- Adjudication. Measured, and scoped to the model and prompt currently in
-- force so a re-run under a new prompt does not double-count history.
--
-- Calls whose token usage was not captured (ledger rows written before the
-- usage_metadata parsing fix) are costed at the MEASURED per-call average of
-- the same model and prompt -- including a '<prompt>-calibration' sample
-- re-judged purely to measure tokens, which never counts as a verdict. They
-- stay counted in unmeasured_calls, so basis reads PARTIAL or ESTIMATED.
adj_calibration AS (
  SELECT
    AVG(input_tokens)  AS avg_in,
    AVG(output_tokens) AS avg_out
  FROM `${CDP_PROJECT}.${CDP_DS}.adjudications`
  WHERE model = '${CDP_ADJUDICATOR_MODEL}'
    AND prompt_version IN ('${CDP_PROMPT_VERSION}', '${CDP_PROMPT_VERSION}-calibration')
    AND input_tokens IS NOT NULL
),
-- Scoped to ONE call per pair in the current grey zone -- i.e. what a clean
-- rebuild costs. The ledger is append-only, so it also holds retries and
-- pairs judged under earlier tier thresholds; that cumulative spend is
-- reported separately as usd_adjudication_ledger_to_date in v_cost_model.
adjudication AS (
  SELECT
    'adjudication'                         AS component,
    COUNT(*)                               AS calls,
    CAST(SUM(IFNULL(a.input_tokens,  c.avg_in))  AS INT64) AS input_tokens,
    CAST(SUM(IFNULL(a.output_tokens, c.avg_out)) AS INT64) AS output_tokens,
    COUNTIF(a.input_tokens IS NULL)        AS unmeasured_calls
  FROM `${CDP_PROJECT}.${CDP_DS}.pair_tiers` AS t
  JOIN `${CDP_PROJECT}.${CDP_DS}.v_adjudications_current` AS a
    USING (record_id_a, record_id_b)
  CROSS JOIN adj_calibration AS c
  WHERE t.tier = 'GREY_ZONE'
),

all_components AS (
  SELECT * FROM call_extract
  UNION ALL SELECT * FROM ticket_extract
  UNION ALL SELECT * FROM ticket_classify
  UNION ALL SELECT * FROM embedding
  UNION ALL SELECT * FROM adjudication
)

SELECT
  c.component,
  c.calls,
  c.input_tokens,
  c.output_tokens,
  c.unmeasured_calls,
  CASE
    WHEN c.calls = 0                      THEN 'NO_CALLS'
    WHEN c.unmeasured_calls = 0           THEN 'MEASURED'
    WHEN c.unmeasured_calls = c.calls     THEN 'ESTIMATED'
    ELSE                                       'PARTIAL'
  END                                     AS basis,
  -- Price each component at its own model's rate. Embedding is input-only.
  ROUND(
    CASE c.component
      WHEN 'embedding' THEN
        c.input_tokens / 1e6 * p.usd_per_1m_embed_input
      WHEN 'adjudication' THEN
          c.input_tokens  / 1e6 * p.usd_per_1m_adjudicate_input
        + c.output_tokens / 1e6 * p.usd_per_1m_adjudicate_output
      ELSE
          c.input_tokens  / 1e6 * p.usd_per_1m_extract_input
        + c.output_tokens / 1e6 * p.usd_per_1m_extract_output
    END, 6)                               AS usd_model_cost
FROM all_components AS c
CROSS JOIN `${CDP_PROJECT}.${CDP_DS}.ref_unit_prices` AS p;


-- ---------------------------------------------------------------------
-- 96c · BigQuery compute, from BigQuery's own accounting
--
-- A view rather than a table, deliberately. INFORMATION_SCHEMA requires
-- permissions the pipeline does not otherwise need, and it is queried
-- lazily — so if the caller lacks access, this view fails on SELECT
-- instead of breaking the build.
--
-- Scoped to jobs since the preflight stage ran, which is the first thing
-- that happens after the datasets are created and is therefore a clean
-- run-start marker.
--
-- The region qualifier must match the dataset location.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW `${CDP_PROJECT}.${CDP_DS}.v_cost_compute` AS
WITH run_start AS (
  SELECT MIN(checked_at) AS t0
  FROM `${CDP_PROJECT}.${CDP_DS}.preflight_result`
)
SELECT
  COUNT(*)                                          AS jobs,
  SUM(j.total_bytes_billed)                         AS bytes_billed,
  ROUND(SUM(j.total_bytes_billed) / POW(1024, 4), 6) AS tib_billed,
  SUM(j.total_slot_ms)                              AS slot_ms,
  ROUND(SUM(j.total_slot_ms) / 3600000.0, 4)        AS slot_hours,
  ROUND(SUM(j.total_bytes_billed) / POW(1024, 4) * p.usd_per_tib_scanned, 4)
                                                    AS usd_on_demand,
  ROUND(SUM(j.total_slot_ms) / 3600000.0 * p.usd_per_slot_hour, 4)
                                                    AS usd_enterprise_slots
FROM `region-${CDP_LOCATION_LOWER}`.INFORMATION_SCHEMA.JOBS_BY_PROJECT AS j
CROSS JOIN `${CDP_PROJECT}.${CDP_DS}.ref_unit_prices` AS p
CROSS JOIN run_start AS r
WHERE j.creation_time >= r.t0
  AND j.job_type       = 'QUERY'
  AND j.state          = 'DONE'
GROUP BY p.usd_per_tib_scanned, p.usd_per_slot_hour;


-- ---------------------------------------------------------------------
-- 96d · The answer
--
-- Total cost of the run, unit economics, and a linear extrapolation to
-- the configured target volume.
--
-- READ THE CAVEATS COLUMN BEFORE QUOTING ANY OF THIS. In particular the
-- extrapolation is LINEAR, and the component that is least likely to
-- behave linearly is adjudication: the number of pairs that reach the
-- grey zone depends on how well blocking discriminates, and blocking gets
-- harder as the corpus grows and near-duplicates become denser. A 75x
-- corpus will not produce exactly 75x the grey zone. It is more likely to
-- produce somewhat more, which is why the sensitivity view exists.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW `${CDP_PROJECT}.${CDP_DS}.v_cost_model` AS
WITH
totals AS (
  SELECT
    SUM(usd_model_cost)                               AS usd_model_total,
    SUM(IF(component = 'adjudication', usd_model_cost, 0)) AS usd_adjudication,
    SUM(IF(component = 'embedding',    usd_model_cost, 0)) AS usd_embedding,
    SUM(IF(component IN ('extraction_calls', 'extraction_tickets',
                         'classification_tickets'), usd_model_cost, 0)) AS usd_extraction,
    SUM(calls)                                        AS ai_calls,
    SUM(input_tokens + output_tokens)                 AS total_tokens,
    COUNTIF(basis IN ('ESTIMATED', 'PARTIAL'))        AS components_estimated
  FROM `${CDP_PROJECT}.${CDP_DS}.cost_components`
),
corpus AS (
  SELECT COUNT(*) AS records FROM `${CDP_PROJECT}.${CDP_DS}.party_records`
),
people AS (
  SELECT COUNT(*) AS people FROM `${CDP_PROJECT}.${CDP_DS}.golden_person`
),
-- Everything the adjudicator has been paid for under this model and prompt,
-- including retries, earlier-threshold grey zones and the calibration
-- sample. This is money already spent, NOT the cost of one rebuild.
ledger AS (
  SELECT
    COUNT(*) AS ledger_calls,
    SUM(  IFNULL(a.input_tokens,  c.avg_in)  / 1e6 * p.usd_per_1m_adjudicate_input
        + IFNULL(a.output_tokens, c.avg_out) / 1e6 * p.usd_per_1m_adjudicate_output)
      AS usd_ledger
  FROM `${CDP_PROJECT}.${CDP_DS}.adjudications` AS a
  CROSS JOIN (
    SELECT AVG(input_tokens) AS avg_in, AVG(output_tokens) AS avg_out
    FROM `${CDP_PROJECT}.${CDP_DS}.adjudications`
    WHERE model = '${CDP_ADJUDICATOR_MODEL}'
      AND prompt_version IN ('${CDP_PROMPT_VERSION}', '${CDP_PROMPT_VERSION}-calibration')
      AND input_tokens IS NOT NULL
  ) AS c
  CROSS JOIN `${CDP_PROJECT}.${CDP_DS}.ref_unit_prices` AS p
  WHERE a.model = '${CDP_ADJUDICATOR_MODEL}'
    AND a.prompt_version IN ('${CDP_PROMPT_VERSION}', '${CDP_PROMPT_VERSION}-calibration')
),
target AS (
  SELECT
    CAST('${CDP_TARGET_RECORDS}'     AS INT64)   AS target_records,
    CAST('${CDP_TARGET_PEOPLE}'      AS INT64)   AS target_people,
    CAST('${CDP_REBUILDS_PER_MONTH}' AS INT64)   AS rebuilds_per_month
)
SELECT
  -- What was actually built
  c.records                                          AS demo_records,
  pe.people                                          AS demo_people_resolved,
  t.ai_calls,
  t.total_tokens,

  -- What it cost, by component
  ROUND(t.usd_extraction,   4)                       AS usd_extraction,
  ROUND(t.usd_embedding,    4)                       AS usd_embedding,
  ROUND(t.usd_adjudication, 4)                       AS usd_adjudication,
  ROUND(t.usd_model_total,  4)                       AS usd_model_total,

  -- Unit economics — the number worth remembering
  ROUND(t.usd_model_total / NULLIF(c.records, 0) * 1000, 4)
                                                     AS usd_model_per_1k_records,

  -- Linear extrapolation to the customer's volume
  tg.target_records,
  ROUND(t.usd_model_total / NULLIF(c.records, 0) * tg.target_records, 2)
                                                     AS usd_model_at_target_per_rebuild,
  ROUND(t.usd_model_total / NULLIF(c.records, 0) * tg.target_records
        * tg.rebuilds_per_month, 2)                  AS usd_model_at_target_per_month,

  -- Money already spent on adjudication across iterations (not per rebuild)
  l.ledger_calls                                     AS adjudication_ledger_calls,
  ROUND(l.usd_ledger, 2)                             AS usd_adjudication_ledger_to_date,

  -- Honesty
  t.components_estimated,
  CASE
    WHEN t.components_estimated = 0 THEN 'All components measured from reported token counts.'
    ELSE FORMAT(
      '%d of 5 components estimated rather than measured (AI.EMBED and AI.CLASSIFY '
      || 'do not report usage metadata; adjudication rows written before token capture '
      || 'are costed at the measured per-call average of a calibration sample). '
      || 'See cost_components.basis.',
      t.components_estimated)
  END                                                AS measurement_note,
  'EXCLUDES BigQuery compute — see v_cost_compute and add it. '
  || 'Per-rebuild figures assume ONE adjudication call per current grey-zone pair; '
  || 'usd_adjudication_ledger_to_date is the cumulative spend including re-runs. '
  || 'Extrapolation is LINEAR in record count; adjudication volume is the '
  || 'component most likely to grow faster than linearly, because blocking '
  || 'discriminates less well as the corpus densifies. Treat the target figure '
  || 'as a floor, not a forecast.'                   AS caveats
FROM totals AS t
CROSS JOIN corpus AS c
CROSS JOIN people AS pe
CROSS JOIN ledger AS l
CROSS JOIN target AS tg;


-- ---------------------------------------------------------------------
-- 96e · Sensitivity
--
-- The single biggest driver of cost at scale is what fraction of
-- candidate pairs reach the adjudicator. That is a threshold decision,
-- not a fact about the data, and it is the lever a customer will actually
-- want to pull.
--
-- This shows what the target-scale bill does as that fraction moves,
-- holding everything else constant. It is the view to have on screen when
-- someone asks "can we make it cheaper?" — the answer is yes, and the
-- cost of doing so is recall, which v_scorecard quantifies.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW `${CDP_PROJECT}.${CDP_DS}.v_cost_sensitivity` AS
WITH base AS (
  SELECT
    (SELECT COUNT(*) FROM `${CDP_PROJECT}.${CDP_DS}.party_records`) AS records,
    (SELECT SUM(IF(component = 'adjudication', usd_model_cost, 0))
     FROM `${CDP_PROJECT}.${CDP_DS}.cost_components`)               AS usd_adjudication,
    (SELECT SUM(IF(component <> 'adjudication', usd_model_cost, 0))
     FROM `${CDP_PROJECT}.${CDP_DS}.cost_components`)               AS usd_fixed,
    (SELECT calls FROM `${CDP_PROJECT}.${CDP_DS}.cost_components`
      WHERE component = 'adjudication')                            AS pairs_judged,
    CAST('${CDP_TARGET_RECORDS}' AS INT64)                          AS target_records
),
multipliers AS (
  SELECT * FROM UNNEST([0.25, 0.5, 1.0, 2.0, 4.0]) AS grey_zone_multiplier
)
SELECT
  m.grey_zone_multiplier,
  CAST(b.pairs_judged * m.grey_zone_multiplier AS INT64)      AS pairs_judged_equivalent,
  ROUND((b.usd_fixed + b.usd_adjudication * m.grey_zone_multiplier)
        / NULLIF(b.records, 0) * b.target_records, 2)         AS usd_at_target_per_rebuild,
  CASE m.grey_zone_multiplier
    WHEN 0.25 THEN 'Aggressive thresholds. Cheapest, and the option most likely to under-merge.'
    WHEN 0.5  THEN 'Tighter than shipped.'
    WHEN 1.0  THEN 'As configured and as scored — this is the row the scorecard describes.'
    WHEN 2.0  THEN 'Looser thresholds, more pairs reviewed by the model.'
    WHEN 4.0  THEN 'Very loose. Diminishing returns; check v_scorecard before paying for this.'
  END                                                         AS interpretation
FROM base AS b
CROSS JOIN multipliers AS m
ORDER BY m.grey_zone_multiplier;
