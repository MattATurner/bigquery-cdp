-- =====================================================================
-- 30 · Embed and index
--
-- One text column, `match_key`, becomes two retrieval surfaces:
--
--   semantic · an embedding, for "Jon Smyth" ≈ "Jonathan Smith"
--   lexical  · BM25 over the same string, for "ACC-48213" = "ACC-48213"
--
-- Neither is sufficient alone, and the demo proves it in stage 50. An
-- embedding will never represent an account number usefully; BM25 will
-- never recognise a nickname. The whole argument for hybrid search rests
-- on that asymmetry.
-- =====================================================================


-- ---------------------------------------------------------------------
-- 30a · Autonomous embedding generation
--
-- The embedding is a GENERATED ALWAYS column. There is no embedding job,
-- no orchestration, no drift between the text and its vector: change
-- match_key and BigQuery regenerates the vector itself. That is the
-- single biggest operational difference from a hand-rolled pipeline, and
-- it is worth pausing on in the room.
--
-- NOTE ON asynchronous:
--   asynchronous = TRUE is MANDATORY, not a preference. BigQuery rejects
--   a synchronous generated embedding column outright:
--     "Generated embedding column requires asynchronous option to be true"
--
--   An earlier draft of this file set it to FALSE deliberately, reasoning
--   that run.sh runs stages in sequence and stage 40 needs the vectors, so
--   a background job would be raced with no SLEEP available in SQL. The
--   reasoning was sound; the option it depended on does not exist.
--
--   So the race is real and has to be handled rather than designed away.
--   The vectors are populated by a background job that is still running
--   when this stage returns, and everything that consumes them now lives
--   in stage 35. run.sh polls v_embedding_health between the two and will
--   not continue until every row is embedded.
--
--   This matters most for party_vectors in stage 35: it is a CTAS with
--   WHERE match_embedding.result IS NOT NULL, so running it early yields
--   an EMPTY table and no error at all.
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.party_search`
(
  record_id         STRING NOT NULL,
  source_system     STRING,
  source_trust      INT64,
  match_key         STRING,
  name_norm         STRING,
  forename_norm     STRING,
  surname_norm      STRING,
  address_norm      STRING,
  postcode_norm     STRING,
  postcode_out      STRING,
  email_norm        STRING,
  phone_e164        STRING,
  dob               DATE,
  account_number    STRING,
  identity_strength INT64,
  blocking_keys     ARRAY<STRING>,

  match_embedding   STRUCT<result ARRAY<FLOAT64>, status STRING>
    GENERATED ALWAYS AS (
      AI.EMBED(
        match_key,
        connection_id => '${CDP_CONNECTION_PATH}',
        endpoint      => '${CDP_EMBEDDING_ENDPOINT}'
      )
    ) STORED OPTIONS (asynchronous = TRUE)
)
CLUSTER BY postcode_out, surname_norm
OPTIONS (
  description = 'Search surface for entity resolution. match_embedding is maintained by '
             || 'BigQuery: there is no embedding pipeline to run or repair.'
);

INSERT INTO `${CDP_PROJECT}.${CDP_DS}.party_search`
(
  record_id, source_system, source_trust, match_key, name_norm, forename_norm,
  surname_norm, address_norm, postcode_norm, postcode_out, email_norm,
  phone_e164, dob, account_number, identity_strength, blocking_keys
)
SELECT
  record_id, source_system, source_trust, match_key, name_norm, forename_norm,
  surname_norm, address_norm, postcode_norm, postcode_out, email_norm,
  phone_e164, dob, account_number, identity_strength, blocking_keys
FROM `${CDP_PROJECT}.${CDP_DS}.party_records`
-- A record with no identity text at all cannot be matched and would only
-- pollute the vector space. Excluded here rather than filtered later, so
-- the count difference is visible.
WHERE match_key IS NOT NULL AND match_key != '';


-- ---------------------------------------------------------------------
-- 30b · Did the embeddings actually land?
--
-- The status field on the generated column is the honest answer. Quota
-- pressure produces partial failures that are easy to miss, and a silently
-- unembedded record is a silently unmatched customer.
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW `${CDP_PROJECT}.${CDP_DS}.v_embedding_health` AS
SELECT
  source_system,
  COUNT(*)                                                        AS records,
  COUNTIF(match_embedding.result IS NOT NULL)                     AS embedded,
  COUNTIF(match_embedding.result IS NULL)                         AS missing,
  COUNTIF(IFNULL(match_embedding.status, '') != '')               AS errored,
  ANY_VALUE(NULLIF(match_embedding.status, ''))                   AS sample_error,
  ANY_VALUE(ARRAY_LENGTH(match_embedding.result))                 AS dimensions
FROM `${CDP_PROJECT}.${CDP_DS}.party_search`
GROUP BY source_system
ORDER BY missing DESC, source_system;
