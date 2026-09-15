# `demo/generate/checks/`

Verification scripts for the synthetic-corpus generator. They were previously
stranded in a scratch directory outside the repository, which meant the only
evidence that the safety guards work was not version-controlled and not
runnable by anyone else. They now live here, resolve every path relative to
this file, and take no absolute paths.

None of these scripts touch GCP. No `bq`, no `gcloud`, no SQL execution, no
network.

---

## The honesty rule these scripts are written to

> A check that is green because the code is right, and a check that is green
> because the input never exercised it, look identical from the outside.

This project has shipped three vacuous-but-green checks already. The ordinal
check saw 3 occurrences at 8k. The first holder-gender check examined **1
ticket out of 45**. The first emitted-name sweep asserted "no injected name
written to any row" against a 4k corpus and passed with zero reverts —
because the pairs were simply never drawn.

Two habits prevent this, and every script here follows them:

1. **Report how many items the check actually examined**, alongside the
   verdict. `0 mismatches` is not a claim; `0 mismatches over 38 assertions`
   is.
2. **Run a negative control before believing a zero.** Break the thing
   deliberately and confirm the check notices. A check that cannot fail
   proves nothing.

And the rule that outranks both, from `LOCALE-SPEC.md` §0.3:

> **Reachability, not occurrence.** A notable name not *appearing* in the
> corpus at seed 42 proves nothing — it may merely not have been drawn. The
> property that matters is whether the forename × surname **cross product**
> can compose it.

Where a script measures occurrence anyway, it does so as a **second opinion**
that reads files on disk rather than objects in memory — so it would catch a
defect in the writer as well as one in the generator — and it says in its own
output that a clean result is not evidence.

---

## The scripts

### `check_corpus.py` — post-generation sweep over `demo/data`

**Proves.** (1a) No banned token is present in any name pool — nation and
language-group names, sacred and Dreaming terms, and the handful of surnames
that identify one public figure on their own. This is a *reachability*
assertion: a token either is in a pool or it is not. (7a) Every roster name
the pools can **compose** is blocked by `_forbidden_pair`, and every roster
entry splits into exactly two parts on the first space. Also: `record_id`
uniqueness across the record-minting files, no reduplicated forename/surname
pairs, `SIBLING_TRAP` forename spread including accented forms, curated
`PUNCTUATION_SUBURBS` coverage in `DIACRITIC_VARIANT` addresses, manifest
sanity.

**Does not prove.** Checks 1b and 7b are occurrence sweeps over the emitted
rows. A hit is a real defect; a miss proves nothing and says so in its own
output. The `PUNCTUATION_SUBURBS` coverage check is a *warning* when coverage
collapses to under half the pool, not a failure — that shape is the defect-4
signature (an address slice indexed on `i` rather than on its own dense
counter), and it needs a human to look at the stride rather than a red build.

**Negative controls.** 1a injects a sentinel token known to be in a pool and
confirms the detector sees it. 7a composes a reachable non-roster pair and
confirms the predicate reports it as unblocked.

```
python3 demo/generate/checks/check_corpus.py [--data-dir DIR] [--generate-dir DIR]
```

---

### `check_emitted_sweep.py` — the emission-time name guard

This is the one that matters. `Person` is the **input** to emission, not the
output: the emitter substitutes a diminutive, a `SURNAME_VARIANTS` entry or a
typo afterwards, so a person named `Robert Hawke` is written to a CRM row as
`Bob Hawke` — a former Prime Minister — and a sweep that walks `world.people`
never sees it.

**Proves.** Section 3 is a **deterministic unit test**. It constructs the
forbidden pair *by hand* and asserts `Emitter._vet_pair` fires. It does not
draw, sample or generate anything, so it cannot pass vacuously. Specifically:

- every live substitution path derived from the pools and the roster reverts,
  the reverted result is not itself forbidden, and the forbidden pair is never
  recorded as emitted;
- the **both-forms-blocked backstop**: `Bob Hawke` ← `Robert Hawke`, where the
  roster blocks the diminutive *and* the canonical form, so there is no legal
  fallback. The designed behaviour is to count it as unfixable and let the
  build-time sweep fail the build — not to silently emit, and not to rename
  the person. This doubles as a conformance test on the roster: LOCALE-SPEC
  §8.3 exception 2 requires both forms to be blocked. If the roster in the
  assembled tree blocks a different pair, the script says so and derives a
  both-blocked pair from the roster so the backstop is still exercised.

**Does not prove.** Section 4 regenerates a small corpus with names injected
into the roster and scans the output. It is an end-to-end smoke test, **not**
proof. Its first version passed with `emitted_name_reverts = 0` because the
injected pairs were never drawn at 4k. It is kept because a *hit* would be a
real defect, and it now prints the number of rows examined so a clean result
cannot be misread. `emitted_name_reverts = 0` on the live corpus is likewise
**not** evidence the guard works — there are only a handful of blocked pairs a
legal person can substitute into, and those people may not exist in the
corpus. Section 3 is what proves the mechanism.

**Negative control.** An innocuous substitution (`Maggie Walsh` ←
`Margaret Walsh`) must pass through untouched. A guard that reverted
everything would satisfy every other assertion in the file.

```
python3 demo/generate/checks/check_emitted_sweep.py [--skip-end-to-end]
python3 demo/generate/checks/check_emitted_sweep.py --people 4000 --records 10000
```

`--skip-end-to-end` runs only the deterministic sections, which need no corpus
and take seconds. Use it in `run_all.sh`-style gating; run the full script
before a demo.

---

### `notable_full_names.py` — roster audit

**Proves.** Structural rules on `NOTABLE_FULL_NAMES` (imported from
`generate.py`, never copied): exactly two parts per entry, no duplicates, at
least the ~110 entries LOCALE-SPEC §8.3 asks for, no silent shrink against an
optional baseline. Then the load-bearing part: which entries the pools can
**compose** (including the substitution layer), that every reachable entry is
blocked, and that no entry blocks a diminutive while leaving the canonical
forename open — same surname means the same person, so reverting must not land
on them.

**Does not prove.** **The roster is not coverage and this audit cannot make it
one.** Two systematic passes over the previous locale's pools found 138
reachable notable names from 461 candidates — a ~30% hit rate that did not
decay between passes, because the binding constraint is the author's recall of
public life, not the pools. A roster that passes every check here is only as
complete as the person who wrote it.

`--candidates FILE` takes one `Forename Surname` per line and reports which
are reachable and which of those are missing from the roster. That is how the
roster gets extended; record the hit rate each pass.

```
python3 demo/generate/checks/notable_full_names.py [--verbose]
python3 demo/generate/checks/notable_full_names.py --candidates candidates.txt
python3 demo/generate/checks/notable_full_names.py --write-baseline roster.txt
python3 demo/generate/checks/notable_full_names.py --baseline roster.txt
```

---

### `check_confusables.py` — `CONFUSABLE_FORENAMES` vs the group pools

**Proves.** Every `fn_a` in the literal resolves through
`World.group_of_forename` to a group consistent with the section comment it
sits under, and its declared gender matches the pool it was found in.
`FORENAME_GROUP` is a *reverse* index resolving to the **heaviest** group, so
a pair ordered with the generic name first draws the shared `SIBLING_TRAP`
surname from the wrong bank — that is defect 1, and LOCALE-SPEC §10.2 requires
the group-distinctive name to come first. The script also fails loudly if its
`SECTION_TO_GROUPS` table and `banks.SURNAMES_BY_GROUP` have drifted apart.

**Does not prove.** That the pairs are *good* confusables, that `fn_b` is
spelled correctly, or that either name is ever drawn. It reads the source
literal and the pools; it never reads the corpus.

**Negative control.** Asserts the first pair against a group it does not
resolve to and confirms the comparison flags it.

```
python3 demo/generate/checks/check_confusables.py [--generate-dir DIR]
```

---

### `check_body_tags.py` — risk-bank tags vs their own prose

This and `check_holder_gender.py` are the regression test for the
`text_banks.py` work in which **45 of 100 `RISK_FLAG` tickets** carried a
cross-field or internal inconsistency. The `Body` gender/age constraint
machinery is the fix. Keep every assertion in these two files.

**Proves.** For every body whose holder-scope referent the rule can resolve,
the declared `gender` tag agrees with the body's own text, and a body using
age-implying language carries a `min_age`. The referent rule matters: a first
version compared gendered words to the tag and reported 10 failures, every
one of them wrong — "my mum", "my dad", "my brother" are gendered **third
parties**, not the account holder. That is the same blind spot as the defect
this project is about: detecting a value without binding it to a person.

**Does not prove.** That the tags are complete. That `_body_fits` honours them
— near-tautological, deliberately untested. That any of these bodies reaches
the corpus: this reads `text_banks.py`, not `demo/data`. Anything the referent
rule cannot resolve is reported as `ADJUDICATE`, not silently counted either
way; roughly six bodies genuinely need a human ("my husband's grocery
account" — is the holder the husband?).

**Negative control.** Inverts every declared gender and asserts the check
detects **N of N** judgeable bodies. If it judges zero, it says so.

```
python3 demo/generate/checks/check_body_tags.py [--verbose]
```

---

### `check_holder_gender.py` — end-to-end holder gender

**Proves.** For every `RISK_FLAG` `DECEASED`/`VULNERABLE` ticket in the corpus
where the holder's gender resolves from their forename via the generator's own
pools *and* the body carries an unambiguous gender signal, the two agree. This
is deliberately independent of the mechanism: `_body_fits` honouring a
`gender` attribute is near-tautological; what matters is whether the text that
reached the corpus agrees with the person it was written about.

**Does not prove.** Anything about `MINOR` tickets — skipped on purpose, they
are first-person from the minor and their gendered language refers to third
parties. Anything about tickets it could not resolve. And **nothing at all if
`checked` is small**: an earlier version resolved gender from the CRM `title`
and examined one ticket out of 45. The script prints the assertion count and
warns below 20.

**Negative control.** `--negative-control` inverts the gender lookup; every
assertion that passes on the real lookup must then fail, and the run reports
N/N detected. The reference run reported **38 assertions checked, 0
mismatches** and **38/38 detected when inverted**.

```
python3 demo/generate/checks/check_holder_gender.py [--data-dir DIR]
python3 demo/generate/checks/check_holder_gender.py --negative-control
```

---

### `verify_corpus_fixes.py` — ticket prose regressions

**Proves.** Reads `support_tickets.parquet` **properly** — the file is
snappy-compressed, so a `grep` returning 0 over `demo/data/` is not evidence
of anything. Asserts no real retail brand or loyalty scheme appears
(LOCALE-SPEC §9), no England-and-Wales or UK-only legal/administrative
vocabulary, no bare decimal amount without a `$`, no doubled preposition in
the power-of-attorney phrasing, and no hardcoded age in prose. Each absence
check is paired with a presence check on the replacement text, so a PASS
requires positive evidence.

**Does not prove.** The presence assertions are a **contract with
`text_banks.py`**. `(personal matters)` is the Australian statutory wording
(Powers of Attorney Act 1998 (Qld) — an attorney may be appointed for
financial, personal and health matters; personal matters are the principal's
care or welfare). If the text-banks worker chooses different wording, **update
this file in the same change** — do not soften the assertion. A positive that
never matches is how a check goes quietly vacuous. The sensitive-bank coverage
block at the end is informational counts only; it asserts nothing.

**Negative control.** Runs the same detector machinery over a synthetic blob
containing every forbidden string and pattern, and fails if any of them is not
caught. An absence assertion passes for two different reasons — the string was
removed, or the string was never there — and this separates them.

```
python3 demo/generate/checks/verify_corpus_fixes.py [--data-dir DIR]
```

---

### `check_preflight.py` — structural lint on `05_preflight.sql`

Locale-neutral. Reads structure, not content.

**Proves.** Balanced parentheses outside string literals, no unterminated
string, exactly one definition per created object, and every `${CDP_*}` token
referenced is in `run.sh`'s `VARS` allowlist — so it renders rather than
expanding to an empty string and reaching BigQuery as a literal `${...}`.

**Does not prove.** That BigQuery accepts any of it. The `AI.CLASSIFY`
signature in particular is unverifiable without a project. **No SQL in this
repository has ever been executed against BigQuery.** Do not read a PASS here
as "the preflight stage works".

**Negative control.** Runs the paren and string scanners over deliberately
malformed SQL and confirms both report it.

```
python3 demo/generate/checks/check_preflight.py [--demo-dir DIR]
```

---

### `compare_runs.py` — determinism gate

Locale-neutral. Compares bytes; never reads a name, an address or an amount.

**Proves.** Two generator runs at the same seed produced byte-identical
output — LOCALE-SPEC §0.1. When a Parquet file differs it decodes it and
reports *which* rows and columns differ, because "files differ" is not
diagnosable for a compressed container. `manifest.json` is compared with its
wall-clock timestamp key removed rather than excluded outright, so a real
change in row counts still shows up. `call_transcripts/` is compared as a
name→sha256 map so an added file is distinguishable from a changed one.

**Does not prove.** That the output is *correct*. That determinism holds at a
different seed or scale. It also cannot see non-determinism that happens to be
stable within one machine and Python build.

Run the two generations **serially**. The one historical failure of this gate
was a concurrent-edit race between two runs sharing a tree, not a generator
defect.

```
python3 demo/generate/checks/compare_runs.py DIR_A DIR_B
```

---

## `run_all.sh`

Runs the checks in dependency order and exits non-zero on the first failure.

```
bash demo/generate/checks/run_all.sh            # static checks only, no corpus needed
bash demo/generate/checks/run_all.sh --full     # adds the corpus-dependent checks
```

The default set needs only `demo/generate/` to import. `--full` additionally
needs a generated corpus in `demo/data/` and `pyarrow` installed. The
determinism gate is not in either set because it needs two output directories;
run it explicitly.

---

## What was deliberately not brought across

**`splice_roster.py`** — dropped. It was a one-shot migration tool that
rewrote the `NOTABLE_FULL_NAMES` block inside `generate.py` in place, anchored
on a literal comment line that no longer exists, and read its input from an
absolute path in a scratch directory. It is a *mutator*, not a check, and a
script that rewrites `generate.py` does not belong in a directory people run
to find out whether something is broken. Its one worthwhile property — refusing
to drop an entry that was previously blocked — survives as
`notable_full_names.py --baseline`.
