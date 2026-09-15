-- =====================================================================
-- 10 · Land the sources
--
-- A deliberate mix of storage types, because the deck claims we meet
-- data where it lives:
--
--   managed  · CRM, e-commerce, loyalty, consent   (curated, governed)
--   external · POS (CSV), support (Parquet), enrichment (JSONL)
--   object   · call transcripts                    (genuinely unstructured)
--
-- Cross-cloud / borderless Lakehouse is explicitly out of scope here.
-- =====================================================================

-- ---------------------------------------------------------------------
-- Managed tables
-- ---------------------------------------------------------------------

LOAD DATA OVERWRITE `${CDP_PROJECT}.${CDP_DS}.src_crm_customers`
(
  record_id     STRING,
  customer_ref  STRING,
  full_name     STRING,
  address_line1 STRING,
  city          STRING,
  postcode      STRING,
  email         STRING,
  phone         STRING,
  dob           DATE,
  created_at    TIMESTAMP
)
FROM FILES (
  format = 'CSV',
  skip_leading_rows = 1,
  uris = ['gs://${CDP_BUCKET}/raw/crm_customers.csv']
);

LOAD DATA OVERWRITE `${CDP_PROJECT}.${CDP_DS}.src_ecom_accounts`
(
  record_id   STRING,
  account_ref STRING,
  first_name  STRING,
  last_name   STRING,
  email       STRING,
  phone       STRING,
  postcode    STRING,
  dob         DATE,
  created_at  TIMESTAMP
)
FROM FILES (
  format = 'CSV',
  skip_leading_rows = 1,
  uris = ['gs://${CDP_BUCKET}/raw/ecom_accounts.csv']
);

LOAD DATA OVERWRITE `${CDP_PROJECT}.${CDP_DS}.src_loyalty_members`
(
  record_id      STRING,
  account_number STRING,
  member_name    STRING,
  address_line1  STRING,
  city           STRING,
  postcode       STRING,
  mobile         STRING,
  dob            DATE,
  card_issued_at TIMESTAMP
)
FROM FILES (
  format = 'CSV',
  skip_leading_rows = 1,
  uris = ['gs://${CDP_BUCKET}/raw/loyalty_members.csv']
);

-- Append-only. Consent is bound to the source record that captured it and
-- is never rewritten — that is what makes the intersection rule provable
-- later, and what lets us answer "who agreed to what, when, and where".
LOAD DATA OVERWRITE `${CDP_PROJECT}.${CDP_DS}.src_consent_events`
(
  consent_id  STRING,
  record_id   STRING,
  channel     STRING,
  status      STRING,
  purpose     STRING,
  captured_at TIMESTAMP
)
FROM FILES (
  format = 'CSV',
  skip_leading_rows = 1,
  uris = ['gs://${CDP_BUCKET}/raw/consent_events.csv']
);

-- ---------------------------------------------------------------------
-- External tables — queried in place, never copied
-- ---------------------------------------------------------------------

CREATE OR REPLACE EXTERNAL TABLE `${CDP_PROJECT}.${CDP_DS}.ext_pos_transactions`
(
  record_id              STRING,
  txn_id                 STRING,
  surname                STRING,
  initial                STRING,
  postcode_outward       STRING,
  loyalty_account_number STRING,
  store_id               STRING,
  txn_ts                 TIMESTAMP,
  amount_aud             NUMERIC,
  category               STRING
)
OPTIONS (
  format = 'CSV',
  skip_leading_rows = 1,
  uris = ['gs://${CDP_BUCKET}/pos/pos_transactions.csv'],
  description = 'In-store transactions. Sparse identity: surname, initial and the first '
             || 'two digits of the postcode only. Loyalty number present on ~35% of rows '
             || 'and is the only strong link this source ever offers.'
);

CREATE OR REPLACE EXTERNAL TABLE `${CDP_PROJECT}.${CDP_DS}.ext_support_tickets`
OPTIONS (
  format = 'PARQUET',
  uris = ['gs://${CDP_BUCKET}/support/support_tickets.parquet'],
  description = 'Support tickets. Free-text bodies contain incidental identifiers, '
             || 'risk indicators, and three deliberate prompt-injection attempts used '
             || 'to demonstrate the adjudicator guard.'
);

CREATE OR REPLACE EXTERNAL TABLE `${CDP_PROJECT}.${CDP_DS}.ext_third_party_enrich`
(
  record_id        STRING,
  name             STRING,
  address          STRING,
  postcode         STRING,
  email            STRING,
  vendor           STRING,
  vendor_confidence FLOAT64
)
OPTIONS (
  format = 'JSON',
  uris = ['gs://${CDP_BUCKET}/enrich/third_party_enrich.jsonl'],
  description = 'Third-party enrichment. Deliberately dirty — stale addresses and some '
             || 'wrong attributions. Lowest trust score; survivorship should rarely let '
             || 'it win a field.'
);

-- ---------------------------------------------------------------------
-- Object table — unstructured, zero ETL
--
-- The transcripts are never extracted into a staging table. AI functions
-- read them where they sit.
-- ---------------------------------------------------------------------

CREATE OR REPLACE EXTERNAL TABLE `${CDP_PROJECT}.${CDP_DS}.obj_call_transcripts`
WITH CONNECTION `${CDP_CONNECTION_PATH}`
OPTIONS (
  object_metadata = 'SIMPLE',
  uris = ['gs://${CDP_BUCKET}/call_transcripts/*.txt'],
  max_staleness = INTERVAL 1 DAY,
  metadata_cache_mode = 'AUTOMATIC',
  description = 'Call transcripts in Cloud Storage, queried in place. Carries the '
             || '"my wife''s account" signal that prevents a caller being merged with '
             || 'the account holder.'
);

CREATE OR REPLACE EXTERNAL TABLE `${CDP_PROJECT}.${CDP_DS}.ext_call_manifest`
(
  record_id STRING,
  uri       STRING,
  call_id   STRING,
  agent_id  STRING,
  call_ts   TIMESTAMP
)
OPTIONS (
  format = 'CSV',
  skip_leading_rows = 1,
  uris = ['gs://${CDP_BUCKET}/raw/call_transcripts_manifest.csv']
);

-- ---------------------------------------------------------------------
-- Ground truth — separate dataset, scoring only
-- ---------------------------------------------------------------------

LOAD DATA OVERWRITE `${CDP_PROJECT}.${CDP_DS_TRUTH}.person_truth`
(
  record_id         STRING,
  true_person_id    STRING,
  true_household_id STRING,
  case_type         STRING,
  notes             STRING
)
FROM FILES (
  format = 'CSV',
  skip_leading_rows = 1,
  uris = ['gs://${CDP_BUCKET}/truth/person_truth.csv']
);

LOAD DATA OVERWRITE `${CDP_PROJECT}.${CDP_DS_TRUTH}.case_catalogue`
(
  case_type        STRING,
  description      STRING,
  expected_outcome STRING,
  deck_slide       INT64,
  target_instances INT64
)
FROM FILES (
  format = 'CSV',
  skip_leading_rows = 1,
  uris = ['gs://${CDP_BUCKET}/truth/case_catalogue.csv']
);

-- ---------------------------------------------------------------------
-- Source trust scores.
--
-- Drives survivorship. The ordering matters more than the absolute
-- values: CRM is verified at point of capture; third-party enrichment is
-- bought, stale and unverifiable.
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.ref_source_trust` AS
SELECT * FROM UNNEST([
  STRUCT('CRM'     AS source_system, 9 AS source_trust, 'Verified at point of capture; staff-maintained' AS rationale),
  STRUCT('LOYALTY',  7, 'Customer-maintained; account number is a strong deterministic key'),
  STRUCT('ECOM',     6, 'Self-service signup; email verified, little else'),
  STRUCT('SUPPORT',  4, 'Captured under time pressure; free-text, frequent typos'),
  STRUCT('CALL',     4, 'Transcribed speech; names are phonetically approximate'),
  STRUCT('POS',      3, 'Minimal identity captured at till'),
  STRUCT('ENRICH',   2, 'Third-party, stale, unverifiable; must rarely win a field')
]);
