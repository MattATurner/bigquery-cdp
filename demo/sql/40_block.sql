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


-- ---------------------------------------------------------------------
-- 40e · Bipartite identifier graph — membership & temporal history
--
-- Models each source record's identifiers as edges in a bipartite graph
-- (SourceRecord / Profile <-> Identifier), matching the WesID_nodes and
-- WesID_edges pattern:
--
--   · Personal & household identifiers extracted from party_records
--     (email, phone, loyalty_account, street address)
--   · Promiscuous operational hubs (shared call-centre callback numbers,
--     in-store checkout kiosk emails, and shared POS terminal device IDs)
--     that attach to hundreds of unrelated customer records and cause
--     naive Connected Components to collapse into a "hairball"
--   · Temporal supersession history (has_identifier_history) tracking
--     when a recycled mobile phone or email moved from one customer to
--     another (transit_to).
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.has_identifier`
CLUSTER BY record_id, identifier_type
AS
WITH real_identifiers AS (
  SELECT
    record_id,
    CONCAT('EM:', email_norm)   AS identifier_id,
    'email'                     AS identifier_type,
    source_system = 'CRM'       AS is_anchor,
    source_system               AS sources,
    source_system               AS first_seen_in,
    source_ts                   AS from_ts
  FROM `${CDP_PROJECT}.${CDP_DS}.party_records`
  WHERE email_norm IS NOT NULL AND email_norm != ''

  UNION ALL

  SELECT
    record_id,
    CONCAT('PH:', phone_e164)   AS identifier_id,
    'phone'                     AS identifier_type,
    source_system = 'LOYALTY'   AS is_anchor,
    source_system               AS sources,
    source_system               AS first_seen_in,
    source_ts                   AS from_ts
  FROM `${CDP_PROJECT}.${CDP_DS}.party_records`
  WHERE phone_e164 IS NOT NULL AND phone_e164 != ''

  UNION ALL

  SELECT
    record_id,
    CONCAT('AC:', account_number) AS identifier_id,
    'loyalty_account'             AS identifier_type,
    TRUE                          AS is_anchor,
    source_system                 AS sources,
    source_system                 AS first_seen_in,
    source_ts                     AS from_ts
  FROM `${CDP_PROJECT}.${CDP_DS}.party_records`
  WHERE account_number IS NOT NULL AND account_number != ''
),
-- Deterministic operational hubs: call-centre fallback numbers, in-store
-- kiosk checkout emails, and shared store tablet device IDs. A small
-- fraction of records touch two hubs, chaining them into one giant
-- component under naive Connected Components.
hub_identifiers AS (
  SELECT
    record_id,
    CASE MOD(ABS(FARM_FINGERPRINT(CONCAT(record_id, '|hub1'))), 6)
      WHEN 0 THEN 'PH:+61290001111'
      WHEN 1 THEN 'PH:+61390002222'
      WHEN 2 THEN 'EM:kiosk.syd@store-checkout.com.au'
      WHEN 3 THEN 'EM:kiosk.mel@store-checkout.com.au'
      WHEN 4 THEN 'EM:service.desk@contact-centre.com.au'
      ELSE        'DV:KIOSK-TERMINAL-AU-01'
    END                         AS identifier_id,
    CASE MOD(ABS(FARM_FINGERPRINT(CONCAT(record_id, '|hub1'))), 6)
      WHEN 0 THEN 'phone'
      WHEN 1 THEN 'phone'
      WHEN 2 THEN 'email'
      WHEN 3 THEN 'email'
      WHEN 4 THEN 'email'
      ELSE        'device_id'
    END                         AS identifier_type,
    FALSE                       AS is_anchor,
    source_system               AS sources,
    source_system               AS first_seen_in,
    source_ts                   AS from_ts
  FROM `${CDP_PROJECT}.${CDP_DS}.party_records`
  WHERE MOD(ABS(FARM_FINGERPRINT(CONCAT(record_id, '|hub_gate'))), 100) < 16

  UNION ALL

  -- Bridge records that also touched a second shared kiosk/call-centre hub
  SELECT
    record_id,
    'PH:+61890003333'           AS identifier_id,
    'phone'                     AS identifier_type,
    FALSE                       AS is_anchor,
    source_system               AS sources,
    source_system               AS first_seen_in,
    source_ts                   AS from_ts
  FROM `${CDP_PROJECT}.${CDP_DS}.party_records`
  WHERE MOD(ABS(FARM_FINGERPRINT(CONCAT(record_id, '|hub_gate'))), 100) < 2
)
SELECT * FROM real_identifiers
UNION ALL
SELECT * FROM hub_identifiers;


-- Full temporal history including closed/recycled phone links (HAD_IDENTIFIER)
CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.has_identifier_history`
CLUSTER BY record_id, identifier_id
AS
WITH current_rows AS (
  SELECT
    FARM_FINGERPRINT(CONCAT(record_id, '|', identifier_id, '|current')) AS row_id,
    record_id,
    identifier_id,
    identifier_type,
    is_anchor,
    from_ts,
    CAST(NULL AS TIMESTAMP) AS to_ts,
    CAST(NULL AS STRING)    AS transit_to,
    TRUE                    AS is_current,
    FALSE                   AS is_deleted,
    sources
  FROM `${CDP_PROJECT}.${CDP_DS}.has_identifier`
),
-- Historical phone recycling events: where two records share a phone but
-- have conflicting dates of birth, record the earlier holder as a superseded
-- historical link with transit_to pointing to the later holder.
recycled AS (
  SELECT
    FARM_FINGERPRINT(CONCAT(a.record_id, '|PH:', a.phone_e164, '|hist')) AS row_id,
    a.record_id,
    CONCAT('PH:', a.phone_e164) AS identifier_id,
    'phone'                     AS identifier_type,
    FALSE                       AS is_anchor,
    a.source_ts                 AS from_ts,
    b.source_ts                 AS to_ts,
    b.record_id                 AS transit_to,
    FALSE                       AS is_current,
    FALSE                       AS is_deleted,
    a.source_system             AS sources
  FROM `${CDP_PROJECT}.${CDP_DS}.party_records` AS a
  JOIN `${CDP_PROJECT}.${CDP_DS}.party_records` AS b
    ON a.phone_e164 = b.phone_e164
   AND a.record_id != b.record_id
   AND a.dob IS NOT NULL AND b.dob IS NOT NULL AND a.dob != b.dob
   AND IFNULL(a.source_ts, TIMESTAMP '2020-01-01') < IFNULL(b.source_ts, TIMESTAMP '2025-01-01')
  WHERE a.phone_e164 IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (PARTITION BY a.record_id, a.phone_e164 ORDER BY b.source_ts) = 1
)
SELECT * FROM current_rows
UNION ALL
SELECT * FROM recycled;


-- ---------------------------------------------------------------------
-- 40f · Identifier nodes with degree, IDF rarity weight, and hub flag
--
-- Degree is a property of the Identifier node itself. Computing it once
-- here makes both the SQL rarity rule and the 2-hop neighbourhood
-- features a simple lookup rather than a repeated self-join.
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.identifier`
CLUSTER BY identifier_type, identifier_id
AS
WITH total AS (
  SELECT GREATEST(COUNT(*), 1) AS n_profiles
  FROM `${CDP_PROJECT}.${CDP_DS}.party_records`
),
cur AS (
  SELECT
    identifier_id,
    ANY_VALUE(identifier_type)                   AS identifier_type,
    COUNT(DISTINCT record_id)                    AS degree,
    COUNTIF(is_anchor)                           AS n_anchor_links,
    STRING_AGG(DISTINCT sources, '|' ORDER BY sources) AS sources,
    MIN(from_ts)                                 AS first_seen_ts,
    MAX(from_ts)                                 AS last_seen_ts
  FROM `${CDP_PROJECT}.${CDP_DS}.has_identifier`
  GROUP BY identifier_id
),
hist AS (
  SELECT
    identifier_id,
    COUNT(DISTINCT record_id)                    AS degree_all_time
  FROM `${CDP_PROJECT}.${CDP_DS}.has_identifier_history`
  GROUP BY identifier_id
)
SELECT
  c.identifier_id,
  c.identifier_type,
  c.degree,
  IFNULL(h.degree_all_time, c.degree)            AS degree_all_time,
  c.n_anchor_links,
  -- Inverse document frequency: rare identifiers carry high weight (~9.9
  -- for a pair); promiscuous hubs carry low weight and are flagged.
  ROUND(LN(SAFE_DIVIDE(t.n_profiles, GREATEST(c.degree, 1))), 4) AS idf_weight,
  c.degree > 25                                  AS is_promiscuous,
  c.sources,
  c.first_seen_ts,
  c.last_seen_ts
FROM cur AS c
LEFT JOIN hist AS h USING (identifier_id)
CROSS JOIN total AS t;


-- ---------------------------------------------------------------------
-- 40g · Co-observed identifier links (linked_identifier)
--
-- Identifiers observed together on the same customer record (the
-- WesID_edges pattern). Stored as unordered non-promiscuous pairs.
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.linked_identifier`
CLUSTER BY lhs_identifier_id, rhs_identifier_id
AS
SELECT
  a.identifier_id            AS lhs_identifier_id,
  b.identifier_id            AS rhs_identifier_id,
  ANY_VALUE(a.identifier_type) AS lhs_type,
  ANY_VALUE(b.identifier_type) AS rhs_type,
  ANY_VALUE(a.record_id)     AS observed_on_record,
  ANY_VALUE(a.sources)       AS edge_source,
  MIN(a.from_ts)             AS from_ts
FROM `${CDP_PROJECT}.${CDP_DS}.has_identifier` AS a
JOIN `${CDP_PROJECT}.${CDP_DS}.has_identifier` AS b
  ON a.record_id = b.record_id
 AND a.identifier_id < b.identifier_id
JOIN `${CDP_PROJECT}.${CDP_DS}.identifier` AS ia ON ia.identifier_id = a.identifier_id
JOIN `${CDP_PROJECT}.${CDP_DS}.identifier` AS ib ON ib.identifier_id = b.identifier_id
WHERE NOT ia.is_promiscuous AND NOT ib.is_promiscuous
GROUP BY 1, 2;


-- ---------------------------------------------------------------------
-- 40h · IDF-weighted bipartite projection & 2-hop neighbourhood summary
--
-- Projects Profile -> Identifier -> Profile (2 hops) and computes:
--   1. The shared-identifier rarity weight (promiscuous hubs weight 0)
--   2. What each profile holds in its 1-hop neighbourhood that it does
--      NOT share with the other profile (unshared emails, phones, and
--      loyalty accounts) — the structural signal that separates a
--      two-person household from a single person's sparse duplicate.
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.profile_projection`
CLUSTER BY record_id_a, record_id_b
AS
WITH shared AS (
  SELECT
    a.record_id      AS record_id_a,
    b.record_id      AS record_id_b,
    a.identifier_id,
    i.identifier_type,
    i.degree,
    i.is_promiscuous,
    IF(i.is_promiscuous, 0.0, i.idf_weight) AS effective_weight
  FROM `${CDP_PROJECT}.${CDP_DS}.has_identifier` AS a
  JOIN `${CDP_PROJECT}.${CDP_DS}.has_identifier` AS b
    ON a.identifier_id = b.identifier_id
   AND a.record_id < b.record_id
  JOIN `${CDP_PROJECT}.${CDP_DS}.identifier` AS i
    ON i.identifier_id = a.identifier_id
  -- Cap fan-out expansion on massive hubs: we sample hub-only pairs up to
  -- a rank cap for graph diagnostics while never expanding 500k+ hub pairs.
  WHERE NOT i.is_promiscuous
     OR MOD(ABS(FARM_FINGERPRINT(CONCAT(a.record_id, '|', b.record_id))), 25) = 0
),
agg AS (
  SELECT
    record_id_a,
    record_id_b,
    ROUND(SUM(effective_weight), 4)                             AS weight,
    COUNT(*)                                                    AS n_shared,
    COUNTIF(NOT is_promiscuous)                                 AS n_shared_non_hub,
    STRING_AGG(identifier_id,   '|' ORDER BY identifier_id)     AS shared_identifiers,
    STRING_AGG(identifier_type, '|' ORDER BY identifier_id)     AS shared_types,
    LOGICAL_OR(is_promiscuous)                                  AS via_hub,
    LOGICAL_AND(is_promiscuous)                                 AS hub_only,
    MIN(degree)                                                 AS min_shared_degree
  FROM shared
  GROUP BY record_id_a, record_id_b
)
SELECT
  g.*,
  -- 2-hop neighbourhood check: does each profile hold its own distinct,
  -- unshared identifier of the same type? Two inboxes or two personal
  -- mobiles alongside a shared phone/address is the signature of a
  -- two-person household rather than a single person's duplicate record.
  (pa.email_norm IS NOT NULL AND pb.email_norm IS NOT NULL
   AND pa.email_norm != pb.email_norm)                          AS unshared_email_both,
  (pa.phone_e164 IS NOT NULL AND pb.phone_e164 IS NOT NULL
   AND pa.phone_e164 != pb.phone_e164)                          AS unshared_phone_both,
  (pa.account_number IS NOT NULL AND pb.account_number IS NOT NULL
   AND pa.account_number != pb.account_number)                  AS unshared_acct_both
FROM agg AS g
JOIN `${CDP_PROJECT}.${CDP_DS}.party_records` AS pa ON pa.record_id = g.record_id_a
JOIN `${CDP_PROJECT}.${CDP_DS}.party_records` AS pb ON pb.record_id = g.record_id_b;

