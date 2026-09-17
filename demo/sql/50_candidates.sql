-- =====================================================================
-- 50 · Candidates
--
-- Three retrieval legs, then one scoring pass.
--
--   lexical   · deterministic keys from stage 40 — exact, cheap, brittle
--   semantic  · VECTOR_SEARCH over the embeddings — tolerant, fuzzy, blind
--               to alphanumeric identifiers
--   hybrid    · reciprocal rank fusion of the two
--
-- The claim the deck makes is that neither leg alone is adequate. Stage
-- 50e measures the overlap so the claim can be checked rather than
-- asserted, and stage 95 scores each leg against ground truth.
--
-- Nothing here decides a merge. This stage decides what is worth the cost
-- of deciding.
-- =====================================================================


-- ---------------------------------------------------------------------
-- 50a · Semantic retrieval
--
-- Every record is used as a probe against the whole corpus. top_k
-- includes the record's own perfect self-match, so the effective depth is
-- one less than configured.
--
-- COSINE because match_key strings vary wildly in length — a POS row is a
-- handful of tokens, a CRM row is a paragraph — and magnitude would
-- otherwise stand in for information content.
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.candidate_pairs_semantic`
CLUSTER BY record_id_a, record_id_b
AS
WITH knn AS (
  SELECT
    query.record_id AS probe_id,
    base.record_id  AS match_id,
    distance
  FROM VECTOR_SEARCH(
    TABLE `${CDP_PROJECT}.${CDP_DS}.party_vectors`, 'embedding',
    (SELECT record_id, embedding FROM `${CDP_PROJECT}.${CDP_DS}.party_vectors`),
    'embedding',
    top_k         => ${CDP_TOPK},
    distance_type => 'COSINE'
  )
  WHERE query.record_id != base.record_id
)
SELECT
  LEAST(probe_id, match_id)    AS record_id_a,
  GREATEST(probe_id, match_id) AS record_id_b,
  -- A pair can be retrieved from both directions with slightly different
  -- neighbour sets; keep the best observation of it.
  MIN(distance)                AS distance,
  1 - MIN(distance)            AS similarity,
  -- Retrieved from both directions is a mild positive signal: the pair is
  -- mutually near, not just near in one crowded neighbourhood.
  COUNT(*) = 2                 AS mutual
FROM knn
GROUP BY record_id_a, record_id_b;


-- ---------------------------------------------------------------------
-- 50b · Reciprocal rank fusion
--
-- RRF combines two ranked lists without needing their scores to be
-- comparable — which matters, because a BM25 score and a cosine distance
-- have no common unit and no stable way to normalise between corpora.
--
--   RRF(d) = Σ over legs of  1 / (k + rank_leg(d))
--
-- k = 60 is the value from the original Cormack et al. paper and the de
-- facto default. Its effect is to flatten the top of each list: with
-- k = 60, ranks 1 and 2 differ by about 1.6%, so a document has to be
-- consistently high across both legs to win, rather than spiking in one.
-- That is precisely the property we want here — a pair that only one leg
-- likes is exactly the pair a human should look at.
--
-- A pair missing from a leg contributes nothing from that leg, rather
-- than a penalty. Absence is not evidence against.
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.candidate_pairs_fused`
CLUSTER BY record_id_a, record_id_b
AS
WITH all_pairs AS (
  SELECT record_id_a, record_id_b FROM `${CDP_PROJECT}.${CDP_DS}.candidate_pairs_blocked`
  UNION DISTINCT
  SELECT record_id_a, record_id_b FROM `${CDP_PROJECT}.${CDP_DS}.candidate_pairs_semantic`
),
joined AS (
  SELECT
    p.record_id_a,
    p.record_id_b,
    l.block_strength,
    l.key_types,
    l.matched_keys,
    l.keys_shared,
    s.similarity,
    s.mutual,
    -- Tested on a payload column, not a join key: with an outer join the
    -- key is present on both sides by construction and would always look
    -- matched.
    l.block_strength IS NOT NULL AS found_lexical,
    s.similarity     IS NOT NULL AS found_semantic
  FROM all_pairs AS p
  LEFT JOIN `${CDP_PROJECT}.${CDP_DS}.candidate_pairs_blocked` AS l
    ON l.record_id_a = p.record_id_a AND l.record_id_b = p.record_id_b
  LEFT JOIN `${CDP_PROJECT}.${CDP_DS}.candidate_pairs_semantic` AS s
    ON s.record_id_a = p.record_id_a AND s.record_id_b = p.record_id_b
),
-- Ranks are computed per probe record over both directions of each pair,
-- so that a record's neighbourhood rank is invariant to alphabetical ID prefix order.
directed_ranks AS (
  SELECT
    record_id_a, record_id_b,
    IF(found_lexical,
       RANK() OVER (PARTITION BY probe ORDER BY block_strength DESC, keys_shared DESC),
       NULL) AS dir_rank_lexical,
    IF(found_semantic,
       RANK() OVER (PARTITION BY probe ORDER BY similarity DESC),
       NULL) AS dir_rank_semantic
  FROM (
    SELECT record_id_a AS probe, record_id_a, record_id_b, found_lexical, found_semantic, block_strength, keys_shared, similarity FROM joined
    UNION ALL
    SELECT record_id_b AS probe, record_id_a, record_id_b, found_lexical, found_semantic, block_strength, keys_shared, similarity FROM joined
  )
),
pair_ranks AS (
  SELECT
    record_id_a, record_id_b,
    MIN(dir_rank_lexical)  AS rank_lexical,
    MIN(dir_rank_semantic) AS rank_semantic
  FROM directed_ranks
  GROUP BY record_id_a, record_id_b
),
ranked AS (
  SELECT
    j.*,
    pr.rank_lexical,
    pr.rank_semantic
  FROM joined AS j
  JOIN pair_ranks AS pr USING (record_id_a, record_id_b)
)
SELECT
  *,
  IFNULL(SAFE_DIVIDE(1, 60 + rank_lexical),  0)
    + IFNULL(SAFE_DIVIDE(1, 60 + rank_semantic), 0) AS rrf_score,
  CASE
    WHEN found_lexical AND found_semantic THEN 'BOTH'
    WHEN found_lexical                    THEN 'LEXICAL_ONLY'
    ELSE                                       'SEMANTIC_ONLY'
  END                                              AS retrieved_by
FROM ranked;


-- ---------------------------------------------------------------------
-- 50c · Pair features
--
-- Explicit, inspectable comparisons. Every one of these is something a
-- data steward would look at by eye, and every one of them ends up in the
-- adjudicator prompt as evidence.
--
-- The weights below are PRIORS, not measurements. They encode an ordering
-- of evidence that any practitioner would recognise — a shared account
-- number outweighs a shared postcode — but the specific numbers are not
-- claimed to be optimal. Stage 95 measures what they actually produce
-- against ground truth; that measurement, not this table, is the result.
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.pair_features`
CLUSTER BY record_id_a, record_id_b
AS
WITH total_records AS (
  SELECT GREATEST(1, COUNT(*)) AS n FROM `${CDP_PROJECT}.${CDP_DS}.party_search`
),
surname_idf AS (
  SELECT
    surname_norm,
    -- Bounded Fellegi-Sunter / IDF weight in [0.50, 1.80]: high-frequency
    -- surnames (e.g. SMITH) contribute less log-odds evidence than rare ones.
    LEAST(1.80, GREATEST(0.50, SAFE_DIVIDE(LN(SAFE_DIVIDE(t.n, COUNT(*))), 5.0))) AS sur_idf_weight
  FROM `${CDP_PROJECT}.${CDP_DS}.party_search`, total_records AS t
  WHERE surname_norm IS NOT NULL AND surname_norm != ''
  GROUP BY surname_norm, t.n
),
postcode_idf AS (
  SELECT
    postcode_norm,
    -- Bounded IDF weight in [0.60, 1.50] discounting dense urban postcodes.
    LEAST(1.50, GREATEST(0.60, SAFE_DIVIDE(LN(SAFE_DIVIDE(t.n, COUNT(*))), 4.5))) AS pc_idf_weight
  FROM `${CDP_PROJECT}.${CDP_DS}.party_search`, total_records AS t
  WHERE postcode_norm IS NOT NULL AND postcode_norm != ''
  GROUP BY postcode_norm, t.n
),
pairs AS (
  SELECT
    f.*,
    a.source_system   AS a_source,  b.source_system   AS b_source,
    a.source_trust    AS a_trust,   b.source_trust    AS b_trust,
    a.name_norm       AS a_name,    b.name_norm       AS b_name,
    a.forename_norm   AS a_fore,    b.forename_norm   AS b_fore,
    a.surname_norm    AS a_sur,     b.surname_norm    AS b_sur,
    a.address_norm    AS a_addr,    b.address_norm    AS b_addr,
    a.postcode_norm   AS a_pc,      b.postcode_norm   AS b_pc,
    a.postcode_out    AS a_pcout,   b.postcode_out    AS b_pcout,
    a.email_norm      AS a_email,   b.email_norm      AS b_email,
    a.phone_e164      AS a_phone,   b.phone_e164      AS b_phone,
    a.dob             AS a_dob,     b.dob             AS b_dob,
    a.account_number  AS a_acct,    b.account_number  AS b_acct,
    a.identity_strength AS a_strength, b.identity_strength AS b_strength,
    a.match_key       AS a_match_key, b.match_key     AS b_match_key,
    IFNULL(si.sur_idf_weight, 1.0) AS surname_idf_weight,
    IFNULL(pi.pc_idf_weight,  1.0) AS postcode_idf_weight
  FROM `${CDP_PROJECT}.${CDP_DS}.candidate_pairs_fused` AS f
  JOIN `${CDP_PROJECT}.${CDP_DS}.party_search` AS a ON a.record_id = f.record_id_a
  JOIN `${CDP_PROJECT}.${CDP_DS}.party_search` AS b ON b.record_id = f.record_id_b
  LEFT JOIN surname_idf  AS si ON si.surname_norm  = a.surname_norm
  LEFT JOIN postcode_idf AS pi ON pi.postcode_norm = a.postcode_norm
),
featured AS (
  SELECT
    p.*,
    (a_acct  IS NOT NULL AND a_acct  = b_acct)  AS acct_match,
    (a_email IS NOT NULL AND a_email = b_email) AS email_match,
    (a_phone IS NOT NULL AND a_phone = b_phone) AS phone_match,
    (a_dob   IS NOT NULL AND a_dob   = b_dob)   AS dob_match,
    -- The single most important negative feature in the system. Two
    -- records with incompatible dates of birth are two people, whatever
    -- else they share. This is what breaks the over-merge chains.
    (a_dob IS NOT NULL AND b_dob IS NOT NULL AND a_dob != b_dob) AS dob_conflict,
    (a_pc    IS NOT NULL AND a_pc    = b_pc)    AS postcode_match,
    (a_pcout IS NOT NULL AND a_pcout = b_pcout) AS district_match,
    (a_sur   IS NOT NULL AND a_sur   = b_sur)   AS surname_match,
    (a_fore  IS NOT NULL AND a_fore  = b_fore)  AS forename_match,
    (a_addr  IS NOT NULL AND a_addr  = b_addr)  AS address_exact,

    -- Normalised edit distance. Capped, because beyond a few edits the
    -- exact value tells you nothing except "different".
    SAFE_DIVIDE(
      GREATEST(LENGTH(IFNULL(a_name, '')), LENGTH(IFNULL(b_name, '')))
        - EDIT_DISTANCE(IFNULL(a_name, ''), IFNULL(b_name, ''), max_distance => 12),
      GREATEST(LENGTH(IFNULL(a_name, '')), LENGTH(IFNULL(b_name, '')))
    ) AS name_similarity,

    SAFE_DIVIDE(
      GREATEST(LENGTH(IFNULL(a_addr, '')), LENGTH(IFNULL(b_addr, '')))
        - EDIT_DISTANCE(IFNULL(a_addr, ''), IFNULL(b_addr, ''), max_distance => 20),
      GREATEST(LENGTH(IFNULL(a_addr, '')), LENGTH(IFNULL(b_addr, '')))
    ) AS address_similarity
  FROM pairs AS p
),
derived AS (
  SELECT
    f.*,
    -- How many hard identifiers agree. Two independent strong identifiers
    -- is the bar for merging without asking anyone — it is roughly what a
    -- steward would accept without hesitating.
    (  IF(acct_match,  1, 0)
     + IF(email_match, 1, 0)
     + IF(phone_match, 1, 0)
     + IF(dob_match,   1, 0)) AS strong_signals,

    -- Two known, genuinely different forenames. This is the household and
    -- shared-email signature: everything else about the pair agrees,
    -- because they live together, and only the given name says they are
    -- two people.
    --
    -- The name-similarity escape hatch matters: Robert/Bob and
    -- Mohammed/Muhammad must NOT be treated as conflicting. A pair that
    -- trips this test is never auto-matched, but it is not rejected
    -- either — it is exactly the kind of thing the adjudicator exists for.
    (a_fore IS NOT NULL AND b_fore IS NOT NULL
     AND a_fore != b_fore
     AND IFNULL(name_similarity, 0) < 0.60) AS forename_conflict,

    -- Mutually near, and near the top of each other's neighbour list.
    -- A relative test rather than an absolute cosine threshold: on short
    -- identity strings almost everything scores highly in absolute terms,
    -- so absolute cutoffs are close to meaningless.
    (IFNULL(mutual, FALSE)
     AND IFNULL(rank_semantic, 999) <= 3
     AND IFNULL(similarity, 0) >= 0.85) AS semantic_strong
  FROM featured AS f
),
scored AS (
  SELECT
    d.*,
    -- Rule score in [0, 1]. Additive evidence weighted by Fellegi-Sunter
    -- IDF frequency priors for surname and postcode, plus explicit penalty.
    LEAST(1.0, GREATEST(0.0,
        IF(acct_match,      0.50, 0.0)
      + IF(email_match,     0.45, 0.0)
      + IF(phone_match,     0.35, 0.0)
      + IF(dob_match,       0.30, 0.0)
      + IF(postcode_match,  0.12 * postcode_idf_weight, 0.0)
      + IF(address_exact,   0.15, 0.0)
      + IF(surname_match,   0.08 * surname_idf_weight,  0.0)
      + IF(forename_match,  0.08, 0.0)
      + 0.15 * IFNULL(name_similarity, 0.0)
      - IF(dob_conflict,    0.50, 0.0)
    )) AS rule_score
  FROM derived AS d
)
SELECT
  s.*,
  -- Semantic similarity can raise a score and can never lower one.
  --
  -- The blend alone would punish exactly the cases the embedding exists
  -- to catch: a married name plus a house move has a matching date of
  -- birth and mobile number but very little textual overlap, and
  -- averaging in a mediocre cosine would drag a near-certain match below
  -- the threshold. Absence of semantic similarity is not evidence
  -- against.
  LEAST(1.0, GREATEST(
    rule_score,
    0.65 * rule_score + 0.35 * IFNULL(similarity, 0.0)
  )) AS combined_score
FROM scored AS s;


-- ---------------------------------------------------------------------
-- 50d · Tiering
--
-- Three outcomes, and the middle one is the expensive one:
--
--   AUTO_MATCH  cheap, deterministic, no LLM involved
--   GREY_ZONE   sent to the adjudicator in stage 60
--   REJECT      discarded, cheaply
--
-- Tiering is driven by ordered RULES, not by the score alone, and the
-- score is used to order within a tier. That is a deliberate choice. A
-- single blended threshold cannot express "a date-of-birth conflict is
-- disqualifying however good everything else looks", and every attempt to
-- encode that by tuning weights produces a number nobody can defend in a
-- review.
--
-- The rails, in order, and why each exists:
--
--   1  A date-of-birth conflict with nothing to explain it is two people.
--      Reject. This is the sibling, household and near-miss defence.
--   2  A date-of-birth conflict alongside a shared account number is a
--      genuine contradiction — a shared card, or bad data. It is not ours
--      to resolve silently, so it goes to the adjudicator.
--   3  A shared loyalty account number, with forenames that agree, is
--      about as good as evidence gets short of a national identifier.
--   4  Two independent strong identifiers agreeing is the bar a steward
--      would accept without hesitating.
--   5  A record carrying almost no identity — a POS row is a surname, an
--      initial and half a postcode — can never auto-match on fuzzy
--      evidence. It needs a hard key or it needs a human.
--   6  Otherwise the score may carry it, but never past a forename
--      conflict.
--   7  Any single strong identifier is worth a question, even if the
--      score is low.
--   8  A mutual, top-ranked semantic neighbour is worth a question too.
--      This is the rail that lets the embedding earn its place: a
--      transliterated name with no shared identifiers reaches the
--      adjudicator through here and nowhere else.
--
-- Over-merging is categorically worse than under-merging throughout.
-- Merging two real people is a privacy incident — one customer can see
-- another's orders, addresses and history. Failing to merge is a
-- data-quality ticket. The rails are asymmetric on purpose.
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE `${CDP_PROJECT}.${CDP_DS}.pair_tiers`
CLUSTER BY tier, record_id_a
AS
SELECT
  f.*,
  CASE
    WHEN dob_conflict AND NOT acct_match                            THEN 'REJECT'
    WHEN dob_conflict                                               THEN 'GREY_ZONE'
    WHEN acct_match AND NOT forename_conflict                       THEN 'AUTO_MATCH'
    WHEN strong_signals >= 2 AND NOT forename_conflict              THEN 'AUTO_MATCH'
    -- Rails 5 and 7 each divert to the adjudicator with no score floor at
    -- all. Measured against ground truth on the first real run, that put
    -- 1,871,745 pairs in the grey zone: 1,097,960 from rail 5 at an average
    -- combined_score of 0.054, and 773,785 from rail 7. "It needs a human"
    -- has to mean there is something for a human to look at; at that volume
    -- it is not a review queue, it is a bill.
    --
    -- Both now carry a floor, chosen from a sweep against ground truth
    -- rather than picked. The guard each rail exists for is unchanged: a
    -- zero-identity pair still cannot reach the AUTO_MATCH rail below, and
    -- semantic_strong still always earns a look.
    --
    --   rail 5 @ 0.15 -> removes 1,032,804 junk pairs, loses 14 true
    --   rail 7 @ 0.40 -> removes   315,124 junk pairs, loses  2 true
    --
    -- 16 true pairs out of 18,774 (0.085%) for a 71% smaller grey zone.
    -- Tighter floors cost recall fast: rail 5 at 0.20 loses 72 more true
    -- pairs to remove only 4,178 more junk.
    -- NO NAME SIGNAL, NO CANDIDATE — at any score.
    --
    -- The score floor below was the wrong instrument on its own. combined_score
    -- blends name, address, semantic and rule evidence, so a pair clears it on
    -- address or semantic proximity while the names share nothing. Measured:
    -- 15,859 grey-zone pairs (19%) had neither forename nor surname matching,
    -- 14,500 of them from this rail, and only 65 were true. The adjudicator was
    -- being asked to compare "Luis Manwlo" with "Layla Hancock" because they
    -- shared a postcode. That is not evidence of a person, and it produces
    -- rationales that make the whole thing look unserious.
    --
    -- A surname change on marriage still leaves a forename signal, so
    -- MARRIED_NAME survives this. What gets cut is BOTH names differing with no
    -- strong identifier to carry the pair.
    --
    -- Threshold swept against ground truth, not picked: 0.70 removes 13,036
    -- junk pairs for 66 true ones. 0.65 keeps 583 more junk to save 7 true;
    -- past 0.70 the trade turns sharply (0.65->0.70 cuts 374 junk per true lost).
    WHEN (a_strength = 0 OR b_strength = 0)
         AND NOT (email_match OR phone_match OR acct_match)
         AND NOT semantic_strong
         AND NOT (surname_match OR forename_match
                  OR IFNULL(name_similarity, 0) >= ${CDP_MIN_NAME_SIMILARITY})
                                                                    THEN 'REJECT'
    WHEN (a_strength = 0 OR b_strength = 0)
         AND NOT (email_match OR phone_match)
         AND NOT semantic_strong
         AND combined_score < ${CDP_TAU_LOW_IDENTITY}               THEN 'REJECT'
    WHEN (a_strength = 0 OR b_strength = 0)
         AND NOT (email_match OR phone_match)                       THEN 'GREY_ZONE'
    WHEN combined_score >= ${CDP_TAU_HI} AND NOT forename_conflict  THEN 'AUTO_MATCH'
    WHEN strong_signals >= 1 AND NOT semantic_strong
         AND combined_score < ${CDP_TAU_SINGLE_SIGNAL}              THEN 'REJECT'
    WHEN strong_signals >= 1                                        THEN 'GREY_ZONE'
    WHEN semantic_strong                                            THEN 'GREY_ZONE'
    WHEN combined_score >= ${CDP_TAU_LO}                            THEN 'GREY_ZONE'
    ELSE                                                                 'REJECT'
  END AS tier,
  CASE
    WHEN dob_conflict AND NOT acct_match
      THEN 'Incompatible dates of birth and nothing to explain it.'
    WHEN dob_conflict
      THEN 'Shared account number but incompatible dates of birth — a genuine contradiction, not ours to resolve silently.'
    WHEN acct_match AND NOT forename_conflict
      THEN 'Shared loyalty account number, forenames consistent, nothing contradicting.'
    WHEN strong_signals >= 2 AND NOT forename_conflict
      THEN 'Two independent strong identifiers agree with no contradicting evidence.'
    WHEN (a_strength = 0 OR b_strength = 0)
         AND NOT (email_match OR phone_match OR acct_match)
         AND NOT semantic_strong
         AND NOT (surname_match OR forename_match
                  OR IFNULL(name_similarity, 0) >= ${CDP_MIN_NAME_SIMILARITY})
      THEN 'Neither forename nor surname matches and no strong identifier connects them — not a candidate at any score.'
    WHEN (a_strength = 0 OR b_strength = 0) AND NOT (email_match OR phone_match)
         AND NOT semantic_strong AND combined_score < ${CDP_TAU_LOW_IDENTITY}
      THEN 'One side carries almost no identity and the score is below the low-identity floor — nothing here for a human to adjudicate.'
    WHEN (a_strength = 0 OR b_strength = 0) AND NOT (email_match OR phone_match)
      THEN 'One side carries almost no identity; fuzzy similarity alone is not sufficient.'
    WHEN combined_score >= ${CDP_TAU_HI} AND NOT forename_conflict
      THEN 'Score above the auto-match threshold with no contradicting evidence.'
    WHEN strong_signals >= 1 AND NOT semantic_strong
         AND combined_score < ${CDP_TAU_SINGLE_SIGNAL}
      THEN 'One strong identifier agrees but everything else disagrees — below the single-signal floor.'
    WHEN strong_signals >= 1
      THEN 'One strong identifier agrees, but not enough to act on alone.'
    WHEN semantic_strong
      THEN 'No shared identifiers, but a mutual top-ranked semantic neighbour — the case the embedding exists for.'
    WHEN combined_score >= ${CDP_TAU_LO}
      THEN 'Plausible but not conclusive.'
    ELSE 'Below the rejection threshold.'
  END AS tier_reason
FROM `${CDP_PROJECT}.${CDP_DS}.pair_features` AS f;


-- ---------------------------------------------------------------------
-- 50e · The funnel
--
-- The shape of this — a large base, a thin middle, a small top — is the
-- entire cost argument. Only the grey zone pays for an LLM call.
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW `${CDP_PROJECT}.${CDP_DS}.v_candidate_funnel` AS
SELECT
  tier,
  COUNT(*)                                                  AS pairs,
  ROUND(100 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)          AS pct,
  ROUND(MIN(combined_score), 3)                             AS min_score,
  ROUND(AVG(combined_score), 3)                             AS avg_score,
  ROUND(MAX(combined_score), 3)                             AS max_score,
  COUNTIF(retrieved_by = 'SEMANTIC_ONLY')                   AS semantic_only,
  COUNTIF(retrieved_by = 'LEXICAL_ONLY')                    AS lexical_only,
  COUNTIF(retrieved_by = 'BOTH')                            AS both
FROM `${CDP_PROJECT}.${CDP_DS}.pair_tiers`
GROUP BY tier
ORDER BY CASE tier WHEN 'AUTO_MATCH' THEN 1 WHEN 'GREY_ZONE' THEN 2 ELSE 3 END;


-- ---------------------------------------------------------------------
-- 50f · What each leg found on its own
--
-- Truth-free, so it can be shown before the scorecard. Two numbers
-- matter:
--
--   LEXICAL_ONLY pairs that scored well — these are the ACC-48213 cases.
--     An embedding-only architecture never sees them.
--   SEMANTIC_ONLY pairs that scored well — nicknames, transliterations,
--     married names. A rules-only architecture never sees them.
--
-- If either column is near zero, the hybrid argument is weaker than the
-- deck claims and the deck should be changed, not the query.
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW `${CDP_PROJECT}.${CDP_DS}.v_retrieval_legs` AS
SELECT
  retrieved_by,
  COUNT(*)                                      AS pairs_retrieved,
  COUNTIF(tier = 'AUTO_MATCH')                  AS became_auto_match,
  COUNTIF(tier = 'GREY_ZONE')                   AS became_grey_zone,
  COUNTIF(tier = 'REJECT')                      AS became_reject,
  ROUND(AVG(combined_score), 3)                 AS avg_score,
  ROUND(AVG(rrf_score), 5)                      AS avg_rrf,
  COUNTIF(acct_match)                           AS with_shared_account,
  COUNTIF(NOT surname_match AND tier != 'REJECT') AS surname_differs_but_kept
FROM `${CDP_PROJECT}.${CDP_DS}.pair_tiers`
GROUP BY retrieved_by
ORDER BY pairs_retrieved DESC;
