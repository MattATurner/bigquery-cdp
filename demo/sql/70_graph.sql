-- =====================================================================
-- 70 · Graph
--
-- Two graphs, and the distinction matters:
--
--   resolution graph · records joined by match decisions. Working
--                      machinery. Its job is to derive person_id.
--   mastered graph   · people, households, addresses, emails, phones,
--                      accounts and the relationships between them. The
--                      published product that downstream teams consume.
--
-- Collapsing them is the most common design mistake in an MDM build. The
-- resolution graph is full of provisional, low-confidence edges that
-- exist to be argued about; the mastered graph must not be.
-- =====================================================================


-- ---------------------------------------------------------------------
-- 70a · Connected components, as a reusable procedure
--
-- Label propagation: every node starts as its own component and
-- repeatedly adopts the smallest label among its neighbours. It converges
-- in as many iterations as the longest path in the graph — a handful for
-- identity data, where clusters are small and dense.
--
-- Written as a procedure because it is run twice: once on all accepted
-- links, and again on a pruned edge set after contradictions are found.
-- ---------------------------------------------------------------------

CREATE OR REPLACE PROCEDURE `${CDP_PROJECT}.${CDP_DS}.sp_connected_components`(
  nodes_tbl STRING,   -- must expose a `node` column
  edges_tbl STRING,   -- must expose `src` and `dst`, both directions present
  out_tbl   STRING,
  max_iter  INT64
)
BEGIN
  DECLARE changed INT64 DEFAULT 1;
  DECLARE i       INT64 DEFAULT 0;

  EXECUTE IMMEDIATE FORMAT("""
    CREATE OR REPLACE TABLE `%s` AS
    SELECT node, node AS comp FROM `%s`
  """, out_tbl, nodes_tbl);

  WHILE changed > 0 AND i < max_iter DO
    EXECUTE IMMEDIATE FORMAT("""
      CREATE OR REPLACE TABLE `%s_next` AS
      SELECT n.node, LEAST(n.comp, IFNULL(MIN(c.comp), n.comp)) AS comp
      FROM `%s` AS n
      LEFT JOIN `%s` AS e ON e.src  = n.node
      LEFT JOIN `%s` AS c ON c.node = e.dst
      GROUP BY n.node, n.comp
    """, out_tbl, out_tbl, edges_tbl, out_tbl);

    EXECUTE IMMEDIATE FORMAT("""
      SELECT COUNT(*)
      FROM `%s_next` AS a
      JOIN `%s` AS b USING (node)
      WHERE a.comp != b.comp
    """, out_tbl, out_tbl) INTO changed;

    EXECUTE IMMEDIATE FORMAT("""
      CREATE OR REPLACE TABLE `%s` AS SELECT * FROM `%s_next`
    """, out_tbl, out_tbl);

    SET i = i + 1;
  END WHILE;

  EXECUTE IMMEDIATE FORMAT("""
    DROP TABLE IF EXISTS `%s_next`
  """, out_tbl);

  -- A run that exits on the iteration guard has NOT converged, and the
  -- resulting clusters are wrong. Fail rather than publish them.
  IF changed > 0 THEN
    RAISE USING MESSAGE = FORMAT(
      'Connected components did not converge in %d iterations on %s. '
      'This usually means an edge set far denser than expected — check the '
      'auto-match threshold before raising max_iter.', max_iter, edges_tbl);
  END IF;
END;


-- ---------------------------------------------------------------------
-- 70b · Pass one — all accepted links
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.graph_nodes`
AS SELECT record_id AS node FROM `${CDP_PROJECT}.${CDP_DS}.party_search`;

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.graph_edges_all`
AS
SELECT record_id_a AS src, record_id_b AS dst FROM `${CDP_PROJECT}.${CDP_DS}.match_decisions`
WHERE decision = 'LINK'
UNION ALL
SELECT record_id_b, record_id_a FROM `${CDP_PROJECT}.${CDP_DS}.match_decisions`
WHERE decision = 'LINK';

CALL `${CDP_PROJECT}.${CDP_DS}.sp_connected_components`(
  '${CDP_PROJECT}.${CDP_DS}.graph_nodes',
  '${CDP_PROJECT}.${CDP_DS}.graph_edges_all',
  '${CDP_PROJECT}.${CDP_DS}.cc_pass1',
  20
);


-- ---------------------------------------------------------------------
-- 70c · Contradiction detection
--
-- Transitive closure is where entity resolution goes wrong at scale. A
-- links to B plausibly, B links to C plausibly, and the closure quietly
-- asserts that A is C — even though A and C were never compared and are
-- demonstrably different people.
--
-- This is the OVERMERGE_BAIT case in the generator, and it is the failure
-- mode that turns a CDP into a data breach. So the closure is not
-- trusted: every component is checked for internal contradiction.
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.component_conflicts`
AS
WITH members AS (
  SELECT c.comp, c.node AS record_id, p.dob, p.name_norm, p.account_number
  FROM `${CDP_PROJECT}.${CDP_DS}.cc_pass1` AS c
  JOIN `${CDP_PROJECT}.${CDP_DS}.party_search` AS p ON p.record_id = c.node
)
SELECT
  comp,
  COUNT(*)                                                    AS members,
  COUNT(DISTINCT dob)                                         AS distinct_dobs,
  ARRAY_AGG(DISTINCT CAST(dob AS STRING) IGNORE NULLS
            ORDER BY CAST(dob AS STRING))                     AS dobs,
  -- More than one date of birth in a cluster means the cluster contains
  -- more than one person. There is no benign reading of this.
  COUNT(DISTINCT dob) > 1                                     AS dob_contradiction
FROM members
GROUP BY comp
HAVING COUNT(DISTINCT dob) > 1;


-- ---------------------------------------------------------------------
-- 70d · Pass two — prune, then re-resolve
--
-- Contradicted components are rebuilt using only edges strong enough to
-- stand on their own: a shared account number, email, phone or date of
-- birth, or a near-certain score. The weak middle link of an A–B–C chain
-- falls away and the cluster splits where it should have split.
--
-- Edges outside contradicted components are untouched. A problem in one
-- cluster does not get to raise the bar for everybody else.
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.graph_edges_pruned`
AS
WITH suspect_nodes AS (
  SELECT c.node
  FROM `${CDP_PROJECT}.${CDP_DS}.cc_pass1` AS c
  JOIN `${CDP_PROJECT}.${CDP_DS}.component_conflicts` AS x USING (comp)
),
links AS (
  SELECT
    d.record_id_a,
    d.record_id_b,
    d.confidence,
    t.a_dob, t.b_dob,
    t.acct_match, t.email_match, t.phone_match, t.dob_match, t.dob_conflict,
    t.combined_score
  FROM `${CDP_PROJECT}.${CDP_DS}.match_decisions` AS d
  JOIN `${CDP_PROJECT}.${CDP_DS}.pair_tiers` AS t
    ON t.record_id_a = d.record_id_a AND t.record_id_b = d.record_id_b
  WHERE d.decision = 'LINK'
),
undirected AS (
  SELECT record_id_a AS u, record_id_b AS v, dob_conflict FROM links
  UNION ALL
  SELECT record_id_b AS u, record_id_a AS v, dob_conflict FROM links
),
-- Triangle support (local clustering consensus): an edge (a, b) that shares
-- a common neighbour c with no DOB conflict belongs to a dense sub-cluster
-- rather than a single weak bridge between two distinct people.
triangle_edges AS (
  SELECT DISTINCT
    l.record_id_a,
    l.record_id_b
  FROM links AS l
  JOIN undirected AS e1
    ON e1.u = l.record_id_a AND NOT e1.dob_conflict
  JOIN undirected AS e2
    ON e2.u = l.record_id_b AND e2.v = e1.v AND NOT e2.dob_conflict
  WHERE e1.v != l.record_id_a AND e1.v != l.record_id_b
),
classified AS (
  SELECT
    l.*,
    (l.record_id_a IN (SELECT node FROM suspect_nodes)
     OR l.record_id_b IN (SELECT node FROM suspect_nodes))        AS in_suspect_component,
    -- In a component already proven to contain conflicting dates of birth,
    -- an edge involving a NULL DOB cannot be trusted as a strong bridge
    -- between two different people. Require explicit DOB agreement.
    (NOT l.dob_conflict
     AND l.a_dob IS NOT NULL AND l.b_dob IS NOT NULL
     AND (l.acct_match OR l.email_match OR l.phone_match OR l.dob_match
          OR l.combined_score >= 0.95))                           AS strong,
    (tr.record_id_a IS NOT NULL AND NOT l.dob_conflict)           AS has_triangle_support
  FROM links AS l
  LEFT JOIN triangle_edges AS tr
    ON tr.record_id_a = l.record_id_a AND tr.record_id_b = l.record_id_b
),
kept AS (
  SELECT record_id_a, record_id_b
  FROM classified
  WHERE NOT in_suspect_component OR strong OR has_triangle_support
)
SELECT record_id_a AS src, record_id_b AS dst FROM kept
UNION ALL
SELECT record_id_b, record_id_a FROM kept;

CALL `${CDP_PROJECT}.${CDP_DS}.sp_connected_components`(
  '${CDP_PROJECT}.${CDP_DS}.graph_nodes',
  '${CDP_PROJECT}.${CDP_DS}.graph_edges_pruned',
  '${CDP_PROJECT}.${CDP_DS}.cc_final',
  20
);


-- ---------------------------------------------------------------------
-- 70e · Stable person identifiers
--
-- The hardest unglamorous problem in the whole build.
--
-- A person_id derived from the cluster itself — the minimum record_id,
-- a hash of the members — changes every time a record is added or
-- removed. Downstream, that means audience memberships churn, suppression
-- lists break, and a customer who was excluded from a campaign last month
-- silently reappears. The identifier has to outlive the cluster that
-- produced it.
--
-- So identifiers are persisted in a crosswalk and inherited: a cluster
-- adopts the person_id already held by the plurality of its members, and
-- only a genuinely new cluster mints a new one. Splits and merges are
-- recorded rather than applied silently.
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `${CDP_PROJECT}.${CDP_DS}.person_crosswalk`
(
  record_id  STRING    NOT NULL,
  person_id  STRING    NOT NULL,
  first_seen TIMESTAMP NOT NULL,
  last_seen  TIMESTAMP NOT NULL
)
CLUSTER BY record_id
OPTIONS (
  description = 'Durable record_id → person_id assignment. Survives re-runs so that '
             || 'downstream audiences and suppression lists remain stable.'
);

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.person_assignment`
AS
WITH comp_members AS (
  SELECT comp, node AS record_id FROM `${CDP_PROJECT}.${CDP_DS}.cc_final`
),
-- Which existing person_id does each component already mostly hold?
inherited AS (
  SELECT comp, person_id, COUNT(*) AS n
  FROM comp_members
  JOIN `${CDP_PROJECT}.${CDP_DS}.person_crosswalk` USING (record_id)
  GROUP BY comp, person_id
),
best AS (
  SELECT comp, person_id AS inherited_person_id
  FROM (
    SELECT comp, person_id,
           ROW_NUMBER() OVER (PARTITION BY comp ORDER BY n DESC, person_id)      AS rn_comp,
           -- Ensure a historical person_id can be inherited by at most ONE
           -- component, so that a split cluster does not re-merge downstream.
           ROW_NUMBER() OVER (PARTITION BY person_id ORDER BY n DESC, comp)      AS rn_person
    FROM inherited
  )
  WHERE rn_comp = 1 AND rn_person = 1
)
SELECT
  m.comp,
  m.record_id,
  COALESCE(
    b.inherited_person_id,
    -- Minted from the component anchor. Deterministic for a given run, and
    -- immediately persisted so it never needs to be derived again.
    CONCAT('PER-', FORMAT('%016x', FARM_FINGERPRINT(m.comp) & 0x7fffffffffffffff))
  ) AS person_id,
  b.inherited_person_id IS NULL AS newly_minted
FROM comp_members AS m
LEFT JOIN best AS b USING (comp);

MERGE `${CDP_PROJECT}.${CDP_DS}.person_crosswalk` AS x
USING `${CDP_PROJECT}.${CDP_DS}.person_assignment` AS a
ON x.record_id = a.record_id
WHEN MATCHED THEN
  UPDATE SET person_id = a.person_id, last_seen = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN
  INSERT (record_id, person_id, first_seen, last_seen)
  VALUES (a.record_id, a.person_id, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP());


-- ---------------------------------------------------------------------
-- 70f · Resolution graph
--
-- Every edge that was considered, with how it was decided and why. This
-- is the audit surface: "why is this record on this profile" has a
-- one-row answer.
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.resolution_edges`
CLUSTER BY record_id_a, record_id_b
AS
SELECT
  d.record_id_a,
  d.record_id_b,
  d.decision,
  d.decided_by,
  d.confidence,
  d.rationale,
  d.contradiction,
  d.retrieved_by,
  d.combined_score,
  d.rule_score,
  d.similarity,
  pa.person_id AS person_id_a,
  pb.person_id AS person_id_b,
  -- An edge the pruning step removed: it was accepted, but the cluster it
  -- would have created contradicted itself.
  d.decision = 'LINK' AND pa.person_id != pb.person_id AS suppressed_by_contradiction
FROM `${CDP_PROJECT}.${CDP_DS}.match_decisions` AS d
LEFT JOIN `${CDP_PROJECT}.${CDP_DS}.person_assignment` AS pa ON pa.record_id = d.record_id_a
LEFT JOIN `${CDP_PROJECT}.${CDP_DS}.person_assignment` AS pb ON pb.record_id = d.record_id_b;


-- ---------------------------------------------------------------------
-- 70g · Mastered graph — nodes
--
-- Seven node types. Emails, phones, addresses and accounts are first
-- class nodes rather than attributes, because that is what makes the
-- interesting questions cheap: "who else uses this phone number", "how
-- many people share this address", "which accounts span households".
-- ---------------------------------------------------------------------

-- 1 · Person
CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.node_person`
CLUSTER BY person_id
AS
SELECT
  a.person_id,
  COUNT(*)                                     AS source_record_count,
  COUNT(DISTINCT p.source_system)              AS source_system_count,
  ARRAY_AGG(DISTINCT p.source_system ORDER BY p.source_system) AS source_systems,
  MAX(p.identity_strength)                     AS best_identity_strength,
  MIN(p.source_ts)                             AS first_seen_at,
  MAX(p.source_ts)                             AS last_seen_at,
  LOGICAL_OR(a.newly_minted)                   AS minted_this_run
FROM `${CDP_PROJECT}.${CDP_DS}.person_assignment` AS a
JOIN `${CDP_PROJECT}.${CDP_DS}.party_records` AS p ON p.record_id = a.record_id
GROUP BY a.person_id;

-- 2 · Source record
CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.node_source_record`
CLUSTER BY record_id
AS
SELECT
  p.record_id,
  p.source_system,
  p.source_trust,
  p.source_natural_key,
  p.source_ts,
  p.raw_name,
  p.raw_postcode,
  p.identity_strength,
  p.evidence_note,
  p.injection_attempt
FROM `${CDP_PROJECT}.${CDP_DS}.party_records` AS p;

-- 3 · Address
CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.node_address`
AS
SELECT
  TO_HEX(SHA256(CONCAT(address_norm, '|', IFNULL(postcode_norm, '')))) AS address_id,
  address_norm,
  postcode_norm,
  postcode_out,
  COUNT(DISTINCT record_id) AS record_count
FROM `${CDP_PROJECT}.${CDP_DS}.party_records`
WHERE address_norm IS NOT NULL
GROUP BY address_norm, postcode_norm, postcode_out;

-- 4 · Email
CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.node_email`
AS
SELECT
  email_norm AS email_id,
  email_norm,
  REGEXP_EXTRACT(email_norm, r'@(.+)$') AS domain,
  COUNT(DISTINCT record_id)             AS record_count
FROM `${CDP_PROJECT}.${CDP_DS}.party_records`
WHERE email_norm IS NOT NULL
GROUP BY email_norm;

-- 5 · Phone
CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.node_phone`
AS
SELECT
  phone_e164 AS phone_id,
  phone_e164,
  -- Mobiles are personal; landlines are household-level, and that difference
  -- should change how much weight a shared number carries.
  --
  -- Every Australian mobile number begins 04, so once norm_phone applies the
  -- +61 country code and drops the trunk zero they all begin '+614'. Australia
  -- has exactly four geographic area codes -- 02, 03, 07 and 08 -- which
  -- normalise to +612, +613, +617 and +618. There is no area code 4, so no
  -- landline can begin '+614' and the test needs no further qualification.
  --
  -- Keep this constant pointed at whatever norm_phone actually emits. It has
  -- been wrong before: the corpus was relocalised, norm_phone changed its
  -- output prefix, and this consumer was not updated, so the test matched
  -- nothing and is_mobile was FALSE for every record in the corpus -- silently,
  -- because a predicate that is always false produces no error and no empty
  -- result, just a quietly wrong weight. Worth remembering when localising
  -- anything else here: update the producer AND grep for its output format.
  STARTS_WITH(phone_e164, '+614') AS is_mobile,
  COUNT(DISTINCT record_id)       AS record_count
FROM `${CDP_PROJECT}.${CDP_DS}.party_records`
WHERE phone_e164 IS NOT NULL
GROUP BY phone_e164;

-- 6 · Loyalty account
CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.node_account`
AS
SELECT
  account_number AS account_id,
  account_number,
  COUNT(DISTINCT record_id) AS record_count
FROM `${CDP_PROJECT}.${CDP_DS}.party_records`
WHERE account_number IS NOT NULL
GROUP BY account_number;

-- 7 · Household
--
-- Inferred from a shared address, and deliberately NOT from a shared
-- surname: that would miss unmarried partners, lodgers and house shares,
-- and would wrongly group unrelated people who happen to share a common
-- surname in a block of flats.
--
-- A household is an inference, not a fact. It is useful for targeting and
-- suppression. It must never be used as evidence that two people are one
-- person.
CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.node_household`
AS
SELECT
  CONCAT('HH-', SUBSTR(address_id, 1, 16)) AS household_id,
  address_id,
  address_norm,
  postcode_norm,
  person_count
FROM (
  SELECT
    TO_HEX(SHA256(CONCAT(p.address_norm, '|', IFNULL(p.postcode_norm, '')))) AS address_id,
    p.address_norm,
    p.postcode_norm,
    COUNT(DISTINCT a.person_id) AS person_count
  FROM `${CDP_PROJECT}.${CDP_DS}.party_records` AS p
  JOIN `${CDP_PROJECT}.${CDP_DS}.person_assignment` AS a ON a.record_id = p.record_id
  WHERE p.address_norm IS NOT NULL AND p.postcode_norm IS NOT NULL
  GROUP BY address_norm, postcode_norm
);


-- ---------------------------------------------------------------------
-- 70h · Mastered graph — edges
-- ---------------------------------------------------------------------

-- 1 · SourceRecord —RESOLVES_TO→ Person
CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.edge_resolves_to`
CLUSTER BY person_id
AS
SELECT
  a.record_id,
  a.person_id,
  p.source_system,
  p.source_trust
FROM `${CDP_PROJECT}.${CDP_DS}.person_assignment` AS a
JOIN `${CDP_PROJECT}.${CDP_DS}.party_records` AS p ON p.record_id = a.record_id;

-- 2 · Person —LIVES_AT→ Address
CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.edge_lives_at`
AS
SELECT
  a.person_id,
  TO_HEX(SHA256(CONCAT(p.address_norm, '|', IFNULL(p.postcode_norm, '')))) AS address_id,
  MAX(p.source_ts)                    AS last_asserted_at,
  MAX(p.source_trust)                 AS best_source_trust,
  COUNT(*)                            AS assertions,
  -- The most recently asserted address from a trustworthy source is the
  -- current one. Everything else is history, and history is worth keeping:
  -- a stale address is how you find someone who has moved.
  ROW_NUMBER() OVER (
    PARTITION BY a.person_id
    ORDER BY MAX(p.source_trust) DESC, MAX(p.source_ts) DESC
  ) = 1                               AS is_current
FROM `${CDP_PROJECT}.${CDP_DS}.party_records` AS p
JOIN `${CDP_PROJECT}.${CDP_DS}.person_assignment` AS a ON a.record_id = p.record_id
WHERE p.address_norm IS NOT NULL
GROUP BY a.person_id, address_id;

-- 3 · Person —MEMBER_OF→ Household
CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.edge_member_of`
AS
SELECT DISTINCT
  e.person_id,
  h.household_id
FROM `${CDP_PROJECT}.${CDP_DS}.edge_lives_at` AS e
JOIN `${CDP_PROJECT}.${CDP_DS}.node_household` AS h USING (address_id)
WHERE e.is_current;

-- 4 · Person —HAS_EMAIL→ Email
CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.edge_has_email`
AS
SELECT
  a.person_id,
  p.email_norm AS email_id,
  MAX(p.source_trust) AS best_source_trust,
  MAX(p.source_ts)    AS last_asserted_at,
  COUNT(*)            AS assertions
FROM `${CDP_PROJECT}.${CDP_DS}.party_records` AS p
JOIN `${CDP_PROJECT}.${CDP_DS}.person_assignment` AS a ON a.record_id = p.record_id
WHERE p.email_norm IS NOT NULL
GROUP BY a.person_id, p.email_norm;

-- 5 · Person —HAS_PHONE→ Phone
CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.edge_has_phone`
AS
SELECT
  a.person_id,
  p.phone_e164 AS phone_id,
  MAX(p.source_trust) AS best_source_trust,
  MAX(p.source_ts)    AS last_asserted_at,
  COUNT(*)            AS assertions
FROM `${CDP_PROJECT}.${CDP_DS}.party_records` AS p
JOIN `${CDP_PROJECT}.${CDP_DS}.person_assignment` AS a ON a.record_id = p.record_id
WHERE p.phone_e164 IS NOT NULL
GROUP BY a.person_id, p.phone_e164;

-- 6 · Person —HOLDS_ACCOUNT→ LoyaltyAccount
CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.edge_holds_account`
AS
SELECT
  a.person_id,
  p.account_number AS account_id,
  COUNT(*) AS assertions
FROM `${CDP_PROJECT}.${CDP_DS}.party_records` AS p
JOIN `${CDP_PROJECT}.${CDP_DS}.person_assignment` AS a ON a.record_id = p.record_id
WHERE p.account_number IS NOT NULL
GROUP BY a.person_id, p.account_number;

-- 7 · Person —SUSPECTED_LINK→ Person
--
-- The steward queue, expressed as graph edges rather than a side table.
-- These are pairs the system refused to decide. Keeping them in the graph
-- means downstream consumers can see that a profile is provisional,
-- instead of discovering it when a customer complains.
CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.edge_suspected_link`
AS
SELECT DISTINCT
  LEAST(pa.person_id, pb.person_id)    AS person_id_a,
  GREATEST(pa.person_id, pb.person_id) AS person_id_b,
  d.confidence,
  d.rationale,
  d.contradiction,
  d.decided_by,
  d.retrieved_by
FROM `${CDP_PROJECT}.${CDP_DS}.match_decisions` AS d
JOIN `${CDP_PROJECT}.${CDP_DS}.person_assignment` AS pa ON pa.record_id = d.record_id_a
JOIN `${CDP_PROJECT}.${CDP_DS}.person_assignment` AS pb ON pb.record_id = d.record_id_b
WHERE d.decision = 'STEWARD'
  AND pa.person_id != pb.person_id;

-- 8 · Person —RELATED_TO→ Person
--
-- Asserted relationships, taken only from what somebody actually said.
-- The call transcript case — "I'm ringing about my wife's account" —
-- produces a relationship edge, which is the correct outcome. The wrong
-- outcome, and the easy one, is a merge.
CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.edge_related_to`
AS
SELECT DISTINCT
  caller.person_id                     AS person_id,
  holder.person_id                     AS related_person_id,
  IFNULL(c.relationship_to_account, 'UNSPECIFIED') AS relationship,
  'CALL_TRANSCRIPT'                    AS asserted_by,
  c.record_id                          AS evidence_record_id
FROM `${CDP_PROJECT}.${CDP_DS}.stg_call_entities` AS c
JOIN `${CDP_PROJECT}.${CDP_DS}.person_assignment` AS caller
  ON caller.record_id = c.record_id
-- The account holder is identified by the account number the caller quoted.
JOIN `${CDP_PROJECT}.${CDP_DS}.edge_holds_account` AS ha
  ON ha.account_id = c.account_number
JOIN `${CDP_PROJECT}.${CDP_DS}.node_person` AS holder
  ON holder.person_id = ha.person_id
WHERE NOT c.caller_is_account_holder
  AND c.account_number IS NOT NULL
  AND caller.person_id != ha.person_id;


-- ---------------------------------------------------------------------
-- 70i · Shape of the result
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW `${CDP_PROJECT}.${CDP_DS}.v_graph_summary` AS
SELECT 'node · person'         AS element, COUNT(*) AS n FROM `${CDP_PROJECT}.${CDP_DS}.node_person`
UNION ALL SELECT 'node · source record', COUNT(*) FROM `${CDP_PROJECT}.${CDP_DS}.node_source_record`
UNION ALL SELECT 'node · household',     COUNT(*) FROM `${CDP_PROJECT}.${CDP_DS}.node_household`
UNION ALL SELECT 'node · address',       COUNT(*) FROM `${CDP_PROJECT}.${CDP_DS}.node_address`
UNION ALL SELECT 'node · email',         COUNT(*) FROM `${CDP_PROJECT}.${CDP_DS}.node_email`
UNION ALL SELECT 'node · phone',         COUNT(*) FROM `${CDP_PROJECT}.${CDP_DS}.node_phone`
UNION ALL SELECT 'node · account',       COUNT(*) FROM `${CDP_PROJECT}.${CDP_DS}.node_account`
UNION ALL SELECT 'edge · resolves_to',   COUNT(*) FROM `${CDP_PROJECT}.${CDP_DS}.edge_resolves_to`
UNION ALL SELECT 'edge · lives_at',      COUNT(*) FROM `${CDP_PROJECT}.${CDP_DS}.edge_lives_at`
UNION ALL SELECT 'edge · member_of',     COUNT(*) FROM `${CDP_PROJECT}.${CDP_DS}.edge_member_of`
UNION ALL SELECT 'edge · has_email',     COUNT(*) FROM `${CDP_PROJECT}.${CDP_DS}.edge_has_email`
UNION ALL SELECT 'edge · has_phone',     COUNT(*) FROM `${CDP_PROJECT}.${CDP_DS}.edge_has_phone`
UNION ALL SELECT 'edge · holds_account', COUNT(*) FROM `${CDP_PROJECT}.${CDP_DS}.edge_holds_account`
UNION ALL SELECT 'edge · suspected_link',COUNT(*) FROM `${CDP_PROJECT}.${CDP_DS}.edge_suspected_link`
UNION ALL SELECT 'edge · related_to',    COUNT(*) FROM `${CDP_PROJECT}.${CDP_DS}.edge_related_to`;


-- ---------------------------------------------------------------------
-- 70j · Cluster size distribution
--
-- The distribution is more informative than the count. A long tail of
-- enormous clusters is the signature of runaway transitive closure, and
-- it is visible here before anyone looks at a single profile.
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW `${CDP_PROJECT}.${CDP_DS}.v_cluster_sizes` AS
SELECT
  source_record_count AS cluster_size,
  COUNT(*)            AS people,
  ROUND(100 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_of_people
FROM `${CDP_PROJECT}.${CDP_DS}.node_person`
GROUP BY cluster_size
ORDER BY cluster_size;
