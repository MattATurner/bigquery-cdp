-- =====================================================================
-- 80 · Survivorship
--
-- Resolution decides which records belong to one person. Survivorship
-- decides what that person's name, address and phone number actually are
-- when the records disagree — which they almost always do.
--
-- Two principles run through this stage:
--
--   1. Survivorship is per FIELD, not per record. The best address and
--      the best email routinely come from different systems. Picking a
--      single "winning record" and copying it wholesale throws away the
--      one thing every other source was right about.
--
--   2. Every surviving value keeps its provenance. "Where did this
--      address come from, and when" must be answerable in one query, by
--      someone who was not in the room when the rules were written.
-- =====================================================================


-- ---------------------------------------------------------------------
-- 80a · Field assertions
--
-- Every value every source ever claimed, flattened to one row per
-- assertion. Nothing is discarded here — the losing values are kept, and
-- they are what makes the conflict count meaningful later.
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.field_assertions`
CLUSTER BY person_id, field
AS
SELECT
  a.person_id,
  p.record_id,
  p.source_system,
  p.source_trust,
  p.source_ts,
  f.field,
  f.value_norm,
  f.value_raw
FROM `${CDP_PROJECT}.${CDP_DS}.party_records` AS p
JOIN `${CDP_PROJECT}.${CDP_DS}.person_assignment` AS a ON a.record_id = p.record_id,
UNNEST([
  STRUCT('forename' AS field, p.forename_norm AS value_norm, COALESCE(NULLIF(p.raw_forename, ''), REGEXP_EXTRACT(p.raw_name, r'^\S+'), p.forename_norm) AS value_raw),
  STRUCT('surname',           p.surname_norm,                COALESCE(NULLIF(p.raw_surname, ''),  REGEXP_EXTRACT(p.raw_name, r'\S+$'), p.surname_norm)),
  STRUCT('full_name',         p.name_norm,                   p.raw_name),
  STRUCT('address',           p.address_norm,                p.raw_address),
  STRUCT('city',              UPPER(p.raw_city),             p.raw_city),
  STRUCT('postcode',          p.postcode_norm,               p.raw_postcode),
  STRUCT('email',             p.email_norm,                  p.raw_email),
  STRUCT('phone',             p.phone_e164,                  p.raw_phone),
  STRUCT('dob',               CAST(p.dob AS STRING),         CAST(p.dob AS STRING)),
  STRUCT('account_number',    p.account_number,              p.account_number)
]) AS f
WHERE f.value_norm IS NOT NULL AND f.value_norm != '';


-- ---------------------------------------------------------------------
-- 80b · The rule
--
-- Ordered, and the order is the policy:
--
--   1. source trust        a CRM address beats a bought one, always
--   2. recency             within a trust tier, newer wins — this is what
--                          makes a house move propagate
--   3. corroboration       more sources asserting the same value
--   4. record_id           a deterministic tie-break, so the same inputs
--                          always produce the same golden record
--
-- Step 4 looks trivial and is not. Without it, two runs over identical
-- data can disagree, and a customer's displayed address flickers between
-- two equally-ranked values. That is the kind of bug that destroys trust
-- in a platform and takes weeks to track down.
--
-- Recency is deliberately SECOND, not first. A fresh record from a
-- third-party enrichment file should not overwrite a verified CRM
-- address just because it arrived this morning.
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.field_survivorship`
CLUSTER BY person_id, field
AS
WITH corroboration AS (
  SELECT
    person_id, field, value_norm,
    COUNT(DISTINCT source_system) AS asserting_sources,
    COUNT(*)                      AS assertions
  FROM `${CDP_PROJECT}.${CDP_DS}.field_assertions`
  GROUP BY person_id, field, value_norm
),
ranked AS (
  SELECT
    fa.*,
    c.asserting_sources,
    c.assertions,
    ROW_NUMBER() OVER (
      PARTITION BY fa.person_id, fa.field
      ORDER BY
        fa.source_trust DESC,
        fa.source_ts DESC NULLS LAST,
        c.asserting_sources DESC,
        fa.record_id
    ) AS rn
  FROM `${CDP_PROJECT}.${CDP_DS}.field_assertions` AS fa
  JOIN corroboration AS c
    ON c.person_id = fa.person_id AND c.field = fa.field AND c.value_norm = fa.value_norm
),
conflict AS (
  SELECT person_id, field, COUNT(DISTINCT value_norm) AS distinct_values
  FROM `${CDP_PROJECT}.${CDP_DS}.field_assertions`
  GROUP BY person_id, field
)
SELECT
  r.person_id,
  r.field,
  r.value_norm                       AS surviving_value_norm,
  r.value_raw                        AS surviving_value,
  r.record_id                        AS won_from_record_id,
  r.source_system                    AS won_from_source,
  r.source_trust,
  r.source_ts                        AS asserted_at,
  r.asserting_sources,
  cf.distinct_values,
  cf.distinct_values > 1             AS was_contested,
  CONCAT(
    'Selected from ', r.source_system,
    ' (trust ', CAST(r.source_trust AS STRING), ')',
    IF(cf.distinct_values > 1,
       CONCAT(' over ', CAST(cf.distinct_values - 1 AS STRING), ' competing value(s)'),
       ' — uncontested'),
    '; corroborated by ', CAST(r.asserting_sources AS STRING), ' source(s).'
  )                                  AS provenance
FROM ranked AS r
JOIN conflict AS cf ON cf.person_id = r.person_id AND cf.field = r.field
WHERE r.rn = 1;


-- ---------------------------------------------------------------------
-- 80c · The golden record
--
-- The wide, consumable view of a person. This is what a marketer, an
-- agent or a service desk actually reads.
--
-- Note the deliberate omission: no consent fields. Consent is computed in
-- stage 85 under its own rules, and is never a survivorship outcome. If
-- consent were resolved here it would inherit the "highest trust wins"
-- logic, and a high-trust GRANTED would silently overwrite a
-- low-trust WITHDRAWN. That is precisely the failure this build exists to
-- prevent.
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.golden_person`
CLUSTER BY person_id
AS
WITH pivoted AS (
  SELECT
    np.person_id,
    MAX(IF(s.field = 'full_name',      s.surviving_value,     NULL)) AS full_name,
    MAX(IF(s.field = 'forename',       s.surviving_value,     NULL)) AS forename,
    MAX(IF(s.field = 'surname',        s.surviving_value,     NULL)) AS surname,
    MAX(IF(s.field = 'address',        s.surviving_value,     NULL)) AS address,
    MAX(IF(s.field = 'address',        s.won_from_record_id,  NULL)) AS address_record_id,
    MAX(IF(s.field = 'city',           s.surviving_value,     NULL)) AS field_city,
    MAX(IF(s.field = 'postcode',       s.surviving_value,     NULL)) AS field_postcode,
    MAX(IF(s.field = 'email',          s.surviving_value,     NULL)) AS email,
    MAX(IF(s.field = 'phone',          s.surviving_value,     NULL)) AS phone,
    SAFE.PARSE_DATE('%Y-%m-%d',
      MAX(IF(s.field = 'dob',          s.surviving_value,     NULL))) AS dob,
    MAX(IF(s.field = 'account_number', s.surviving_value,     NULL)) AS account_number,
    COUNTIF(s.was_contested)                                         AS contested_fields,
    COUNT(s.field)                                                   AS populated_fields,
    MAX(s.source_trust)                                              AS best_source_trust,
    MAX(s.asserted_at)                                               AS most_recent_assertion
  FROM `${CDP_PROJECT}.${CDP_DS}.node_person` AS np
  LEFT JOIN `${CDP_PROJECT}.${CDP_DS}.field_survivorship` AS s
    ON s.person_id = np.person_id
  GROUP BY np.person_id
)
SELECT
  p.person_id,
  p.full_name,
  p.forename,
  p.surname,
  p.address,
  -- Keep address components as a coherent tuple from the winning address record
  -- to prevent Chimera/Frankenstein addresses across cities/states.
  COALESCE(addr_rec.raw_city,     p.field_city)     AS city,
  COALESCE(addr_rec.raw_postcode, p.field_postcode) AS postcode,
  p.email,
  p.phone,
  p.dob,
  p.account_number,
  p.contested_fields,
  p.populated_fields,
  p.best_source_trust,
  p.most_recent_assertion
FROM pivoted AS p
LEFT JOIN `${CDP_PROJECT}.${CDP_DS}.party_records` AS addr_rec
  ON addr_rec.record_id = p.address_record_id;


-- ---------------------------------------------------------------------
-- 80d · Which sources actually win
--
-- Worth showing, because it is usually a surprise. If a low-trust source
-- is winning a large share of fields, it is not because the rule is
-- broken — it is because the high-trust sources are silent, and that is a
-- data-capture problem rather than a matching one.
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW `${CDP_PROJECT}.${CDP_DS}.v_survivorship_by_source` AS
SELECT
  won_from_source                                   AS source_system,
  ANY_VALUE(source_trust)                           AS trust,
  COUNT(*)                                          AS fields_won,
  ROUND(100 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)  AS pct_of_fields_won,
  COUNTIF(was_contested)                            AS won_against_competition,
  ARRAY_AGG(DISTINCT field ORDER BY field)          AS fields
FROM `${CDP_PROJECT}.${CDP_DS}.field_survivorship`
GROUP BY won_from_source
ORDER BY fields_won DESC;


-- ---------------------------------------------------------------------
-- 80e · Show me one person, end to end
--
-- The single most useful query in the whole demo. Give it a person_id and
-- it returns every field, the value that survived, where it came from,
-- and what it beat.
--
--   SELECT * FROM cdp.tf_explain_person('PER-00000000deadbeef');
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE FUNCTION `${CDP_PROJECT}.${CDP_DS}.tf_explain_person`(p_person_id STRING)
AS (
  SELECT
    s.field,
    s.surviving_value,
    s.won_from_source,
    s.source_trust,
    s.asserted_at,
    s.was_contested,
    s.provenance,
    -- The values that lost, so the decision can be challenged rather than
    -- merely accepted.
    ARRAY(
      SELECT AS STRUCT fa.source_system, fa.value_raw, fa.source_trust, fa.source_ts
      FROM `${CDP_PROJECT}.${CDP_DS}.field_assertions` AS fa
      WHERE fa.person_id = s.person_id
        AND fa.field     = s.field
        AND fa.value_norm != s.surviving_value_norm
      ORDER BY fa.source_trust DESC
    ) AS rejected_values
  FROM `${CDP_PROJECT}.${CDP_DS}.field_survivorship` AS s
  WHERE s.person_id = p_person_id
);
