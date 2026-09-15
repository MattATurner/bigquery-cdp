# Composable CDP — Plain-English Notes

A companion to the 17-slide deck. Written for people who will be in the room but do not work in data: marketing, compliance, finance, exec sponsors.

---

## If you remember three things

1. **The hard part of a customer data platform is working out which records are the same person.** Everything else is comparatively easy.
2. **We can now do that inside BigQuery, and the system writes down its reasoning** — in plain sentences a non-technical person can read and challenge.
3. **Merging customer records will probably shrink your contactable marketing audience.** That is the system working correctly. See the consent section below *before* you see the number.

---

## Slide-by-slide

| # | Slide | What it actually means |
| :-- | :--- | :--- |
| 1 | Title | We're proposing a customer data platform assembled from Google components, rather than bought as a single product. |
| 2 | Your customer isn't one customer | The same person shows up separately in your CRM, website, loyalty scheme and call recordings. Nobody has joined them up. The fourth example is a phone call where someone says "my wife's account" — a hint that two people might be involved, which almost no system today can pick up. |
| 3 | The shift | Traditional platforms copy all your customer data into their own system. We leave it where it is and work on it there. Fewer copies of sensitive data, fewer places it can leak. |
| 4 | **Thesis** | The core argument. Loading data, building segments and sending them to ad platforms are commodity capabilities everyone offers. Correctly identifying *who is who* is the bit that's genuinely hard, and it determines whether everything downstream is right or wrong. |
| 5 | Architecture | The five stages: get the data, tidy it up, work out who's who, build the profile, use it. Only stage three is interesting. Two bands underneath: one supplies *meaning* (agreed definitions), one enforces *rules* (who can see what). |
| 6 | Access | We read your data where it sits — including files in other clouds, PDFs and call recordings — instead of duplicating it. Framed as a security argument, not a cost one. |
| 7 | Process | AI reads unstructured things (call transcripts, emails, scanned documents) and pulls out useful facts — names, postcodes, account numbers, and whether the caller was actually the account holder. |
| 8 | Self-updating fingerprints | Every record gets a "meaning fingerprint" that lets us find similar records. It updates itself whenever the record changes. Previously this needed a separate specialist database and a team to keep it in sync. |
| 9 | Two kinds of search | Explained in detail below. Short version: you need both meaning-based *and* exact-match search, because postcodes and account numbers don't have "meaning". |
| 10 | The funnel | Roughly 85% of decisions are obvious and handled automatically. Only the genuinely ambiguous ~12% go to the AI. This is what keeps the cost sane. |
| 11 | **Explainability** ★ | The most important slide. Two records shown side by side, then the system's verdict — *and its reasoning, written out in English*. Read it aloud. Old systems can merge records but cannot tell you why. |
| 12 | Joining up the chains | If record A matches B, and B matches C, then A, B and C are all one person. Also catches contradictions and stops runaway merges. |
| 13 | The golden record | One profile per person, where every individual field remembers which source it came from. Nothing is deleted; you can always unpick it. |
| 14 | Identity + context | Knowing *who* the customer is isn't enough. You also need everyone to agree what "active customer" means. Otherwise an AI assistant gives you a confident answer using someone else's definition. |
| 15 | Activate | What you actually do with it: real-time personalisation, better ad match rates, dependable reporting, and asking questions of your customer base in plain language. |
| 16 | Governance | Who can see what, consent enforcement, and a permanent record of every merge decision the AI made. |
| 17 | Proof & next steps | A three-phase pilot. Deliberately contains almost no numbers — we measure on your data rather than quoting someone else's. |

---

## The six things people get stuck on

### 1. Merging marketing preferences and consent — read this one properly

This is the concept most likely to cause a real problem, and it is routinely got wrong.

Say Jane appears in three of your systems:

- **Online shop** — she ticked "yes, email me offers"
- **Loyalty scheme** — she left the box unticked
- **Call centre** — she explicitly said "stop emailing me"

You merge these into one Jane. **What are her email preferences now?**

The tempting answer — and the default behaviour in a lot of tooling — is to take the *union*: she said yes somewhere, so yes. **This is wrong, and it is the version that gets you fined.**

Consent is not a property of a person. It is a specific promise, made to a specific part of your business, for a specific purpose, at a specific moment. When you merge the records, the promises do not merge with them.

**Our rules:**

| Rule | Meaning |
| :--- | :--- |
| Consent never travels across a merge | A "yes" given to the online shop does not become a "yes" for the loyalty programme |
| Permission is the **intersection**, not the union | The merged profile can only be contacted in ways *every* contributing record allows |
| Explicit withdrawal always wins | "Stop emailing me" beats any earlier yes, regardless of dates |
| Every statement stays bound to its source | We can always show who agreed to what, when, and through which channel |

So in Jane's case: **no marketing email.** One system said no, one said stop. Two out of three saying yes would not change that.

> **Warn marketing before they see the number.** Doing this properly will usually *reduce* your contactable audience, sometimes noticeably. That is not the platform underperforming. It means your previous audience figure was overstated, and some of the people in it you did not actually have permission to contact. Better to find that out now than in a regulator's letter.

A related trap: **households.** Four people at one address is four consent positions, not one. If you merge a household into a single profile, you have just applied one person's preferences to three other adults.

---

### 2. "Why can't we just match on email address?"

Because:
- People have several email addresses, and change them
- Couples and families share one address
- The shop records `j.smith@`, the app records `jsmith+shopping@`, the call centre mistypes it
- Plenty of records have no email at all, especially in-store purchases
- Two different people genuinely can share a work address (`info@`, `accounts@`)

Email is a strong signal when it's present and verified. It is nowhere near sufficient on its own.

---

### 3. Two kinds of search, and why you need both

**Meaning-based search** understands that "Jon Smyth" and "Jonathan Smith" are probably the same person, and that "Bob" is short for "Robert". It works on similarity of meaning.

**Exact-match search** looks for literal strings: `2042`, `ACC-88231`.

The catch: meaning-based search is bad at things that have no meaning. A postcode isn't a concept — it's just characters. And yet a matching postcode is some of your *strongest* evidence.

So we run both. Meaning-based catches human variation; exact-match catches the identifiers. Neither is sufficient alone, which is why systems built on only one of them plateau at disappointing match rates.

Which raises the obvious question: **how do you combine two sets of results?**

---

### 3a. Reciprocal Rank Fusion — how the two searches get combined

You now have two lists of candidate matches, each in its own order of preference. You need one list.

**Why you can't just average the scores.** The two searches produce numbers that mean completely different things. Meaning-based search might say `0.82`; exact-match might say `14.3`. Those aren't on the same scale, they aren't even the same *kind* of measurement, and the ranges shift as your data changes. Averaging them is meaningless, and normalising them requires constant hand-tuning that breaks the moment your data does.

**The trick: throw the scores away and use only the positions.**

Reciprocal Rank Fusion ignores how confident each search claims to be, and looks only at *where* each record came in each list. A record scores points for placing well in a list, and the points from both lists are added together.

> **The judging analogy.** Two judges rank the same contestants — one scores technique, one scores artistry, on scales that can't be compared. You can't average their marks. But you *can* compare their orderings. Someone both judges placed near the top beats someone one judge loved and the other didn't rate at all. That's RRF.

**A worked example.** We're looking for matches to *Jonathan Smith, 12 Wattle Street, Newtown NSW 2042*.

*Meaning-based search returns:*
1. Jon Smyth, 12 Wattle St, Newtown, 2042
2. Johnathan Smithe, 40 Brunswick Street, Fitzroy VIC 3065
3. J. Smith, 12 Wattle Street, Newtown 2042

*Exact-match search (on the postcode) returns:*
1. J. Smith, 12 Wattle Street, Newtown 2042
2. Jon Smyth, 12 Wattle St, Newtown, 2042
3. Mai Nguyễn, 14 Wattle Street, Newtown, 2042

Each appearance is worth `1 ÷ (60 + position)`. Add up what each record earns:

| Record | Meaning-based | Exact-match | Total | Final |
| :--- | :--- | :--- | :--- | :--- |
| Jon Smyth | 1st → 0.0164 | 2nd → 0.0161 | **0.0325** | 1st |
| J. Smith | 3rd → 0.0159 | 1st → 0.0164 | **0.0323** | 2nd |
| Johnathan Smithe | 2nd → 0.0161 | — | **0.0161** | 3rd |
| Mai Nguyễn | — | 3rd → 0.0159 | **0.0159** | 4th |

**What just happened, and why it's the right outcome:**

- The two records that appeared in **both** lists scored roughly double the ones that appeared in only one. Agreement between two independent methods is the strongest signal available, and RRF rewards it automatically.
- **Johnathan Smithe** was the meaning-based search's second-favourite — similar-sounding name — but he's in Melbourne, a different city with a different postcode, so the postcode search never saw him. He drops below both genuine candidates.
- **Mai Nguyễn** has exactly the right postcode but she's a neighbour at number 14, not our person. The meaning-based search didn't rate her, so she sinks too.

Neither search alone gets this ordering right. Together they do, with no tuning.

> **A Unicode aside.** Mai's surname illustrates a problem that has nothing to do with AI. If one system stores *Nguyễn* and another stores *Nguyen*, a naive exact-match join treats them as two different people — and a careless "strip anything that isn't a plain letter" clean-up step is worse still, because it deletes the accented character outright, turning *José* into *Jos* and destroying the letter rather than the accent. Done properly it is deterministic and needs no model at all: decompose with NFKD, drop the combining marks, and *Nguyễn*, *José* and *Renée* fall out as *Nguyen*, *Jose* and *Renee*.
>
> **Where that stops working is the interesting part.** A handful of Latin letters are single code points with *no* canonical decomposition, so NFKD leaves them completely untouched — *Ł*, *Ø*, *Đ*, *Ħ*, *Ŧ*, and *ß*, *Æ*, *Œ*. Put *Łukasz* through a textbook decompose-and-strip-marks routine and you get *Łukasz* straight back, unchanged. The one name in the pile that most looks like it should fold is the one that silently doesn't, which is exactly the kind of bug that ships. Those need an explicit lookup table on top — *ł→l*, *ø→o*, *ß→ss*, *æ→ae* — and if you skip it, the half of the demo that claims "normalisation alone solves this" quietly stops being true.
>
> And a third class isn't an encoding problem at all. *Müller* is conventionally written *Mueller* in English-speaking countries; no amount of Unicode normalisation will ever get you from one to the other, because that is a transliteration convention rather than a character encoding. That one genuinely does need the graph and the adjudicator.
>
> Worth saying out loud: not every identity problem needs an LLM. Some of them need someone to have read the spec — and some of them need someone to have read the *Unicode* spec.

**Why the 60?** It's a dampener. Without it, 1st place would score 1.0 and 2nd place only 0.5 — a huge gap, letting a single search's top pick dominate. Adding 60 makes 1st and 2nd nearly equal, so the method cares about *"near the top of both lists"* rather than *"first in one list"*. Sixty is the long-standing default from the original research; it rarely needs changing.

**Why this matters commercially:** RRF needs no calibration, no weighting decisions, and no retuning when your data shifts. That's the difference between an identity system someone has to babysit and one that just runs.

---

### 4. What the "AI adjudicator" actually does

For the small fraction of genuinely ambiguous cases, we show an AI model two records and ask the same question you'd ask an experienced colleague: *are these the same person?*

It returns four things:
- **A verdict** — yes or no
- **A confidence score** — how sure it is
- **A written reason** — a sentence or two of plain English
- **Evidence tags** — short codes like `dob_exact`, so you can analyse patterns across millions of decisions

The written reason is the genuinely new capability. If a customer exercises their right to ask why you linked their records, "the algorithm decided" is not an acceptable answer. A stored, readable explanation is.

We keep every decision permanently, along with which version of the AI made it, so results stay reproducible and any change to the system can be tested before it goes live.

---

### 5. Over-merging is much worse than under-merging

Two failure modes:

- **Under-merge** — you miss a duplicate. Result: you count a customer twice and send two mailings. Annoying and slightly embarrassing.
- **Over-merge** — you combine two *different* people. Result: one person's order history, address and contact details are now visible in the other's profile.

The second is a data breach, not a data-quality ticket. So the system is deliberately tuned to be cautious: when the evidence is genuinely balanced, it declines to merge. We also automatically flag suspiciously large clusters — if 400 records have merged into one "person", something has gone wrong, and we quarantine it before it reaches production.

And critically: **unmerging is a normal, supported operation**, not a data-recovery project. Source records are never overwritten, so a bad merge can always be undone.

---

### 6. Knowing *who* vs. knowing *what the words mean*

Suppose you resolve identity perfectly, then let an AI assistant loose on the data. Someone asks: *"how many active customers do we have in EMEA?"*

The assistant needs two separate things:

- **Who the customers are** — the golden record. Solved by everything in slides 8–13.
- **What "active" means** — bought in the last 90 days? Logged in this year? Holds an open subscription?

Finance, marketing and the board frequently have three different definitions. If nobody has written one down, the assistant picks one and states the result with total confidence. You get a precise, authoritative, wrong number — faster than before.

Knowledge Catalog is where those agreed definitions live, alongside a record of where every figure came from. That second part does double duty: it grounds the AI *and* it satisfies auditors.

---

## What happens when it gets something wrong?

A fair question, and the honest answer has four parts:

1. It will get some things wrong. Any system does, including human data stewards.
2. Uncertain cases go to a person rather than being decided automatically.
3. Every decision is recorded with its reasoning, so mistakes are findable rather than invisible.
4. Every merge can be reversed without data loss.

The comparison worth making is not "AI versus perfect". It's "AI versus a rules engine written in 2014 that nobody fully understands and that can't explain itself either".

---

## Honest caveats to state out loud

- **Two capabilities are in Preview** (pre-general-release): the combined search method, and reading data directly from other clouds. Neither sits in the critical path — the core identity engine uses fully released features only.
- **The percentages on the funnel slide are illustrative**, not measured. Real figures depend on your data quality and come out of the pilot.
- **There is no ready-made screen for data stewards.** Reviewing uncertain cases needs a small interface built, or integration with a tool you already have.
- **The only firm number in the deck** is a published performance figure from Google. Everything else is deliberately left to be measured on your data.

---

## Jargon translator

| They say | It means |
| :--- | :--- |
| Golden record | The single combined profile for one real person |
| Identity resolution / MDM | Working out which records describe the same person |
| Embedding / vector | A "meaning fingerprint" that lets you find similar records |
| Hybrid search | Using meaning-based and exact-match search together |
| Reciprocal Rank Fusion (RRF) | The method for merging two result lists — uses each record's *position* in each list, not the raw scores |
| Adjudicator | The AI that decides the genuinely ambiguous cases |
| Grey zone | The ambiguous minority of cases needing real judgement |
| Survivorship | The rules deciding which value wins when sources disagree |
| Cluster / graph | A group of records all determined to be the same person |
| Over-merge | Wrongly combining two different people |
| Lineage | The trail showing where a piece of data came from |
| Reverse ETL | Pushing the finished profile back out to the systems that use it |
| Zero-ETL | Reading data where it already lives instead of copying it |

---

## Awkward questions, and answers

**"Isn't this just MDM again? We tried that."**
Yes — and it was the right idea. It failed on cost, and on the fact that nobody could explain its decisions. Both of those constraints have genuinely changed.

**"How much will the AI cost?"**
Only the ambiguous minority goes near it, and there's a cheaper pre-filter before that. We model the actual figure in the pilot rather than guessing now.

**"Can we keep our existing CDP?"**
Yes. The golden record moves to BigQuery; your existing tool becomes one of the places you send it.

**"What if the AI hallucinates a merge?"**
It doesn't merge anything unilaterally. It proposes, with a confidence score. Low confidence goes to a human, everything is logged, and anything can be undone.

**"Why will our audience numbers go down?"**
Because some of the people in the old number were duplicates, and some you didn't have permission to contact. See the consent section.

**"Is this real customer data? That looks like a real person."**
No. Every record in the demo is synthetic — generated, not sampled from anyone's systems. Say so plainly, and say it before anyone has to ask.

It is worth understanding *why* someone might ask. The demo data is built from real Australian name-frequency data: actual forename and surname distributions, real suburbs, real state postcode ranges. That is exactly what makes it look credible instead of looking like `Test User 00417`. But it has an unavoidable consequence — **a name generator drawing from a country's real naming stock will compose the names of real people in that country, including well-known ones.** There are roughly two million possible name combinations and about twenty-seven million Australians, so collisions are arithmetic, not carelessness. The same stock reaches well-known Britons and Americans too, for the same reason.

This cannot be filtered away. A generator that produced no recognisable names would not be producing realistic names, and the data would stop doing its job. There is a blocklist covering the names that would genuinely derail a presentation, but it is a safety net, not a guarantee, and it is honest to describe it that way.

So: the records are synthetic, any resemblance to real persons is coincidental, and the one-line disclaimer on the worked-example slide exists for exactly this reason. If a name on screen does land awkwardly, the answer is short — *"synthetic data, generated from public name-frequency statistics"* — and then move on.
