-- =====================================================================
-- 95 · Scorecard
--
-- The only stage that is allowed to read ground truth, and the only one
-- that matters.
--
-- Everything before this point is a demonstration of mechanism. A
-- mechanism that has not been measured is a hypothesis. This stage
-- measures it, including — especially — where it fails.
--
-- Two views are the deliverable:
--   v_scorecard     the headline numbers, with the configuration that
--                   produced them, so any figure can be reproduced
--   v_case_results  the hard cases, one row each, pass or fail
--
-- If v_case_results shows failures, that is the correct outcome to
-- present. A demo where every case passes on the first run is a demo
-- whose cases are too easy, and an audience of practitioners will know it.
-- =====================================================================


-- ---------------------------------------------------------------------
-- 95a · Pair sets
--
-- Entity resolution is scored pairwise: for every pair of records, did
-- the system agree with truth about whether they are the same person?
--
-- Pairwise scoring is used rather than cluster accuracy because it
-- degrades gracefully. Cluster accuracy calls a nine-record cluster with
-- one wrong member a total failure; pairwise scoring calls it eight
-- correct decisions and one wrong one, which is a far more useful thing
-- to act on.
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.eval_pairs`
CLUSTER BY record_id_a, record_id_b
AS
WITH truth_pairs AS (
  SELECT
    a.record_id AS record_id_a,
    b.record_id AS record_id_b
  FROM `${CDP_PROJECT}.${CDP_DS_TRUTH}.person_truth` AS a
  JOIN `${CDP_PROJECT}.${CDP_DS_TRUTH}.person_truth` AS b
    ON a.true_person_id = b.true_person_id
   AND a.record_id < b.record_id
),
predicted_pairs AS (
  SELECT
    a.record_id AS record_id_a,
    b.record_id AS record_id_b
  FROM `${CDP_PROJECT}.${CDP_DS}.person_assignment` AS a
  JOIN `${CDP_PROJECT}.${CDP_DS}.person_assignment` AS b
    ON a.person_id = b.person_id
   AND a.record_id < b.record_id
),
combined AS (
  SELECT record_id_a, record_id_b FROM truth_pairs
  UNION DISTINCT
  SELECT record_id_a, record_id_b FROM predicted_pairs
)
SELECT
  c.record_id_a,
  c.record_id_b,
  t.record_id_a IS NOT NULL AS is_true_pair,
  p.record_id_a IS NOT NULL AS is_predicted_pair,
  CASE
    WHEN t.record_id_a IS NOT NULL AND p.record_id_a IS NOT NULL THEN 'TP'
    WHEN t.record_id_a IS     NULL AND p.record_id_a IS NOT NULL THEN 'FP'
    ELSE                                                              'FN'
  END AS outcome,
  -- Why the system got it wrong, where that can be determined. A false
  -- negative that was never retrieved is a search problem; one that was
  -- retrieved and rejected is a scoring problem; one that reached the
  -- adjudicator and was declined is a judgement problem. They need
  -- completely different fixes.
  f.retrieved_by,
  ti.tier,
  d.decision,
  d.decided_by,
  d.confidence
FROM combined AS c
LEFT JOIN truth_pairs AS t
  ON t.record_id_a = c.record_id_a AND t.record_id_b = c.record_id_b
LEFT JOIN predicted_pairs AS p
  ON p.record_id_a = c.record_id_a AND p.record_id_b = c.record_id_b
LEFT JOIN `${CDP_PROJECT}.${CDP_DS}.candidate_pairs_fused` AS f
  ON f.record_id_a = c.record_id_a AND f.record_id_b = c.record_id_b
LEFT JOIN `${CDP_PROJECT}.${CDP_DS}.pair_tiers` AS ti
  ON ti.record_id_a = c.record_id_a AND ti.record_id_b = c.record_id_b
LEFT JOIN `${CDP_PROJECT}.${CDP_DS}.match_decisions` AS d
  ON d.record_id_a = c.record_id_a AND d.record_id_b = c.record_id_b;


-- ---------------------------------------------------------------------
-- 95b · Headline scorecard
--
-- Every number here is measured on this run, on this corpus, with the
-- configuration printed alongside it. None of it is quoted from anywhere
-- else, and none of it should be repeated without the configuration
-- attached.
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW `${CDP_PROJECT}.${CDP_DS}.v_scorecard` AS
WITH counts AS (
  SELECT
    COUNTIF(outcome = 'TP') AS tp,
    COUNTIF(outcome = 'FP') AS fp,
    COUNTIF(outcome = 'FN') AS fn
  FROM `${CDP_PROJECT}.${CDP_DS}.eval_pairs`
),
clusters AS (
  SELECT
    (SELECT COUNT(DISTINCT true_person_id)
     FROM `${CDP_PROJECT}.${CDP_DS_TRUTH}.person_truth`)        AS true_people,
    (SELECT COUNT(DISTINCT person_id)
     FROM `${CDP_PROJECT}.${CDP_DS}.person_assignment`)         AS predicted_people,
    (SELECT COUNT(*) FROM `${CDP_PROJECT}.${CDP_DS}.party_records`) AS records
),
-- A predicted cluster containing two or more real people. The privacy
-- failure, counted separately from the aggregate because it is not the
-- same kind of error as a missed merge.
overmerges AS (
  SELECT COUNT(*) AS n
  FROM (
    SELECT a.person_id
    FROM `${CDP_PROJECT}.${CDP_DS}.person_assignment` AS a
    JOIN `${CDP_PROJECT}.${CDP_DS_TRUTH}.person_truth` AS t USING (record_id)
    GROUP BY a.person_id
    HAVING COUNT(DISTINCT t.true_person_id) > 1
  )
),
-- One real person spread across two or more predicted clusters.
undermerges AS (
  SELECT COUNT(*) AS n
  FROM (
    SELECT t.true_person_id
    FROM `${CDP_PROJECT}.${CDP_DS_TRUTH}.person_truth` AS t
    JOIN `${CDP_PROJECT}.${CDP_DS}.person_assignment` AS a USING (record_id)
    GROUP BY t.true_person_id
    HAVING COUNT(DISTINCT a.person_id) > 1
  )
),
steward AS (
  SELECT
    COUNTIF(decision = 'STEWARD') AS queued,
    COUNT(*)                      AS decisions
  FROM `${CDP_PROJECT}.${CDP_DS}.match_decisions`
),
llm AS (
  SELECT COUNT(*) AS adjudicated
  FROM `${CDP_PROJECT}.${CDP_DS}.v_adjudications_current`
),
candidates AS (
  SELECT COUNT(*) AS evaluated FROM `${CDP_PROJECT}.${CDP_DS}.pair_tiers`
)
SELECT
  -- Quality
  c.tp, c.fp, c.fn,
  ROUND(SAFE_DIVIDE(c.tp, c.tp + c.fp), 4)                    AS pairwise_precision,
  ROUND(SAFE_DIVIDE(c.tp, c.tp + c.fn), 4)                    AS pairwise_recall,
  ROUND(SAFE_DIVIDE(2 * c.tp, 2 * c.tp + c.fp + c.fn), 4)     AS pairwise_f1,

  -- The two error types, kept apart on purpose. They are not
  -- interchangeable: an over-merge is a privacy incident, an under-merge
  -- is a data-quality ticket.
  o.n                                                         AS clusters_containing_multiple_people,
  u.n                                                         AS people_split_across_clusters,

  -- Shape
  cl.records,
  cl.true_people,
  cl.predicted_people,
  ROUND(SAFE_DIVIDE(cl.predicted_people, cl.true_people), 4)  AS people_count_ratio,

  -- Cost and effort
  cand.evaluated                                              AS pairs_evaluated,
  l.adjudicated                                               AS pairs_sent_to_llm,
  ROUND(100 * SAFE_DIVIDE(l.adjudicated, cand.evaluated), 3)  AS pct_of_pairs_using_an_llm,
  s.queued                                                    AS pairs_queued_for_a_human,
  ROUND(100 * SAFE_DIVIDE(s.queued, s.decisions), 2)          AS pct_of_decisions_deferred,

  -- Reproducibility. These belong on the same row as the results; a
  -- score without its configuration is an anecdote.
  '${CDP_SEED}'                                               AS generator_seed,
  '${CDP_TAU_HI}'                                             AS tau_high,
  '${CDP_TAU_LO}'                                             AS tau_low,
  '${CDP_ACCEPT_CONFIDENCE}'                                  AS accept_confidence,
  '${CDP_ADJUDICATOR_MODEL}'                                  AS adjudicator_model,
  '${CDP_PROMPT_VERSION}'                                     AS prompt_version,
  '${CDP_EMBEDDING_ENDPOINT}'                                 AS embedding_endpoint,
  CURRENT_TIMESTAMP()                                         AS scored_at
FROM counts AS c, clusters AS cl, overmerges AS o, undermerges AS u,
     steward AS s, llm AS l, candidates AS cand;


-- ---------------------------------------------------------------------
-- 95c · Hard cases
--
-- Each planted case, scored on the pairs that involve it. A case passes
-- only on perfect precision AND perfect recall within its own pairs —
-- there is no partial credit, because a case that half works is a case
-- that fails on the customer it matters to.
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW `${CDP_PROJECT}.${CDP_DS}.v_case_results` AS
WITH case_pairs AS (
  SELECT
    ct AS case_type,
    e.outcome,
    e.retrieved_by,
    e.tier,
    e.decision,
    e.decided_by,
    e.record_id_a,
    e.record_id_b
  FROM `${CDP_PROJECT}.${CDP_DS}.eval_pairs` AS e
  LEFT JOIN `${CDP_PROJECT}.${CDP_DS_TRUTH}.person_truth` AS ta ON ta.record_id = e.record_id_a
  LEFT JOIN `${CDP_PROJECT}.${CDP_DS_TRUTH}.person_truth` AS tb ON tb.record_id = e.record_id_b,
  UNNEST(
    CASE
      WHEN ta.case_type NOT IN ('NORMAL', 'SINGLETON')
           AND tb.case_type NOT IN ('NORMAL', 'SINGLETON')
           AND ta.case_type != tb.case_type
        THEN [ta.case_type, tb.case_type]
      WHEN ta.case_type NOT IN ('NORMAL', 'SINGLETON') THEN [ta.case_type]
      WHEN tb.case_type NOT IN ('NORMAL', 'SINGLETON') THEN [tb.case_type]
      WHEN ta.case_type = 'SINGLETON' OR tb.case_type = 'SINGLETON' THEN ['SINGLETON']
      ELSE ['NORMAL']
    END
  ) AS ct
),
in_scope AS (
  SELECT * FROM case_pairs WHERE case_type != 'NORMAL'
),
scored AS (
  SELECT
    case_type,
    COUNT(*)                AS pairs_evaluated,
    COUNTIF(outcome = 'TP') AS tp,
    COUNTIF(outcome = 'FP') AS fp,
    COUNTIF(outcome = 'FN') AS fn,
    -- Where the failures came from, so a fail is actionable rather than
    -- merely embarrassing.
    COUNTIF(outcome = 'FN' AND retrieved_by IS NULL)              AS fn_never_retrieved,
    COUNTIF(outcome = 'FN' AND tier = 'REJECT')                   AS fn_scored_too_low,
    COUNTIF(outcome = 'FN' AND decided_by = 'LLM')                AS fn_declined_by_llm,
    COUNTIF(outcome = 'FN' AND decision = 'STEWARD')              AS fn_awaiting_a_human,
    COUNTIF(outcome = 'FP' AND decided_by = 'RULE')               AS fp_from_rules,
    COUNTIF(outcome = 'FP' AND decided_by = 'LLM')                AS fp_from_llm,
    COUNTIF(retrieved_by = 'SEMANTIC_ONLY')                       AS found_only_semantically,
    COUNTIF(retrieved_by = 'LEXICAL_ONLY')                        AS found_only_lexically
  FROM in_scope
  GROUP BY case_type
)
SELECT
  s.case_type,
  cc.description,
  cc.expected_outcome,
  cc.deck_slide,
  cc.target_instances,
  s.pairs_evaluated,
  s.tp, s.fp, s.fn,
  ROUND(SAFE_DIVIDE(s.tp, s.tp + s.fp), 3) AS precision,
  ROUND(SAFE_DIVIDE(s.tp, s.tp + s.fn), 3) AS recall,
  s.fp = 0 AND s.fn = 0                    AS passed,
  s.fn_never_retrieved,
  s.fn_scored_too_low,
  s.fn_declined_by_llm,
  s.fn_awaiting_a_human,
  s.fp_from_rules,
  s.fp_from_llm,
  s.found_only_semantically,
  s.found_only_lexically,
  CASE
    WHEN s.fp = 0 AND s.fn = 0                THEN 'Handled correctly.'
    WHEN s.fp > 0 AND cc.expected_outcome LIKE 'DO_NOT_MERGE%'
      THEN 'OVER-MERGED — this is the serious direction of failure. Tighten before demoing.'
    WHEN s.fn > 0 AND s.fn_never_retrieved > 0
      THEN 'Missed at retrieval. Neither search leg surfaced the pair; blocking or embedding text is the place to look.'
    WHEN s.fn > 0 AND s.fn_scored_too_low > 0
      THEN 'Retrieved but scored below the grey zone. A threshold problem, not a search problem.'
    WHEN s.fn > 0 AND s.fn_declined_by_llm > 0
      THEN 'Reached the adjudicator and was declined. A prompt or evidence problem.'
    WHEN s.fn_awaiting_a_human > 0
      THEN 'Deferred to a steward. Arguably correct behaviour rather than a failure.'
    ELSE 'Mixed failure — inspect the pairs directly.'
  END AS diagnosis
FROM scored AS s
LEFT JOIN `${CDP_PROJECT}.${CDP_DS_TRUTH}.case_catalogue` AS cc USING (case_type)
ORDER BY passed, case_type;


-- ---------------------------------------------------------------------
-- 95d · Does hybrid retrieval actually earn its place?
--
-- The claim in the deck is that semantic-only and lexical-only
-- architectures each miss a distinct class of true match. This is the
-- test of that claim, against truth.
--
-- The honest reading: if "recall from semantic alone" and "recall from
-- lexical alone" are both close to the hybrid figure, then hybrid is
-- costing complexity for very little, and the deck should say so.
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW `${CDP_PROJECT}.${CDP_DS}.v_retrieval_recall` AS
WITH truth_pairs AS (
  SELECT a.record_id AS record_id_a, b.record_id AS record_id_b
  FROM `${CDP_PROJECT}.${CDP_DS_TRUTH}.person_truth` AS a
  JOIN `${CDP_PROJECT}.${CDP_DS_TRUTH}.person_truth` AS b
    ON a.true_person_id = b.true_person_id AND a.record_id < b.record_id
),
retrieved AS (
  SELECT
    t.record_id_a,
    t.record_id_b,
    f.retrieved_by
  FROM truth_pairs AS t
  LEFT JOIN `${CDP_PROJECT}.${CDP_DS}.candidate_pairs_fused` AS f
    ON f.record_id_a = t.record_id_a AND f.record_id_b = t.record_id_b
)
SELECT
  COUNT(*)                                                       AS true_pairs,
  COUNTIF(retrieved_by IS NOT NULL)                              AS retrieved_by_hybrid,
  COUNTIF(retrieved_by IN ('LEXICAL_ONLY', 'BOTH'))              AS retrieved_by_lexical,
  COUNTIF(retrieved_by IN ('SEMANTIC_ONLY', 'BOTH'))             AS retrieved_by_semantic,
  ROUND(100 * SAFE_DIVIDE(COUNTIF(retrieved_by IS NOT NULL), COUNT(*)), 2)
                                                                 AS pct_recall_hybrid,
  ROUND(100 * SAFE_DIVIDE(COUNTIF(retrieved_by IN ('LEXICAL_ONLY','BOTH')), COUNT(*)), 2)
                                                                 AS pct_recall_lexical_only_architecture,
  ROUND(100 * SAFE_DIVIDE(COUNTIF(retrieved_by IN ('SEMANTIC_ONLY','BOTH')), COUNT(*)), 2)
                                                                 AS pct_recall_semantic_only_architecture,
  COUNTIF(retrieved_by = 'LEXICAL_ONLY')                         AS pairs_a_semantic_system_would_miss,
  COUNTIF(retrieved_by = 'SEMANTIC_ONLY')                        AS pairs_a_lexical_system_would_miss,
  COUNTIF(retrieved_by IS NULL)                                  AS pairs_neither_leg_found
FROM retrieved;


-- ---------------------------------------------------------------------
-- 95e · The failures, individually
--
-- For the inevitable question: "show me one it got wrong."
--
-- Having this query ready, and offering it before being asked, is worth
-- more to a technical audience than any headline number.
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW `${CDP_PROJECT}.${CDP_DS}.v_failures` AS
SELECT
  e.outcome,
  e.record_id_a,
  e.record_id_b,
  a.match_key                AS record_a,
  b.match_key                AS record_b,
  ta.case_type               AS case_a,
  tb.case_type               AS case_b,
  ta.notes                   AS truth_note_a,
  e.retrieved_by,
  e.tier,
  e.decision,
  e.decided_by,
  e.confidence,
  t.combined_score,
  t.rule_score,
  t.similarity,
  t.dob_conflict,
  j.rationale                AS llm_rationale,
  j.contradiction            AS llm_contradiction
FROM `${CDP_PROJECT}.${CDP_DS}.eval_pairs` AS e
LEFT JOIN `${CDP_PROJECT}.${CDP_DS}.party_search` AS a ON a.record_id = e.record_id_a
LEFT JOIN `${CDP_PROJECT}.${CDP_DS}.party_search` AS b ON b.record_id = e.record_id_b
LEFT JOIN `${CDP_PROJECT}.${CDP_DS_TRUTH}.person_truth` AS ta ON ta.record_id = e.record_id_a
LEFT JOIN `${CDP_PROJECT}.${CDP_DS_TRUTH}.person_truth` AS tb ON tb.record_id = e.record_id_b
LEFT JOIN `${CDP_PROJECT}.${CDP_DS}.pair_tiers` AS t
  ON t.record_id_a = e.record_id_a AND t.record_id_b = e.record_id_b
LEFT JOIN `${CDP_PROJECT}.${CDP_DS}.v_adjudications_current` AS j
  ON j.record_id_a = e.record_id_a AND j.record_id_b = e.record_id_b
WHERE e.outcome != 'TP'
-- False positives first: they are the ones that matter most.
--
-- This was `ORDER BY e.outcome`, which sorts ascending, and 'FN' < 'FP' --
-- so it did exactly the opposite of what the comment claimed and led with
-- false negatives. An explicit CASE says the intent rather than relying on
-- the alphabet.
--
-- The trailing record_id keys are a deterministic tiebreak, not decoration.
-- This view is read through a LIMIT in the notebook, and without a total
-- order the set of rows a human actually sees is arbitrary and can change
-- between runs. A stable order makes the visible rows a fixed, reviewable
-- set -- which is what lets the displayed records be vetted at all.
ORDER BY
  CASE e.outcome WHEN 'FP' THEN 0 WHEN 'FN' THEN 1 ELSE 2 END,
  t.combined_score DESC,
  e.record_id_a,
  e.record_id_b;
