-- =====================================================================
-- 40 · Block
--
-- 20,000 records is 199,990,000 possible pairs. Comparing them all is
-- both unaffordable and unnecessary: the overwhelming majority of pairs
-- share nothing at all.
--
-- Blocking is the cheap, deterministic first pass that throws most of
-- them away. It is also the stage where recall is most often silently
-- lost — anything blocking misses, no amount of clever scoring
-- downstream can recover. So this stage does two things: it generates the
-- pairs, and it reports honestly on what it discarded.
-- =====================================================================


-- ---------------------------------------------------------------------
-- 40a · Block sizes
--
-- A block is every record sharing one key. Most are tiny. A few are
-- pathological — a dense urban postcode district, or a null-ish key that
-- slipped through normalisation — and those are what turn a blocking
-- stage into a runaway self-join.
--
-- Oversized blocks are dropped rather than sampled, and the drop is
-- recorded. Silently truncating a block is how you end up unable to
-- explain why one customer never got resolved.
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.block_stats`
AS
WITH exploded AS (
  SELECT record_id, key
  FROM `${CDP_PROJECT}.${CDP_DS}.party_search`, UNNEST(blocking_keys) AS key
)
SELECT
  key,
  SPLIT(key, ':')[OFFSET(0)]                       AS key_type,
  COUNT(*)                                         AS members,
  COUNT(*) * (COUNT(*) - 1) / 2                    AS pairs_implied,
  -- A block of N members implies N(N-1)/2 comparisons, so this grows
  -- quadratically and a single junk key can dominate the whole run.
  -- Past the threshold the key is not discriminating anything and is
  -- almost certainly a data artefact (a default postcode, a placeholder
  -- phone number, an unparsed address).
  --
  -- Parameterised because it MUST move with corpus size: 500 was right at
  -- 20k records, and leaving it there at 200k would discard genuine
  -- signal — a real postcode in a dense urban area legitimately holds
  -- thousands of people once the corpus is national.
  --
  -- Dropped keys are recorded here rather than filtered silently, so
  -- v_blocking_by_key can show exactly what recall was traded away.
  COUNT(*) > ${CDP_MAX_BLOCK_SIZE}                 AS oversized
FROM exploded
GROUP BY key
HAVING COUNT(*) > 1;


-- ---------------------------------------------------------------------
-- 40b · Candidate pairs from deterministic keys
--
-- Each key type carries a different weight, and the weights are ordinal
-- rather than calibrated — they order the evidence, they do not claim to
-- measure it:
--
--   AC  account number      100  a shared loyalty account is near-proof
--   EM  email               90   strong, but couples do share addresses
--   PH  phone               80   strong, but landlines are household-level
--   ND  surname + DOB       70   strong together, weak apart
--   SX  soundex + outward   30   a hint, nothing more
--   PC  postcode district   10   a neighbourhood, not a person
--
-- Note what is deliberately absent: no pair is *accepted* here. This
-- stage only decides what is worth looking at.
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.candidate_pairs_blocked`
CLUSTER BY record_id_a, record_id_b
AS
WITH exploded AS (
  SELECT p.record_id, key
  FROM `${CDP_PROJECT}.${CDP_DS}.party_search` AS p, UNNEST(p.blocking_keys) AS key
),
usable AS (
  SELECT e.record_id, e.key
  FROM exploded AS e
  JOIN `${CDP_PROJECT}.${CDP_DS}.block_stats` AS b USING (key)
  WHERE NOT b.oversized
),
paired AS (
  SELECT
    a.record_id AS record_id_a,
    b.record_id AS record_id_b,
    a.key
  FROM usable AS a
  JOIN usable AS b
    ON a.key = b.key
   -- Ordering the pair once removes the mirror image and self-comparison
   -- in a single predicate.
   AND a.record_id < b.record_id
)
SELECT
  record_id_a,
  record_id_b,
  ARRAY_AGG(DISTINCT SPLIT(key, ':')[OFFSET(0)] ORDER BY SPLIT(key, ':')[OFFSET(0)]) AS key_types,
  ARRAY_AGG(key ORDER BY key)                                                        AS matched_keys,
  MAX(CASE SPLIT(key, ':')[OFFSET(0)]
        WHEN 'AC' THEN 100
        WHEN 'EM' THEN 90
        WHEN 'PH' THEN 80
        WHEN 'ND' THEN 70
        WHEN 'SX' THEN 30
        WHEN 'PC' THEN 10
        ELSE 0
      END)                                                                           AS block_strength,
  COUNT(DISTINCT key)                                                                AS keys_shared
FROM paired
GROUP BY record_id_a, record_id_b;


-- ---------------------------------------------------------------------
-- 40c · The reduction, stated plainly
--
-- This is the number to put on screen. Not because the ratio is
-- impressive in itself — any blocking scheme produces a large one — but
-- because it sets up the honest question that follows: what did we lose?
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW `${CDP_PROJECT}.${CDP_DS}.v_blocking_funnel` AS
WITH n AS (
  SELECT COUNT(*) AS records FROM `${CDP_PROJECT}.${CDP_DS}.party_search`
),
dropped AS (
  SELECT
    IFNULL(SUM(IF(oversized, members, 0)), 0)        AS members_in_dropped_blocks,
    IFNULL(SUM(IF(oversized, pairs_implied, 0)), 0)  AS pairs_in_dropped_blocks,
    COUNTIF(oversized)                               AS blocks_dropped
  FROM `${CDP_PROJECT}.${CDP_DS}.block_stats`
),
kept AS (
  SELECT COUNT(*) AS candidate_pairs
  FROM `${CDP_PROJECT}.${CDP_DS}.candidate_pairs_blocked`
)
SELECT
  n.records,
  n.records * (n.records - 1) / 2                               AS pairs_brute_force,
  kept.candidate_pairs,
  ROUND(
    100 * (1 - SAFE_DIVIDE(kept.candidate_pairs,
                           n.records * (n.records - 1) / 2)), 4) AS pct_eliminated,
  SAFE_DIVIDE(n.records * (n.records - 1) / 2, kept.candidate_pairs) AS reduction_factor,
  dropped.blocks_dropped,
  dropped.pairs_in_dropped_blocks,
  -- Honest caveat: pairs that only ever co-occurred in an oversized block
  -- are not in the candidate set. The semantic leg in stage 50 is the
  -- safety net for exactly this, which is a large part of why it exists.
  'Pairs lost to oversized blocks are recovered, if at all, by the semantic leg in stage 50.'
    AS caveat
FROM n, dropped, kept;


-- ---------------------------------------------------------------------
-- 40d · Where the keys come from
--
-- Breaks the candidate set down by the strongest key that produced it.
-- The interesting row is AC: a small number of pairs, carrying almost all
-- of the certainty in the system, and every one of them invisible to a
-- purely semantic approach.
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW `${CDP_PROJECT}.${CDP_DS}.v_blocking_by_key` AS
SELECT
  CASE block_strength
    WHEN 100 THEN 'AC · shared account number'
    WHEN  90 THEN 'EM · shared email'
    WHEN  80 THEN 'PH · shared phone'
    WHEN  70 THEN 'ND · surname + date of birth'
    WHEN  30 THEN 'SX · soundex + outward postcode'
    WHEN  10 THEN 'PC · postcode district only'
    ELSE          'unknown'
  END                                    AS strongest_key,
  block_strength,
  COUNT(*)                               AS pairs,
  ROUND(AVG(keys_shared), 2)             AS avg_keys_shared
FROM `${CDP_PROJECT}.${CDP_DS}.candidate_pairs_blocked`
GROUP BY strongest_key, block_strength
ORDER BY block_strength DESC;
