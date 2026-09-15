-- =====================================================================
-- 85 · Consent
--
-- The stage that most MDM builds get wrong, and the one with legal
-- consequences when they do.
--
-- Merging two records merges their behaviour, their orders and their
-- addresses. It must NOT merge their permissions. Consent was given by a
-- person, to a specific organisation, through a specific channel, for a
-- specific purpose, at a specific moment — and joining two rows in a
-- warehouse does not create permission that nobody ever gave.
--
-- Three rules, in order:
--
--   1. A suppression always wins. Deceased or minor indications override
--      everything, including an explicit grant.
--   2. An explicit withdrawal always wins over a grant, regardless of
--      which is more recent. "I changed my mind" does not expire.
--   3. Otherwise permission is the INTERSECTION, not the union. A profile
--      may be contacted on a channel only where every contributing record
--      agrees it may be.
--
-- Rule 3 is the expensive one, and the one commercial pressure pushes
-- against. Stage 85d puts a number on exactly how many contacts it costs
-- — and therefore how many unlawful contacts the union rule would have
-- produced.
-- =====================================================================


-- ---------------------------------------------------------------------
-- 85a · Consent state per source record
--
-- Consent events are append-only, so the current state of a record is
-- its most recent event for that channel and purpose. Nothing is
-- rewritten; the history remains queryable.
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.consent_record_state`
CLUSTER BY record_id, channel
AS
SELECT * EXCEPT (rn)
FROM (
  SELECT
    e.record_id,
    e.channel,
    e.purpose,
    e.status,
    e.captured_at,
    e.consent_id,
    ROW_NUMBER() OVER (
      PARTITION BY e.record_id, e.channel, e.purpose
      ORDER BY e.captured_at DESC, e.consent_id
    ) AS rn
  FROM `${CDP_PROJECT}.${CDP_DS}.src_consent_events` AS e
)
WHERE rn = 1;


-- ---------------------------------------------------------------------
-- 85b · Suppressions
--
-- Sourced from the risk classification in stage 20. These are not
-- preferences and are not negotiable — a marketing send to a deceased
-- customer's household is the kind of failure that reaches the press.
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.person_suppression`
CLUSTER BY person_id
AS
SELECT
  a.person_id,
  LOGICAL_OR(s.suppress_marketing)                            AS suppress_marketing,
  ARRAY_AGG(DISTINCT s.risk_category IGNORE NULLS
            ORDER BY s.risk_category)                         AS risk_categories,
  ANY_VALUE(s.risk_evidence)                                  AS sample_evidence,
  ARRAY_AGG(DISTINCT s.record_id ORDER BY s.record_id)        AS evidence_record_ids
FROM `${CDP_PROJECT}.${CDP_DS}.stg_support_entities` AS s
JOIN `${CDP_PROJECT}.${CDP_DS}.person_assignment` AS a ON a.record_id = s.record_id
WHERE s.risk_category != 'NONE'
GROUP BY a.person_id;


-- ---------------------------------------------------------------------
-- 85c · Effective permission per person, channel and purpose
--
-- Both rules are computed side by side. The union rule is not here
-- because it is a reasonable option — it is here so that the cost of
-- doing the right thing can be stated precisely instead of argued about.
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.person_consent`
CLUSTER BY person_id, channel
AS
WITH per_person AS (
  SELECT
    a.person_id,
    c.channel,
    c.purpose,
    COUNT(*)                                             AS contributing_records,
    LOGICAL_OR(c.status = 'WITHDRAWN')                   AS any_withdrawn,
    LOGICAL_OR(c.status = 'GRANTED')                     AS any_granted,
    LOGICAL_AND(c.status = 'GRANTED')                    AS all_granted,
    COUNTIF(c.status = 'GRANTED')                        AS granted_count,
    COUNTIF(c.status = 'WITHDRAWN')                      AS withdrawn_count,
    COUNTIF(c.status = 'NOT_GIVEN')                      AS not_given_count,
    MIN(IF(c.status = 'WITHDRAWN', c.captured_at, NULL)) AS first_withdrawn_at,
    MAX(c.captured_at)                                   AS latest_event_at,
    ARRAY_AGG(STRUCT(c.record_id, c.status, c.captured_at)
              ORDER BY c.captured_at)                    AS evidence
  FROM `${CDP_PROJECT}.${CDP_DS}.consent_record_state` AS c
  JOIN `${CDP_PROJECT}.${CDP_DS}.person_assignment` AS a ON a.record_id = c.record_id
  GROUP BY a.person_id, c.channel, c.purpose
),
-- How many of a person's records could have carried a consent statement
-- but do not. Under a strict reading, silence is not permission.
coverage AS (
  SELECT person_id, COUNT(*) AS total_records
  FROM `${CDP_PROJECT}.${CDP_DS}.person_assignment`
  GROUP BY person_id
)
SELECT
  p.person_id,
  p.channel,
  p.purpose,
  p.contributing_records,
  cv.total_records,
  p.granted_count,
  p.withdrawn_count,
  p.not_given_count,

  -- THE RULE
  CASE
    WHEN IFNULL(sp.suppress_marketing, FALSE) AND p.purpose = 'MARKETING' THEN 'SUPPRESSED'
    WHEN p.any_withdrawn                                                  THEN 'WITHDRAWN'
    WHEN p.all_granted                                                    THEN 'GRANTED'
    ELSE                                                                       'NOT_GIVEN'
  END                                        AS effective_status,

  -- The stricter reading: a record that never said anything counts
  -- against permission rather than being ignored. Offered as a column
  -- rather than imposed, because which reading applies is a legal
  -- decision, not an engineering one — but it should be a decision
  -- somebody consciously makes.
  CASE
    WHEN IFNULL(sp.suppress_marketing, FALSE) AND p.purpose = 'MARKETING' THEN 'SUPPRESSED'
    WHEN p.any_withdrawn                                                  THEN 'WITHDRAWN'
    WHEN p.all_granted AND p.contributing_records = cv.total_records      THEN 'GRANTED'
    ELSE                                                                       'NOT_GIVEN'
  END                                        AS effective_status_strict,

  -- The common, wrong implementation. Retained purely for comparison.
  CASE
    WHEN p.any_granted THEN 'GRANTED'
    ELSE                    'NOT_GIVEN'
  END                                        AS naive_union_status,

  IFNULL(sp.suppress_marketing, FALSE)       AS suppressed,
  sp.risk_categories,
  p.first_withdrawn_at,
  p.latest_event_at,
  p.evidence,

  CASE
    WHEN IFNULL(sp.suppress_marketing, FALSE) AND p.purpose = 'MARKETING'
      THEN CONCAT('Suppressed: ', ARRAY_TO_STRING(sp.risk_categories, ', '),
                  ' indication found in support contact.')
    WHEN p.any_withdrawn
      THEN CONCAT('Withdrawn on ', FORMAT_TIMESTAMP('%Y-%m-%d', p.first_withdrawn_at),
                  '. Withdrawal is absolute and is not overridden by a later grant '
                  'from another source.')
    WHEN p.all_granted
      THEN CONCAT('All ', CAST(p.contributing_records AS STRING),
                  ' contributing record(s) granted permission on this channel.')
    ELSE
      CONCAT(CAST(p.granted_count AS STRING), ' of ',
             CAST(p.contributing_records AS STRING),
             ' contributing record(s) granted permission — not unanimous, '
             'so permission is not inherited.')
  END                                        AS explanation
FROM per_person AS p
JOIN coverage AS cv ON cv.person_id = p.person_id
LEFT JOIN `${CDP_PROJECT}.${CDP_DS}.person_suppression` AS sp ON sp.person_id = p.person_id;


-- ---------------------------------------------------------------------
-- 85d · What the rule costs, and what it prevents
--
-- The number to put in front of a CMO. The union rule produces a bigger
-- audience; every extra contact in it is a contact the customer did not
-- agree to, on a channel where at least one of their records says no.
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW `${CDP_PROJECT}.${CDP_DS}.v_consent_impact` AS
SELECT
  channel,
  purpose,
  COUNT(*)                                          AS people_with_a_stated_preference,
  COUNTIF(naive_union_status = 'GRANTED')           AS audience_union_rule,
  COUNTIF(effective_status = 'GRANTED')             AS audience_intersection_rule,
  COUNTIF(effective_status_strict = 'GRANTED')      AS audience_strict_rule,
  COUNTIF(naive_union_status = 'GRANTED'
          AND effective_status != 'GRANTED')        AS contacts_the_union_rule_would_add,
  COUNTIF(naive_union_status = 'GRANTED'
          AND effective_status = 'WITHDRAWN')       AS of_which_explicitly_withdrawn,
  COUNTIF(effective_status = 'SUPPRESSED')          AS suppressed_for_risk,
  ROUND(100 * SAFE_DIVIDE(
    COUNTIF(naive_union_status = 'GRANTED' AND effective_status != 'GRANTED'),
    NULLIF(COUNTIF(naive_union_status = 'GRANTED'), 0)), 2) AS pct_of_union_audience_unlawful
FROM `${CDP_PROJECT}.${CDP_DS}.person_consent`
GROUP BY channel, purpose
ORDER BY channel, purpose;


-- ---------------------------------------------------------------------
-- 85e · The conflict cases, named
--
-- The generator plants people whose records carry GRANTED, NOT_GIVEN and
-- WITHDRAWN for the same channel across three different systems. This is
-- not a contrived edge case: it is what happens when a customer signs up
-- online, opts out in store, and never updates the app.
--
-- Put one of these on screen. It is the single clearest illustration of
-- why "merge the profiles" and "merge the permissions" are different
-- operations.
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW `${CDP_PROJECT}.${CDP_DS}.v_consent_conflicts` AS
SELECT
  c.person_id,
  g.full_name,
  c.channel,
  c.purpose,
  c.granted_count,
  c.withdrawn_count,
  c.not_given_count,
  c.naive_union_status  AS would_have_been_contacted,
  c.effective_status    AS actual_decision,
  c.explanation,
  c.evidence
FROM `${CDP_PROJECT}.${CDP_DS}.person_consent` AS c
LEFT JOIN `${CDP_PROJECT}.${CDP_DS}.golden_person` AS g USING (person_id)
WHERE c.granted_count > 0
  AND (c.withdrawn_count > 0 OR c.not_given_count > 0)
ORDER BY c.withdrawn_count DESC, c.granted_count DESC;


-- ---------------------------------------------------------------------
-- 85f · The activation-safe audience
--
-- The only table any downstream campaign should read. If a marketer can
-- reach person_consent directly, sooner or later somebody will write
-- their own interpretation of the rules — and it will be the union one.
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW `${CDP_PROJECT}.${CDP_DS}.v_contactable` AS
SELECT
  c.person_id,
  c.channel,
  c.purpose,
  g.full_name,
  g.email,
  g.phone,
  g.postcode
FROM `${CDP_PROJECT}.${CDP_DS}.person_consent` AS c
JOIN `${CDP_PROJECT}.${CDP_DS}.golden_person` AS g USING (person_id)
WHERE c.effective_status = 'GRANTED';
