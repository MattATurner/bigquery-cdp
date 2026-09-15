-- =====================================================================
-- E · Real-time resolution (appendix)
--
-- Everything else in this demo is batch: resolve the whole corpus, publish
-- the graph, activate from it. That is the right default, because entity
-- resolution is fundamentally an all-pairs problem.
--
-- But once the graph exists, resolving ONE inbound record against it is a
-- different and much cheaper problem — a single probe into an index, not
-- a self-join. That is what AI.SEARCH is for, and it is the capability the
-- published 133x slot-efficiency figure describes.
--
-- This scenario simulates an inbound event. It takes a record that is
-- already in the corpus, deliberately damages it the way a real web form
-- would (a transposed pair of characters in the name), and asks: with no
-- account number, no cookie, and no login, can we work out who this is?
--
-- Why a real record rather than a made-up one: because the ground truth
-- is then known, so the answer can be checked rather than admired. The
-- last column is the one that matters.
--
-- WHAT THIS IS NOT
-- ----------------
-- This is a single-query probe, not a service. A production real-time
-- path needs a latency SLA, a decision on whether an uncertain match
-- blocks the transaction or resolves asynchronously, and a policy for
-- what happens when the probe creates a new person that the next batch
-- run then merges away. None of that is in scope here. The claim is only
-- that the retrieval primitive is fast enough to build on.
-- =====================================================================

-- Scripting rather than a single SELECT: AI.SEARCH and the lookup TVFs
-- take a SCALAR query string, so the probe has to be materialised into a
-- variable before it can be passed. This is the same constraint that
-- forces the bulk path in stage 50 to use VECTOR_SEARCH against a query
-- table instead.

DECLARE probe_record_id STRING;
DECLARE probe_person_id STRING;
DECLARE clean_key       STRING;
DECLARE probe_key       STRING;
DECLARE cut             INT64;

-- Pick a probe deterministically: a record belonging to a person who has
-- several records, so there is something to find. Ordered by record_id so
-- the same record is chosen on every run and the demo is repeatable.
SET probe_record_id = (
  SELECT e.record_id
  FROM `${CDP_PROJECT}.${CDP_DS}.edge_resolves_to` AS e
  JOIN (
    SELECT person_id
    FROM `${CDP_PROJECT}.${CDP_DS}.edge_resolves_to`
    GROUP BY person_id
    HAVING COUNT(*) >= 3
    ORDER BY COUNT(*) DESC, MIN(person_id)
    LIMIT 1
  ) AS p USING (person_id)
  ORDER BY e.record_id
  LIMIT 1
);

SET probe_person_id = (
  SELECT person_id
  FROM `${CDP_PROJECT}.${CDP_DS}.edge_resolves_to`
  WHERE record_id = probe_record_id
);

SET clean_key = (
  SELECT match_key
  FROM `${CDP_PROJECT}.${CDP_DS}.party_search`
  WHERE record_id = probe_record_id
);

-- Damage it. Transposing two adjacent characters near the middle is the
-- single most common human typing error, and it is exactly the kind of
-- corruption that defeats an equality join while leaving both lexical and
-- semantic retrieval a reasonable chance.
SET cut = GREATEST(2, CAST(CHAR_LENGTH(clean_key) / 2 AS INT64));
SET probe_key = CONCAT(
  SUBSTR(clean_key, 1, cut - 1),
  SUBSTR(clean_key, cut + 1, 1),
  SUBSTR(clean_key, cut,     1),
  SUBSTR(clean_key, cut + 2)
);

-- One probe. No self-join, no blocking pass, no full scan of the corpus.
WITH hits AS (
  SELECT *
  FROM `${CDP_PROJECT}.${CDP_DS}.tf_lookup_hybrid`(probe_key)
),
-- Attach the person each candidate record already resolves to, and count
-- how much of the retrieved set agrees. Agreement across several
-- independently-retrieved records is a far stronger signal than any one
-- record's similarity score.
attributed AS (
  SELECT
    e.person_id,
    COUNT(*)                          AS supporting_records,
    MIN(h.record_id)                  AS example_record
  FROM hits AS h
  JOIN `${CDP_PROJECT}.${CDP_DS}.edge_resolves_to` AS e
    ON e.record_id = h.record_id
  -- Exclude the probe record itself. Finding the record you just copied is
  -- not a result, and leaving it in would make this look far better than
  -- it is.
  WHERE h.record_id != probe_record_id
  GROUP BY e.person_id
),
ranked AS (
  SELECT
    *,
    ROW_NUMBER() OVER (ORDER BY supporting_records DESC, person_id) AS rn
  FROM attributed
),
-- A single-row anchor, LEFT JOINed to the winner. Without this, a probe
-- that retrieves nothing returns zero rows and the demo silently shows an
-- empty table — which is the one outcome most worth seeing, because
-- "would have created a duplicate" is the failure this whole system
-- exists to prevent.
anchor AS (SELECT 1 AS k)
SELECT
  probe_record_id                                      AS inbound_record,
  clean_key                                            AS original_key,
  probe_key                                            AS damaged_key_as_received,
  (SELECT COUNT(*) FROM hits)                          AS candidates_retrieved,
  r.person_id                                          AS resolved_to,
  r.supporting_records,
  r.example_record                                     AS matched_against,
  probe_person_id                                      AS correct_answer,
  -- The only column that matters.
  CASE
    WHEN r.person_id IS NULL            THEN 'NO MATCH — would create a new person'
    WHEN r.person_id = probe_person_id  THEN 'CORRECT'
    ELSE                                     'WRONG — resolved to a different person'
  END                                                  AS outcome,
  (SELECT COUNT(*) FROM `${CDP_PROJECT}.${CDP_DS}.party_search`)
                                                       AS corpus_records_searched
FROM anchor AS a
LEFT JOIN ranked AS r ON r.rn = 1;
