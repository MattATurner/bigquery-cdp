-- =====================================================================
-- A · Does person_id survive a re-run?
--
-- The question nobody asks in a demo and everybody hits in production.
--
-- If person_id is derived from the cluster — the smallest record_id, a
-- hash of the members — then adding one record to a cluster changes the
-- identifier for everyone in it. Downstream, suppression lists stop
-- matching, audience memberships churn, and a customer who unsubscribed
-- last month quietly becomes a new person who never did.
--
-- This build persists identifiers in a crosswalk and inherits them. To
-- see it: run the pipeline, note the output below, then run
--   ./run.sh --from 40
-- and run this scenario again. minted_this_run should be 0 the second
-- time, and first_seen should be unchanged.
-- =====================================================================

WITH churn AS (
  SELECT
    COUNT(*)                                                   AS people,
    COUNTIF(minted_this_run)                                   AS minted_this_run,
    COUNTIF(NOT minted_this_run)                               AS inherited
  FROM `${CDP_PROJECT}.${CDP_DS}.node_person`
),
ages AS (
  SELECT
    COUNT(DISTINCT person_id)                                  AS ids_in_crosswalk,
    COUNT(*)                                                   AS records_mapped,
    MIN(first_seen)                                            AS oldest_id_first_seen,
    MAX(last_seen)                                             AS most_recent_touch,
    COUNTIF(first_seen < last_seen)                            AS ids_seen_more_than_once
  FROM `${CDP_PROJECT}.${CDP_DS}.person_crosswalk`
),
-- The failure this design prevents, made concrete: how many downstream
-- audience memberships would have been invalidated if identifiers were
-- derived rather than persisted.
exposure AS (
  SELECT COUNT(*) AS contactable_rows_at_risk
  FROM `${CDP_PROJECT}.${CDP_DS}.v_contactable`
)
SELECT
  c.people,
  c.minted_this_run,
  c.inherited,
  a.ids_in_crosswalk,
  a.records_mapped,
  a.ids_seen_more_than_once,
  a.oldest_id_first_seen,
  a.most_recent_touch,
  e.contactable_rows_at_risk,
  IF(c.minted_this_run = c.people,
     'FIRST RUN — every identifier was minted. Re-run and compare.',
     'RE-RUN — inherited identifiers held; only genuinely new clusters minted.')
    AS interpretation
FROM churn AS c, ages AS a, exposure AS e;
