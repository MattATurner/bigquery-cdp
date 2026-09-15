# Data Contract — generator ↔ pipeline

The generator writes to `demo/data/`. The loader (`sql/10_land_sources.sql`) expects exactly these
names, columns and types. Change one side, change the other.

All data is **synthetic**. No real people.

**Locale: Australia.** Postcodes are 4 digits with no letters and follow the real state
ranges (NSW `2xxx`, VIC `3xxx`, QLD `4xxx`, SA `5xxx`, WA `6xxx`, TAS `7xxx`, NT `08xx`,
ACT `26xx`). Phone numbers use Australian mobile (`04xx xxx xxx`) and landline
(`(02)`/`(03)`/`(07)`/`(08)`) formats; the international form is `+61` with the trunk zero
**dropped**, so `0412 345 678` normalises to `+61412345678` and never to `+610412…`.
Addresses carry a street, a suburb, a state abbreviation and a postcode. Currency is AUD.
Names are drawn from a mix reflecting the Australian population — predominantly standard
English forenames and surnames, alongside Chinese, Vietnamese, Indian, Arabic, Greek,
Italian, Filipino, Korean and other South-East Asian name stock, with accented Latin
spellings where they occur naturally.

The locale rules are specified in full in [`../LOCALE-SPEC.md`](../LOCALE-SPEC.md).

---

## Identity-bearing sources

Every identity-bearing record carries a globally unique `record_id` of the form
`<SRC>-<8 hex>` (e.g. `CRM-1a2b3c4d`) so records are traceable across every stage.

### 1. `crm_customers.csv` → **managed table** · trust 9
| Column | Type | Notes |
| :--- | :--- | :--- |
| `record_id` | STRING | `CRM-xxxxxxxx` |
| `customer_ref` | STRING | Source natural key |
| `full_name` | STRING | Single field, as CRMs usually store it |
| `address_line1` | STRING | |
| `city` | STRING | |
| `postcode` | STRING | Mostly well-formed |
| `email` | STRING | Verified |
| `phone` | STRING | Mixed formats |
| `dob` | DATE | Rarely null |
| `created_at` | TIMESTAMP | |

### 2. `ecom_accounts.csv` → **managed table** · trust 6
| Column | Type | Notes |
| :--- | :--- | :--- |
| `record_id` | STRING | `ECOM-xxxxxxxx` |
| `account_ref` | STRING | |
| `first_name` | STRING | Often a diminutive |
| `last_name` | STRING | |
| `email` | STRING | `+tag` and dot variants common |
| `phone` | STRING | Often null |
| `postcode` | STRING | ~40% null |
| `dob` | DATE | ~60% null |
| `created_at` | TIMESTAMP | |

### 3. `loyalty_members.csv` → **managed table** · trust 7
| Column | Type | Notes |
| :--- | :--- | :--- |
| `record_id` | STRING | `LOY-xxxxxxxx` |
| `account_number` | STRING | `ACC-nnnnnnn` — the alphanumeric hook for hard case #4 |
| `member_name` | STRING | |
| `address_line1` | STRING | Sometimes carries the suburb after a comma |
| `city` | STRING | |
| `postcode` | STRING | Format drift: leading zero stripped (`0812` → `812`), padded, or area-only. Only the Northern Territory has `08xx` postcodes, so Darwin is the sole producer of the stripped-zero variant — a deliberate trap, not an accident. |
| `mobile` | STRING | |
| `dob` | DATE | ~30% null |
| `card_issued_at` | TIMESTAMP | |

### 4. `pos_transactions.csv` → **external CSV on GCS** · trust 3
Sparse identity, high volume. Doubles as the transaction fact source.
| Column | Type | Notes |
| :--- | :--- | :--- |
| `record_id` | STRING | `POS-xxxxxxxx` |
| `txn_id` | STRING | |
| `surname` | STRING | |
| `initial` | STRING | Single character |
| `postcode_outward` | STRING | **Name retained for pipeline compatibility.** Australia has no outward code, so this is the first 2 digits of the 4-digit postcode, e.g. `20` for `2011`. The first digit is the state and the first two are a coarse regional bucket — meaningful, but not an identity. |
| `loyalty_account_number` | STRING | ~35% populated — the only strong link POS ever has |
| `store_id` | STRING | |
| `txn_ts` | TIMESTAMP | |
| `amount_aud` | NUMERIC | |
| `category` | STRING | For downstream RFM |

### 5. `support_tickets.parquet` → **external Parquet on GCS** · trust 4
| Column | Type | Notes |
| :--- | :--- | :--- |
| `record_id` | STRING | `SUP-xxxxxxxx` |
| `ticket_id` | STRING | |
| `contact_name` | STRING | |
| `contact_email` | STRING | Sometimes null |
| `body` | STRING | Free text. Contains incidental identifiers, the deceased/minor hints for case #11, and **exactly 3 prompt-injection attempts** |
| `created_at` | TIMESTAMP | |

### 6. `call_transcripts/*.txt` + `call_transcripts_manifest.csv` → **Object Table on GCS** · trust 4
Manifest columns: `record_id` (`CALL-xxxxxxxx`), `uri`, `call_id`, `agent_id`, `call_ts`.
Transcript bodies carry the *"my wife's account"* signal for hard case #10.

### 7. `third_party_enrich.jsonl` → **external JSONL on GCS** · trust 2
Deliberately dirty: stale addresses and some genuinely wrong attributions.
Fields: `record_id` (`ENR-xxxxxxxx`), `name`, `address`, `postcode`, `email`, `vendor`, `vendor_confidence` (FLOAT).

---

## Consent

### 8. `consent_events.csv` → **managed table**, append-only
| Column | Type | Notes |
| :--- | :--- | :--- |
| `consent_id` | STRING | |
| `record_id` | STRING | **Source-bound** — consent attaches to the record, never the person |
| `channel` | STRING | `EMAIL` \| `SMS` \| `POST` \| `PHONE` |
| `status` | STRING | `GRANTED` \| `WITHDRAWN` \| `NOT_GIVEN` |
| `purpose` | STRING | `MARKETING` \| `SERVICE` |
| `captured_at` | TIMESTAMP | |

Hard case #9 requires at least one person whose records carry `GRANTED`, `NOT_GIVEN` and
`WITHDRAWN` for the same channel across three different sources.

---

## Ground truth — pipeline must never read this

Lands in a **separate dataset** (`<prefix>_truth`), not the working dataset.

### 9. `truth/person_truth.csv`
| Column | Type | Notes |
| :--- | :--- | :--- |
| `record_id` | STRING | |
| `true_person_id` | STRING | `P-nnnnnn` |
| `true_household_id` | STRING | Nullable |
| `case_type` | STRING | `NORMAL`, `SINGLETON`, or one of the 15 hard-case codes |
| `notes` | STRING | Human-readable explanation of the trap |

### 10. `truth/case_catalogue.csv`
| Column | Type |
| :--- | :--- |
| `case_type` | STRING |
| `description` | STRING |
| `expected_outcome` | STRING (`MERGE` \| `DO_NOT_MERGE` \| `MERGE_WITH_FLAG` \| `BREAK_CHAIN`) |
| `deck_slide` | INT64 |
| `target_instances` | INT64 |

**Hard-case codes (15).** The original twelve:
`HOUSEHOLD`, `SIBLING_TRAP`, `MARRIED_NAME`, `ACCOUNT_ONLY`, `POSTCODE_NEAR_MISS`,
`TRANSLITERATION`, `SOLE_TRADER`, `SHARED_EMAIL`, `CONSENT_CONFLICT`, `UNSTRUCTURED_ONLY`,
`RISK_FLAG`, `OVERMERGE_BAIT`.

Plus three name-shape cases:

| Code | Expected outcome | What it tests |
| :--- | :--- | :--- |
| `DIACRITIC_VARIANT` | `MERGE` | The same person recorded with and without diacritics (`José Muñoz` / `Jose Munoz`, `Renée` / `Renee`, `Nguyễn` / `Nguyen`, `Łukasz` / `Lukasz`). Half the instances differ **only** by the diacritic and are solvable by correct Unicode normalisation alone; the other half combine the diacritic difference with a second divergence, or use a conventional transliteration that NFKD cannot recover (`Müller` / `Mueller`). A small number put the difference in the **address** rather than the name — as apostrophe, hyphen and `St`/`Saint` drift, because Australian place names rarely carry accents. The 50/50 split is deliberate and load-bearing. |
| `NAME_ORDER` | `MERGE` | Given and family name transposed between systems (`Chen Wei` / `Wei Chen`), sometimes with an adopted Western forename alongside (`Grace Chen`). |
| `NAME_ORDER_TRAP` | `DO_NOT_MERGE` | Two **different** people whose records look like a name transposition of each other but are not. The hard negative for `NAME_ORDER`. |

> [!IMPORTANT]
> `NAME_ORDER_TRAP` is a separate `case_type` rather than a flag on `NAME_ORDER` because
> `v_case_results` in `95_scorecard.sql` joins on `case_type` and compares the observed
> outcome against a single `expected_outcome` per case. One code carrying two outcomes
> would force a special case into the scorer.

### 11. `data/manifest.json`
Row counts per file, person count, per-`case_type` counts, and the generator seed.
`run.sh` validates actual loaded row counts against this and fails loudly on mismatch.

Also carries three namesake metrics:

| Field | Meaning |
| :--- | :--- |
| `incidental_name_collisions` | People sharing an exact full name with someone else. Expected and realistic. |
| `ambiguous_name_collisions` | The subset sharing a full name **and** a city **and** a birth year within 2. Should be `0`. |
| `name_separability_fallbacks` | Times the generator gave up trying to keep a namesake separable. Should be `0`. |

> [!IMPORTANT]
> **Namesake guarantee.** Untagged namesakes are deliberately kept *separable* — any two
> people sharing a full name differ on city and by at least 5 years of age. Namesakes that
> are genuinely indistinguishable would ask the pipeline a question the data cannot answer
> and would depress precision for reasons unrelated to the matching algorithm. Every
> deliberately hard identity collision is tagged with a `case_type`.

---

## Determinism

The generator takes `--seed` and must be fully reproducible. The seed is recorded in
`manifest.json` and printed in the scorecard, so any result can be regenerated exactly.
