-- =====================================================================
-- 35 · Embedding finalisation — indexes, bulk vector surface, lookups
--
-- WHY THIS IS A SEPARATE STAGE FROM 30
--
-- BigQuery requires a GENERATED ALWAYS embedding column to be declared
-- OPTIONS(asynchronous = TRUE) — a synchronous generated embedding column
-- is rejected outright ("Generated embedding column requires asynchronous
-- option to be true"). So the vectors in party_search are populated by a
-- background job that is still running when stage 30 returns.
--
-- Everything below needs those vectors to exist:
--   30c  the TREE_AH hybrid index is built over match_embedding
--   30d  party_vectors is a CTAS with WHERE match_embedding.result IS NOT
--        NULL — run it too early and it silently yields an EMPTY table,
--        no error, and every downstream stage then succeeds with the
--        wrong numbers
--
-- run.sh therefore polls v_embedding_health between stage 30 and this one
-- and refuses to continue until every row is embedded. SQL has no SLEEP,
-- which is why the wait lives in bash rather than here.
-- =====================================================================


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
-- match_key must appear here as well as in lexical_search_columns:
-- BigQuery rejects the index otherwise ("Lexical search column match_key
-- must be in the list of stored columns"). The BM25 leg reads it from the
-- index, so it has to be stored alongside the vector.
STORING (record_id, source_system, source_trust, match_key, name_norm, postcode_norm,
         email_norm, phone_e164, dob, account_number, identity_strength)
OPTIONS (
  index_type             = 'TREE_AH',
  distance_type          = 'COSINE',
  lexical_search_columns = ['match_key']
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
