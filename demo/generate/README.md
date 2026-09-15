# Synthetic data generator

Builds the entire demo corpus described in [`demo/CONTRACT.md`](../CONTRACT.md):
seven identity-bearing sources, a consent event log, the call transcripts, and
the hidden ground truth that the pipeline is scored against.

The corpus is localised to **Australia** — Australian names, suburbs,
4-digit state-coded postcodes, `04xx`/`(0x)` phone numbers, AUD amounts and
grocery-retail free text. The narrative is deliberately generic: no supermarket
chain, loyalty scheme or competitor is named anywhere. The loyalty programme is
referred to only as a **"loyalty card"**, deliberately as a common noun rather
than a name. An earlier draft gave the scheme an invented brand name, which
turned out to collide with a real supermarket loyalty programme — a bad
collision precisely because this is a grocery loyalty scenario, the one context
where a reader will make the connection. Any invented scheme name risks
colliding with a real one somewhere, so the generic noun is the safer choice.
Every major Australian grocery chain runs a scheme of exactly this kind and
several of them are household names: do not reach for one of those, and do not
coin a replacement.

Everything here is **synthetic**. No real person, address, phone number, email
address or transaction appears in the output, and the generator makes no
network calls.

---

## Usage

```bash
python generate.py --seed 42 --people 80000 --records 200000 --out ../data
```

That is the canonical invocation and the one the demo ships with. It takes
about a minute and writes roughly 69 MB.

For fast debugging cycles there is a tenth-scale config that exercises every
code path:

```bash
python generate.py --seed 42 --people 8000 --records 20000 --out ../data
```

About 10 seconds and 7 MB. Note that the two are **not** subsets of each other
— every draw shifts when the population size changes.

### Dependencies

Standard library plus **pyarrow**, which is needed only to write
`support_tickets.parquet`. Nothing else — no faker, no pandas.

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python generate.py --seed 42 --people 80000 --records 200000 --out ../data
```

> On a corp machine without direct PyPI access, install through the Airlock
> proxy index rather than pypi.org.

### Options

| Flag | Default | Meaning |
| --- | --- | --- |
| `--seed` | `42` | Seeds everything. Same seed + same config → byte-identical output. |
| `--people` | `80000` | Number of distinct real people (i.e. distinct `true_person_id`). |
| `--records` | `200000` | **Exact** number of identity-bearing records across the seven sources. The generator tops up or trims the tail to hit this number precisely. |
| `--out` | `../data` | Output root. Created if absent. No bucket, project or path is ever hardcoded. |
| `--case-instances` | auto | Instances of *each* of the 15 hard cases. Defaults to `records / 2000`, clamped to `[22, 250]` — so 100 at the default scale and 22 at 20k. The contract floor is 20. |
| `--max-transcripts` | `6000` | Hard cap on individual transcript `.txt` files. Call records beyond the cap are re-planned onto other sources. Thousands of tiny objects are slow to upload to and list in GCS, and the demo reads maybe three of them aloud. |
| `--singleton-pct` | `15.0` | Percentage of people with exactly one source record. |
| `--no-verify` | off | Skips the post-generation self-check. Not recommended. |
| `--quiet` | off | Suppresses the summary table. |
| `--profile` | off | Wall clock and peak traced memory to stderr. Roughly doubles runtime, and is deliberately **not** written to `manifest.json`, which must stay byte-identical between runs. |

Plus the twelve corruption knobs below.

### Self-check

Unless `--no-verify` is passed, the generator re-reads its own in-memory state
after writing and asserts eleven invariants: exact record count, exact person
count, globally unique `record_id`, every truth row resolving to a real record,
every hard case hitting its instance target, exactly three prompt injections,
`ACCOUNT_ONLY` people carrying exactly two records, household sizes of four,
and so on. A failure raises rather than writing a quietly wrong corpus.

---

## What gets written

```
<out>/
  crm_customers.csv              # trust 9
  ecom_accounts.csv              # trust 6
  loyalty_members.csv            # trust 7
  pos_transactions.csv           # trust 3
  support_tickets.parquet        # trust 4
  call_transcripts_manifest.csv  # trust 4
  call_transcripts/CALL-xxxxxxxx.txt
  third_party_enrich.jsonl       # trust 2
  consent_events.csv
  truth/person_truth.csv
  truth/case_catalogue.csv
  manifest.json
```

Conventions worth knowing before you load it:

- **Nulls.** Empty string in CSV, absent-or-empty in JSONL, real nulls in
  Parquet. Stated in `manifest.json.null_convention`.
- **Timestamps.** `%Y-%m-%d %H:%M:%S UTC` as text in CSV and JSONL; a real
  `timestamp('us', tz='UTC')` in Parquet.
- **Transcript URIs.** `call_transcripts_manifest.uri` is **relative** to the
  data root (`call_transcripts/CALL-xxxxxxxx.txt`). Prefix it with
  `gs://<bucket>/<prefix>/` at load time. This is deliberate — nothing in the
  corpus names a bucket. Stated in `manifest.json.uri_convention`.
- **Row order.** Every file is sorted by `record_id` (consent by `consent_id`),
  so row order carries no identity signal. A pipeline cannot cheat by assuming
  that adjacent rows belong together.
- **`manifest.json`** carries row counts per file, person count, per-case
  counts, the seed, the full corruption config, the namesake metrics, and the
  ids of the three prompt-injection records.

`truth/` is the answer key. It is written alongside the data for convenience;
in a real run you would stage it somewhere the pipeline cannot read.

---

## Australian conventions

These are the details an Australian audience will check.

| Thing | How it is generated |
| --- | --- |
| **Postcodes** | 4 digits, no letters, consistent with the suburb and its state (NSW `2xxx`, VIC `3xxx`, QLD `4xxx`, SA `5xxx`, WA `6xxx`, TAS `7xxx`, ACT `26xx`, NT `08xx`). Northern Territory postcodes genuinely start with `0`, which sets up the leading-zero trap below. |
| **Addresses** | `street, suburb, STATE, postcode`. The suburb is load-bearing — real (suburb, postcode) pairs across the 18 centres in `banks_places.py`, Sydney carrying the most. `TODO(count)`: exact pair total and per-city counts once the rebuilt `banks_places.py` lands; the previous localisation carried 321 pairs across 24 centres and that figure does **not** carry over. The Australian unit form `3/42 Bourke Street` appears alongside `Flat 2,` and `Unit 5,`. |
| **Mobiles** | `040` / `041` / `042` / `043` / `044` / `045` / `046` / `047` / `048` / `049` prefixes, weighted unevenly — real `04xx` allocation is not uniform, and a flat distribution is a tell. |
| **Landlines** | `(02)` NSW and ACT, `(03)` VIC and TAS, `(07)` QLD, `(08)` SA, WA and NT — matched to the person's city. |
| **`+61` forms** | Drop the trunk zero: `+61 412 345 678`, never `+61 0412 …`. This is a genuine normalisation trap and it is in there on purpose. |
| **Currency** | AUD, written `$42.60`. The POS column is `amount_aud`. |
| **Names** | Drawn group-first from 10 pools — Anglo, Chinese, Indian, Vietnamese, Filipino, Arabic, Greek, Italian, Korean and other South-East Asian — weighted to Australian reality and **varied by region**: Sydney is the most diverse, Melbourne carries markedly more Greek and Italian stock, Perth is Anglo-heavy with a South-East Asian component, and regional centres are strongly Anglo. A 16% cross-group rate reflects intermarriage. |
| **Diacritics** | Real UTF-8 accented Latin forms (`José`, `Renée`, `Müller`, `Nguyễn`, `Łukasz`), used only where the name genuinely takes one. |

The ten name-group keys are `ANGLO`, `CHINESE`, `INDIAN`, `VIETNAMESE`,
`FILIPINO`, `ARABIC`, `GREEK`, `ITALIAN`, `KOREAN` and `SE_ASIAN`, with `ANGLO`
at 62% of the national default mix. The regional variation runs off five
region-profile keys, and **every group key appears in every profile**:

| Profile | Applied to | Character |
| --- | --- | --- |
| `DEFAULT` | the national mix | the baseline weighting |
| `METRO_SYDNEY` | Sydney | highest diversity |
| `METRO_MELBOURNE` | Melbourne | high diversity, Greek and Italian heavy |
| `METRO_PERTH` | Perth | Anglo-heavy, some South-East Asian |
| `REGIONAL` | everywhere else | strongly Anglo |

> [!NOTE]
> Brisbane and Adelaide are assigned `REGIONAL`, which understates them — both
> are genuinely diverse cities. It is a simplification made because five
> profiles is already enough moving parts, not a claim about either city. If
> that skew matters for your use of the corpus, it is the first thing to change.

> [!NOTE]
> **`postcode_outward` is a misnomer, kept deliberately.** Australia has no
> outward code — that is a UK alphanumeric concept. The POS column keeps its
> UK-era name so the pipeline schema does not churn, but it holds the **first
> two digits** of the postcode. Unlike the previous localisation, those digits
> are genuinely meaningful here: the first digit is the **state**, and the first
> two together are a coarse **regional bucket** within it. It is still never an
> identity.

---

## Case catalogue

Each of the 15 hard cases is emitted `--case-instances` times (100 at the
default scale). `truth/case_catalogue.csv` carries the same table,
machine-readable, with the deck slide each case backs.

| `case_type` | Expected | What it is |
| --- | --- | --- |
| `HOUSEHOLD` | `DO_NOT_MERGE` | Four people at one address, different forenames, different DOBs. Four `person_id`s, one `household_id`. Forename initials are forced distinct so the POS rows (surname + initial + postcode area) stay in principle separable. |
| `SIBLING_TRAP` | `DO_NOT_MERGE` | Two siblings at the same address with the same surname and confusable forenames (Jon/John, Alexander/Alexandra). The DOB is the only reliable discriminator, so both siblings are guaranteed a DOB on at least one record. |
| `MARRIED_NAME` | `MERGE` | One woman, maiden name on the older records and married name on the newer, with an address move part-way through. |
| `TRANSLITERATION` | `MERGE` | The same person spelled two ways (Siosaia/Josiah, Xiao Wei/Xiaowei, Min-jun/Minjoon). On every third instance the ecom row drops postcode and DOB and uses a different email, so the name is the *only* link. |
| `DIACRITIC_VARIANT` | `MERGE` | The same person written with and without diacritics (`José`/`Jose`, `Nguyễn`/`Nguyen`, `Łukasz`/`Lukasz`). **Half the instances differ by the diacritic alone** — address, DOB, email and mobile are held identical on purpose, so those are solvable by correct Unicode normalisation and nothing else, and a regression in name folding fails loudly right here. The other half pair the diacritic difference with a second divergence (stale address, missing DOB, diminutive forename), so normalisation narrows the gap and the graph plus adjudicator finish the job. The 50/50 split is deliberate and load-bearing. Conventional transliterations (`Müller` → `Mueller`) appear where they are genuinely the customary spelling — those are **not** recoverable by normalisation, and they are what carries the "normalisation gets you close, the graph closes it" half. A slice puts the difference in the **address** instead of the name; see the note below, because that slice does *not* test accent folding. |
| `NAME_ORDER` | `MERGE` | Given and family name transposed between systems — `Wei Chen` in the CRM, `Chen Wei` on the loyalty card. A matcher that compares first-name to first-name and surname to surname scores this as an active double *non*-match, which is worse than a weak match. A third of instances also carry an adopted Western forename (`Grace Chen`), which is how this usually looks in a real Australian customer file. |
| `NAME_ORDER_TRAP` | `DO_NOT_MERGE` | The hard negative for the above: two genuinely different people whose records look like a transposition of one another. |
| `SHARED_EMAIL` | `DO_NOT_MERGE` | Two different people legitimately using one mailbox — a couple or a parent and child. |
| `POSTCODE_NEAR_MISS` | `DO_NOT_MERGE` | Same name, adjacent postcodes, different people. |
| `ACCOUNT_ONLY` | `MERGE` | Two records whose *only* shared signal is the loyalty account number; names, addresses and emails all differ. These people carry **exactly two** records by construction — a third would let the cluster link on something else and void the test. |
| `SOLE_TRADER` | `MERGE_WITH_FLAG` | A personal identity and a one-person business at the same address and phone — a cafe owner, a food-truck operator, a rest-home cook buying in bulk. Truth assigns both to the same person; the expectation is that the business record is *typed* as a business association rather than folded into the personal golden record. |
| `RISK_FLAG` | `MERGE_WITH_FLAG` | The records merge cleanly, but the free text discloses deceased / minor / vulnerable status. Minors are given DOBs aged 14–17 so the disclosure is internally consistent. |
| `UNSTRUCTURED_ONLY` | `DO_NOT_MERGE` | A proxy caller — spouse, carer, adult child — phoning about someone else's account. Truth assigns the call to the *caller*; the account holder's name, postcode and account number appear inside the transcript as bait. |
| `CONSENT_CONFLICT` | `MERGE` | One person, three sources, contradictory consent on the same channel. Merging is correct; the resulting consent state must be the conservative one. |
| `OVERMERGE_BAIT` | `BREAK_CHAIN` | An A↔B↔C chain where A–B and B–C each look plausible but A and C have incompatible DOBs (minimum gap 26 years, median 40). Ownership of the bridging record alternates, so a pipeline cannot learn "the bridge is always the older record". |

> [!IMPORTANT]
> **The `DIACRITIC_VARIANT` address slice tests punctuation, not accents.** In
> the previous localisation that slice drifted an accented suburb name against
> its stripped form, so it genuinely exercised accent folding on the address
> path.
> Australia has very few place names carrying a diacritic, and inventing one
> (`Coogeé` for `Coogee`) would be fake data. So the slice now drifts the
> address on **apostrophe, hyphen and `St`/`Saint`** instead — `O'Connor` /
> `OConnor` / `O Connor`, hyphen present or absent, `St Marys` / `Saint Marys`.
> That still exercises the address normalisation path, which is the point of
> the slice: address and name normalisation are usually different code paths
> and only one of them tends to get tested. But it is **not** an accent-folding
> test, and nobody should present it as one.

Two untagged categories complete the file:

- `NORMAL` — ordinary multi-source people, the bulk of the corpus.
- `SINGLETON` — people with exactly one record (`--singleton-pct`, default 15%).
  These are also hard negatives: a pipeline that over-merges will absorb them.

There are additionally ~9,300 **natural background households**
(`--natural-household-rate`): two or three distinct people sharing an address,
tagged `NORMAL` with a populated `true_household_id`. This matters. If every
same-address pair in the corpus were a tagged `HOUSEHOLD` trap, the dataset
would be gameable.

---

## Namesakes

Two people sharing a name is normal and the corpus should contain plenty. Two
people sharing a name who *cannot be told apart* is a different thing: it asks
the pipeline a question the data cannot answer, and it drags precision down
for reasons that have nothing to do with the matching algorithm.

So the generator does not suppress namesakes — it guarantees they are
**separable**. Any two people drawing the same full name must live in
different cities and be born at least five years apart, with a ceiling of four
people per exact name. `manifest.json` reports all three figures:

| Field | 20k config | 200k config |
| --- | --- | --- |
| `incidental_name_collisions` | 79 (1.0% of people) | 4,998 (6.2% of people) |
| `ambiguous_name_collisions` (same name, same city, DOB within 2) | 0 | 1 pair |
| `name_separability_fallbacks` (times the guarantee could not be met) | 0 | 0 |

The rate climbs with scale because the number of *pairs* grows quadratically
while the name banks stay fixed — 6.2% at 80,000 people is roughly what a real
file of that size looks like. Flattening it away would mean inventing a
population whose names are uniformly distributed, which no real population is.

At 200k exactly one ambiguous pair survives, and both of its members belong to
a tagged `SHARED_EMAIL` case. **No untagged pair in the corpus is
indistinguishable** — which is the property the scorecard actually depends on.

> [!WARNING]
> The separability check has to be applied at **every** point a name or a city
> is assigned, not just at creation. Natural background households originally
> moved a member into the head's city and overwrote their surname *after*
> `make_person` had vetted the name, which silently produced indistinguishable
> namesakes while `name_separability_fallbacks` still read zero. If you add a
> code path that mutates `forename`, `surname` or `addr` after the fact, it
> must re-check `World._separable` and re-register with `World._claim_name`.

---

## Tuning the corruption rates

Every knob is a probability in `[0, 1]`, exposed as a CLI flag and echoed into
`manifest.json.corruption`. Raise them to make matching harder.

| Flag | Default | Effect |
| --- | --- | --- |
| `--typo-rate` | `0.07` | Per-field chance of one realistic keying error: keyboard-neighbour substitution, dropped char, doubled char, or adjacent swap. |
| `--transpose-rate` | `0.04` | Chance a full name is written surname-first. |
| `--diminutive-rate` | `0.45` | Chance an ecom first name uses a diminutive (Bill for William, Jono for Jonathan, Shaz for Sharon) *when one exists for that name*. The realised rate is lower because not every forename has one. |
| `--surname-variant-rate` | `0.12` | Chance of a phonetic surname variant (Smyth/Smith, Ngyuen/Nguyen, Babic/Babich). |
| `--postcode-drift-rate` | `0.35` | Chance of postcode format drift. Australia-specific modes: **leading zero stripped** (`0812` → `812`, the Excel trap, and the heaviest-weighted mode because it only fires on postcodes that start with zero — which in Australia means the Northern Territory and nowhere else), whitespace padding, state-prefixing (`NT `), area-digits-only, and a genuine typo that changes which postcode it is. |
| `--phone-format-drift-rate` | `0.55` | Chance of phone format drift: `+61` and `0061` international forms (correctly dropping the trunk zero), spacing changes, leading-zero loss. |
| `--email-drift-rate` | `0.30` | Chance of dot, plus-tag or provider-domain drift (`gmail.com`/`googlemail.com`, `hotmail.com`/`hotmail.com.au`). Variants that would land on another person's mailbox are reverted, so accidental cross-person email collisions do not pollute the truth. |
| `--missing-field-rate` | `0.08` | Baseline sparsity on optional fields, on top of the per-source null rates the contract fixes. |
| `--stale-address-rate` | `0.25` | Chance a low-trust source still shows a previous address. |
| `--move-rate` | `0.18` | Chance a person has moved during the window at all. |
| `--natural-household-rate` | `0.14` | Share of people placed into an untagged 2–3 person address-sharing household. |
| `--enrich-wrong-attribution-rate` | `0.08` | Share of third-party enrich rows that carry one person's name against another's address and email. Truth follows the **name**; the truth `notes` column says `WRONG_ATTRIBUTION:` and explains. |

### Determinism caveat

Output is byte-identical for a given **seed *and* corruption config**. Changing
any rate changes the stream of draws and therefore the whole corpus — that is
intended, but it means you cannot compare two runs with different knobs
row-by-row. The same applies to `--people` and `--records`.

Two further caveats:

- Randomness is derived with `blake2b` over `"seed|part|part"`, never Python's
  built-in `hash()`, which is randomised per process for strings and would
  silently destroy reproducibility.
- Parquet embeds a `created_by` writer-version string, so **upgrading pyarrow
  changes the file bytes** even when the data is identical. `requirements.txt`
  pins a range for this reason. CSV, JSONL and the transcripts are unaffected.

---

## Layout

| File | Role |
| --- | --- |
| `generate.py` | The generator: world model, emitters, the 15 case builders, writers, self-check, CLI. |
| `banks.py` | Thin aggregator over the two reference-data modules, plus the commerce banks: POS categories, sole-trader trades, enrich vendors, agent ids. |
| `banks_names.py` | Names by cultural group, regional weightings, diminutives, surname variants, transliteration families, accented (diacritic-bearing) names, and the given/family transposition families. |
| `banks_places.py` | Cities, suburbs with their postcodes and states, streets, building forms, suburb punctuation variants, mobile prefixes, email domains. |
| `text_banks.py` | Free-text banks — support ticket bodies, call transcript dialogue, the three prompt injections. |
| `requirements.txt` | `pyarrow`, pinned to a range. |

Names are drawn **group-first** so that forename and surname are plausible
together; drawing the two halves independently produced obviously synthetic
combinations. The group is itself biased by the person's region, so the name
mix in Cabramatta differs from the mix in Bendigo.

---

## Name banks: provenance and the parallel-pool trap

> [!CAUTION]
> **The non-Anglo name content here has not been reviewed by native speakers.**
> The Chinese, Vietnamese, Indian, Arabic, Greek, Italian, Korean, Filipino and
> other South-East Asian pools were assembled by people who do not speak those
> languages. Before this corpus is shown to an Australian audience — which is to
> say, an audience that contains speakers of every one of them — someone who
> does should review each pool. This caveat stands regardless of how clean the
> automated checks look.
>
> **Scanning the word lists is not enough.** The failure mode is not typos, it
> is judgement calls a non-speaker cannot make:
>
> 1. **Is this a name at all?** Deity names, honorifics, dictionary words and
>    place names look exactly like personal names to someone outside the
>    language. The previous localisation shipped all four classes before a
>    reviewer caught them.
> 2. **Is the diacritic right?** `Nguyễn`, `José`, `Müller` and `Łukasz` each
>    carry marks that a non-speaker will copy rather than verify. A wrong mark
>    is not a cosmetic error here — it is the entire content of the
>    `DIACRITIC_VARIANT` case, so a wrong mark puts a wrong claim on a slide.
> 3. **Is the forename/surname split right?** Several of these naming systems
>    do not divide the way the two-column schema assumes.
>
> `banks_places.py` has had **no review at all**. Suburb names, their
> state and postcode pairings, and the street names in `STREETS` have had none
> of the scrutiny the name banks have had. Please include it in scope.
>
> **None of the sweeps described below have been re-run against the Australian
> pools.** The defect history in this section was found on the previous
> localisation's pools. The *mechanisms* survive the relocalisation; the
> *findings* do not, and nothing here should be read as a clean bill of health
> for the current banks.

### First two defects — bad words in the pools

In the previous localisation the minority-language name pools were generated
and then had to be rebuilt **twice**, for two *different* reasons. Both are
worth recording, because the second one is a structural trap that will catch
the next person too — including on the Australian pools, which have not yet
been through either sweep.

**First defect — the general pools.** The minority-group entries in
`MALE_FORENAMES_BY_GROUP`, `FEMALE_FORENAMES_BY_GROUP` and `SURNAMES_BY_GROUP`
were padded with **deity names** (nobody is named those), **dictionary words**
(the generator's author could not tell a common noun from a given name in a
language they did not speak), a surname sitting in a forename list, and
**identifiable public figures weighted to the head of the distribution** —
including one surname that did not belong to the cultural group it was filed
under at all. Rebuilt by hand.

**Second defect — the parallel pools.** The accented-name pools now called
`DIACRITIC_FORENAMES` and `DIACRITIC_SURNAMES` **were not touched by that
rebuild and still contained the same class of error** — the same deity names,
a tribal-group name, a historical monarch, and more dictionary words.

They were missed because they are a *parallel* pool: `DIACRITIC_VARIANT` reads
them directly and never goes through `MALE_FORENAMES_BY_GROUP` or
`SURNAMES_BY_GROUP`. "Fix the minority name pools" naturally meant the three
obvious dictionaries, and the fix was reported complete while the worst-placed
instance of the problem survived — worst-placed because `DIACRITIC_VARIANT` is
the case most likely to be put on a slide, being the one whose entire purpose is
demonstrating that non-English orthography is handled correctly.

**This trap is live again.** The `DIACRITIC_*` pools are being rebased onto
accented Latin names for this relocalisation. They are still a parallel pool,
they are still read directly, and they still bypass the general banks. A rebuild
of the general pools that forgets them will reproduce this defect exactly.

### Inventory of parallel pools

Every pool below can put a name on screen **without passing through the general
banks**. Any future correctness sweep must cover all of them explicitly.

| Pool | Module | Consumer | Entries |
| --- | --- | --- | --- |
| `DIACRITIC_FORENAMES` | `banks_names` | `DIACRITIC_VARIANT` | `TODO(count)` |
| `DIACRITIC_SURNAMES` | `banks_names` | `DIACRITIC_VARIANT` | `TODO(count)` |
| `TRANSLITERATION_FORENAMES` | `banks_names` | `TRANSLITERATION` | 54 |
| `TRANSLITERATION_SURNAMES` | `banks_names` | `TRANSLITERATION` | 42 |
| `NAME_ORDER_FAMILIES` | `banks_names` | `NAME_ORDER`, `NAME_ORDER_TRAP` | 132 triples |
| `CONFUSABLE_FORENAMES` | **`generate.py`** | `SIBLING_TRAP` | 32 pairs |
| `AGENT_FIRST_NAMES` | `text_banks` | call transcripts | 16 |
| `DIMINUTIVES` *values* | `banks_names` | ecom `first_name` | 261 |
| `SURNAME_VARIANTS` *values* | `banks_names` | surname drift | 108 |
| `PUNCTUATION_SUBURBS` | `banks_places` | `DIACRITIC_VARIANT` (address) | `TODO(count)` |
| `NAMED_BUILDINGS` | `banks_places` | `address_line1` | 15 |

The `DIMINUTIVES` and `SURNAME_VARIANTS` *values* deserve particular care: they
are never drawn as names, only substituted in, so they never appear in the
general banks and a check that only walks the banks will not see them at all.

`scratch/audit_name_pools.py` sweeps all of the above against a banned set of
deity names, group and tribal names, dictionary words and identifiable public
figures. It is not a substitute for a human reviewer — it only catches terms
someone already thought to ban, and its banned set is inherited from the
previous localisation and has not yet been rebuilt for the Australian pools.

### Third defect — clean pools, wrong combinations

A third round found five more problems, and the important thing about them is
that **four of the five could not have been caught by scrubbing pools at all**,
because every individual word involved was correct.

| # | Defect | Why no pool sweep could find it |
| --- | --- | --- |
| 1 | 4 of 64 `CONFUSABLE_FORENAMES` resolved to the wrong group | `Ana`, `Rosa`, `Louis`, `Anna` were in their intended minority pool **and** in the far heavier dominant pool. `FORENAME_GROUP` is a reverse index that keeps the highest-weighted group, so they resolved to the dominant group and the sibling got a surname from it. The same index exists today with `ANGLO` as the heavy pool, so the trap is unchanged. |
| 2 | **A national landmark emitted as a customer name** | Neither half was wrong. The forename was retained deliberately as a genuine contemporary given name; the surname was a real surname with well-known bearers. Only the *combination* named a famous place. No pool sweep can see this, because a pool sweep examines words one at a time. |
| 3 | 12 reduplicated names (`Lin Lin`, `Lewis Lewis`) | The forename and surname banks legitimately share entries, so a draw can put the same word in both positions. `Thomas Thomas`, `Nguyen Nguyen` and `Mario Mario` are the equivalents the Australian pools can produce. |
| 4 | Half of the address-variant suburb pool was dead code | `address_flavour` fired only when `i % 6 == 0`, so `i` was always even and `subs[i % 20]` could only reach even indices. Ten suburbs had never appeared in any corpus. The workaround has been **deleted rather than ported** — the replacement slice indexes on its own dense counter, never on anything derived from `i`, so the bug cannot recur. |
| 5 | Two unanswerable pairs on the scorecard | A `SHARED_EMAIL` couple both named `Lin Xie` (`Lin` is in both the male and female Chinese pools) whose own truth note claimed "different forenames"; and a `SIBLING_TRAP` sibling colliding with a `HOUSEHOLD` member in the same city. |

> [!IMPORTANT]
> **Point 1 generalises: being in the right pool is not sufficient. A name must
> be *dominant* in that pool to survive the reverse index.** Adding a name to
> `GREEK` does nothing if `ANGLO` also carries it at a higher weight — and
> `ANGLO` is 62% of the national mix, so it out-weighs every other pool by
> default.

### The structural fix: check the output, not the draw sites

Defects 3 and 5 both appeared *after* a guard was added inside `make_person`.
Each arrived through a different path that bypassed it:

- pools indexed directly, never touching `make_person` (`diacritic_variant`);
- builders pinning **both** name halves, leaving nothing to redraw
  (`shared_email`, `sibling_trap`, `NAME_ORDER`);
- mutations applied **after** `make_person` had already vetted the name
  (natural-household surname adoption, the `postcode_near_miss` forename
  overwrite).

That last category is the same failure as the `DIACRITIC_*` miss in a new guise.
Guarding draw sites requires enumerating every draw site, and **that
enumeration kept being incomplete** — three times, by two different people.

So the check is now **output-side**. At verify time the generator raises if a
forbidden pair survived, *regardless of which path created it*. This is the only
check here that does not depend on having enumerated anything, and it is the
reason a builder added later cannot quietly reintroduce the bug. Prefer this
shape of check over another guard.

#### Defect 6: the output-side check inspected the wrong object

The first version of that sweep walked `world.people` and read `p.forename` and
`p.surname`. That is not what gets written. `Emitter._pick_forename` and
`_pick_surname` substitute a `DIMINUTIVES` entry, a `SURNAME_VARIANTS` entry or
a typo **at emission time**, after the sweep's view of the name:

| Emitted to the file | Underlying `Person` | Sweep saw a problem? |
| --- | --- | --- |
| `Bill Shorten` | `William Shorten` | no |
| `Mike Baird` | `Michael Baird` | no |
| `Dan Andrews` | `Daniel Andrews` | no |
| `Jackie Chan` | `Jacqueline Chen` | no |

The first three are the ordinary shape of the problem: each is a real public
figure who is *known by the diminutive*, so the roster entry for the canonical
forename does not fire and the emitted row does. `Jackie Chan` is the clearest
case of all: **neither `Jackie` nor `Chan` is in any pool.** It is composed
entirely out of the substitution layer, so no check over pool contents — and no
roster entry — could ever have caught it.

The substitution layers also make the real name space materially larger than the
pools suggest. On the previous localisation's pools, 1,439 forenames expanded to
1,654 written forms and 1,435 surnames to 1,528, turning 2,128,672 base pairs
into **2,692,106** written ones. `TODO(count)`: the equivalent measurement has
**not** been taken on the Australian pools. The ratio is the transferable part;
the absolute numbers are not, and should not be quoted for this corpus.

The lesson is the same one a level further down. "Check the output" had been
applied to the `Person`, but the `Person` is the *input* to emission; the output
is the row. The sweep now runs over emitted name pairs at a single choke point,
which covers diminutives, variants, typos and the `forename_override` /
`surname_override` keys in `Person.extra` — the last of which are read by the
emitter but currently written by nothing, i.e. an unguarded door standing open
for the next person who needs one.

`manifest.json` gained `forbidden_pair_unfixable` (must stay `0`) and
`ambiguous_name_collision_detail`, which names the people and case types behind
the count. The bare count was actively misleading — at one point 37 ambiguous
pairs coexisted with a counter reading zero.

#### Defect 7: three mechanisms that looked live and controlled nothing

Three separate times on this project a thing that **looks like the mechanism,
reads like the mechanism, and controls nothing** was mistaken for the real one:

| Thing | Looked like | Actually |
| --- | --- | --- |
| The `+447` predicate in `70_graph.sql` | UK mobile detection | Matched nothing after localisation. It fed `is_personal_device` in `90_downstream.sql`, so a segmentation feature was **silently constant** |
| The original cross-product assertion | A guard on name-pool contents | Constructed so that it **could never fail** |
| `LOYALTY_PROGRAMME` in `banks.py` | The source of the brand name in the corpus | **Nothing imports it.** All 2,474 corpus occurrences came from hardcoded strings in `text_banks.py` |

The third is worth recording in detail because of *how* it was diagnosed. The
claim made was: *"the corpus will regenerate with the brand unless you change
that line."* That was asserted from reading the constant, without checking
whether anything imported it. Nothing did — the corpus would have regenerated
clean regardless, because the strings that actually produced the brand had
already been fixed.

> [!IMPORTANT]
> **Reading a constant and inferring its effect is not the same as enumerating
> its importers.** A four-second `grep` for the identifier would have caught all
> three of these. The failure is not ignorance of the codebase; it is accepting
> a plausible causal story about a mechanism instead of checking it — which is
> the same error the three defects themselves represent, one level up.

#### Defect 8: there is no cross-field consistency check, and free text is full of checkable claims

Every check built for this corpus walks **one surface at a time**: name pools,
emitted name pairs, ticket bodies, displayed rows. A defect that lives in the
*relationship between two fields* is invisible to all of them by construction,
because each individual surface is clean when examined alone.

**The worked example is the `MINOR` risk bodies.** `_render_risk_ticket` sets
`slots["age"] = p.age_on()`, so the age printed in a ticket is derived from the
holder's own date of birth and **always matches it exactly**. A check on the
*value* passes. A check on the *format* passes. Both did.

What was wrong was the **referent**. Five of the fifteen bodies were written
from a guardian's point of view — *"My son entered your competition. He's
{age}"* — which binds `{age}` to a third party. The record then reads as a
15-year-old account holder with a 15-year-old son.

The absurd prose was the symptom. The real damage was to the ground truth:

- `person_truth` asserts `RISK_FLAG (MINOR) … discloses a MINOR condition` about
  **the holder**, and the scorecard grades `risk_flag=MINOR` on the holder.
- But the correct reading of *"my son is 14"* is that **the holder is an adult**.
- So for those records **a model that extracts the text correctly is graded
  wrong** — the pipeline is right, the scorecard says it is wrong, and there is
  no way to explain that on stage.

> [!IMPORTANT]
> A check has to bind the value **to a person**, not just to a format. "Is this
> a plausible age?" passes. "Whose age is it?" is the question that fails.

The invariant is now stated at the head of `MINOR_BODIES` — `{age}` is always
the age of the person in `contact_name` — because nothing in the file said so,
and five bodies violated it without any check noticing.

**The general shape.** Free text that asserts anything checkable against a
structured column on the same record is a latent defect of this class. In this
corpus the checkable dimensions are:

| Claim in the text | Structured counterpart |
| --- | --- |
| an age, a life stage, a school year | `dob`, emitted to **both** the CRM and loyalty surfaces |
| "my wife", "he", "her" | the holder's gender, legible from the forename and the `Mr`/`Mrs` title |
| "when I was {younger}" | `created_at` |
| "my loyalty card, {account}" | the existence of a row in `loyalty_members.csv` |
| a suburb, a city, a postcode | `address_line1`, `city`, `postcode` |

Gender and age constraints are now **declared on the body itself** — see the
`Body` class in `text_banks.py` — rather than left implicit, so that the
generator can filter the bank to bodies that fit the drawn person, and so that
the next person adding a body has to state its assumptions. A naming convention
would not have survived; a required field might.

The contrasting safe shape is worth naming too. Claims like *"you have rung her
four times this month"* or *"eleven emails in the last fortnight"* have **no
structured counterpart anywhere in the corpus** — there is no contact log, no
email log. They cannot contradict anything, and they carry the same narrative
weight. Where a detail does not need to be checkable, it is cheaper to make it
uncheckable than to keep it consistent.

### Notable names: the conclusion of this whole exercise

> [!IMPORTANT]
> **Notability is not a property that can be filtered out of a realistic name
> generator.** The pools are built from real Australian name-frequency data,
> which is the only way to make them look right. Two thousand-odd forenames and
> fifteen hundred-odd surnames compose **millions of pairs** — and drawn from
> the actual naming stock of a country of twenty-seven million, that space
> necessarily contains a large fraction of the names real Australians have,
> including the notable ones. It reaches British and American public figures
> too, because the `ANGLO` pools draw on naming stock all three countries
> share. A generator that produced no famous names would be producing
> unrealistic names.

> [!IMPORTANT]
> **Reachability, not occurrence. This is the single most important idea in this
> section.** Checking that a notable name does not *appear* in the corpus at
> seed 42 proves nothing at all — it may simply not have been drawn. The
> property that matters is whether the forename × surname **cross product can
> compose it**, which is independent of seed, of run size, and of how many rows
> you looked at. Any check that measures occurrence is worthless and must not be
> written. Any check that measures reachability is load-bearing and must be
> preserved. The `notable_reachable` computation cross-products roster forenames
> and surnames against the **pools**, never against the corpus, and that is
> exactly why it is the check that counts.

This was established by measurement, not assertion. On the previous
localisation's pools, two systematic passes tested **461 candidate notable
names** for *reachability* and found **138 reachable**. The hit rate was ~30%
and **did not decay between passes**, because the binding constraint is the
author's recall of public life, not the contents of the pools. Every new
category thought of yielded another 30%.

`TODO(count)`: these passes have **not** been re-run against the Australian
pools. The ~30% figure is the transferable finding — and if anything it should
be expected to hold or rise, because the roster now has to cover Australian,
British and American public life rather than one country's. Categories not yet
tested include musicians, academics, judges, mayors, chefs, and anyone notable
in Britain or North America sharing the same naming stock.

#### `NOTABLE_FULL_NAMES` is not coverage

The roster in `generate.py` blocks a hundred-odd pairs — at least the ~110 the
previous roster carried, and the rebuild targets more. `TODO(count)`: the exact
entry count, and the percentage of the reachable space it removes, must be
filled in once the rebuilt roster lands. On the previous pools that percentage
was **0.005%**, and the order of magnitude is the point: whatever the new number
is, it will be a rounding error against the reachable space. The roster exists
for the names that would *stop the room*, and it should never be described as
anything more. Its selection rule:

> Block a pair when it is **distinctive and famous** — when an ordinary person
> seeing it on screen would think of one specific individual. Do **not** block a
> name merely because someone famous has it. `Steve Smith` is an Australian
> cricket captain and also about the most generic name the `ANGLO` pool can
> produce; blocking it removes a name real customers have and protects nobody.

Two deliberate exceptions: the **crime and miscarriage-of-justice** group is
blocked regardless of distinctiveness, because the harm there is not
embarrassment; and where a diminutive reaches a notable name, **both forms** are
blocked, since reverting the substitution lands on the same real person
(`Bill Shorten` *and* `William Shorten`). The exception to that exception: where
the canonical form is innocuous because the *surname* also differs, block only
the reachable one.

Australia's size matters when applying the rule. It is a much smaller country
than the United States, so — exactly as the previous localisation's comment
observed about an even smaller one — a national representative's name is
uniquely associated with one public figure far more often here than it would be
in a larger country. Expect the "distinctive and famous" test to fire more often
than it feels like it should.

#### What actually protects the demo

1. **The emitted-row sweep** — the only mechanism that does not depend on a
   list. See above.
2. **Vetting what is displayed, not what is generated.** Of 200,000 records, a
   human reads perhaps a hundred. That set is closed and can be checked
   exhaustively; the other 199,900 are never read and carry almost no risk.
   This is the mitigation that actually finishes.
3. **Saying so.** The demo materials carry a *synthetic data; any resemblance to
   real persons is coincidental* notice. Given that the reachable set includes
   victims of crime and people wrongly convicted of it, this is not optional.

### The adjudication rule for a doubtful name, and its counterweight

The previous localisation kept a table here recording three specific forenames
of uncertain standing, why each was removed, and **how confident the author was
in each call** — High, Moderate, Low. Those pools are gone with the
relocalisation, so the specific entries have gone with them. The method is worth
keeping, because the Australian pools will raise exactly the same questions and
nobody has yet asked them.

The rule that was applied, and should be applied again:

1. **When unsure, leave it out.** A name that might be a dictionary word, a
   deity, a title or a historical figure comes out of the pool. The corpus loses
   very little; shipping the wrong one costs a great deal more.
2. **Record the confidence, not just the decision.** The three entries were
   removed on High, Moderate and Low confidence respectively, and saying so is
   what made the Low one reviewable. A bare list of removals would have hidden
   the weakest call among the strong ones.
3. **Over-correction has a cost too — it is just a less visible one.** The same
   rule argued *against* removing two names whose contemporary use is genuinely
   common, on the grounds that a customer file from that country containing
   nobody of that name would itself be wrong. Stripping every name that any
   reviewer might query produces a bland, unrepresentative corpus, and no check
   will ever flag it.

> [!NOTE]
> **No equivalent adjudication has been carried out on the Australian pools.**
> There is no table here because the work has not been done, not because there
> is nothing to decide. A reviewer for any of the nine non-Anglo pools should
> expect to produce one.

---

## Known limitations

Read these before you rely on a number from this corpus.

1. **Phone numbers are not from a reserved range, and Australia does have
   one.** The UK has Ofcom's `07700 900000–900999` drama block, and the ACMA
   publishes an equivalent list of fictitious numbers for use in radio, film and
   television. **This corpus does not draw from it.** The reserved list holds a
   few hundred numbers; the corpus needs tens of thousands of distinct ones, and
   repeating a handful of reserved numbers across 80,000 people would destroy
   the phone field as a matching signal — which is one of the things the demo is
   for. So the generator instead places mobiles and landlines in number ranges
   chosen to sit away from densely-allocated blocks. That is a mitigation, not a
   guarantee: **a generated number could in principle belong to somebody.** Do
   not dial anything in this corpus, and do not reuse this scheme for anything
   that sends messages. If a future variant needs numbers that are *guaranteed*
   unallocated, the ACMA list is the place to start and the corpus size is the
   thing that will have to give.
2. **`SIBLING_TRAP`'s forename pool is monocultural.**
   `CONFUSABLE_FORENAMES` (in `generate.py`, not the name banks — it is the
   *second* parallel pool, same failure mode as `DIACRITIC_*`) is being rebased
   onto English confusables for this relocalisation: `Jon`/`John`,
   `Steven`/`Stephen`, `Catherine`/`Katherine`, `Sean`/`Shaun` and more of that
   kind. Two things follow, and they pull in opposite directions:
   - **One half of the old defect is genuinely fixed.** The pool previously
     carried `Mohammed`/`Muhammad`, `Aisha`/`Ayesha` and similar, which resolved
     to no group at all because there was no Arabic group to resolve to, and so
     fell back to dominant-pool surnames — producing combinations like
     `Muhammad Anderson`. `ARABIC` now exists as one of the ten groups, so that
     specific fallback no longer applies as described.
   - **The other half is not fixed, and arguably got worse.** An English-only
     confusable pool means that across 100 instances the case **never produces a
     sibling pair from any of the nine non-Anglo groups** — in a corpus where
     those groups are together 38% of the name mix. Confusable-forename
     pairs exist in every one of those naming traditions; none are represented.

   This is cosmetic rather than structural: the case still *works* as a
   `DO_NOT_MERGE` trap. But a reviewer is entitled to ask why the only siblings
   the pipeline is asked to keep apart are Anglo ones. Left unchanged pending a
   decision.

   **Not verified here.** Whether the rebase actually lands as specified is the
   `generate.py` worker's change, not this one. This entry describes the
   intended state.
3. **Exact full-name collisions are common and that is intended.** See
   [Namesakes](#namesakes) above. The rate is driven by finite name banks
   rather than true population frequencies, but every collision is separable
   by city and age.
4. **Small ethnic pools are concentrated.** The `ANGLO` surname pool is large
   enough to keep its top-10 share low; the smallest pools (Filipino and Korean)
   run to a top-10 share an order of magnitude higher, so the same handful of
   surnames recurs within them. Those groups are a few percent of the
   population, so the absolute effect on the corpus is small, but it is visible
   if you slice by group. `TODO(count)`: per-pool sizes and top-10 shares need
   re-measuring on the Australian pools — the previous localisation's figures
   (741 dominant-pool surnames at a 1.8% top-10 share, smallest pools at 33%) do
   **not** carry over, and the flatness rule the pools are built to is max 1.5%
   top-1 and max 10% top-10.
5. **Twelve untagged cross-person email collisions at 200k.** Email drift
   (dots, plus-tags, provider-domain swaps) is reverted when it would land on
   another person's mailbox, but the check is against the *normalised* address
   and a handful still slip through at full scale. Twelve pairs in 80,000
   people. The independent audit reports them as a warning; the 20k config has
   none, so this only shows up at scale.
6. **Household DOB sparsity.** A minority of `HOUSEHOLD` people (116 of 400 at
   200k) carry no DOB on any record, because their records are POS/ecom-only.
   They remain separable by forename initial, but a DOB-dependent rule will not
   split them.
7. **Diminutive coverage is bounded by the bank, not the knob.** Many forenames
   genuinely have no common short form, so the realised rate sits well below
   `--diminutive-rate`.
8. **Two truth assignments are judgement calls.** `SOLE_TRADER` assigns the
   personal and business records to the same `true_person_id`; enrich
   wrong-attribution rows follow the name rather than the address. Both are
   defensible, both are documented in the truth `notes` column, and a scorer
   that disagrees should say so explicitly rather than silently marking them
   wrong.
9. **Sydney is over-represented.** It carries the heaviest city weight in the
   corpus, by a wider margin than its share of the national population, because
   the 18 centres in `banks_places.py` are **urban only** — no rural or remote
   addresses exist in the corpus at all, and around a third of Australians live
   outside the capital cities. Sydney's share *of urban Australia* is much
   closer to its corpus share than its national share is, which is the same
   defence the previous localisation offered, and it is only a partial one. It
   is a skew worth knowing about if you slice by region. `TODO(count)`: the
   realised per-city shares need reading off `manifest.json` once the rebuilt
   `banks_places.py` lands.
10. **Five modules, not one.** The reference data is large enough that keeping
   it in `generate.py` would have made the file unreadable.
11. **There is no cross-field consistency check.** Nothing verifies that a claim
   made in free text agrees with the structured columns on the same record —
   that a stated age matches `dob`, that "my wife" matches the holder's gender,
   or that a quoted loyalty number corresponds to a row in
   `loyalty_members.csv`. Gender and age are now *declared* per body (the `Body`
   class in `text_banks.py`) and filtered at render time, which closes the two
   dimensions that were actually wrong, but it is a constraint system rather
   than a check: it prevents an untagged body from being drawn for an unsuitable
   person, and does nothing about a body whose tags are wrong or absent. See
   [Defect 8](#defect-8-there-is-no-cross-field-consistency-check-and-free-text-is-full-of-checkable-claims)
   for why this class of defect survived every check built so far.
