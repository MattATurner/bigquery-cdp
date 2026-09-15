-- =====================================================================
-- B · The case for hybrid search
--
-- Two records for one person. Different names, different addresses,
-- different emails. The only thing they share is a loyalty account
-- number.
--
-- An embedding cannot help here. "ACC-48213" carries no semantic content;
-- the model has nothing to represent. BM25 finds it instantly, because a
-- rare alphanumeric token is exactly the high-IDF signal lexical search
-- is built on.
--
-- The reverse case is in the same output: pairs found only semantically,
-- where the names are so different that no keyword overlaps.
--
-- Run this alongside a live single-query lookup to make it tangible:
--   SELECT * FROM `PROJECT.DATASET.tf_lookup_hybrid`('ACC-48213');
--   SELECT * FROM `PROJECT.DATASET.tf_lookup_vector`('ACC-48213');
-- =====================================================================

WITH by_leg AS (
  SELECT
    t.retrieved_by,
    COUNT(*)                                     AS pairs,
    COUNTIF(t.tier != 'REJECT')                  AS survived_scoring,
    COUNTIF(d.decision = 'LINK')                 AS became_links,
    COUNTIF(t.acct_match)                        AS sharing_an_account_number,
    COUNTIF(NOT t.surname_match)                 AS with_different_surnames,
    ROUND(AVG(t.similarity), 3)                  AS avg_semantic_similarity
  FROM `${CDP_PROJECT}.${CDP_DS}.pair_tiers` AS t
  LEFT JOIN `${CDP_PROJECT}.${CDP_DS}.match_decisions` AS d
    ON d.record_id_a = t.record_id_a AND d.record_id_b = t.record_id_b
  GROUP BY t.retrieved_by
)
SELECT
  retrieved_by,
  pairs,
  survived_scoring,
  became_links,
  sharing_an_account_number,
  with_different_surnames,
  avg_semantic_similarity,
  CASE retrieved_by
    WHEN 'LEXICAL_ONLY'
      THEN 'Invisible to a vector-only architecture. Mostly shared identifiers.'
    WHEN 'SEMANTIC_ONLY'
      THEN 'Invisible to a keyword-only architecture. Nicknames, transliterations, married names.'
    ELSE 'Found by both legs — the easy majority.'
  END AS what_this_row_means
FROM by_leg
ORDER BY became_links DESC;
