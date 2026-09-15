-- =====================================================================
-- 05 · Preflight
--
-- Exercises the three AI surfaces the pipeline calls — AI.EMBED (stage 30),
-- AI.GENERATE (stages 20 and 60) and AI.CLASSIFY (stage 20) — using the
-- same argument shapes the real stages use, against a handful of rows.
--
-- Why this exists: the pipeline lands 200k records, embeds them, and calls
-- two different models across stages 10–95. A wrong model ID, a missing
-- IAM grant on the connection's service account, or a model that is not
-- available in this region will fail — but it will fail at stage 20, after
-- the expensive landing work, with an error message that points at the
-- symptom rather than the cause.
--
-- This stage fails in seconds instead, and says which thing is broken.
--
-- Every check uses ASSERT, so a failure aborts the script rather than
-- recording a row that nobody reads.
--
-- WHAT THIS STAGE DOES NOT COVER
--
-- AI.SEARCH is not probed, and cannot be from here: it requires a table
-- with a TREE_AH index over an embedding column, which does not exist
-- until stage 30. That is a real gap rather than an oversight — hybrid
-- search is Public Preview, so "not enabled for this project or region"
-- is one of the more likely first-run failures, and it will surface at
-- stage 30 rather than here. If stage 30 fails on the index creation,
-- that is the first thing to check.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 05a · Embedding model
--
-- Same function and argument shape as the generated column in stage 30.
-- If the endpoint name is wrong or the connection cannot reach Vertex AI,
-- this is where it surfaces.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TEMP TABLE _pf_embed AS
SELECT
  AI.EMBED(
    'preflight probe: identity string',
    connection_id => '${CDP_CONNECTION_PATH}',
    endpoint      => '${CDP_EMBEDDING_ENDPOINT}'
  ) AS e;

ASSERT (SELECT e.status IS NULL OR e.status = '' FROM _pf_embed)
  AS 'PREFLIGHT FAILED — embedding model rejected the call. Check CDP_EMBEDDING_ENDPOINT (currently ${CDP_EMBEDDING_ENDPOINT}) is a valid model available in ${CDP_LOCATION}, and that the connection service account for ${CDP_CONNECTION_PATH} holds roles/aiplatform.user. Run: bq show --connection --location=${CDP_LOCATION} ${CDP_CONNECTION}';

ASSERT (SELECT ARRAY_LENGTH(e.result) > 0 FROM _pf_embed)
  AS 'PREFLIGHT FAILED — embedding model returned an empty vector. The call succeeded but produced nothing usable, which usually means the endpoint name resolves to a non-embedding model.';

-- The dimensionality is recorded in 05e, once every probe has run.

-- ---------------------------------------------------------------------
-- 05b · Extraction model
--
-- Stage 20 asks this model for structured output over untrusted text. The
-- probe below uses the same output_schema mechanism, because "the model
-- exists" and "the model honours a schema" are different failures.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TEMP TABLE _pf_extract AS
SELECT
  AI.GENERATE(
    prompt => (
      'Return the forename and surname from this text as structured output. ',
      'Text: Jane Wiremu called about an order.'
    ),
    connection_id => '${CDP_CONNECTION_PATH}',
    endpoint      => '${CDP_EXTRACTION_MODEL}',
    output_schema => 'forename STRING, surname STRING'
  ) AS g;

ASSERT (SELECT g.status IS NULL OR g.status = '' FROM _pf_extract)
  AS 'PREFLIGHT FAILED — extraction model rejected the call. Check CDP_EXTRACTION_MODEL (currently ${CDP_EXTRACTION_MODEL}). Note the Gemini 2.5 family is scheduled for deprecation from 16 Oct 2026; if you are pinned to a 2.5 model it may no longer be served in ${CDP_LOCATION}.';

ASSERT (SELECT g.forename IS NOT NULL FROM _pf_extract)
  AS 'PREFLIGHT FAILED — extraction model returned no structured output. The call succeeded but output_schema was not honoured. Stage 20 depends on structured extraction, so this would fail there instead.';

-- ---------------------------------------------------------------------
-- 05b2 · Classification model
--
-- AI.CLASSIFY is a genuinely different API surface from AI.GENERATE, not a
-- variation on it: the input is positional, the taxonomy arrives as an
-- array of STRUCTs, and the return is a
-- bare STRING rather than a STRUCT — so there is no .status field to test
-- and a rejected call surfaces as a query error rather than a status value.
--
-- It therefore has failure modes 05b cannot catch: the function not being
-- available in ${CDP_LOCATION}, the optimization_mode argument being
-- rejected, or an endpoint that serves AI.GENERATE but not AI.CLASSIFY.
--
-- The taxonomy below is copied verbatim from 20b, deliberately, so the
-- probe exercises the real category list rather than a simplified one.
-- That is a genuine wart — two copies that must be kept in sync, and
-- nothing enforces it. Passing the list in from a table was not attempted
-- because AI.CLASSIFY most likely requires a literal array, and a
-- preflight that fails against a working pipeline is worse than a
-- duplicated list. If you edit the categories in 20b, edit them here.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TEMP TABLE _pf_classify AS
SELECT
  AI.CLASSIFY(
    'Subject: closing an account. My mother passed away last month and I need to close her account.',
    categories => [
      STRUCT('NONE'         AS label, 'No risk or vulnerability indication' AS description),
      STRUCT('DECEASED',        'The customer is stated or strongly implied to have died'),
      STRUCT('MINOR',           'The person is, or is stated to be, under 18'),
      STRUCT('VULNERABLE',      'Illness, disability, care arrangements, or a stated inability to manage the account'),
      STRUCT('BEREAVEMENT',     'A bereavement in the household affecting someone other than the customer'),
      STRUCT('THIRD_PARTY',     'Somebody is acting on the customer\'s behalf: power of attorney, executor, carer, relative')
    ],
    connection_id     => '${CDP_CONNECTION_PATH}',
    endpoint          => '${CDP_EXTRACTION_MODEL}'
  ) AS risk_category;

ASSERT (SELECT risk_category IS NOT NULL FROM _pf_classify)
  AS 'PREFLIGHT FAILED — AI.CLASSIFY returned NULL. The call did not error, so the connection and endpoint are reachable, but no label came back. Stage 20 derives suppress_marketing from this value, so a null here means no ticket would ever be suppressed.';

-- The closed-taxonomy claim in 20b, tested rather than assumed.
--
-- This matters more than it looks. Stage 20 computes
--   risk_category IN ('DECEASED', 'MINOR') AS suppress_marketing
-- so a label outside the supplied set does not raise anything — it makes
-- suppress_marketing silently FALSE. A marketing suppression that quietly
-- stops suppressing is exactly the failure this pipeline exists to prevent,
-- and it would not show up anywhere downstream as an error.
ASSERT (
  SELECT risk_category IN (
    'NONE', 'DECEASED', 'MINOR', 'VULNERABLE', 'BEREAVEMENT', 'THIRD_PARTY'
  ) FROM _pf_classify
)
  AS 'PREFLIGHT FAILED — AI.CLASSIFY returned a label outside the supplied taxonomy. The closed-taxonomy guarantee that stage 20 relies on does not hold for this model. suppress_marketing would silently evaluate FALSE for every off-taxonomy label, so this must be fixed rather than tolerated.';

-- ---------------------------------------------------------------------
-- 05c · Adjudicator model
--
-- Same shape as the stage 60 call: a verdict plus a confidence, because a
-- model that returns the verdict but not a usable FLOAT64 confidence would
-- break tiering downstream rather than here.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TEMP TABLE _pf_adjudicate AS
SELECT
  AI.GENERATE(
    prompt => (
      'Are these the same person? Answer MATCH or NO_MATCH with a confidence between 0 and 1. ',
      'A: Jane Wiremu, born 1985-03-02. B: Jane Wiremu, born 1985-03-02.'
    ),
    connection_id => '${CDP_CONNECTION_PATH}',
    endpoint      => '${CDP_ADJUDICATOR_MODEL}',
    output_schema => 'verdict STRING, confidence FLOAT64'
  ) AS g;

ASSERT (SELECT g.status IS NULL OR g.status = '' FROM _pf_adjudicate)
  AS 'PREFLIGHT FAILED — adjudicator model rejected the call. Check CDP_ADJUDICATOR_MODEL (currently ${CDP_ADJUDICATOR_MODEL}).';

ASSERT (SELECT g.confidence IS NOT NULL FROM _pf_adjudicate)
  AS 'PREFLIGHT FAILED — adjudicator returned no numeric confidence. Stage 60 tiers on confidence against CDP_ACCEPT_CONFIDENCE and CDP_STEWARD_CONFIDENCE, so a null here means every pair would fall through to the steward queue.';

-- ---------------------------------------------------------------------
-- 05e · Record what was found
--
-- Created last, after every probe, so it can record probe *results* and
-- not just the configured names. The embedding dimensionality matters
-- beyond this stage: stage 30 builds a vector index over it and stage 50
-- self-joins against it, so a silent dimension change between runs would
-- corrupt both. Worth knowing before, not after.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.preflight_result` AS
SELECT
  CURRENT_TIMESTAMP()              AS checked_at,
  '${CDP_EMBEDDING_ENDPOINT}'      AS embedding_endpoint,
  (SELECT ARRAY_LENGTH(e.result) FROM _pf_embed)   AS embedding_dimensions,
  '${CDP_EXTRACTION_MODEL}'        AS extraction_model,
  '${CDP_ADJUDICATOR_MODEL}'       AS adjudicator_model,
  '${CDP_CONNECTION_PATH}'         AS connection_path,
  '${CDP_LOCATION}'                AS location,
  (SELECT risk_category FROM _pf_classify)         AS classification_probe,
  (SELECT g.verdict     FROM _pf_adjudicate)       AS adjudicator_probe,
  (SELECT g.confidence  FROM _pf_adjudicate)       AS adjudicator_probe_confidence;

-- ---------------------------------------------------------------------
-- 05d · Sanity, not correctness
--
-- This is NOT a quality check. Two byte-identical records is the easiest
-- possible question, and a bereavement stated in plain words is the
-- easiest possible classification. Getting either right proves nothing
-- about the hard cases. They are here only to catch a model that is
-- answering but answering nonsense — a wiring problem, not an accuracy
-- problem.
--
-- Warning columns rather than ASSERTs, deliberately: a model that says
-- NO_MATCH here is suspicious, but it is the scorecard in stage 95 that
-- gets to decide whether the adjudicator is good enough, not this probe.
-- The ASSERTs above are confined to things that are unambiguously broken
-- wiring — a null, an empty vector, an off-taxonomy label.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW `${CDP_PROJECT}.${CDP_DS}.v_preflight` AS
SELECT
  p.*,
  CASE
    WHEN p.embedding_dimensions BETWEEN 128 AND 4096 THEN 'OK'
    ELSE 'UNUSUAL — check the endpoint is the model you think it is'
  END AS dimension_check,
  -- The probe body says a parent died and the writer is closing her
  -- account. DECEASED is the intended reading; BEREAVEMENT and
  -- THIRD_PARTY are defensible on the same text, so they are not treated
  -- as wrong. Anything else means the taxonomy is not being applied.
  CASE
    WHEN p.classification_probe = 'DECEASED'                      THEN 'OK'
    WHEN p.classification_probe IN ('BEREAVEMENT', 'THIRD_PARTY') THEN 'DEFENSIBLE — the probe text supports this reading'
    ELSE 'UNUSUAL — the model is answering but not applying the taxonomy'
  END AS classification_check,
  CASE
    WHEN p.adjudicator_probe = 'MATCH' THEN 'OK'
    ELSE 'UNUSUAL — the adjudicator did not match two byte-identical records'
  END AS adjudicator_check
FROM `${CDP_PROJECT}.${CDP_DS}.preflight_result` p;
