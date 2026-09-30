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
  SELECT
    c.comp,
    c.node AS record_id,
    p.dob,
    p.name_norm,
    p.forename_norm,
    p.surname_norm,
    p.email_norm,
    p.phone_e164,
    p.account_number
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
  -- more than one person. Likewise, two full-forename records with
  -- incompatible forenames, distinct emails, and distinct phones bridged
  -- through an initial-only loyalty stub indicate a recycled-phone collision.
  COUNT(DISTINCT dob) > 1                                     AS dob_contradiction
FROM members
GROUP BY comp
HAVING COUNT(DISTINCT dob) > 1
    OR (COUNT(DISTINCT CASE WHEN LENGTH(forename_norm) > 1 THEN forename_norm END) > 1
        AND COUNT(DISTINCT email_norm) > 1
        AND COUNT(DISTINCT phone_e164) > 1
        AND EDIT_DISTANCE(
              MIN(CASE WHEN LENGTH(forename_norm) > 1 THEN forename_norm END),
              MAX(CASE WHEN LENGTH(forename_norm) > 1 THEN forename_norm END),
              max_distance => 5
            ) > 2);


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
    t.street_match, t.street_conflict, t.initial_only,
    t.unshared_phone_both, t.unshared_email_both, t.unshared_acct_both,
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
-- In SIBLING_TRAP and recycled-phone collisions, when a loyalty stub already
-- has a same-phone partner with no street conflict, an unshared-phone street
-- link on the other side is the weak bridge and is dropped.
same_street_phone_nodes AS (
  SELECT record_id_a AS node FROM links WHERE phone_match AND NOT street_conflict
  UNION DISTINCT
  SELECT record_id_b AS node FROM links WHERE phone_match AND NOT street_conflict
),
classified AS (
  SELECT
    l.*,
    (l.record_id_a IN (SELECT node FROM suspect_nodes)
     OR l.record_id_b IN (SELECT node FROM suspect_nodes))        AS in_suspect_component,
    (NOT l.dob_conflict AND (
       (l.a_dob IS NOT NULL AND l.b_dob IS NOT NULL
        AND (l.acct_match OR l.email_match OR l.phone_match OR l.dob_match
             OR l.combined_score >= 0.95))
       OR (l.acct_match AND NOT l.street_conflict)
       OR (l.street_match AND NOT l.unshared_email_both AND NOT l.unshared_acct_both
           AND (NOT l.unshared_phone_both
                OR (l.record_id_a NOT IN (SELECT node FROM same_street_phone_nodes)
                    AND l.record_id_b NOT IN (SELECT node FROM same_street_phone_nodes))))
    ))                                                            AS strong,
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
),
default_minted AS (
  SELECT
    m.comp,
    m.record_id,
    b.inherited_person_id,
    CONCAT('PER-', FORMAT('%016x', FARM_FINGERPRINT(m.comp) & 0x7fffffffffffffff)) AS candidate_mint_id
  FROM comp_members AS m
  LEFT JOIN best AS b USING (comp)
)
SELECT
  d.comp,
  d.record_id,
  COALESCE(
    d.inherited_person_id,
    -- If a split component's anchor hash was already inherited by the other
    -- half of the split, salt the newly minted ID so two distinct components
    -- never collide on person_id.
    IF(taken.inherited_person_id IS NOT NULL,
       CONCAT('PER-', FORMAT('%016x', FARM_FINGERPRINT(CONCAT(d.comp, '|split')) & 0x7fffffffffffffff)),
       d.candidate_mint_id)
  ) AS person_id,
  d.inherited_person_id IS NULL AS newly_minted
FROM default_minted AS d
LEFT JOIN (SELECT DISTINCT inherited_person_id FROM best) AS taken
  ON taken.inherited_person_id = d.candidate_mint_id;

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
SELECT
  LEAST(pa.person_id, pb.person_id)    AS person_id_a,
  GREATEST(pa.person_id, pb.person_id) AS person_id_b,
  MAX(d.confidence)                    AS confidence,
  ANY_VALUE(d.rationale)               AS rationale,
  ANY_VALUE(d.contradiction)           AS contradiction,
  ANY_VALUE(d.decided_by)              AS decided_by,
  ANY_VALUE(d.retrieved_by)            AS retrieved_by
FROM `${CDP_PROJECT}.${CDP_DS}.match_decisions` AS d
JOIN `${CDP_PROJECT}.${CDP_DS}.person_assignment` AS pa ON pa.record_id = d.record_id_a
JOIN `${CDP_PROJECT}.${CDP_DS}.person_assignment` AS pb ON pb.record_id = d.record_id_b
WHERE d.decision = 'STEWARD'
  AND pa.person_id != pb.person_id
GROUP BY 1, 2;

-- 8 · Person —RELATED_TO→ Person
--
-- Asserted relationships, taken only from what somebody actually said.
-- The call transcript case — "I'm ringing about my wife's account" —
-- produces a relationship edge, which is the correct outcome. The wrong
-- outcome, and the easy one, is a merge.
CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.edge_related_to`
AS
SELECT
  caller.person_id                                         AS person_id,
  holder.person_id                                         AS related_person_id,
  ANY_VALUE(IFNULL(c.relationship_to_account, 'UNSPECIFIED')) AS relationship,
  'CALL_TRANSCRIPT'                                        AS asserted_by,
  ANY_VALUE(c.record_id)                                   AS evidence_record_id
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
  AND caller.person_id != ha.person_id
GROUP BY 1, 2;


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
UNION ALL SELECT 'node · identifier',    COUNT(*) FROM `${CDP_PROJECT}.${CDP_DS}.identifier`
UNION ALL SELECT 'edge · resolves_to',   COUNT(*) FROM `${CDP_PROJECT}.${CDP_DS}.edge_resolves_to`
UNION ALL SELECT 'edge · lives_at',      COUNT(*) FROM `${CDP_PROJECT}.${CDP_DS}.edge_lives_at`
UNION ALL SELECT 'edge · member_of',     COUNT(*) FROM `${CDP_PROJECT}.${CDP_DS}.edge_member_of`
UNION ALL SELECT 'edge · has_email',     COUNT(*) FROM `${CDP_PROJECT}.${CDP_DS}.edge_has_email`
UNION ALL SELECT 'edge · has_phone',     COUNT(*) FROM `${CDP_PROJECT}.${CDP_DS}.edge_has_phone`
UNION ALL SELECT 'edge · holds_account', COUNT(*) FROM `${CDP_PROJECT}.${CDP_DS}.edge_holds_account`
UNION ALL SELECT 'edge · suspected_link',COUNT(*) FROM `${CDP_PROJECT}.${CDP_DS}.edge_suspected_link`
UNION ALL SELECT 'edge · related_to',    COUNT(*) FROM `${CDP_PROJECT}.${CDP_DS}.edge_related_to`
UNION ALL SELECT 'edge · has_identifier',COUNT(*) FROM `${CDP_PROJECT}.${CDP_DS}.has_identifier`;


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


-- ---------------------------------------------------------------------
-- 70k · Comparative resolution runs
--
-- Runs three resolution algorithms over the exact same source records and
-- bipartite identifier graph so their cluster distributions and pairwise
-- accuracy can be compared side-by-side:
--
--   1. baseline_cc    · Naive Connected Components over all shared
--                       identifiers (including promiscuous call-centre and
--                       kiosk hubs). Demonstrates the "hairball" collapse.
--   2. weighted_cc    · IDF-weighted bipartite graph projection (weight >= 7.0,
--                       promiscuous hubs weighted 0). Dissolves the hub
--                       hairball in pure SQL, but still merges households
--                       and recycled phones and misses semantic matches.
--   3. composable_cdp · Full pipeline: Bipartite Rarity + 2-Hop
--                       Neighbourhood + Hybrid Search (AI.SEARCH +
--                       VECTOR_SEARCH + RRF) + Gemini Adjudicator +
--                       Pass-2 Contradiction Pruning.
-- ---------------------------------------------------------------------

-- 1 · Baseline Connected Components (star-encoded per identifier_id so
--     hub components converge in O(N) edges without materialising cliques)
CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.edges_baseline_cc`
AS
WITH id_anchors AS (
  SELECT
    record_id,
    MIN(record_id) OVER (PARTITION BY identifier_id) AS anchor_record_id
  FROM `${CDP_PROJECT}.${CDP_DS}.has_identifier`
)
SELECT DISTINCT record_id AS src, anchor_record_id AS dst
FROM id_anchors
WHERE record_id != anchor_record_id
UNION DISTINCT
SELECT DISTINCT anchor_record_id AS src, record_id AS dst
FROM id_anchors
WHERE record_id != anchor_record_id;

CALL `${CDP_PROJECT}.${CDP_DS}.sp_connected_components`(
  '${CDP_PROJECT}.${CDP_DS}.graph_nodes',
  '${CDP_PROJECT}.${CDP_DS}.edges_baseline_cc',
  '${CDP_PROJECT}.${CDP_DS}.cc_baseline',
  20
);

-- 2 · IDF-Weighted Projection Connected Components (weight >= 7.0)
CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.edges_weighted_cc`
AS
SELECT record_id_a AS src, record_id_b AS dst
FROM `${CDP_PROJECT}.${CDP_DS}.profile_projection`
WHERE weight >= 7.0
UNION ALL
SELECT record_id_b AS src, record_id_a AS dst
FROM `${CDP_PROJECT}.${CDP_DS}.profile_projection`
WHERE weight >= 7.0;

CALL `${CDP_PROJECT}.${CDP_DS}.sp_connected_components`(
  '${CDP_PROJECT}.${CDP_DS}.graph_nodes',
  '${CDP_PROJECT}.${CDP_DS}.edges_weighted_cc',
  '${CDP_PROJECT}.${CDP_DS}.cc_weighted',
  20
);

-- 3 · Unified multi-method cluster assignments (wesid_assignments)
CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.wesid_assignments`
CLUSTER BY method, record_id
AS
WITH raw_methods AS (
  SELECT
    'baseline_cc'    AS method,
    'run_baseline'   AS run_id,
    node             AS record_id,
    CONCAT('baseline_cc:', comp) AS wesid
  FROM `${CDP_PROJECT}.${CDP_DS}.cc_baseline`

  UNION ALL

  SELECT
    'weighted_cc'    AS method,
    'run_weighted'   AS run_id,
    node             AS record_id,
    CONCAT('weighted_cc:', comp) AS wesid
  FROM `${CDP_PROJECT}.${CDP_DS}.cc_weighted`

  UNION ALL

  SELECT
    'composable_cdp' AS method,
    'run_composable' AS run_id,
    record_id,
    CONCAT('composable_cdp:', person_id) AS wesid
  FROM `${CDP_PROJECT}.${CDP_DS}.person_assignment`
)
SELECT
  record_id,
  record_id AS profile_id,
  wesid,
  method,
  run_id,
  COUNT(*) OVER (PARTITION BY method, wesid) AS component_size,
  TRUE                                       AS is_latest,
  CURRENT_TIMESTAMP()                        AS assigned_at
FROM raw_methods;

-- 4 · Cluster summary per method (wesid_cluster)
CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.wesid_cluster`
CLUSTER BY method, wesid
AS
SELECT
  a.wesid,
  a.run_id,
  a.method,
  COUNT(DISTINCT a.record_id)                                      AS component_size,
  COUNT(DISTINCT a.record_id)                                      AS n_profiles,
  COUNT(DISTINCT h.identifier_id)                                  AS n_identifiers,
  COUNT(DISTINCT IF(i.is_promiscuous, h.identifier_id, NULL))      AS n_hub_identifiers,
  COUNT(DISTINCT a.record_id) >= 20                                AS is_hairball,
  TRUE                                                             AS is_latest,
  CURRENT_TIMESTAMP()                                              AS created_at
FROM `${CDP_PROJECT}.${CDP_DS}.wesid_assignments` AS a
LEFT JOIN `${CDP_PROJECT}.${CDP_DS}.has_identifier` AS h USING (record_id)
LEFT JOIN `${CDP_PROJECT}.${CDP_DS}.identifier`     AS i USING (identifier_id)
GROUP BY a.wesid, a.run_id, a.method;

-- 5 · Resolution run metadata (resolution_runs)
CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.resolution_runs`
AS
SELECT
  run_id,
  method,
  CASE method
    WHEN 'baseline_cc'    THEN 0.0
    WHEN 'weighted_cc'    THEN 7.0
    WHEN 'composable_cdp' THEN CAST(${CDP_TAU_HI} AS FLOAT64)
  END                                               AS threshold,
  SUM(n_profiles)                                   AS n_profiles,
  COUNT(*)                                          AS n_components,
  MAX(n_profiles)                                   AS largest_component,
  COUNTIF(is_hairball)                              AS n_hairballs,
  SUM(IF(is_hairball, n_profiles, 0))               AS profiles_in_hairballs,
  TRUE                                              AS is_latest,
  CURRENT_TIMESTAMP()                               AS created_at
FROM `${CDP_PROJECT}.${CDP_DS}.wesid_cluster`
GROUP BY run_id, method;


-- ---------------------------------------------------------------------
-- 70l · Native BigQuery Property Graph (cdp_identity_graph)
--
-- Declares one ISO GQL Property Graph across both the bipartite
-- resolution machinery (SourceRecord, Identifier, WesID, ComparedWith)
-- and the mastered customer entity graph (Person, Household, Address,
-- Email, Phone, LoyaltyAccount).
--
-- Schema OPTIONS (description, synonyms) provide the semantic metadata
-- read by BigQuery Studio's %%bigquery --graph visualiser and
-- Conversational Analytics Data Agents.
-- ---------------------------------------------------------------------

CREATE OR REPLACE PROPERTY GRAPH `${CDP_PROJECT}.${CDP_DS}.cdp_identity_graph`
  NODE TABLES (
    `${CDP_PROJECT}.${CDP_DS}.node_person` AS Person
      KEY (person_id)
      DEFAULT LABEL OPTIONS (
        description = 'A mastered golden customer identity resolved by the Composable CDP pipeline.',
        synonyms = ['golden profile', 'resolved person', 'customer', 'mastered identity']
      )
      PROPERTIES (
        person_id              OPTIONS (description = 'Durable mastered person identifier (PER-...)'),
        source_record_count    OPTIONS (description = 'Number of source records resolved into this person', synonyms = ['cluster size']),
        source_system_count    OPTIONS (description = 'Number of distinct source systems contributing to this person'),
        best_identity_strength OPTIONS (description = 'Highest identity verification strength across contributing records'),
        first_seen_at          OPTIONS (description = 'Earliest timestamp across contributing source records'),
        last_seen_at           OPTIONS (description = 'Most recent timestamp across contributing source records'),
        minted_this_run        OPTIONS (description = 'TRUE if this person_id was newly minted in the latest run')
      ),
    `${CDP_PROJECT}.${CDP_DS}.node_source_record` AS SourceRecord
      KEY (record_id)
      DEFAULT LABEL OPTIONS (
        description = 'A raw customer profile record from a brand or channel source system (CRM, LOYALTY, ECOMM, POS, CALL, SURVEY).',
        synonyms = ['profile', 'customer record', 'source profile']
      )
      PROPERTIES (
        record_id          OPTIONS (description = 'Unique source record key', synonyms = ['profile_id', 'customer id']),
        source_system      OPTIONS (description = 'Originating system (CRM, LOYALTY, ECOMM, POS, CALL, SURVEY)', synonyms = ['brand', 'channel']),
        source_trust       OPTIONS (description = 'Trust weight of the originating source system'),
        source_natural_key OPTIONS (description = 'Source-system native key'),
        source_ts          OPTIONS (description = 'Record timestamp in the source system'),
        raw_name           OPTIONS (description = 'Raw customer name as captured in the source system'),
        raw_postcode       OPTIONS (description = 'Raw postcode as captured in the source system'),
        identity_strength  OPTIONS (description = 'Identity verification level of the record'),
        evidence_note      OPTIONS (description = 'Free-text call or survey note attached to the record'),
        injection_attempt  OPTIONS (description = 'TRUE if the free-text field contained a prompt-injection attempt')
      ),
    `${CDP_PROJECT}.${CDP_DS}.identifier` AS Identifier
      KEY (identifier_id)
      DEFAULT LABEL OPTIONS (
        description = 'A normalised identifier node in the bipartite identity graph (email, phone, loyalty_account, device_id) with degree, IDF rarity weight, and promiscuous hub detection.',
        synonyms = ['identity key', 'contact point', 'bipartite identifier']
      )
      PROPERTIES (
        identifier_id   OPTIONS (description = 'Prefixed identifier value (EM:, PH:, AC:, DV:)'),
        identifier_type OPTIONS (description = 'Kind of identifier: email, phone, loyalty_account, device_id'),
        degree          OPTIONS (description = 'Number of distinct source records currently holding this identifier', synonyms = ['fan-out', 'promiscuity']),
        degree_all_time OPTIONS (description = 'Number of distinct source records that ever held this identifier'),
        n_anchor_links  OPTIONS (description = 'Number of records for which this identifier is a primary anchor'),
        idf_weight      OPTIONS (description = 'Inverse document frequency rarity weight ln(N / degree); high = rare = strong evidence', synonyms = ['rarity', 'IDF']),
        is_promiscuous  OPTIONS (description = 'TRUE if shared by more than 25 source records (call-centre phone, store kiosk email/device)', synonyms = ['hub', 'promiscuous hub']),
        sources         OPTIONS (description = 'Pipe-separated source systems that reported this identifier'),
        first_seen_ts   OPTIONS (description = 'First timestamp the identifier was observed'),
        last_seen_ts    OPTIONS (description = 'Most recent timestamp the identifier was observed')
      ),
    `${CDP_PROJECT}.${CDP_DS}.wesid_cluster` AS WesID
      KEY (wesid, run_id)
      DEFAULT LABEL OPTIONS (
        description = 'A resolved identity cluster produced by one of the compared resolution methods (baseline_cc, weighted_cc, composable_cdp).',
        synonyms = ['cluster', 'component', 'resolved cluster']
      )
      PROPERTIES (
        wesid             OPTIONS (description = 'Method-prefixed cluster identifier'),
        run_id            OPTIONS (description = 'Identifier of the resolution run'),
        method            OPTIONS (description = 'Resolution algorithm: baseline_cc, weighted_cc, or composable_cdp', synonyms = ['algorithm']),
        component_size    OPTIONS (description = 'Number of source records in the cluster'),
        n_profiles        OPTIONS (description = 'Number of source records in the cluster', synonyms = ['cluster size']),
        n_identifiers     OPTIONS (description = 'Number of distinct identifiers held by records in the cluster'),
        n_hub_identifiers OPTIONS (description = 'Number of promiscuous hub identifiers inside the cluster'),
        is_hairball       OPTIONS (description = 'TRUE if 20 or more source records were fused into a single component', synonyms = ['hairball', 'giant component']),
        is_latest         OPTIONS (description = 'TRUE for the latest run of the method'),
        created_at        OPTIONS (description = 'Timestamp when the cluster was computed')
      ),
    `${CDP_PROJECT}.${CDP_DS}.node_household` AS Household
      KEY (household_id)
      DEFAULT LABEL OPTIONS (
        description = 'An inferred residential household grouping resolved people who share a current verified street address.',
        synonyms = ['family unit', 'residence']
      )
      PROPERTIES (
        household_id  OPTIONS (description = 'Household identifier (HH-...)'),
        address_id    OPTIONS (description = 'Identifier of the shared residential address'),
        address_norm  OPTIONS (description = 'Normalised residential street address'),
        postcode_norm OPTIONS (description = 'Normalised postcode'),
        person_count  OPTIONS (description = 'Number of distinct resolved people currently living at this household')
      ),
    `${CDP_PROJECT}.${CDP_DS}.node_address` AS Address
      KEY (address_id)
      DEFAULT LABEL OPTIONS (
        description = 'A normalised street address and postcode.',
        synonyms = ['street address', 'location']
      )
      PROPERTIES (
        address_id    OPTIONS (description = 'SHA-256 address identifier'),
        address_norm  OPTIONS (description = 'Normalised street address'),
        postcode_norm OPTIONS (description = 'Normalised 4-digit Australian postcode'),
        postcode_out  OPTIONS (description = '3-digit postcode district prefix'),
        record_count  OPTIONS (description = 'Number of source records asserting this address')
      ),
    `${CDP_PROJECT}.${CDP_DS}.node_email` AS Email
      KEY (email_id)
      DEFAULT LABEL OPTIONS (
        description = 'A normalised email address.',
        synonyms = ['email address', 'inbox']
      )
      PROPERTIES (
        email_id     OPTIONS (description = 'Normalised email address key'),
        email_norm   OPTIONS (description = 'Normalised email address'),
        domain       OPTIONS (description = 'Email domain'),
        record_count OPTIONS (description = 'Number of source records asserting this email')
      ),
    `${CDP_PROJECT}.${CDP_DS}.node_phone` AS Phone
      KEY (phone_id)
      DEFAULT LABEL OPTIONS (
        description = 'An E.164 normalised Australian telephone number (+614... personal mobile or +612/3/7/8... household landline).',
        synonyms = ['phone number', 'mobile', 'landline']
      )
      PROPERTIES (
        phone_id     OPTIONS (description = 'E.164 phone identifier'),
        phone_e164   OPTIONS (description = 'E.164 formatted phone number'),
        is_mobile    OPTIONS (description = 'TRUE if Australian mobile (+614...), FALSE if geographic landline'),
        record_count OPTIONS (description = 'Number of source records asserting this phone number')
      ),
    `${CDP_PROJECT}.${CDP_DS}.node_account` AS LoyaltyAccount
      KEY (account_id)
      DEFAULT LABEL OPTIONS (
        description = 'A retail loyalty or membership account number.',
        synonyms = ['loyalty card', 'member account']
      )
      PROPERTIES (
        account_id     OPTIONS (description = 'Loyalty account identifier'),
        account_number OPTIONS (description = 'Loyalty account number'),
        record_count   OPTIONS (description = 'Number of source records asserting this loyalty account')
      )
  )
  EDGE TABLES (
    `${CDP_PROJECT}.${CDP_DS}.edge_resolves_to` AS ResolvesTo
      KEY (record_id, person_id)
      SOURCE KEY (record_id) REFERENCES SourceRecord (record_id)
      DESTINATION KEY (person_id) REFERENCES Person (person_id)
      LABEL RESOLVES_TO
      PROPERTIES (
        source_system OPTIONS (description = 'Originating source system of the record'),
        source_trust  OPTIONS (description = 'Trust weight of the source system')
      ),
    `${CDP_PROJECT}.${CDP_DS}.has_identifier` AS HasIdentifier
      KEY (record_id, identifier_id)
      SOURCE KEY (record_id) REFERENCES SourceRecord (record_id)
      DESTINATION KEY (identifier_id) REFERENCES Identifier (identifier_id)
      LABEL HAS_IDENTIFIER
      PROPERTIES (
        identifier_type OPTIONS (description = 'Type of identifier linked'),
        is_anchor       OPTIONS (description = 'TRUE if primary anchor in the source system'),
        sources         OPTIONS (description = 'Source system reporting the link'),
        first_seen_in   OPTIONS (description = 'Source system where link was first seen'),
        from_ts         OPTIONS (description = 'Timestamp when link was asserted')
      ),
    `${CDP_PROJECT}.${CDP_DS}.has_identifier_history` AS HadIdentifier
      KEY (row_id)
      SOURCE KEY (record_id) REFERENCES SourceRecord (record_id)
      DESTINATION KEY (identifier_id) REFERENCES Identifier (identifier_id)
      LABEL HAD_IDENTIFIER
      PROPERTIES (
        identifier_type OPTIONS (description = 'Type of identifier'),
        is_anchor       OPTIONS (description = 'TRUE if primary anchor'),
        from_ts         OPTIONS (description = 'Start of validity window'),
        to_ts           OPTIONS (description = 'End of validity window when superseded/recycled'),
        transit_to      OPTIONS (description = 'Record ID of the later customer who acquired the recycled phone/identifier'),
        is_current      OPTIONS (description = 'TRUE if currently active, FALSE if historical/superseded'),
        is_deleted      OPTIONS (description = 'TRUE if deleted'),
        sources         OPTIONS (description = 'Source system reporting the link')
      ),
    `${CDP_PROJECT}.${CDP_DS}.linked_identifier` AS LinkedIdentifier
      KEY (lhs_identifier_id, rhs_identifier_id)
      SOURCE KEY (lhs_identifier_id) REFERENCES Identifier (identifier_id)
      DESTINATION KEY (rhs_identifier_id) REFERENCES Identifier (identifier_id)
      LABEL LINKED_TO
      PROPERTIES (
        lhs_type           OPTIONS (description = 'Left-hand identifier type'),
        rhs_type           OPTIONS (description = 'Right-hand identifier type'),
        observed_on_record OPTIONS (description = 'Example source record where both identifiers co-occurred'),
        edge_source        OPTIONS (description = 'Source system where co-occurrence was observed'),
        from_ts            OPTIONS (description = 'Earliest co-occurrence timestamp')
      ),
    `${CDP_PROJECT}.${CDP_DS}.wesid_assignments` AS AssignedWesID
      KEY (record_id, wesid, run_id)
      SOURCE KEY (record_id) REFERENCES SourceRecord (record_id)
      DESTINATION KEY (wesid, run_id) REFERENCES WesID (wesid, run_id)
      LABEL ASSIGNED_WESID
      PROPERTIES (
        method         OPTIONS (description = 'Resolution algorithm (baseline_cc, weighted_cc, composable_cdp)'),
        run_id         OPTIONS (description = 'Resolution run identifier'),
        component_size OPTIONS (description = 'Size of the assigned cluster'),
        is_latest      OPTIONS (description = 'TRUE for latest run'),
        assigned_at    OPTIONS (description = 'Assignment timestamp')
      ),
    `${CDP_PROJECT}.${CDP_DS}.resolution_edges` AS ComparedWith
      KEY (record_id_a, record_id_b)
      SOURCE KEY (record_id_a) REFERENCES SourceRecord (record_id)
      DESTINATION KEY (record_id_b) REFERENCES SourceRecord (record_id)
      LABEL COMPARED_WITH
      PROPERTIES (
        decision                    OPTIONS (description = 'Final resolution decision: LINK, UNLINK, or STEWARD'),
        decided_by                  OPTIONS (description = 'Decider: RULE, LLM, or LLM_GUARD'),
        confidence                  OPTIONS (description = 'Confidence score in [0, 1]'),
        rationale                   OPTIONS (description = 'Plain-English explanation of the decision'),
        contradiction               OPTIONS (description = 'Explicit contradicting evidence cited'),
        retrieved_by                OPTIONS (description = 'Hybrid retrieval leg: LEXICAL_ONLY, SEMANTIC_ONLY, or BOTH'),
        combined_score              OPTIONS (description = 'Fused rule + semantic score'),
        rule_score                  OPTIONS (description = 'Deterministic + graph rarity score'),
        similarity                  OPTIONS (description = 'Cosine similarity of record embeddings'),
        suppressed_by_contradiction OPTIONS (description = 'TRUE if an accepted LINK was pruned in Pass 2 due to cluster DOB contradiction')
      ),
    `${CDP_PROJECT}.${CDP_DS}.edge_lives_at` AS LivesAt
      KEY (person_id, address_id)
      SOURCE KEY (person_id) REFERENCES Person (person_id)
      DESTINATION KEY (address_id) REFERENCES Address (address_id)
      LABEL LIVES_AT
      PROPERTIES (
        last_asserted_at  OPTIONS (description = 'Most recent timestamp this address was asserted for this person'),
        best_source_trust OPTIONS (description = 'Highest source trust asserting this address'),
        assertions        OPTIONS (description = 'Number of records asserting this address'),
        is_current        OPTIONS (description = 'TRUE for the person\'s current primary residential address')
      ),
    `${CDP_PROJECT}.${CDP_DS}.edge_member_of` AS MemberOf
      KEY (person_id, household_id)
      SOURCE KEY (person_id) REFERENCES Person (person_id)
      DESTINATION KEY (household_id) REFERENCES Household (household_id)
      LABEL MEMBER_OF
      NO PROPERTIES,
    `${CDP_PROJECT}.${CDP_DS}.edge_has_email` AS HasEmail
      KEY (person_id, email_id)
      SOURCE KEY (person_id) REFERENCES Person (person_id)
      DESTINATION KEY (email_id) REFERENCES Email (email_id)
      LABEL HAS_EMAIL
      PROPERTIES (
        best_source_trust OPTIONS (description = 'Highest source trust asserting this email'),
        last_asserted_at  OPTIONS (description = 'Most recent timestamp this email was asserted'),
        assertions        OPTIONS (description = 'Number of source records asserting this email')
      ),
    `${CDP_PROJECT}.${CDP_DS}.edge_has_phone` AS HasPhone
      KEY (person_id, phone_id)
      SOURCE KEY (person_id) REFERENCES Person (person_id)
      DESTINATION KEY (phone_id) REFERENCES Phone (phone_id)
      LABEL HAS_PHONE
      PROPERTIES (
        best_source_trust OPTIONS (description = 'Highest source trust asserting this phone'),
        last_asserted_at  OPTIONS (description = 'Most recent timestamp this phone was asserted'),
        assertions        OPTIONS (description = 'Number of source records asserting this phone')
      ),
    `${CDP_PROJECT}.${CDP_DS}.edge_holds_account` AS HoldsAccount
      KEY (person_id, account_id)
      SOURCE KEY (person_id) REFERENCES Person (person_id)
      DESTINATION KEY (account_id) REFERENCES LoyaltyAccount (account_id)
      LABEL HOLDS_ACCOUNT
      PROPERTIES (
        assertions OPTIONS (description = 'Number of source records asserting this loyalty account')
      ),
    `${CDP_PROJECT}.${CDP_DS}.edge_suspected_link` AS SuspectedLink
      KEY (person_id_a, person_id_b)
      SOURCE KEY (person_id_a) REFERENCES Person (person_id)
      DESTINATION KEY (person_id_b) REFERENCES Person (person_id)
      LABEL SUSPECTED_LINK
      PROPERTIES (
        confidence    OPTIONS (description = 'Adjudicator confidence score'),
        rationale     OPTIONS (description = 'Reason the pair was deferred to a human data steward'),
        contradiction OPTIONS (description = 'Ambiguity or conflict noted by the adjudicator'),
        decided_by    OPTIONS (description = 'Decider that routed the pair to the steward queue'),
        retrieved_by  OPTIONS (description = 'Retrieval leg that surfaced the pair')
      ),
    `${CDP_PROJECT}.${CDP_DS}.edge_related_to` AS RelatedTo
      KEY (person_id, related_person_id)
      SOURCE KEY (person_id) REFERENCES Person (person_id)
      DESTINATION KEY (related_person_id) REFERENCES Person (person_id)
      LABEL RELATED_TO
      PROPERTIES (
        relationship       OPTIONS (description = 'Inferred or stated relationship (e.g. SPOUSE, FAMILY) extracted from call transcript'),
        asserted_by        OPTIONS (description = 'Source of relationship assertion (CALL_TRANSCRIPT)'),
        evidence_record_id OPTIONS (description = 'Source record ID of the call transcript')
      )
  );

-- Clean up iterative connected-components scratch tables
DROP TABLE IF EXISTS `${CDP_PROJECT}.${CDP_DS}.cc_pass1_next`;
DROP TABLE IF EXISTS `${CDP_PROJECT}.${CDP_DS}.cc_final_next`;
DROP TABLE IF EXISTS `${CDP_PROJECT}.${CDP_DS}.cc_baseline_next`;
DROP TABLE IF EXISTS `${CDP_PROJECT}.${CDP_DS}.cc_weighted_next`;


