# Locale specification — Australia

**Status: binding.** This document is the single source of truth for the delocalisation
refactor. Every worker on this change reads it and nothing contradicts it. Where this
document and a source comment disagree, this document wins and the comment gets rewritten.

The corpus was localised to New Zealand: te reo Māori names, macrons, NZ suburbs, NZ
postcodes, `02x` mobiles, NZD. The owner wants it **generic and reusable** — plain
standard English names, Australian formats. Nothing te-reo-specific, nothing NZ-specific.

All data remains **synthetic**. No real person, address, telephone number, email address
or loyalty account is represented anywhere in the corpus.

---

## 0. The three rules that outrank everything else

1. **Determinism.** Seed 42 must produce byte-identical output across runs. Never iterate
   a `set` or `dict` where the iteration order reaches the output. Never introduce
   unseeded randomness. Where a pool is a `set` for membership testing, sort it before
   you iterate it. Fixed strides (`i % len(pool)`, `(i * 7 + 3) % len(pool)`) are fine and
   are used deliberately — leave them alone unless this document says otherwise.

2. **The safety architecture is repointed, never deleted.** The generator has
   `FORBIDDEN_PAIRS`, a reduplication rule, a notable-name roster, `Emitter._vet_pair`,
   and a two-layer output-side sweep that aborts the build. Every one of those survives
   this change with new *contents* and identical *mechanism*. The demo previously risked
   emitting real New Zealanders; it now risks emitting real Australians, Britons and
   Americans. Same failure, different roster.

3. **Reachability, not occurrence.** A notable name not *appearing* in the corpus at seed
   42 proves nothing — it may merely not have been drawn. The property that matters is
   whether the forename × surname **cross product** can compose it. Any check that
   measures occurrence is worthless and must not be written. Any check that measures
   reachability is load-bearing and must be preserved.

---

## 1. Name groups

`PAKEHA` is gone. The dominant group is now `ANGLO`.

### 1.1 Exact group key list — do not add or remove keys without telling the coordinator

```
ANGLO        CHINESE      INDIAN       VIETNAMESE   FILIPINO
ARABIC       GREEK        ITALIAN      KOREAN       SE_ASIAN
```

Ten groups, down from twelve. **Removed:** `MAORI`, `SAMOAN`, `TONGAN`,
`PASIFIKA_OTHER`, `CROATIAN`, `AFRIKAANS`. **Added:** `VIETNAMESE`, `ARABIC`, `GREEK`,
`ITALIAN`. **Renamed:** `PAKEHA` → `ANGLO`.

Rationale for the additions: Arabic (Lebanese), Greek and Italian name stock is a real
and large part of the Australian population and its data; Vietnamese is required because
the `TRANSLITERATION` hard case leans on Vietnamese diacritics and the
`DIACRITIC_VARIANT` case uses `Nguyễn`/`Nguyen`. These are not decoration — two hard
cases stop working without them.

### 1.2 `NAME_GROUP_WEIGHTS` (national default, sums to 1000)

```
ANGLO        620
CHINESE       70
INDIAN        70
ITALIAN       45
GREEK         32
VIETNAMESE    45
ARABIC        40
FILIPINO      30
KOREAN        20
SE_ASIAN      28
```

### 1.3 Region profile keys

The old keys were `DEFAULT`, `AUCKLAND`, `WELLINGTON`, `SOUTH_ISLAND`, `EAST_COAST`.
The new keys are:

```
DEFAULT          national mix (the table above)
METRO_SYDNEY     highest diversity
METRO_MELBOURNE  high diversity, Greek/Italian heavy
METRO_PERTH      Anglo-heavy, some SE Asian
REGIONAL         strongly Anglo
```

Suggested weights (workers may tune, but all five keys must exist and every group key
must appear in every profile):

| group | DEFAULT | METRO_SYDNEY | METRO_MELBOURNE | METRO_PERTH | REGIONAL |
|---|---|---|---|---|---|
| ANGLO | 620 | 470 | 480 | 650 | 820 |
| CHINESE | 70 | 110 | 105 | 60 | 25 |
| INDIAN | 70 | 110 | 90 | 75 | 30 |
| ITALIAN | 45 | 55 | 85 | 40 | 30 |
| GREEK | 32 | 45 | 75 | 20 | 15 |
| VIETNAMESE | 45 | 70 | 70 | 30 | 20 |
| ARABIC | 40 | 75 | 45 | 25 | 15 |
| FILIPINO | 30 | 30 | 20 | 50 | 20 |
| KOREAN | 20 | 20 | 15 | 15 | 10 |
| SE_ASIAN | 28 | 15 | 15 | 35 | 15 |

`CROSS_GROUP_RATE` stays a float around `0.16`. Australian intermarriage rates are in the
same band; keep the value and rewrite the comment so it no longer says "New Zealand".

### 1.4 The `ANGLO` fallback is hardcoded in `generate.py`

`generate.py` falls back to the literal string `"PAKEHA"` in **four** places — the
forename picker, the surname picker, `group_of_surname` and `group_of_forename`
(around lines 1064, 1076, 1081, 1085). All four become `"ANGLO"`. This is a
cross-file dependency between the `banks_names.py` worker and the `generate.py`
worker: **both must make the change or the build dies at import.**

### 1.5 Name content

Forenames and surnames are ordinary standard English names of the kind found across
Australia, the UK and the US for `ANGLO`, and genuinely representative name stock for the
other nine groups. Keep the existing flatness rule: **max 1.5% top-1, max 10% top-10**, so
no single name dominates and the matcher is not solving a trivially skewed distribution.

Keep the weighted-tuple shape `list[tuple[str, int]]` exactly as it is. `banks.py`
`_flatten` and `_reverse` depend on it.

---

## 2. Geography

### 2.1 `CITIES` tuple shape — unchanged

```python
CITIES: list[tuple[str, str, str, list[tuple[str, int]], int]] = [
    (city_name, std_dialling_code, region_profile, [(suburb, postcode), ...], weight),
]
```

`std` was the NZ area code (`'09'`, `'04'`, `'03'`). It is now the Australian area code —
`'02'`, `'03'`, `'07'`, `'08'`. `region_profile` must be one of the five keys in §1.3.

### 2.2 Cities, states, area codes and postcode ranges

| City | State | Area code | Region profile | Postcode range | Weight (rel.) |
|---|---|---|---|---|---|
| Sydney | NSW | 02 | METRO_SYDNEY | 2000–2234, 2745–2770 | highest |
| Melbourne | VIC | 03 | METRO_MELBOURNE | 3000–3207 | high |
| Brisbane | QLD | 07 | REGIONAL* | 4000–4179 | high |
| Perth | WA | 08 | METRO_PERTH | 6000–6175 | medium |
| Adelaide | SA | 08 | REGIONAL* | 5000–5117 | medium |
| Gold Coast | QLD | 07 | REGIONAL | 4207–4230 | medium |
| Canberra | ACT | 02 | REGIONAL | 2600–2618 | low |
| Newcastle | NSW | 02 | REGIONAL | 2280–2305 | low |
| Wollongong | NSW | 02 | REGIONAL | 2500–2530 | low |
| Hobart | TAS | 03 | REGIONAL | 7000–7055 | low |
| Geelong | VIC | 03 | REGIONAL | 3214–3220 | low |
| Townsville | QLD | 07 | REGIONAL | 4810–4818 | low |
| Cairns | QLD | 07 | REGIONAL | 4868–4879 | low |
| **Darwin** | **NT** | **08** | **REGIONAL** | **0800–0832** | **low — see §2.3** |
| Launceston | TAS | 03 | REGIONAL | 7248–7250 | low |
| Toowoomba | QLD | 07 | REGIONAL | 4350–4352 | low |
| Ballarat | VIC | 03 | REGIONAL | 3350–3356 | low |
| Bendigo | VIC | 03 | REGIONAL | 3550–3556 | low |

\* Brisbane and Adelaide are genuinely diverse; assigning them `REGIONAL` is a
simplification made only because five profiles is already enough moving parts. If a
worker prefers to give Brisbane `METRO_SYDNEY`-like weights under a sixth key, say so
first — do not do it silently.

Suburbs must be **real Australian suburb names** paired with their **real postcode** for
that city, exactly as the NZ version did. Aim for a comparable suburb count per city
(Sydney ~55, Melbourne ~45, others 8–30) so address diversity does not collapse.

### 2.3 The leading-zero drift case — load-bearing, do not lose it

Postcodes are stored as integers in the loyalty source, so a leading zero is dropped
natively. That is a deliberate data-quality trap the pipeline must handle, and it is the
**whole reason Darwin is in the city list**.

- NT postcodes are `08xx` (Darwin `0800`, `0810`, `0812`, `0820`, `0828`, `0832`).
- `0812` stored as an integer becomes `812`.
- The loyalty source relies on this format drift. Keep the drift, keep Darwin, and keep
  Darwin's weight non-trivial enough that the case actually fires at 200k. It does not
  need to be large — it needs to be non-zero and reachable.
- ACT `2600–2618` and NSW `2000+` do **not** have leading zeros, so Darwin is the only
  producer of this trap. Removing Darwin silently removes a hard-case signal.

### 2.4 `MACRON_SUBURBS` is deleted

The pool of macronised suburbs (`Ōtāhuhu`/`Otahuhu`, `Ōrākei`/`Orakei`, …) and its
`MACRON_SUBURB_MAP` in `banks.py` go away entirely. See §5 for what replaces the address
half of the diacritic case.

**Also delete the `i % 6` / `subs[i % 20]` reachability workaround.** Defect 4 in the
build-status doc: `address_flavour` only fired when `i % 6 == 0`, so `i` was always even
and `subs[i % 20]` could only ever hit even indices — half the curated pool was
unreachable. The previous session patched around it by indexing on a separate flavour
counter. With `MACRON_SUBURBS` gone, **delete the workaround rather than port it**; the
new address-diacritic slice must index on its own dense counter from the start so the
bug cannot recur. Do not reintroduce an index derived from `i`.

### 2.5 Streets

`STREETS` keeps its `list[tuple[str, int]]` shape. Replace the NZ thoroughfares with
Australian ones. Use the Australian thoroughfare vocabulary: Street, Road, Avenue,
Drive, Court, Place, Crescent, Parade, Terrace, Close, Way, Grove, Esplanade, Circuit,
Boulevard, Lane, Rise, Highway. Street *names* should be ordinary Australian stock
(Wattle, Banksia, Jacaranda, Bourke, Macquarie, Flinders, Sturt, Hume, Gipps, Victoria,
King, Queen, Park, Beach, Station, Church, High, Mill, Railway, …). No Māori street names.

### 2.6 Address shape

```
[unit prefix] <number> <street>, <suburb>  <STATE> <postcode>
```

- Unit prefixes stay as they are (`Flat {n}, `, `Unit {n}, `, `{n}/`) — `{n}/` is
  idiomatic Australian and already present. Replace `Apartment {n}, ` with `Apt {n}, `
  if you like, but it is not required.
- `NAMED_BUILDINGS` should lose anything NZ-specific and gain plausible generic
  Australian apartment-complex names. Invented names only — do not name a real building.
- **State abbreviation is now part of the address.** The `Address` dataclass must carry
  or derive the state. `one_line()` and `street_and_suburb()` must render the Australian
  order: suburb, then state, then postcode. This is a change to `generate.py`'s `Address`
  class, coordinated with `10_land_sources.sql` — see §7.

---

## 3. Telephone

### 3.1 Formats

| Kind | Format | Notes |
|---|---|---|
| Mobile | `04xx xxx xxx` | e.g. `0412 345 678`. Also seen as `0412345678` and `0412-345-678`. |
| Landline | `(0A) xxxx xxxx` | `A` ∈ {2, 3, 7, 8}; e.g. `(08) 9456 7890`. Also `0A xxxx xxxx`. |
| International mobile | `+61 4xx xxx xxx` | **trunk zero dropped** |
| International landline | `+61 A xxxx xxxx` | **trunk zero dropped** |

`MOBILE_PREFIXES` becomes the Australian mobile prefix set: `040`, `041`, `042`, `043`,
`044`, `045`, `046`, `047`, `048`, `049`. Weight them unevenly — `04**` allocation is not
uniform in practice and a flat distribution is a tell.

### 3.2 Trunk-zero handling — this broke once already

The build-status doc records a live pipeline bug: `70_graph.sql` tested a normalised
phone string against a hardcoded NZ constant, and the fix was `'+642'`. **The same
construct exists today and must be repointed, not deleted.**

Normalisation rule, and it must be the same rule in Python and in SQL:

- `0412 345 678` → `+61412345678`
- `+61 412 345 678` → `+61412345678`
- `(08) 9456 7890` → `+61894567890`
- The trunk `0` is **dropped** when the `+61` country code is applied. `+610412…` is
  wrong and is exactly the bug class to watch for.

The mobile test in `70_graph.sql` becomes: normalised number starts with `'+614'`.
Rewrite the comment there — it currently explains NZ `020/021/022/027` prefixes and
which NZ landline regions do not collide. The Australian statement is simpler: mobiles
are `04x`, landline area codes are `2/3/7/8`, so `+614` is unambiguous. **Verify the
claim you write; do not copy the shape of the old sentence.**

---

## 4. Currency

Currency is **AUD**, written `$42.60` (same symbol, so no formatting change).

### 4.1 Column renames — all three sides must agree

| Old | New | Files |
|---|---|---|
| `amount_nzd` | `amount_aud` | `CONTRACT.md`, `generate.py` (×2), `10_land_sources.sql`, `90_downstream.sql` (×4), `generate/README.md` |
| `monetary_nzd` | `monetary_aud` | `90_downstream.sql` (×7) |
| `avg_basket_nzd` | `avg_basket_aud` | `90_downstream.sql` (×2) |
| `avg_spend_nzd` | `avg_spend_aud` | `90_downstream.sql`, **`demo/notebook.ipynb`** |
| `household_spend_nzd` | `household_spend_aud` | `90_downstream.sql` |

`demo/notebook.ipynb` is easy to miss — it names `avg_spend_nzd` in a displayed query
string. It is JSON; edit the string inside the cell, do not reformat the notebook.

---

## 5. Diacritics — the model that replaces macrons

### 5.1 What changes conceptually

The NZ build had a **three-orthography** model for one language: macronised (`Tāmati`),
stripped (`Tamati`), double-vowel (`Taamati`). The double-vowel form is te-reo-specific
and **goes away**.

The Australian model is a **two-orthography** model across many languages: the accented
form and the folded form. Some names additionally have a conventional *transliterated*
third form (`Müller` → `Mueller`) which is **not** recoverable by Unicode normalisation —
that is the direct functional replacement for double-vowel, and it preserves the
"normalisation gets you close, the graph finishes the job" half of the case.

| Accented | NFKD-foldable | Conventional variant |
|---|---|---|
| José | Jose | — |
| Renée | Renee | — |
| Müller | Muller | **Mueller** |
| Nguyễn | Nguyen | — |
| Łukasz | Lukasz | — (Ł is *not* NFKD-foldable — see §5.3) |

### 5.2 Function renames

| Old | New | Behaviour |
|---|---|---|
| `has_macron(s)` | `has_diacritic(s)` | true if NFKD yields any combining mark **or** the string contains a non-foldable Latin letter (§5.3) |
| `strip_macrons(s)` | `fold_diacritics(s)` | NFKD, drop combining marks, then apply the special-case table |
| `double_vowel(s)` | `conventional_variant(s)` | `ü`→`ue`, `ö`→`oe`, `ä`→`ae`, `ß`→`ss`; returns the input unchanged when no rule applies |
| `_MACRON_VOWELS` | *(delete)* | replaced by general NFKD |
| `_STRIP_MACRON_TABLE` | `_FOLD_SPECIAL_TABLE` | now holds only the non-decomposable cases |

`_fold_name()` in `generate.py` (used by `FORBIDDEN_PAIRS`) **already** does general NFKD
+ combining-mark removal + casefold. It is correct and generic. Leave its body alone;
just extend it with the §5.3 special cases so `Łukasz` folds to `lukasz`.

### 5.3 The characters NFKD does not fold — get this right

`Ł ł Ø ø Đ đ Ħ ħ Ŧ ŧ` are **single code points with no canonical decomposition**. NFKD
leaves them untouched. `Æ æ Œ œ ß` likewise.

A fold table must handle these explicitly:

```
ł→l  Ł→L   ø→o  Ø→O   đ→d  Đ→D   ß→ss   æ→ae  Æ→AE   œ→oe  Œ→OE
```

This matters twice over:

1. `Łukasz` is in the `DIACRITIC_VARIANT` pool. Without the special case it folds to
   `Łukasz`, the "normalisation only" half of the case silently stops being solvable by
   normalisation, and the slide becomes a lie.
2. The same gap exists in SQL — see §6.

### 5.4 The NFKD-first ordering is a bug fix. Do not undo it.

`00_setup.sql`'s `fold_macrons` was at one point implemented as a character *deletion*
(strip the accented character) rather than a *fold* (replace it with its base letter).
That was a real defect and it was fixed to NFKD-first. The replacement `fold_diacritics`
**must** keep NFKD-first semantics: decompose, then remove combining marks, then apply
the special-case replacements. Deleting accented characters loses the letter entirely and
breaks matching on exactly the names the case is about.

---

## 6. SQL normalisation UDFs

In `demo/sql/00_setup.sql`:

- `fold_macrons(s)` → **`fold_diacritics(s)`**. Rename every call site. NFKD-first
  (`NORMALIZE(s, NFKD)`, strip combining marks via a `Mn` regex class), then the §5.3
  special-case replacements, then whatever casing the current function applies.
- `norm_name`, `norm_email`, `norm_address` — repoint at `fold_diacritics` and rewrite
  the macron commentary. `norm_address` currently explains that macronised street and
  suburb names lose the letter entirely; that comment describes the *old bug* and must go.
- `norm_postcode` — Australian postcodes are 4 digits, same as NZ, so the digit rule is
  unchanged. **Keep the leading-zero repair** (`812` → `0812`): §2.3 is why it exists.
  Rewrite the comment to say NT rather than NZ.
- `postcode_outward` — the name is retained for pipeline compatibility. The NZ comment
  says "in NZ there is no outward code, so this is the first 2 digits". For Australia the
  first 2 digits are genuinely meaningful (state + region), so the function is unchanged
  but the comment gets *better*, not just different: say that the first digit is the
  state and the first two digits are a regional bucket.
- `norm_phone` — must implement §3.2. Trunk zero dropped under `+61`.

---

## 7. The data contract

`demo/CONTRACT.md`, the generator's actual output, and the column declarations in
`demo/sql/10_land_sources.sql` must agree **column for column**. Three sides, one change.

Changes:

- Delete the `**Locale: New Zealand.**` paragraph. Replace with an Australian equivalent
  that states: 4-digit postcodes with real state ranges, `04xx` mobiles and
  `(02)/(03)/(07)/(08)` landlines, `+61` with trunk zero dropped, addresses carrying
  suburb **and state**, currency AUD, and names drawn from a mix reflecting the
  Australian population.
- `amount_nzd` → `amount_aud` in the `pos_transactions.csv` table.
- The `loyalty_members.csv` `postcode` note currently reads "leading zero stripped
  (`0612` → `612`)". Change the example to `0812` → `812` and say NT.
- The `postcode_outward` note must be rewritten per §6.
- `case_type` is documented as "one of the 15 hard-case codes" — the count stays 15, but
  `MACRON_VARIANT` is now `DIACRITIC_VARIANT` wherever the codes are enumerated.
- **If a worker adds a `state` column to any source**, it must be added to `CONTRACT.md`
  and `10_land_sources.sql` in the same change. The default position is: **do not add a
  state column.** Carry the state inside `address_line1` / the rendered address string,
  exactly as the suburb is carried today. Adding a column is a contract change with
  downstream reach into `20_normalise.sql` and is out of scope unless the coordinator
  says otherwise.

---

## 8. Safety architecture — repointing, item by item

### 8.1 `FORBIDDEN_PAIRS`

Mechanism unchanged: a `set[tuple[str, str]]` of case-folded, diacritic-folded
(forename, surname) pairs, populated from two sources — a short hand-written list of
pairs whose halves are individually innocuous, and the full `NOTABLE_FULL_NAMES` roster
split on the first space.

The NZ seed entries (`Tāne Mahuta`, `Tāne Nui`, `Rangi Nui`) go. The Australian
equivalent — pairs where **neither half is wrong but the combination is** — should be
populated where you can find genuine examples. If you cannot find any that are not
already covered by the roster, **leave the seed loop present with an empty or
near-empty list and a comment explaining what it is for.** Do not delete the loop: it is
the mechanism, and the next person to find such a pair needs somewhere to put it.

### 8.2 The reduplication rule

`_forbidden_pair` blocks any pair whose folded forename equals its folded surname
(`Lin Lin`, `Hōhepa Hōhepa`). This is locale-independent and stays **exactly as it is**.
Do not touch it. It fires on `Thomas Thomas`, `Nguyen Nguyen` and `Mario Mario` in the
new pools just as it did on the old ones.

### 8.3 `NOTABLE_FULL_NAMES`

Rebuild the roster for Australian, British and American public figures. The selection
rule is preserved verbatim in spirit and must be restated in the comment block:

> Block a pair when it is **distinctive and famous** — when an ordinary reader seeing it
> on a screen would think of one specific person. Do **not** block a name merely because
> someone famous happens to have it.

Two exceptions, both carried over:

1. **The crime and miscarriage-of-justice group is blocked regardless of
   distinctiveness.** The harm there is not embarrassment. Australia has its own such
   names and they must be on the list.
2. **Where a diminutive reaches a notable name, block both the diminutive and the
   canonical forename.** Reverting a substitution must not land on the same real person.
   The exception to the exception: if the canonical form is innocuous because the
   *surname* also differs, block only the reachable one.

Categories to cover: federal and state politics (current and recent PMs, premiers,
opposition leaders), sport (cricket, AFL, NRL, tennis, swimming, Olympians), arts and
entertainment (actors, musicians, authors, broadcasters), business, science and
medicine, Indigenous Australian leaders and activists, plus British and American figures
whose names the Anglo pools can reach. Aim for **at least the ~110 entries the NZ roster
carried**; more is better. Include a "not reachable today, listed because one pool edit
would make them so" section — the NZ version had one and it is cheap insurance.

The comment must keep the honest caveat: **this list is not coverage.** Two systematic
passes on the NZ pools found 138 reachable notable names from 461 candidates — a ~30% hit
rate that did not decay, because the binding constraint is the author's recall, not the
pools. The emitted-row sweep is the safety net; the roster is a knowledge artefact.

Also carry over the malformed-entry rule: an entry that does not split into exactly two
parts on the first space is a **hard build failure**, not a warning. A typo in the roster
must not silently fail to block anything.

Australia is a smaller country than the US, so — exactly as the NZ comment observed — a
name is uniquely associated with one public figure more often than it would be in a
larger one. Expect the "distinctive and famous" test to pass more often than it feels
like it should.

### 8.4 `Emitter._vet_pair` and the two-layer output sweep

**Do not touch the mechanism.** It is the single choke point where both halves of a name
are final, after diminutive, `SURNAME_VARIANTS` and typo substitution. All five emission
sites route through it. If a substituted pair is forbidden, the *substitution* is undone
rather than the person renamed.

The two sweep layers are not redundant and both stay:

| Layer | Walks | Catches | Blind to |
|---|---|---|---|
| (a) primary | `em.emitted_names` | anything written to a row, post-substitution | names embedded in free text |
| (b) secondary | `world.people` | transcripts, ticket bodies, truth notes | substitutions |

Both raise `SystemExit` and abort the build. Keep both. Keep the error text's diagnostic
pointer — the one that tells the reader to look at `banks.DIMINUTIVES` and
`banks.SURNAME_VARIANTS` rather than the name banks when the underlying person is
innocuous. That sentence is why the failure is debuggable.

The blind spot this was built to close is real and large: on the NZ pools, 1,439
forenames expanded to 1,654 written forms and 1,435 surnames to 1,528 — 2,064,965 base
pairs against 2,527,312 written pairs, 462,347 of which the person-walking check could
not see. `Jackie Chan` was composed entirely out of the substitution layer from two
halves in no pool at all. The Australian equivalent exists; assume it does.

Keep the `manifest.json` diagnostics `forbidden_pair_unfixable` (must stay 0) and
`ambiguous_name_collision_detail`. A bare count was actively misleading before.

### 8.5 The reachability check

The `notable_reachable` computation — cross-producting roster forenames and surnames
against the *pools* rather than against the corpus — is the check that matters. Preserve
it exactly. It is sorted, which is what keeps it deterministic; do not replace the
`sorted(...)` with a set comprehension.

---

## 9. Brand neutrality

The narrative is a grocery retailer. It must name **no real chain and no real scheme.**

Specifically forbidden anywhere in code, data, prose, SQL or the deck:

> Everyday Rewards · Woolworths · Coles · flybuys · Qantas Frequent Flyer · Velocity ·
> Clubcard · Tesco · Onecard · Nectar · IGA · Aldi · Countdown · New World · Pak'nSave

Refer to it only as a **"loyalty card"** — a common noun. `banks.LOYALTY_PROGRAMME` is
already the string `"loyalty card"`; keep it that way.

`BUSINESS_SUFFIXES` currently contains `"NZ Ltd"`. Replace with `"Pty Ltd"` — and note
that `"Pty Ltd"` is the idiomatic Australian form, so it should probably carry more
weight than `"Ltd"` / `"Limited"`.

Store names, vendor names and building names must all be invented.

---

## 10. The hard case catalogue — 15 cases, 100 instances each

| # | `case_type` | Status |
|---|---|---|
| 1 | `HOUSEHOLD` | unchanged |
| 2 | `SIBLING_TRAP` | unchanged |
| 3 | `MARRIED_NAME` | unchanged |
| 4 | `ACCOUNT_ONLY` | unchanged |
| 5 | `POSTCODE_NEAR_MISS` | unchanged mechanism, AU postcodes |
| 6 | `TRANSLITERATION` | unchanged — pools stay |
| 7 | `SOLE_TRADER` | unchanged |
| 8 | `SHARED_EMAIL` | unchanged |
| 9 | `CONSENT_CONFLICT` | unchanged |
| 10 | `UNSTRUCTURED_ONLY` | unchanged |
| 11 | `RISK_FLAG` | unchanged — **see §11** |
| 12 | `OVERMERGE_BAIT` | unchanged |
| 13 | **`MACRON_VARIANT` → `DIACRITIC_VARIANT`** | **rebased — see §10.1** |
| 14 | `NAME_ORDER` | unchanged — pools stay |
| 15 | `NAME_ORDER_TRAP` | unchanged — pools stay |

`CASE_CODES` is derived from `CASE_CATALOGUE`, so renaming the entry propagates —
**but** the rename must also land in: the `macron_variant()` method name, its call site
in the case runner, `truth/case_catalogue.csv` content, the scorecard SQL if it names
cases, `CONTRACT.md`, `demo/README.md`, `demo/generate/README.md`, `index.html`, and the
verifier scripts. Grep for `MACRON_VARIANT` and `macron_variant` and fix every hit.

### 10.1 `DIACRITIC_VARIANT`

Pools: `MACRON_FORENAMES` / `MACRON_SURNAMES` become `DIACRITIC_FORENAMES` /
`DIACRITIC_SURNAMES`, rebased on accented Latin names genuinely common in Australian
data — José/Jose, Renée/Renee, Müller/Mueller, Nguyễn/Nguyen, Łukasz/Lukasz, and more in
that vein (Zoë, Chloé, Séan, Aisling, Björn, Mikaël, Jörg, Søren, Đặng, Trần, Phạm,
Hoàng, Kowalczyk-style Polish, Muñoz, Ibáñez, García, Fernández, Šimić, Novák, Horváth).

**Keep the deliberate 50/50 split. It is a load-bearing slide.**

- `normalisation_only` half (`i % 2 == 0`): the **only** difference between records is the
  diacritic. Everything else — address, DOB, email, mobile — held identical on purpose.
  Solvable by correct Unicode normalisation and nothing else. The demo's line is "you fix
  this with NFKD, not with a language model", and a regression in name folding must fail
  loudly here.
- The other half carries a second divergence (stale address, missing DOB, diminutive
  forename), so normalisation narrows it and the graph plus adjudicator finish the job.

Within the first half, a slice puts the difference in the **address** rather than the
name, because address normalisation and name normalisation are usually different code
paths and only one of them tends to get tested. With `MACRON_SUBURBS` gone, source that
slice from Australian suburbs that genuinely carry a diacritic or an apostrophe —
e.g. `Coogee`/`Coogeé` is fake and unacceptable, but real options exist: **`Yarralumla`
has none, so use apostrophe and hyphen suburbs** (`O'Connor` ACT/WA, `O'Halloran Hill` SA,
`O'Sullivan Beach` SA, `Kings Langley` vs `King's Langley` as a punctuation drift,
`Coffs Harbour`, `Dandenong North`) **plus genuinely accented locality names**
(`Cañada`-style is wrong for Australia). Honest position: Australia has very few
diacritic place names, so **run the address slice on punctuation and spacing drift
instead of accents** — apostrophe present/absent (`O'Connor` / `OConnor` / `O Connor`),
hyphen present/absent, and `St` / `Saint`. That still exercises the address normalisation
path, which is the point of the slice. State this substitution in the case note and in
the README so nobody thinks the address slice tests accent folding.

Keep the forename/surname pools sharing entries on purpose where it is genuine, and
**keep the deterministic surname-stepping loop** that avoids reduplication when the
fixed stride puts the same word in both halves. That loop exists because both halves are
pinned before `make_person` sees them, so its guard cannot redraw. Port it verbatim,
changing only the pool names.

### 10.2 `CONFUSABLE_FORENAMES`

Rebase on English confusables. The required pairs: **Jon/John, Steven/Stephen,
Catherine/Katherine, Sean/Shaun.** Extend with more of the same kind — Brian/Bryan,
Geoffrey/Jeffrey, Alan/Allan/Allen, Ann/Anne, Lesley/Leslie, Mark/Marc, Neil/Neal,
Philip/Phillip, Rachel/Rachael, Sara/Sarah, Terry/Terrie, Tracy/Tracey, Clare/Claire,
Marion/Marian, Gail/Gayle, Kristen/Kirsten, Carol/Caroline (careful — that is a different
name, not a confusable; do not include it).

Preserve the defect-1 fix: the reverse index resolves a name to its *heaviest* group, so
a pair ordered with the generic name first will draw a surname from the wrong group.
**Order each pair so the group-distinctive name is first.** The probe that asserts each
pair against its section comment is one of the verifier scripts; it must still pass.

---

## 11. `text_banks.py` — the part that must survive untouched

The build-status doc's addendum records that **45 of the 100 `RISK_FLAG` tickets carried
at least one cross-field or internal inconsistency, and all were fixed.** That work is
expensive and easy to destroy with a careless search-and-replace.

**Preserve, in full:**

- The `Body` class and its **gender/age constraint machinery**. `_render_risk_ticket`
  once picked bodies with `rng.choice` and never read `p.gender`; 23 of 46 bodies assert
  a gender, and the result was *"My wife **Tāne Wilson** is dead"* in roughly 29 of 100
  tickets. The constraint tags are the fix.
- Guardian-perspective `MINOR` bodies, where `{age}` is the holder's age and parent-voice
  bodies must not bind it to a third party.
- The ordinal fix (`"the {day}th"` → "the 22th" was wrong in 19.2% of occurrences).
- The `DECEASED 12` before/after day-slot fix.
- The `VULNERABLE` age-agnostic body tagging (holders are 74–92; 11 of 16 bodies were
  age-agnostic, producing a 91-year-old who "lost my job").
- The Change B mechanism where two `MINOR` bodies complain the record holds the wrong
  age and the generator emits a deliberately wrong DOB — **the same value to CRM and
  loyalty**, so no `dob_conflict` is created and the merge rails are untouched.

The text-banks worker's job is **de-NZ-ing the prose only**: currency references, place
names, idiom, `Anzac biscuits` (fine in Australia, actually — but check it reads as
generic grocery stock), and any NZ regulatory or retail vocabulary. Ticket bodies,
transcripts and retail free text keep their structure, their tags and their counts.

Exactly **3 prompt-injection attempts** in ticket bodies. Do not change that number.

---

## 12. Regulatory position — Australia

`index.html` carries an NZ Privacy Act 2020 callout. Replace with the Australian position.
**Verified 15 Sep 2026 against OAIC and Gilbert + Tobin:**

- The governing statute is the **Privacy Act 1988 (Cth)**.
- It contains **13 Australian Privacy Principles (APPs)** in Schedule 1.
- **APP 12** — access to personal information: an individual may request access to the
  personal information an entity holds about them, and the entity must provide it unless
  a specific exception applies.
- **APP 13** — correction of personal information.
- **APP 10** — quality: reasonable steps to ensure personal information is accurate, up
  to date and complete.
- **APP 1** — open and transparent management, including a clearly expressed and current
  APP privacy policy.
- **New APP 1.7–1.9**, introduced by the **Privacy and Other Legislation Amendment Act
  2024** and commencing **10 December 2026**, require an APP entity's privacy policy to
  disclose the kinds of personal information used in substantially automated decisions,
  and the kinds of decisions made solely or substantially by a computer program, where
  those decisions could reasonably be expected to significantly affect an individual's
  rights or interests.

The last point is the strongest version of the existing callout's argument and is
squarely on-narrative for an automated identity-resolution pipeline. The existing line —
*"'The algorithm decided' is not an answer. A rationale string is."* — should be kept; it
is the point of the slide. Keep the comparative sweep to GDPR, DPDP and CCPA.

Do not overstate. APP 1.7–1.9 is a **transparency-in-privacy-policy** obligation, not a
general right to an individual explanation of a specific decision. Write it accurately.

---

## 13. What to leave alone

- `demo/sql/05_preflight.sql`, `20_normalise.sql`, `30_embed.sql`, `40_block.sql`,
  `50_candidates.sql`, `60_adjudicate.sql`, `80_survivorship.sql`, `85_consent.sql`,
  `95_scorecard.sql` — no NZ residue; touch only if a rename reaches them.
- `demo/scenarios/*` — no NZ residue except through column renames.
- `ARCHITECTURE.md` — no NZ residue at all. Verify before editing.
- `demo/TEARDOWN.md`, `demo/config.env.example`, `demo/run.sh`, `demo/setup.sh` — clean.
  Re-grep rather than assume.
- The deck's **external font loading** in `index.html` is a known separate issue and is
  **out of scope**. Do not fix it, do not vendor fonts, do not mention it as done.
- Anything to do with GCP. No `config.env`, no `bq`/`gcloud`/`gsutil`, no SQL execution,
  no `git`.
- Model IDs, cost-model unit prices, `CDP_MAX_BLOCK_SIZE`, `CDP_GREYZONE_CAP` — all
  unrelated to locale.

---

## 14. Residue grep — the acceptance test

The whole edited tree must come back clean on, case-insensitively:

```
NZ · New Zealand · Māori · maori · macron · nzd · Auckland · Wellington ·
Christchurch · Ponsonby · +64 · te reo · iwi · atua · Aotearoa · Pākehā · Pasifika
```

Two known false-positive shapes to expect and to report rather than "fix":

- `iwi` matches inside other words (e.g. `kiwifruit`, and any identifier containing the
  letter run). Check each hit.
- `nz` matches inside `Anzac`. `Anzac biscuits` in `text_banks.py` is an Australian
  grocery item and is **legitimate**; report it as a deliberate survivor if it stays.
