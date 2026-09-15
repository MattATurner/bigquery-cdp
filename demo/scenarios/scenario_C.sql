-- =====================================================================
-- C · Merging people is not merging permissions
--
-- One customer. Three systems. Online they opted in to email marketing.
-- In store they explicitly opted out. In the app they were never asked.
--
-- Merge the records naively and the profile inherits the opt-in, because
-- somewhere in the customer's history there is a GRANTED. The customer
-- then receives an email they explicitly said no to — from the same
-- organisation they said it to.
--
-- The intersection rule says permission exists only where every
-- contributing record agrees, and an explicit withdrawal is absolute.
--
-- The last column is the one for the CMO: how much audience the correct
-- rule costs. It is also, read the other way, how many unlawful contacts
-- the convenient rule would have sent.
-- =====================================================================

SELECT
  channel,
  purpose,
  people_with_a_stated_preference,
  audience_union_rule                 AS audience_if_we_merge_permissions,
  audience_intersection_rule          AS audience_under_the_intersection_rule,
  contacts_the_union_rule_would_add   AS contacts_avoided,
  of_which_explicitly_withdrawn       AS of_which_had_explicitly_said_no,
  suppressed_for_risk,
  pct_of_union_audience_unlawful      AS pct_of_the_easy_audience_that_was_unlawful
FROM `${CDP_PROJECT}.${CDP_DS}.v_consent_impact`
ORDER BY contacts_avoided DESC;
