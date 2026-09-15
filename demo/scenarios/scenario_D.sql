-- =====================================================================
-- D · Breaking the chain
--
-- A looks like B. B looks like C. Therefore A is C — and now one profile
-- contains two different people, one of whom can see the other's orders.
--
-- This is transitive closure doing exactly what it is designed to do,
-- and it is how entity resolution becomes a data breach. It cannot be
-- fixed by better pair scoring, because the A–C pair was never scored:
-- it was inferred.
--
-- The defence is to distrust the closure. Every cluster is checked for
-- internal contradiction, and a contradicted cluster is rebuilt using
-- only edges strong enough to stand alone. The weak middle link falls
-- away and the cluster splits where it should have.
--
-- Below: the clusters that were caught, and the OVERMERGE_BAIT case
-- result. A non-zero contradicted-cluster count is a good sign — it means
-- the trap was laid and the guard fired.
-- =====================================================================

WITH caught AS (
  SELECT
    COUNT(*)                     AS contradicted_clusters_found,
    SUM(members)                 AS records_involved,
    MAX(distinct_dobs)           AS worst_case_distinct_dobs
  FROM `${CDP_PROJECT}.${CDP_DS}.component_conflicts`
),
split AS (
  -- Edges that were accepted as links, but whose endpoints ended up in
  -- different people after pruning. These are the links the contradiction
  -- guard overrode.
  SELECT COUNT(*) AS links_overridden_by_the_guard
  FROM `${CDP_PROJECT}.${CDP_DS}.resolution_edges`
  WHERE suppressed_by_contradiction
),
bait AS (
  SELECT
    IFNULL(MAX(tp), 0)        AS tp,
    IFNULL(MAX(fp), 0)        AS fp,
    IFNULL(MAX(fn), 0)        AS fn,
    IFNULL(MAX(CAST(passed AS INT64)), 0) = 1 AS overmerge_bait_passed,
    ANY_VALUE(diagnosis)      AS diagnosis
  FROM `${CDP_PROJECT}.${CDP_DS}.v_case_results`
  WHERE case_type = 'OVERMERGE_BAIT'
),
overall AS (
  SELECT clusters_containing_multiple_people
  FROM `${CDP_PROJECT}.${CDP_DS}.v_scorecard`
)
SELECT
  c.contradicted_clusters_found,
  c.records_involved,
  c.worst_case_distinct_dobs,
  s.links_overridden_by_the_guard,
  o.clusters_containing_multiple_people AS over_merges_remaining,
  b.overmerge_bait_passed,
  b.tp AS bait_pairs_correct,
  b.fp AS bait_pairs_over_merged,
  b.fn AS bait_pairs_missed,
  b.diagnosis
FROM caught AS c, split AS s, bait AS b, overall AS o;
