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
  ARRAY(
    SELECT AS STRUCT channel, purpose, effective_status
    FROM `${CDP_PROJECT}.${CDP_DS}.person_consent` AS c
    WHERE c.person_id = g.person_id
    ORDER BY channel, purpose
  ) AS permissions,
  ARRAY(
    SELECT line FROM interactions AS i WHERE i.person_id = g.person_id LIMIT 10
  ) AS notable_interactions,
  -- Explicit uncertainty. This is the field that stops an agent asserting
  -- something it should have asked about.
  ARRAY(
    SELECT field
    FROM `${CDP_PROJECT}.${CDP_DS}.field_survivorship` AS f
    WHERE f.person_id = g.person_id AND f.was_contested
    ORDER BY field
  ) AS fields_with_conflicting_sources
FROM `${CDP_PROJECT}.${CDP_DS}.golden_person` AS g
JOIN `${CDP_PROJECT}.${CDP_DS}.node_person`   AS n USING (person_id)
LEFT JOIN `${CDP_PROJECT}.${CDP_DS}.person_rfm` AS r USING (person_id);


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
  l.segment_name,
  l.suggested_action
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
