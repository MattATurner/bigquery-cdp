-- =====================================================================
-- 00 · Setup
--
-- Creates the working dataset and the separate ground-truth dataset.
--
-- The separation is deliberate and load-bearing: the pipeline must never
-- read truth. Keeping it in its own dataset makes an accidental join
-- visible in review rather than silently inflating the score.
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS `${CDP_PROJECT}.${CDP_DS}`
OPTIONS (
  location    = '${CDP_LOCATION}',
  description = 'Composable CDP demo — working dataset. Synthetic data only.'
);

CREATE SCHEMA IF NOT EXISTS `${CDP_PROJECT}.${CDP_DS_TRUTH}`
OPTIONS (
  location    = '${CDP_LOCATION}',
  description = 'GROUND TRUTH — scoring only. The pipeline must never read this dataset. '
             || 'Any pipeline stage that joins to it is a bug.'
);

-- ---------------------------------------------------------------------
-- Normalisation helpers.
--
-- These establish a deterministic *representation*. They deliberately do
-- NOT fold away human variation — no nickname expansion, no phonetic
-- collapsing. That signal is what the semantic search leg and the
-- adjudicator exist to interpret. Over-normalising here is the most
-- common way to silently destroy recall.
--
-- Locale: Australia. Postcodes, phone numbers and thoroughfare
-- abbreviations are all locale-specific. If this is re-pointed at another
-- market, these functions and nothing else are what needs to change:
-- norm_postcode, postcode_outward, norm_phone and norm_address. The
-- diacritic fold and the name/email keys are locale-neutral.
-- ---------------------------------------------------------------------

-- Diacritic folding, made explicit.
--
-- Australian source data carries accented Latin spellings from every
-- migration wave the country has had: José/Jose, Renée/Renee,
-- Müller/Mueller, Nguyễn/Nguyen, Łukasz/Lukasz. Source systems disagree
-- about them constantly — the same person is accented in one system,
-- stripped in another, and occasionally transliterated by hand in a third
-- that predates Unicode support.
--
-- The fold runs in three ordered steps and the order is load-bearing:
--
--   1. NORMALIZE(s, NFKD) decomposes a precomposed letter into its base
--      letter plus a combining mark, so 'é' becomes 'e' + U+0301.
--   2. The \p{Mn} regex class drops the combining marks, leaving the base
--      letter behind. 'Nguyễn' -> 'Nguyen'.
--   3. A small explicit table handles the characters NFKD does NOT
--      decompose, because they are single code points with no canonical
--      decomposition rather than base-plus-accent:
--
--          ł -> l   Ł -> L     ø -> o   Ø -> O     đ -> d   Đ -> D
--          ß -> ss  æ -> ae    Æ -> AE  œ -> oe    Œ -> OE
--
--      Step 3 is not optional. NFKD leaves 'Łukasz' completely untouched,
--      so without the table the stroked L survives, 'Łukasz' never folds
--      to 'Lukasz', and the half of the DIACRITIC_VARIANT hard case that
--      is supposed to be solvable by normalisation alone silently stops
--      being solvable. Note ß and æ/œ fold to TWO letters, which is why
--      this is a replacement table and not a character transliteration.
--
-- This table must stay byte-identical to the one in the generator's
-- Python fold. If the two drift, records that the generator considers a
-- matched pair stop matching here, and only the scorecard will notice.
--
-- The ORDER above is itself a bug fix. This function was once implemented
-- as a character *deletion* — strip anything non-ASCII — which DELETES
-- the letter rather than folding it: 'Tāmati' became 'Tmati' and 'José'
-- became 'Jos'. Normalising to NFKD first folds the accent and keeps the
-- letter. Do not reorder these steps; the deletion form is easy to
-- reintroduce and fails silently.
--
-- This is called out as its own function so the behaviour is testable and
-- named, rather than being an undocumented side effect of NFKD somewhere
-- in a larger expression that someone could optimise away.
--
-- Note this is a lossy fold applied to the MATCH key only. Display values
-- in golden_person retain their accents; spelling someone's name back to
-- them incorrectly is not an acceptable outcome of deduplicating them.
CREATE OR REPLACE FUNCTION `${CDP_PROJECT}.${CDP_DS}.fold_diacritics`(s STRING) AS (
  -- Step 3: the non-decomposable special cases, applied outermost.
  REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
  REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
    -- Steps 1 and 2: decompose, then drop the combining marks.
    REGEXP_REPLACE(NORMALIZE(IFNULL(s, ''), NFKD), r'\p{Mn}', '')
  , 'ł', 'l'), 'Ł', 'L')
  , 'ø', 'o'), 'Ø', 'O')
  , 'đ', 'd'), 'Đ', 'D')
  , 'ß', 'ss')
  , 'æ', 'ae'), 'Æ', 'AE')
  , 'œ', 'oe'), 'Œ', 'OE')
);

-- Name match key: fold diacritics, uppercase, keep only A-Z, 0-9 and
-- single spaces.
--
-- The fold runs BEFORE the character-class filter on purpose. This
-- function used to call NORMALIZE_AND_CASEFOLD directly, which decomposes
-- the letter but leaves the combining mark standing in the string, so the
-- [^A-Z0-9 ] filter turned every mark into a SPACE and split the word:
-- 'Müller' normalised to 'MU LLER' rather than 'MULLER', and then failed
-- to match the 'Mueller' spelling it was supposed to catch. Routing
-- through fold_diacritics removes the marks before the filter ever sees
-- them, and picks up the ł/ø/đ/ß/æ/œ cases NFKD does not decompose.
CREATE OR REPLACE FUNCTION `${CDP_PROJECT}.${CDP_DS}.norm_name`(s STRING) AS (
  NULLIF(
    TRIM(REGEXP_REPLACE(
      REGEXP_REPLACE(
        UPPER(`${CDP_PROJECT}.${CDP_DS}.fold_diacritics`(IFNULL(s, ''))),
        r'[^A-Z0-9 ]', ' '),
      r'\s+', ' ')),
    '')
);

-- Lowercase and strip +tags. Deliberately NOT dot-folding: that is only
-- semantically correct for some providers, and applying it universally
-- merges genuinely distinct addresses.
-- A model instructed to "return NULL for anything not stated" returns the
-- WORD. Measured on the first real run against BigQuery: 773 records arrived
-- carrying account_number 'null' or 'NULL', and 365 carrying email 'null' --
-- every one of them from the two AI-extracted sources (SUPPORT, CALL) and
-- none from the five structured ones.
--
-- Left alone those are shared identifiers. acct_match fires between any two
-- of them, so 660 unrelated people held the same "account number" and the
-- pipeline was correct to think they matched. It is the single largest
-- manufactured false-positive source in the build.
--
-- Strip at the boundary rather than relying on the prompt. The prompt wording
-- is also fixed, but wording cannot be guaranteed and this cannot be bypassed
-- by a model having a bad day. Applied to every AI-extracted string field in
-- stage 20 before it reaches a comparison.
CREATE OR REPLACE FUNCTION `${CDP_PROJECT}.${CDP_DS}.strip_sentinel`(s STRING) AS (
  NULLIF(
    CASE
      WHEN LOWER(TRIM(IFNULL(s, ''))) IN (
             'null', 'none', 'nil', 'n/a', 'na', 'unknown', 'undefined',
             'not stated', 'not provided', 'not specified', 'unspecified',
             'not available', 'no value', '-', '--', '?'
           )
      THEN ''
      ELSE TRIM(IFNULL(s, ''))
    END,
  '')
);

CREATE OR REPLACE FUNCTION `${CDP_PROJECT}.${CDP_DS}.norm_email`(s STRING) AS (
  NULLIF(REGEXP_REPLACE(LOWER(TRIM(IFNULL(s, ''))), r'\+[^@]*@', '@'), '')
);

-- Australian postcode: exactly four digits, no letters, no inward/outward
-- split. Anything that is not four digits after stripping punctuation is
-- returned as NULL rather than guessed at — a malformed postcode should
-- fail the completeness check loudly, not become a bad blocking key
-- quietly.
--
-- The one exception is the leading-zero repair, and it exists because of a
-- real and deliberate data-quality trap in the loyalty source. Northern
-- Territory postcodes are 08xx (Darwin 0800, 0810, 0812, 0820, 0828,
-- 0832). The loyalty system stores postcodes as INTEGERS, so the leading
-- zero is dropped on the way in and 0812 arrives here as 812. Left alone
-- that fails the four-digit test, returns NULL, and every NT member
-- silently loses their postcode — which would quietly delete a hard case
-- the pipeline is supposed to demonstrate it can handle.
--
-- The repair is deliberately narrow: only a three-digit value in the 8xx
-- range is padded, because NT is the only state whose postcodes carry a
-- leading zero (ACT is 26xx, NSW is 2xxx and up). Any other short value is
-- still malformed and still returns NULL, so the loud-failure rule above
-- survives intact for genuine junk.
CREATE OR REPLACE FUNCTION `${CDP_PROJECT}.${CDP_DS}.norm_postcode`(s STRING) AS (
  LPAD(
    REGEXP_EXTRACT(
      REGEXP_REPLACE(IFNULL(s, ''), r'\D', ''),
      r'^(\d{4}|8\d{2})$'),
    4, '0')
);

-- Coarse geographic prefix, used as a blocking key.
--
-- The name is retained from the UK build (where it meant the outward code)
-- so downstream callers do not change, but the semantics are different.
-- In Australia the leading digits are genuinely meaningful rather than an
-- arbitrary slice: the FIRST digit is the state or territory —
--
--     0 NT      2 NSW/ACT    3 VIC    4 QLD
--     5 SA      6 WA         7 TAS
--
-- — and the first TWO digits narrow that to a coarse regional bucket
-- within the state (20xx/21xx inner Sydney, 30xx/31xx inner Melbourne,
-- 40xx Brisbane, 50xx Adelaide, 60xx Perth, 70xx Hobart, 08xx Darwin,
-- 26xx Canberra).
--
-- Meaningful is not the same as identifying. Two digits is a deliberately
-- blunt instrument and it over-collects heavily in Sydney and Melbourne,
-- which is why it carries the lowest block_strength in stage 40 and never
-- contributes enough on its own to reach AUTO_MATCH.
--
-- It is computed from the NORMALISED postcode, not the raw string, so the
-- NT leading-zero repair is applied first. This matters: a loyalty record
-- arriving as the integer 812 would otherwise bucket as '81' while the
-- same household's CRM record bucketed as '08', and the two would never be
-- compared. The COALESCE keeps the old raw-prefix behaviour for values too
-- malformed to normalise, so no blocking key that exists today is lost.
CREATE OR REPLACE FUNCTION `${CDP_PROJECT}.${CDP_DS}.postcode_outward`(s STRING) AS (
  COALESCE(
    SUBSTR(`${CDP_PROJECT}.${CDP_DS}.norm_postcode`(s), 1, 2),
    REGEXP_EXTRACT(REGEXP_REPLACE(IFNULL(s, ''), r'\D', ''), r'^(\d{2})')
  )
);

-- Australian mobile/landline to E.164 (+61). A production build should use
-- a proper library via a remote function; digit-stripping is sufficient for
-- a demo with a single known country, and the limitation is noted in the
-- README.
--
-- The leading-zero rule is the one that actually matters here. Australian
-- numbers carry a trunk 0 domestically — 0412 345 678 for a mobile,
-- (08) 9456 7890 for a landline — and the trunk 0 is DROPPED, not
-- retained, when the +61 country code is applied. Source systems get this
-- wrong in both directions, so a number arriving as '+61 0412...' is
-- repaired rather than trusted: '+610412...' is always wrong and is the
-- specific bug class this function exists to absorb.
--
-- Worked examples. All three of the first three must land on the same
-- shape, and the fourth is the repair:
--
--     0412 345 678     ->  +61412345678
--     +61 412 345 678  ->  +61412345678
--     (08) 9456 7890   ->  +61894567890
--     +61 0412 345 678 ->  +61412345678   (trunk zero removed)
--
-- This rule must stay identical to the generator's Python phone
-- normalisation. A divergence does not raise an error, it just quietly
-- stops every phone-based match from firing.
--
-- Downstream note for stage 70: because the trunk zero is dropped, an
-- Australian mobile always normalises to a string starting '+614', while
-- landlines start '+612', '+613', '+617' or '+618' (area codes 2, 3, 7
-- and 8). No landline area code is 4, so '+614' is an unambiguous mobile
-- test.
CREATE OR REPLACE FUNCTION `${CDP_PROJECT}.${CDP_DS}.norm_phone`(s STRING) AS (
  CASE
    WHEN s IS NULL OR TRIM(s) = '' THEN NULL
    -- Already international, but with the erroneous trunk zero retained.
    -- Drop the '0' sitting between the country code and the number.
    WHEN STARTS_WITH(REGEXP_REPLACE(IFNULL(s, ''), r'\D', ''), '610')
      THEN CONCAT('+61', SUBSTR(REGEXP_REPLACE(s, r'\D', ''), 4))
    -- Already international and correctly formed.
    WHEN STARTS_WITH(REGEXP_REPLACE(IFNULL(s, ''), r'\D', ''), '61')
      THEN CONCAT('+', REGEXP_REPLACE(s, r'\D', ''))
    -- Domestic form: drop the trunk zero.
    WHEN STARTS_WITH(REGEXP_REPLACE(IFNULL(s, ''), r'\D', ''), '0')
      THEN CONCAT('+61', SUBSTR(REGEXP_REPLACE(s, r'\D', ''), 2))
    ELSE CONCAT('+61', REGEXP_REPLACE(IFNULL(s, ''), r'\D', ''))
  END
);

-- Address standardisation: common Australian thoroughfare abbreviations,
-- plus the punctuation drift Australian address data actually exhibits.
--
-- NOTE the fold_diacritics call sits before the character-class filter,
-- and it has to. The filter turns anything outside [A-Z0-9 ] into a SPACE,
-- so a combining mark still standing at that point would split the word
-- instead of vanishing from it. Folding first means 'Nguyễn Street'
-- reduces to 'NGUYEN STREET' rather than 'NGUY N STREET'.
--
-- Australia has very few accented place names, so the DIACRITIC_VARIANT
-- hard case exercises this function through punctuation and spacing drift
-- rather than through accents. That is a deliberate substitution and it is
-- recorded in the case note: the address slice of that case does NOT test
-- accent folding, it tests the two things Australian address data really
-- does disagree about.
--
--   * Apostrophes are DELETED rather than replaced with a space, so
--     "O'Connor" and "OConnor" both reduce to 'OCONNOR'. The third
--     variant, "O Connor", deliberately still differs. Collapsing that
--     space as well would need a rule that also merges genuinely
--     unrelated addresses; narrowing a candidate rather than resolving it
--     outright is exactly what the graph and the adjudicator exist to
--     finish.
--
--   * 'St Kilda' and 'Saint Kilda' both reduce to 'SAINT KILDA'. The
--     Saint rewrite runs BEFORE the ST -> STREET expansion and only fires
--     where ST is followed by a space and another word, so
--     '12 Wattle St, Redfern' still expands to STREET — the comma is what
--     stops the Saint pattern matching, and it is still present at that
--     point in the chain. An address that drops the comma
--     ('12 Wattle St Redfern') is read as a Saint and normalises
--     'incorrectly', but it does so for every copy of that address, so
--     the key still agrees with itself. In a blocking key, determinism is
--     worth more than linguistic correctness.
--
-- State abbreviations (NSW, VIC, QLD, SA, WA, TAS, NT, ACT) and the
-- four-digit postcode are already bare alphanumerics and pass straight
-- through.
CREATE OR REPLACE FUNCTION `${CDP_PROJECT}.${CDP_DS}.norm_address`(s STRING) AS (
  NULLIF(TRIM(REGEXP_REPLACE(
    REGEXP_REPLACE(
      REGEXP_REPLACE(
        REGEXP_REPLACE(
          REGEXP_REPLACE(
            REGEXP_REPLACE(
              REGEXP_REPLACE(
                REGEXP_REPLACE(
                  REGEXP_REPLACE(
                    REGEXP_REPLACE(
                      REGEXP_REPLACE(
                        REGEXP_REPLACE(
                          REGEXP_REPLACE(
                            REGEXP_REPLACE(
                              REGEXP_REPLACE(
                                REGEXP_REPLACE(
                                  REGEXP_REPLACE(
                                    REGEXP_REPLACE(
                                      REGEXP_REPLACE(
                                        UPPER(`${CDP_PROJECT}.${CDP_DS}.fold_diacritics`(IFNULL(s, ''))),
                                        r"['\x{2019}\x{02BC}]", ''),
                                      r'\bST\.? ([A-Z])', r'SAINT \1'),
                                    r'[^A-Z0-9 ]', ' '),
                                  r'\bPDE\b',   'PARADE'),
                                r'\bCCT\b',     'CIRCUIT'),
                              r'\bCT\b',        'COURT'),
                            r'\bESP\b',         'ESPLANADE'),
                          r'\bBLVD\b',          'BOULEVARD'),
                        r'\bBVD\b',             'BOULEVARD'),
                      r'\bLN\b',                'LANE'),
                    r'\bAVE\b',                 'AVENUE'),
                  r'\bST\b',                    'STREET'),
                r'\bRD\b',                      'ROAD'),
              r'\bDR\b',                        'DRIVE'),
            r'\bCRES\b',                        'CRESCENT'),
          r'\bTCE\b',                           'TERRACE'),
        r'\bPL\b',                              'PLACE'),
      r'\bHWY\b',                               'HIGHWAY'),
    r'\s+', ' ')), '')
);

