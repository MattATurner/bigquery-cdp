-- =====================================================================
-- 90 · Downstream
--
-- Everything to this point was cost. This is the return.
--
-- Five things that are either impossible or unreliable without a
-- mastered customer graph, and straightforward with one. None of them
-- requires data to leave BigQuery, and none of them requires a separate
-- CDP product.
--
--   90a  segmentation   · RFM + k-means, on people rather than records
--   90b  household      · the unit families actually buy as
--   90c  graph risk     · shared identifiers, which only a graph exposes
--   90d  agent grounding· a profile an LLM can read and answer from
--   90e  activation     · audiences that are consent-safe by construction
--
-- The recurring point: every one of these was previously computed per
-- source system, and therefore computed wrongly.
-- =====================================================================


-- ---------------------------------------------------------------------
-- 90a · Segmentation
--
-- RFM at person level. The comparison worth drawing on screen: the same
-- calculation over raw POS records treats one customer with three loyalty
-- cards as three lukewarm customers rather than one very good one. Every
-- decision downstream — budget, offer, priority — then follows from a
-- number that was never true.
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.person_rfm`
CLUSTER BY person_id
AS
WITH txns AS (
  SELECT
    a.person_id,
    t.txn_ts,
    t.amount_aud,
    t.category
  FROM `${CDP_PROJECT}.${CDP_DS}.ext_pos_transactions` AS t
  JOIN `${CDP_PROJECT}.${CDP_DS}.person_assignment` AS a ON a.record_id = t.record_id
),
bounds AS (
  SELECT MAX(txn_ts) AS as_of FROM txns
)
SELECT
  t.person_id,
  DATE_DIFF(DATE(b.as_of), DATE(MAX(t.txn_ts)), DAY)      AS recency_days,
  COUNT(*)                                                AS frequency,
  ROUND(SUM(t.amount_aud), 2)                             AS monetary_aud,
  ROUND(AVG(t.amount_aud), 2)                             AS avg_basket_aud,
  COUNT(DISTINCT t.category)                              AS category_breadth,
  ARRAY_AGG(DISTINCT t.category ORDER BY t.category)      AS categories,
  MIN(t.txn_ts)                                           AS first_purchase_at,
  MAX(t.txn_ts)                                           AS last_purchase_at
FROM txns AS t, bounds AS b
GROUP BY t.person_id, b.as_of;


-- Trained on the resolved population. Five clusters is a starting point,
-- not a finding — the right number comes from silhouette scores on real
-- data, and claiming otherwise in a demo would be dishonest.
CREATE OR REPLACE MODEL `${CDP_PROJECT}.${CDP_DS}.model_person_segments`
OPTIONS (
  model_type            = 'KMEANS',
  num_clusters          = 5,
  standardize_features  = TRUE,
  kmeans_init_method    = 'KMEANS++'
) AS
SELECT
  recency_days,
  frequency,
  monetary_aud,
  category_breadth
FROM `${CDP_PROJECT}.${CDP_DS}.person_rfm`;

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.person_segments`
CLUSTER BY person_id
AS
-- ML.PREDICT passes non-feature columns straight through, so person_id
-- comes back attached to its own prediction. Joining the result back to
-- the input on floating-point equality would work here and break the
-- first time a feature is rounded differently.
SELECT
  person_id,
  CENTROID_ID AS segment_id,
  recency_days,
  frequency,
  monetary_aud,
  category_breadth
FROM ML.PREDICT(
  MODEL `${CDP_PROJECT}.${CDP_DS}.model_person_segments`,
  (
    SELECT person_id, recency_days, frequency, monetary_aud, category_breadth
    FROM `${CDP_PROJECT}.${CDP_DS}.person_rfm`
  )
);


-- Segments are numbers until somebody names them. AI.GENERATE reads the
-- centroid statistics and produces a label a marketer can use, which is
-- a small thing that removes a genuinely annoying manual step.
CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.segment_labels`
AS
WITH profile AS (
  SELECT
    segment_id,
    COUNT(*)                        AS people,
    ROUND(AVG(recency_days), 1)     AS avg_recency_days,
    ROUND(AVG(frequency), 1)        AS avg_frequency,
    ROUND(AVG(monetary_aud), 2)     AS avg_spend_aud,
    ROUND(AVG(category_breadth), 1) AS avg_categories
  FROM `${CDP_PROJECT}.${CDP_DS}.person_segments`
  GROUP BY segment_id
)
SELECT
  p.*,
  AI.GENERATE(
    prompt => (
      'Name and describe a retail customer segment from these averages. '
   || 'Be plain and commercial; avoid jargon and avoid inventing facts not '
   || 'present in the numbers. Statistics: ',
      TO_JSON_STRING(p)
    ),
    connection_id => '${CDP_CONNECTION_PATH}',
    endpoint      => '${CDP_EXTRACTION_MODEL}',
    output_schema => 'segment_name STRING, description STRING, suggested_action STRING'
  ) AS g
FROM profile AS p;


-- ---------------------------------------------------------------------
-- 90b · Household
--
-- Families buy as a unit and are marketed to as individuals, which is how
-- four people at one address receive four copies of the same catalogue.
--
-- The household is derived from resolved people sharing a current
-- address. Note what it is NOT: it is not a merge. The four people remain
-- four people with four sets of preferences.
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.household_profile`
CLUSTER BY household_id
AS
SELECT
  h.household_id,
  h.address_norm,
  h.postcode_norm,
  COUNT(DISTINCT m.person_id)                          AS people,
  ROUND(SUM(IFNULL(r.monetary_aud, 0)), 2)             AS household_spend_aud,
  SUM(IFNULL(r.frequency, 0))                          AS household_transactions,
  MIN(r.recency_days)                                  AS most_recent_purchase_days,
  ARRAY_AGG(DISTINCT g.surname IGNORE NULLS
            ORDER BY g.surname)                        AS surnames,
  -- More than one surname at an address is normal and is not evidence of
  -- anything. It is recorded because it changes how a household offer
  -- should be worded, not whether one should be sent.
  COUNT(DISTINCT g.surname) > 1                        AS multi_surname,
  COUNTIF(c.effective_status = 'GRANTED') > 0          AS at_least_one_contactable
FROM `${CDP_PROJECT}.${CDP_DS}.node_household` AS h
JOIN `${CDP_PROJECT}.${CDP_DS}.edge_member_of` AS m USING (household_id)
LEFT JOIN `${CDP_PROJECT}.${CDP_DS}.golden_person` AS g ON g.person_id = m.person_id
LEFT JOIN `${CDP_PROJECT}.${CDP_DS}.person_rfm`   AS r ON r.person_id = m.person_id
LEFT JOIN `${CDP_PROJECT}.${CDP_DS}.person_consent` AS c
  ON c.person_id = m.person_id AND c.channel = 'POST' AND c.purpose = 'MARKETING'
GROUP BY h.household_id, h.address_norm, h.postcode_norm;


-- The catalogue-duplication number. Unglamorous, immediately credible,
-- and usually larger than anyone expects.
CREATE OR REPLACE VIEW `${CDP_PROJECT}.${CDP_DS}.v_household_waste` AS
SELECT
  COUNT(*)                                                   AS households,
  SUM(people)                                                AS people,
  SUM(GREATEST(people - 1, 0))                               AS duplicate_mailings_avoided,
  ROUND(100 * SAFE_DIVIDE(SUM(GREATEST(people - 1, 0)), SUM(people)), 2)
                                                             AS pct_of_mailings_avoidable,
  COUNTIF(people > 1)                                        AS multi_person_households,
  COUNTIF(multi_surname)                                     AS multi_surname_households
FROM `${CDP_PROJECT}.${CDP_DS}.household_profile`
WHERE at_least_one_contactable;


-- ---------------------------------------------------------------------
-- 90c · Shared identifiers
--
-- A graph question that a flat customer table cannot answer at all:
-- which identifiers are shared by people we have decided are different?
--
-- Most sharing is innocent — couples share a landline, families share an
-- email. A phone number attached to fifteen unrelated people, across
-- multiple postcode districts, is not innocent. Either resolution is
-- wrong, or something is.
--
-- Note the framing: this surfaces things to look at, and asserts nothing.
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW `${CDP_PROJECT}.${CDP_DS}.v_shared_identifiers` AS
WITH shared_phone AS (
  SELECT
    'PHONE'                              AS identifier_type,
    e.phone_id                           AS identifier,
    COUNT(DISTINCT e.person_id)          AS people,
    ARRAY_AGG(DISTINCT e.person_id ORDER BY e.person_id LIMIT 20) AS person_ids,
    ANY_VALUE(n.is_mobile)               AS is_personal_device
  FROM `${CDP_PROJECT}.${CDP_DS}.edge_has_phone` AS e
  JOIN `${CDP_PROJECT}.${CDP_DS}.node_phone` AS n ON n.phone_id = e.phone_id
  GROUP BY e.phone_id
  HAVING COUNT(DISTINCT e.person_id) > 1
),
shared_email AS (
  SELECT
    'EMAIL',
    e.email_id,
    COUNT(DISTINCT e.person_id),
    ARRAY_AGG(DISTINCT e.person_id ORDER BY e.person_id LIMIT 20),
    FALSE
  FROM `${CDP_PROJECT}.${CDP_DS}.edge_has_email` AS e
  GROUP BY e.email_id
  HAVING COUNT(DISTINCT e.person_id) > 1
),
shared_account AS (
  SELECT
    'LOYALTY_ACCOUNT',
    e.account_id,
    COUNT(DISTINCT e.person_id),
    ARRAY_AGG(DISTINCT e.person_id ORDER BY e.person_id LIMIT 20),
    FALSE
  FROM `${CDP_PROJECT}.${CDP_DS}.edge_holds_account` AS e
  GROUP BY e.account_id
  HAVING COUNT(DISTINCT e.person_id) > 1
)
SELECT *,
  CASE
    WHEN identifier_type = 'PHONE' AND is_personal_device AND people >= 5
      THEN 'REVIEW · a personal mobile shared by five or more people is unusual'
    WHEN people >= 10
      THEN 'REVIEW · sharing at this scale is rarely a household'
    WHEN people BETWEEN 2 AND 4
      THEN 'EXPECTED · consistent with a household or a couple'
    ELSE 'MONITOR'
  END AS assessment
FROM (
  SELECT * FROM shared_phone
  UNION ALL SELECT * FROM shared_email
  UNION ALL SELECT * FROM shared_account
)
ORDER BY people DESC;


-- ---------------------------------------------------------------------
-- 90d · Grounding for agents
--
-- An agent cannot reason about a customer scattered across eight systems.
-- It can reason about one profile with stated provenance and explicit
-- gaps.
--
-- The profile deliberately carries what is NOT known —
-- fields_with_conflicting_sources — because an agent told that a date of
-- birth is contested will ask, where an agent given a single clean value
-- will assert.
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.person_context`
CLUSTER BY person_id
AS
WITH interactions AS (
  SELECT
    a.person_id,
    CONCAT('[', p.source_system, ' ',
           IFNULL(FORMAT_TIMESTAMP('%Y-%m-%d', p.source_ts), 'undated'), '] ',
           IFNULL(p.evidence_note, p.raw_name)) AS line
  FROM `${CDP_PROJECT}.${CDP_DS}.party_records` AS p
  JOIN `${CDP_PROJECT}.${CDP_DS}.person_assignment` AS a ON a.record_id = p.record_id
  WHERE p.evidence_note IS NOT NULL
),

-- These three were ARRAY(SELECT ... WHERE x.person_id = g.person_id) against
-- other tables. BigQuery cannot de-correlate a subquery that references
-- another table once it carries ORDER BY or LIMIT:
--   "Correlated subqueries that reference other tables are not supported
--    unless they can be de-correlated, such as by transforming them into an
--    efficient JOIN."
-- So each is pre-aggregated per person and LEFT JOINed below. A join miss
-- yields a NULL array, which BigQuery stores as an empty array -- identical
-- to what the empty subquery produced.
consent_agg AS (
  SELECT
    person_id,
    ARRAY_AGG(STRUCT(channel, purpose, effective_status)
              ORDER BY channel, purpose) AS permissions
  FROM `${CDP_PROJECT}.${CDP_DS}.person_consent`
  GROUP BY person_id
),

interaction_agg AS (
  SELECT
    person_id,
    ARRAY_AGG(line LIMIT 10) AS notable_interactions
  FROM interactions
  GROUP BY person_id
),

contested_agg AS (
  SELECT
    person_id,
    ARRAY_AGG(field ORDER BY field) AS fields_with_conflicting_sources
  FROM `${CDP_PROJECT}.${CDP_DS}.field_survivorship`
  WHERE was_contested
  GROUP BY person_id
)

SELECT
  g.person_id,
  g.full_name,
  g.email,
  g.phone,
  g.postcode,
  g.contested_fields,
  n.source_systems,
  n.source_record_count,
  r.recency_days,
  r.frequency,
  r.monetary_aud,
  ca.permissions,
  ia.notable_interactions,
  -- Explicit uncertainty. This is the field that stops an agent asserting
  -- something it should have asked about.
  co.fields_with_conflicting_sources
FROM `${CDP_PROJECT}.${CDP_DS}.golden_person` AS g
JOIN `${CDP_PROJECT}.${CDP_DS}.node_person`   AS n USING (person_id)
LEFT JOIN `${CDP_PROJECT}.${CDP_DS}.person_rfm` AS r USING (person_id)
LEFT JOIN consent_agg     AS ca ON ca.person_id = g.person_id
LEFT JOIN interaction_agg AS ia ON ia.person_id = g.person_id
LEFT JOIN contested_agg   AS co ON co.person_id = g.person_id;


-- Ask a question about a customer. The prompt forbids invention and
-- requires the answer to cite which part of the profile it came from,
-- which is the difference between grounding and guessing.
CREATE OR REPLACE TABLE FUNCTION `${CDP_PROJECT}.${CDP_DS}.tf_ask_about_person`(
  p_person_id STRING, question STRING
)
AS (
  SELECT
    c.person_id,
    question AS asked,
    AI.GENERATE(
      prompt => (
        '''Answer a question about a customer using ONLY the profile below.

If the profile does not contain the answer, say so plainly and say what would need
to be checked. Never infer, estimate or fill a gap.

Cite which part of the profile your answer came from.

If fields_with_conflicting_sources lists a field you rely on, say that the value is
contested and give the caveat.

Never state or imply permission to contact on a channel unless permissions shows
GRANTED for that channel.

QUESTION: ''',
        question,
        '''

PROFILE:
''',
        TO_JSON_STRING(c)
      ),
      connection_id => '${CDP_CONNECTION_PATH}',
      endpoint      => '${CDP_EXTRACTION_MODEL}',
      output_schema => 'answer STRING, grounded_in STRING, confident BOOL'
    ) AS response
  FROM `${CDP_PROJECT}.${CDP_DS}.person_context` AS c
  WHERE c.person_id = p_person_id
);


-- ---------------------------------------------------------------------
-- 90e · Activation
--
-- The final audience. Consent-safe by construction: it reads
-- v_contactable, which only ever contains people whose every contributing
-- record agreed.
--
-- A marketer cannot accidentally widen this audience, because the
-- permission logic is not theirs to reinterpret.
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW `${CDP_PROJECT}.${CDP_DS}.v_audience_lapsed_high_value` AS
SELECT
  c.person_id,
  c.full_name,
  c.email,
  c.postcode,
  r.monetary_aud,
  r.recency_days,
  r.frequency,
  s.segment_id,
  -- Nested, not flat: segment_labels stores the whole AI.GENERATE result in
  -- column g, matching the convention in stages 20 and 60. The notebook
  -- reads g.segment_name too, so the struct stays and the view reaches in.
  l.g.segment_name,
  l.g.suggested_action
FROM `${CDP_PROJECT}.${CDP_DS}.v_contactable` AS c
JOIN `${CDP_PROJECT}.${CDP_DS}.person_rfm` AS r USING (person_id)
LEFT JOIN `${CDP_PROJECT}.${CDP_DS}.person_segments` AS s USING (person_id)
LEFT JOIN `${CDP_PROJECT}.${CDP_DS}.segment_labels`  AS l
  ON l.segment_id = s.segment_id
WHERE c.channel = 'EMAIL'
  AND c.purpose = 'MARKETING'
  AND r.recency_days > 180
  AND r.monetary_aud > 500;


-- The before/after that justifies the whole programme. The same audience
-- definition, computed on unresolved source records and on resolved
-- people, produces different customers and a different spend figure.
CREATE OR REPLACE VIEW `${CDP_PROJECT}.${CDP_DS}.v_activation_before_after` AS
WITH unresolved AS (
  -- What you get treating every loyalty card as a customer.
  SELECT
    COUNT(DISTINCT t.loyalty_account_number)          AS customers,
    ROUND(SUM(t.amount_aud), 2)                       AS total_spend,
    ROUND(AVG(t.amount_aud), 2)                       AS avg_txn
  FROM `${CDP_PROJECT}.${CDP_DS}.ext_pos_transactions` AS t
  WHERE t.loyalty_account_number IS NOT NULL
),
resolved AS (
  SELECT
    COUNT(*)                                          AS customers,
    ROUND(SUM(monetary_aud), 2)                       AS total_spend,
    ROUND(AVG(avg_basket_aud), 2)                     AS avg_txn
  FROM `${CDP_PROJECT}.${CDP_DS}.person_rfm`
)
SELECT 'unresolved · one loyalty card = one customer' AS basis,
       customers, total_spend,
       ROUND(SAFE_DIVIDE(total_spend, customers), 2)  AS spend_per_customer
FROM unresolved
UNION ALL
SELECT 'resolved · one person = one customer',
       customers, total_spend,
       ROUND(SAFE_DIVIDE(total_spend, customers), 2)
FROM resolved;


-- ---------------------------------------------------------------------
-- 90f · Semantic Property Graph with DDL MEASUREs (cdp_semantic_graph)
--
-- Exposes the identity graph as a star-shaped semantic layer with DDL
-- MEASURE() definitions so GRAPH_EXPAND + AGG() aggregates metrics
-- exactly once per entity key (preventing fan-out double counting across
-- profile-identifier links).
--
-- Shape:
--   Membership (root, one row per current record-identifier link)
--     |-- LINKS_PROFILE ----> Profile    (with baseline_cc, weighted_cc,
--     |                                   and composable_cdp clusters)
--     '-- LINKS_IDENTIFIER -> Identifier (with degree, IDF, promiscuity)
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.sem_membership`
AS
SELECT
  record_id,
  record_id                 AS profile_id,
  identifier_id,
  identifier_type,
  IF(is_anchor, 1, 0)       AS anchor_flag,
  sources,
  first_seen_in,
  from_ts                   AS available_from_ts
FROM `${CDP_PROJECT}.${CDP_DS}.has_identifier`;

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.sem_identifier`
AS
SELECT
  identifier_id,
  identifier_type,
  degree,
  degree_all_time,
  idf_weight,
  is_promiscuous,
  IF(is_promiscuous, 1, 0)  AS promiscuous_flag,
  sources,
  first_seen_ts,
  last_seen_ts
FROM `${CDP_PROJECT}.${CDP_DS}.identifier`;

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.sem_profile`
AS
WITH id_summary AS (
  SELECT
    h.record_id,
    COUNT(DISTINCT h.identifier_id)                            AS n_identifiers,
    COUNTIF(h.is_anchor)                                       AS n_anchor,
    LOGICAL_OR(h.identifier_type = 'email')                    AS has_email,
    LOGICAL_OR(h.identifier_type = 'phone')                    AS has_phone,
    LOGICAL_OR(h.identifier_type = 'loyalty_account')          AS has_loyalty_id,
    MAX(IF(i.is_promiscuous, 1, 0))                            AS touches_hub_flag
  FROM `${CDP_PROJECT}.${CDP_DS}.has_identifier` AS h
  JOIN `${CDP_PROJECT}.${CDP_DS}.identifier`     AS i USING (identifier_id)
  GROUP BY h.record_id
),
latest AS (
  SELECT
    a.record_id,
    a.method,
    a.wesid,
    c.n_profiles AS cluster_size,
    c.is_hairball
  FROM `${CDP_PROJECT}.${CDP_DS}.wesid_assignments` AS a
  JOIN `${CDP_PROJECT}.${CDP_DS}.wesid_cluster`     AS c
    ON c.wesid = a.wesid AND c.run_id = a.run_id
  WHERE a.is_latest AND c.is_latest
)
SELECT
  p.record_id,
  p.record_id                                                  AS profile_id,
  p.source_system                                              AS sources,
  1                                                            AS n_sources,
  IFNULL(s.n_identifiers, 0)                                   AS n_identifiers,
  IFNULL(s.n_anchor, 0)                                        AS n_anchor,
  IFNULL(s.has_email, FALSE)                                   AS has_email,
  IFNULL(s.has_phone, FALSE)                                   AS has_phone,
  IFNULL(s.has_loyalty_id, FALSE)                              AS has_loyalty_id,
  p.source_system                                              AS first_seen_in,
  p.source_ts                                                  AS first_seen_ts,
  IFNULL(s.touches_hub_flag, 0)                                AS touches_hub_flag,
  b.wesid                                                      AS baseline_wesid,
  b.cluster_size                                               AS baseline_cluster_size,
  IF(b.is_hairball, 1, 0)                                      AS baseline_hairball_flag,
  w.wesid                                                      AS weighted_wesid,
  w.cluster_size                                               AS weighted_cluster_size,
  IF(w.is_hairball, 1, 0)                                      AS weighted_hairball_flag,
  c.wesid                                                      AS composable_wesid,
  c.cluster_size                                               AS composable_cluster_size,
  IF(c.is_hairball, 1, 0)                                      AS composable_hairball_flag,
  IF(b.cluster_size != c.cluster_size, 1, 0)                   AS baseline_composable_disagree_flag
FROM `${CDP_PROJECT}.${CDP_DS}.party_records` AS p
LEFT JOIN id_summary AS s USING (record_id)
LEFT JOIN latest     AS b ON b.record_id = p.record_id AND b.method = 'baseline_cc'
LEFT JOIN latest     AS w ON w.record_id = p.record_id AND w.method = 'weighted_cc'
LEFT JOIN latest     AS c ON c.record_id = p.record_id AND c.method = 'composable_cdp';

CREATE OR REPLACE PROPERTY GRAPH `${CDP_PROJECT}.${CDP_DS}.cdp_semantic_graph`
  NODE TABLES (
    `${CDP_PROJECT}.${CDP_DS}.sem_membership` AS Membership
      KEY (record_id, identifier_id)
      DEFAULT LABEL OPTIONS (
        description = 'One current link between a customer source record and a normalised identifier. Root table of the semantic graph.',
        synonyms = ['link', 'identifier membership', 'record-identifier pair']
      )
      PROPERTIES (
        record_id         OPTIONS (description = 'Customer source record key', synonyms = ['profile_id', 'customer id']),
        profile_id        OPTIONS (description = 'Alias of record_id for cross-notebook compatibility'),
        identifier_id     OPTIONS (description = 'Normalised identifier value (EM:, PH:, AC:, DV:)'),
        identifier_type   OPTIONS (description = 'Kind of identifier: email, phone, loyalty_account, device_id', synonyms = ['id type']),
        anchor_flag       OPTIONS (description = '1 if primary anchor identifier in the source system, else 0'),
        sources           OPTIONS (description = 'Originating source system (CRM, LOYALTY, ECOMM, POS, CALL, SURVEY)', synonyms = ['source systems', 'brands']),
        first_seen_in     OPTIONS (description = 'Source system where the link was first observed'),
        available_from_ts OPTIONS (description = 'Timestamp when the link was recorded'),
        MEASURE(COUNT(record_id))   AS link_count        OPTIONS (description = 'Number of record-identifier links', synonyms = ['links', 'memberships']),
        MEASURE(SUM(anchor_flag))   AS anchor_link_count OPTIONS (description = 'Number of links that are anchor identifiers')
      ),
    `${CDP_PROJECT}.${CDP_DS}.sem_profile` AS Profile
      KEY (record_id)
      DEFAULT LABEL OPTIONS (
        description = 'A customer source record plus where each identity-resolution method (baseline_cc, weighted_cc, composable_cdp) placed it.',
        synonyms = ['customer', 'customer profile', 'record']
      )
      PROPERTIES (
        record_id                         OPTIONS (description = 'Source record key', synonyms = ['profile_id']),
        profile_id                        OPTIONS (description = 'Customer profile key'),
        sources                           OPTIONS (description = 'Originating source system', synonyms = ['brand', 'source system']),
        n_sources                         OPTIONS (description = 'Number of source systems for this record'),
        n_identifiers                     OPTIONS (description = 'Number of current identifiers held by the record'),
        n_anchor                          OPTIONS (description = 'Number of anchor identifiers held'),
        has_email                         OPTIONS (description = 'Record holds an email address'),
        has_phone                         OPTIONS (description = 'Record holds a phone number'),
        has_loyalty_id                    OPTIONS (description = 'Record holds a loyalty account number'),
        first_seen_in                     OPTIONS (description = 'Originating source system'),
        first_seen_ts                     OPTIONS (description = 'Record timestamp'),
        touches_hub_flag                  OPTIONS (description = '1 if the record touches at least one promiscuous hub identifier (degree > 25), else 0'),
        baseline_wesid                    OPTIONS (description = 'Cluster assigned by baseline_cc (naive connected components)'),
        baseline_cluster_size             OPTIONS (description = 'Number of records in the baseline_cc cluster'),
        baseline_hairball_flag            OPTIONS (description = '1 if the baseline_cc cluster is a hairball (>= 20 records), else 0'),
        weighted_wesid                    OPTIONS (description = 'Cluster assigned by weighted_cc (IDF-weighted bipartite projection)'),
        weighted_cluster_size             OPTIONS (description = 'Number of records in the weighted_cc cluster'),
        weighted_hairball_flag            OPTIONS (description = '1 if the weighted_cc cluster is a hairball (>= 20 records), else 0'),
        composable_wesid                  OPTIONS (description = 'Cluster assigned by composable_cdp (2-Hop Graph + Hybrid Search + Gemini Adjudicator + Contradiction Guard)'),
        composable_cluster_size           OPTIONS (description = 'Number of records in the composable_cdp cluster'),
        composable_hairball_flag          OPTIONS (description = '1 if the composable_cdp cluster is a hairball (>= 20 records), else 0'),
        baseline_composable_disagree_flag OPTIONS (description = '1 if baseline_cc and composable_cdp place the record in clusters of different size'),
        MEASURE(COUNT(record_id))                         AS profile_count                      OPTIONS (description = 'Number of distinct customer records', synonyms = ['profiles', 'records']),
        MEASURE(AVG(n_identifiers))                       AS avg_identifiers_per_profile        OPTIONS (description = 'Average number of current identifiers per record'),
        MEASURE(SUM(touches_hub_flag))                    AS profiles_touching_hubs             OPTIONS (description = 'Number of records holding at least one promiscuous hub identifier'),
        MEASURE(COUNT(DISTINCT baseline_wesid))           AS baseline_wesid_count               OPTIONS (description = 'Number of distinct clusters produced by baseline_cc'),
        MEASURE(COUNT(DISTINCT weighted_wesid))           AS weighted_wesid_count               OPTIONS (description = 'Number of distinct clusters produced by weighted_cc'),
        MEASURE(COUNT(DISTINCT composable_wesid))         AS composable_wesid_count             OPTIONS (description = 'Number of distinct clusters produced by composable_cdp'),
        MEASURE(SUM(baseline_hairball_flag))              AS profiles_in_baseline_hairballs     OPTIONS (description = 'Number of records inside a hairball under baseline_cc'),
        MEASURE(SUM(weighted_hairball_flag))              AS profiles_in_weighted_hairballs     OPTIONS (description = 'Number of records inside a hairball under weighted_cc'),
        MEASURE(SUM(composable_hairball_flag))            AS profiles_in_composable_hairballs   OPTIONS (description = 'Number of records inside a hairball under composable_cdp'),
        MEASURE(MAX(baseline_cluster_size))               AS largest_baseline_cluster           OPTIONS (description = 'Largest baseline_cc cluster size'),
        MEASURE(MAX(weighted_cluster_size))               AS largest_weighted_cluster           OPTIONS (description = 'Largest weighted_cc cluster size'),
        MEASURE(MAX(composable_cluster_size))             AS largest_composable_cluster         OPTIONS (description = 'Largest composable_cdp cluster size'),
        MEASURE(AVG(baseline_cluster_size))               AS avg_baseline_cluster_size          OPTIONS (description = 'Average baseline_cc cluster size'),
        MEASURE(AVG(composable_cluster_size))             AS avg_composable_cluster_size        OPTIONS (description = 'Average composable_cdp cluster size'),
        MEASURE(SUM(baseline_composable_disagree_flag))   AS review_candidates                  OPTIONS (description = 'Number of records where baseline_cc and composable_cdp disagree on cluster size')
      ),
    `${CDP_PROJECT}.${CDP_DS}.sem_identifier` AS Identifier
      KEY (identifier_id)
      DEFAULT LABEL OPTIONS (
        description = 'A normalised identifier with degree, IDF rarity weight, and promiscuity.',
        synonyms = ['identity key', 'contact point']
      )
      PROPERTIES (
        identifier_id    OPTIONS (description = 'Normalised identifier value'),
        identifier_type  OPTIONS (description = 'Kind of identifier: email, phone, loyalty_account, device_id'),
        degree           OPTIONS (description = 'Number of distinct records currently holding this identifier'),
        degree_all_time  OPTIONS (description = 'Number of distinct records that ever held this identifier'),
        idf_weight       OPTIONS (description = 'IDF rarity weight ln(N / degree)'),
        is_promiscuous   OPTIONS (description = 'TRUE if shared by more than 25 records (hub)'),
        promiscuous_flag OPTIONS (description = '1 if promiscuous hub, else 0'),
        sources          OPTIONS (description = 'Pipe-separated source systems that reported the identifier'),
        first_seen_ts    OPTIONS (description = 'First timestamp the identifier was observed'),
        last_seen_ts     OPTIONS (description = 'Most recent timestamp the identifier was observed'),
        MEASURE(COUNT(identifier_id))  AS identifier_count             OPTIONS (description = 'Number of distinct identifiers'),
        MEASURE(SUM(promiscuous_flag)) AS promiscuous_identifier_count OPTIONS (description = 'Number of promiscuous hub identifiers'),
        MEASURE(MAX(degree))           AS max_degree                   OPTIONS (description = 'Largest number of records sharing one identifier'),
        MEASURE(AVG(degree))           AS avg_degree                   OPTIONS (description = 'Average number of records per identifier'),
        MEASURE(AVG(idf_weight))       AS avg_idf_weight               OPTIONS (description = 'Average IDF rarity weight')
      )
  )
  EDGE TABLES (
    `${CDP_PROJECT}.${CDP_DS}.sem_membership` AS LINKS_PROFILE
      KEY (record_id, identifier_id)
      SOURCE KEY (record_id, identifier_id) REFERENCES Membership (record_id, identifier_id)
      DESTINATION KEY (record_id) REFERENCES Profile (record_id)
      DEFAULT LABEL OPTIONS (description = 'The profile/record side of an identifier membership link')
      NO PROPERTIES,
    `${CDP_PROJECT}.${CDP_DS}.sem_membership` AS LINKS_IDENTIFIER
      KEY (record_id, identifier_id)
      SOURCE KEY (record_id, identifier_id) REFERENCES Membership (record_id, identifier_id)
      DESTINATION KEY (identifier_id) REFERENCES Identifier (identifier_id)
      DEFAULT LABEL OPTIONS (description = 'The identifier side of an identifier membership link')
      NO PROPERTIES
  );

