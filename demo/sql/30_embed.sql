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
--   Production should use OPTIONS(asynchronous = TRUE) — embeddings are
--   generated in the background and the write is never blocked.
--   This demo runs synchronously, because run.sh executes stages in
--   sequence and stage 40 needs the vectors to exist. Asynchronous
--   generation would mean stage 40 racing a background job with no
--   SLEEP available in SQL to wait on it.
--   Flip the option and add a polling step if you want to show the
--   production behaviour. The tradeoff is real and worth naming rather
--   than hiding.
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
    ) STORED OPTIONS (asynchronous = FALSE)
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


-- ---------------------------------------------------------------------
-- 30c · Hybrid index — for live, single-query lookup
--
-- TREE_AH with lexical_search_columns is what makes AI.SEARCH run in
-- HYBRID mode: BM25 and vector retrieval over the same index, fused with
-- reciprocal rank fusion. This is the path that carries the published
-- slot-efficiency gain for single-query search, and it is the path a
-- customer-facing agent would call.
--
-- Vector index creation requires at least 5,000 rows in the base table.
-- With the default corpus (20,000 records) that is comfortably met; a
-- smaller --records value will cause this statement to fail, which is why
-- the README pins a minimum.
-- ---------------------------------------------------------------------

CREATE VECTOR INDEX IF NOT EXISTS idx_party_hybrid
ON `${CDP_PROJECT}.${CDP_DS}.party_search`(match_embedding)
STORING (record_id, source_system, source_trust, name_norm, postcode_norm,
         email_norm, phone_e164, dob, account_number, identity_strength)
OPTIONS (
  index_type             = 'TREE_AH',
  distance_type          = 'COSINE',
  lexical_search_columns = '["match_key"]'
);


-- ---------------------------------------------------------------------
-- 30d · Bulk vector surface
--
-- A second, plain ARRAY<FLOAT64> copy of the same vectors.
--
-- Why duplicate: stage 40 resolves the whole corpus against itself using
-- VECTOR_SEARCH with a query *table*, which is the batch path. Stage 50's
-- live demo uses AI.SEARCH with a single query string, which is the
-- interactive path. Keeping them on separate, purpose-built indexes means
-- neither is compromised to suit the other, and the demo can show both
-- without caveats.
--
-- No extra embedding cost: the vectors are copied, not regenerated.
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.party_vectors`
CLUSTER BY postcode_out
AS
SELECT
  record_id,
  source_system,
  source_trust,
  match_key,
  name_norm,
  surname_norm,
  postcode_out,
  postcode_norm,
  email_norm,
  phone_e164,
  dob,
  account_number,
  identity_strength,
  match_embedding.result AS embedding
FROM `${CDP_PROJECT}.${CDP_DS}.party_search`
WHERE match_embedding.result IS NOT NULL;

CREATE VECTOR INDEX IF NOT EXISTS idx_party_vectors
ON `${CDP_PROJECT}.${CDP_DS}.party_vectors`(embedding)
STORING (record_id, source_system, source_trust, name_norm, postcode_out,
         email_norm, phone_e164, dob, account_number, identity_strength)
OPTIONS (
  index_type    = 'IVF',
  distance_type = 'COSINE',
  ivf_options   = '{"num_lists": 200}'
);


-- ---------------------------------------------------------------------
-- 30e · Search index for the lexical leg
--
-- BM25 over match_key. The account-number case is the one to watch:
-- ACC-48213 is a single high-IDF token that BM25 scores decisively and an
-- embedding model treats as noise.
-- ---------------------------------------------------------------------

CREATE SEARCH INDEX IF NOT EXISTS idx_party_text
ON `${CDP_PROJECT}.${CDP_DS}.party_search`(match_key)
OPTIONS (analyzer = 'LOG_ANALYZER');


-- ---------------------------------------------------------------------
-- 30f · Live lookup, two ways
--
-- These two table functions are the side-by-side that makes the hybrid
-- argument concrete. Same corpus, same query, one retrieval mode
-- different. Run both against an account number and the difference is
-- not subtle.
--
--   SELECT * FROM cdp.tf_lookup_hybrid('ACC-48213');
--   SELECT * FROM cdp.tf_lookup_vector('ACC-48213');
--
-- top_k is fixed at a literal because AI.SEARCH requires it; parameterise
-- by editing the function if you need a different depth.
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE FUNCTION `${CDP_PROJECT}.${CDP_DS}.tf_lookup_hybrid`(probe STRING)
AS (
  SELECT 'HYBRID' AS retrieval_mode, s.*
  FROM AI.SEARCH(
         TABLE `${CDP_PROJECT}.${CDP_DS}.party_search`,
         'match_key',
         probe,
         top_k => 10,
         mode  => 'HYBRID'
       ) AS s
);

CREATE OR REPLACE TABLE FUNCTION `${CDP_PROJECT}.${CDP_DS}.tf_lookup_vector`(probe STRING)
AS (
  SELECT 'VECTOR' AS retrieval_mode, s.*
  FROM AI.SEARCH(
         TABLE `${CDP_PROJECT}.${CDP_DS}.party_search`,
         'match_key',
         probe,
         top_k => 10,
         mode  => 'VECTOR'
       ) AS s
);
