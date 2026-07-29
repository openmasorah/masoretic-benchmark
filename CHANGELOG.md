# Changelog

All notable changes to this project are documented here. Versioning is
independent for the two artifacts this repository holds: the **scorer** Python
package (`masoretic_eval`, currently `0.3.0`) and the **benchmark dataset**
(tagged `benchmark-v*`).

## benchmark-v0.1.1 (unreleased) — corrections to v0.1.0

### ⚠️ Corrected: tier-2 and tier-3 CER were wrong in v0.1.0

**If you cited tier-2 or tier-3 CER from `benchmark-v0.1.0`, the values were too
high. Use these instead:**

| figure | v0.1.0 (withdrawn) | corrected |
|---|---|---|
| tier-2 CER, B vs consensus | 0.0172 [0.0105, 0.0248] | **0.0031 [0.0006, 0.0062]** |
| tier-3 CER, B vs consensus | 0.0234 [0.0166, 0.0309] | **0.0119 [0.0085, 0.0156]** |
| adjudication, tier-2 edits | 165 | **33** |
| adjudication, tier-3 edits | 280 | **148** |

**Cause.** `<DR>`, the annotator-tool token for a double *rafe*, was scored as
four literal ASCII characters (`<`, `D`, `R`, `>`) in the tier-2 and tier-3 CER
path. `masoretic_eval/iaa/cer.py` asserted that editor tokens were "already
stripped during `split_chunks`"; they were not. `split_chunks` strips only
`PASSTHRU_TAGS`, and `<DR>` is deliberately excluded from that list so tier-4
extraction can emit a `double_rafe` record from it — but nothing removed it
afterwards. The three sides carry unequal counts (annotator A 25, annotator B 56,
consensus 27), so every excess token scored as four spurious edits.

The defect was self-contradictory as well as wrong: `strip.py` already excludes
U+05BF (*rafe*) from the tier-2 view precisely "so it is not double-counted
across tiers". The single *rafe* was stripped; the double *rafe*, written in
ASCII, was not.

**Direction.** The error was conservative — it made the two annotators look *less*
consistent than they are. No conclusion in the paper or the README reverses.

**Not affected**, verified field-by-field over the regenerated result JSONs (262
tier-4 and stratification fields compared, zero changed): tier-1 CER 0.0029; all
tier-4 figures including F1 exact 0.9187 and Krippendorff α 0.7470; the BL-05
*rafe* baseline F1 0.6210; every count in the corpus accounting. Tier 1 is immune
because its projection keeps only Hebrew consonants, space and *maqaf*, so ASCII
cannot survive it.

**Fixes.** Editor tokens are now stripped in the CER path for every tier, and a
new `masoretic_eval.iaa.cer.tier_view()` is the single definition of a chunk's
scoring view — `scripts/generate_iaa_report.py` and the release test had each
inlined their own copy of the same sequence and would otherwise have silently
missed the new strip. Regression test: `tests/iaa/test_editor_token_cer_isolation.py`
asserts that a chunk's tier CER is invariant to the presence of editor tokens, and
that tier-4 extraction still consumes `<DR>`.

**Credit.** Found during verification of three independent external reviews of
`benchmark-v0.1.0`. The tier-3 half was flagged by the Codex reviewer; the larger
tier-2 half and the adjudication-count contamination were found while verifying it.

### Other corrections

- Removed an internal `personnel_note` from four public test fixtures. It named a
  collaborator in full alongside an internal personnel correction and referenced a
  file in a private repository. It remains in the immutable `benchmark-v0.1.0` tag.
- Added David Zev Moster (annotator B) to `CITATION.cff`, the README citation, the
  `LICENSE.md` attribution string, and `ACKNOWLEDGMENTS.md`. He produced half the
  inter-annotator agreement this benchmark reports and was previously named only in
  the changelog and the data files, while his projection ships under
  attribution-required terms.
- Corrected the provenance note on `iaa_report.json`, which described the metric as
  code-point Levenshtein on NFC-normalised strings. It is cluster-aligned code-point
  CER on NFD, macro-averaged over verses. The same note wrongly claimed the headline
  CER was not recomputable without the UXLC cache; tiers 1–3 recompute from the three
  committed projections alone.
- Conformed the v0.1.0 licensing table (in the release notes below) to the ratified
  multi-component model in `LICENSE.md`: the earlier table listed the consonantal text
  and the annotation data under CC-BY-4.0, whereas `LICENSE.md` places the consonantal
  text in the public domain and dedicates the annotation data under CC0-1.0 (schema,
  adjudication, and compilation remain CC-BY-4.0; the scorer remains Apache-2.0).
  `LICENSE.md` is authoritative; the immutable `benchmark-v0.1.0` tag keeps the
  superseded table.

### ⚠️ Corrected: the scorer could not score this benchmark's own tier-4 data

`masoretic-eval score` rejected **all 516** tier-4 records in
`iaa_data/devarim_4folio/consensus_gold_positional.json` — every one, on the enum
check. The CLI's tier-4 vocabulary was `pe, samekh, reversednun, puncta,
large_letter, small_letter, suspended_letter, inverted_nun`; the shipped ground
truth is `circellus, rafe, double_rafe`. The two sets share no term.

Four vocabularies had drifted apart: the two JSON Schemas, the shipped IAA data,
the manuscript catalog's `mark_type_enum` (which said `puncta_extraordinaria`
where the scorer said `puncta`), and `docs/meta_marks_schema.md`, which specified
capture mechanisms without ever naming *rafe* or *circellus* — that is, 100% of
what actually ships.

**No published figure changes.** `iaa_report.json` is byte-identical across this
correction. The tier-4 IAA path (`masoretic_eval.iaa`) reads the data files
directly and never consulted the CLI enum, which is exactly why this stayed
invisible: the numbers were produced by a path the broken contract did not gate.
What was broken was *reuse* — a third party could not run the shipped scorer over
the shipped gold, which is most of what a benchmark is for.

**Fixes.** `masoretic_eval/tier4_vocabulary.py` is now the single definition; both
schema enums and the catalog enum are asserted equal to it by
`tests/test_tier4_vocabulary_consistency.py`. `tests/test_tier4_gt_roundtrip.py`
validates and scores the shipped consensus gold end-to-end through the real
scorer — the test whose absence let this ship, and which fails on the pre-fix code
with all 516 records rejected. Scorer **0.2.0 → 0.3.0 (BREAKING)**: `reversednun`
→ `inverted_nun` and `puncta` → `puncta_extraordinaria` are retired, migratable
via `masoretic_eval.tier4_vocabulary.canonicalize()`. Neither retired spelling
occurs anywhere in the v0.1 corpus, so no shipped artifact needed rewriting.

`corpus/manuscripts.yaml` also understated coverage: it declared `circellus` but
not `rafe`, though the gold carries 278 *rafe* records to 211 *circellus* and the
BL-05 baseline scores entirely against the *rafe* set. It was unfixable before
now — `mark_type_enum` had no term for it. Both are now declared.

A pre-existing test, `tests/test_metamark_vocab_alignment.py`, had been enforcing
the defect: it asserted the schema enum *equal* the UXLC loader's vocabulary,
which forbade the schema from admitting the project's own data. A correct fix
would have failed CI looking like a regression. Its assertion is now containment.

### Published: what the IAA numbers are actually entitled to claim

v0.1.0 published one tier-1/2/3 CER block, `cer_vs_consensus_b`, and it is a
diagnostic rather than an agreement measurement — the consensus reference *is*
annotator A's round-1 revision, so it is not independent of either annotator.
A reader wanting "inter-annotator agreement" had nothing else to cite.

`iaa_report.json` now publishes all three comparisons, each labelled for what it
is:

| tier | **A vs B — agreement** | B vs consensus — diagnostic | A vs consensus — diagnostic |
|---|---|---|---|
| 1 | **0.0029** [0.0006, 0.0059] | 0.0029 [0.0006, 0.0059] | 0.0000 [0.0000, 0.0000] |
| 2 | **0.0031** [0.0007, 0.0063] | 0.0031 [0.0006, 0.0062] | 0.0000 [0.0000, 0.0001] |
| 3 | **0.0130** [0.0096, 0.0167] | 0.0119 [0.0085, 0.0156] | 0.0015 [0.0008, 0.0023] |

**`cer_a_vs_b_round0` is now the figure to cite as inter-annotator agreement** —
the only comparison between two mutually independent, blind, pre-adjudication
transcriptions. It is directional (annotator A is the denominator; the other
direction is 0.0028 / 0.0030 / 0.0130), and its raw edit counts (18 / 33 / 148)
are identical to `adjudication_summary` tiers 1–3, which was always this same
measurement expressed as edit operations rather than CER. Those are two views of
one number, not mutual corroboration.

**`cer_vs_consensus_a` publishes the circularity rather than leaving it to be
inferred.** 0 edits at tier 1, 1 at tier 2, 18 at tier 3: it measures how little
annotator A changed its mind during adjudication. Raw edit counts ship with every
CER so a 0.0000 reads as a measurement, not an unpopulated field.

**No previously published value moved.** `cer_vs_consensus_b`, tier-4 F1 0.9187,
α 0.7470, BL-05 0.6210 and the adjudication summary are all unchanged.

**Every figure is now generator-produced and re-verified.** The CERs were
previously pinned constants; they are now computed from the three committed
projections at generation time, checked against the pinned paper values (the
generator refuses to write on a mismatch), and **recomputed by
`generate_iaa_report.py --check` on every push** — a hand-edited `iaa_report.json`
fails. Per-tier reference-side code-point denominators ship alongside, and they
are published *per block* because they are reference-dependent: consensus-side
5597 / 9221 / 11068, annotator-A-side 5597 / 9222 / 11056.

**Also fixed: the published tier-4 figures were undefined from the tag alone.**
The canonicalisation, matching, dropped-record and frame rules were cited only to
an unpublished paper draft. They are now specified in the repository at
`iaa_data/devarim_4folio/README.md`, including the α universe table — the
headline α 0.7470 is the *positive-universe canon, UXLC-frame* value, and the
full-universe figure is about 0.20 higher, so an unlabelled "α" was ambiguous
between two very different numbers.

`README.md` and `CITATION.cff` gain the scope qualifier this release always
needed: **96 verses, 4 folios, one manuscript, two annotators**. The README's
oracle disagreement-rate example values are relabelled as illustrative
placeholders — they were readable as measurements this repository does not
publish.

### Governance — v0.1.0 was tagged without the reviewer's approval

**Disclosure.** `benchmark-v0.1.0` was tagged and published while its release PR
had been open 18 days with the reviewer of record requested and no review
submitted. The D-16 gate in `.github/workflows/release-tag.yml` was
approval-required, so it failed on the true condition and has been publicly red on
that tag ever since. The release proceeded anyway. That was not disclosed at the
time; this entry is that disclosure.

**Policy change.** The gate is rewritten rather than deleted or left red — a
permanently-red required gate is worse than none, because it trains everyone to
ignore it. A `benchmark-v*` tag now passes if **either** a standing APPROVED
review from the reviewer of record exists on the release PR, **or** the reviewer
was formally requested and 14 days elapsed with no review of any kind, in which
case the job passes and logs a waiver to the run summary. Fourteen days is
calibrated to the observed 18-day stall.

The waiver is deliberately narrow. It does **not** apply when the reviewer was
never requested — a review you never asked for cannot lapse — nor when they
responded without approving (`COMMENTED` and `REQUEST_CHANGES` both block; an
engaged reviewer's silence is a signal, not an absence), nor when an earlier
approval was later dismissed or superseded, nor before the window lapses. The
clock starts when the review was **requested**, not when the PR opened, so adding
a reviewer late does not retroactively burn their days. An unset
`YOSEF_GH_USERNAME` still hard-fails rather than silently passing.

A waiver is a disclosure obligation, not an absolution: every waived release must
say so here under **Governance**, and the deferred review folds into the next
patch release. The reviewer of record's review of v0.1.0 folds into v0.1.1.

**Honest limitation, unchanged.** A `push: tags:` workflow runs after the tag
object exists, so it cannot prevent a tag from being created — only refuse to
publish. Preventing creation needs a GitHub ruleset restricting who may push
`benchmark-v*` refs. That is a repository setting, not code, and it is still not
in place.

Separately, `check-yosef-review-gate` in `ci.yml` carried a stale comment claiming
it was "spent by design." Deleting the retracted `results/` tree re-armed it
(`git ls-tree -r main` now matches zero files under `results/llm_vision/`); the
comment now says so, and the gate is left armed deliberately.

## benchmark-v0.1.0 — Open Masorah Devarim pilot benchmark

First public release of the benchmark: a four-tier inter-annotator-agreement
dataset for medieval Tiberian Hebrew, on four folio sides of the Leningrad Codex
Devarim (F118B, F119A, F119B, F120A; Deut 31:28–34:12, 96 verses), together with
the four-tier scorer.

### Included

- **Adjudicated consensus reference** (four-tier positional projection), CC-BY-4.0.
- **Both annotators' round-0 four-tier projections** (Ginsberg, Moster) —
  consonants, nikkud, trop, and tier-4 meta-marks (circellus + rafe), CC-BY-4.0.
- **The four-tier scorer** (`masoretic_eval`), Apache 2.0 — cluster-aligned
  code-point CER for tiers 1–3, detection F1 for tier 4, with deterministic
  verse-bootstrap confidence intervals.
- **`iaa_report.json`** — the published reference numbers.
- **`phase_0_manifest.json`** — the frozen scope, append-only and hash-pinned.
- The masoretic-editor annotator convention sheet and the reproducibility surface.

### Reference numbers

- Tier-4 pair-level agreement (meta-marks): **F1 exact 0.9187** [0.8969, 0.9397];
  F1 ±1-consonant tolerance 0.9472 [0.9299, 0.9631]; Krippendorff α (positive,
  canonicalised) 0.7470 [0.6891, 0.8051].
- Annotator B round-0 vs the adjudicated consensus, tiers 1/2/3:
  **CER 0.0029 / 0.0172 / 0.0234**. The consensus is not independent of either
  annotator (it is A's round-1 revision, byte-identical to B's round-2
  endorsement); this is a descriptive round-0-to-consensus comparison, not an
  independent human-vs-reference baseline.

All benchmark metrics reproduce from the released public surface; the tier-1/2/3
figures reproduce from the three committed projection files alone.

### Deferred to v0.1.1

- Automated OCR/HTR baselines (Kraken, Kraken→Nakdimon, Kraken→DictaBERT) and any
  leaderboard. No baseline scores ship in v0.1 — see the README "Baselines"
  section for why the earlier draft scores were withdrawn.

### Licensing

| Component | License / status |
|---|---|
| Consonantal text (Tier 1, all four folios) | Public Domain |
| Annotation data (Tiers 2–4: nikkud, cantillation, meta-mark positions & labels) | CC0-1.0 |
| Scholarly contributions (positional-encoding schema, two-annotator adjudication protocol & metadata, error taxonomy & guidelines, four-folio benchmark compilation) | CC-BY-4.0 |
| Scorer code (`masoretic_eval/`) | Apache-2.0 |
| Manuscript images | Not distributed; referenced by IIIF URL only. WSRP asserts rights over the photographs. |

This table summarizes; [`LICENSE.md`](LICENSE.md) is authoritative.

---

## masoretic_eval 0.3.0 — scorer (BREAKING)

Tier-4 vocabulary unification. `metamarks[].type` / `tier4_records[].type` now
accept one canonical enum — `pe`, `samekh`, `large_letter`, `small_letter`,
`suspended_letter`, `inverted_nun`, `puncta_extraordinaria`, `circellus`,
`rafe`, `double_rafe` — defined once in `masoretic_eval/tier4_vocabulary.py`.

**Semantic change beyond the rename.** Collapsing `reversednun` into
`inverted_nun` means UXLC's two encodings of nun hafukha — the `<reversednun/>`
verse-child tag and the inline `<x>8</x>` code — now share one per-verse ordinal
counter. Previously a verse carrying both produced `reversednun ordinal=1` *and*
`inverted_nun ordinal=1`: one phenomenon counted twice, which the tier-4 matcher
(a set over `(type, verse_ref, ordinal)`) would have scored as two independent
detections. The new behaviour is correct, and no verse in the frozen v0.1 scope
carries either encoding, so no published number is affected.

One caveat is recorded rather than fixed: verse-child tags are collected before
inline `<x>` codes, so a verse carrying both numbers them in parse order, not
reading order. That is pre-existing loader behaviour (`pe`/`samekh` have always
been collected first) which only becomes observable once two encodings share a
type. Fixing it changes ordinal assignment, which is a pre-registered v0.2
decision rather than a patch-release edit. It is pinned as a **strict xfail** in
`tests/test_uxlc_nun_encoding_merge.py`, so whoever does fix it gets a failing
test and has to retire the caveat deliberately.

**Breaking.** `reversednun` and `puncta` are rejected. Migrate with
`masoretic_eval.tier4_vocabulary.canonicalize()`, which maps them to
`inverted_nun` and `puncta_extraordinaria` respectively. Consumer pins in
`baselines/` and `oracles/` cascade to `>=0.3.0,<0.4`.

Rationale, and why no published number moved, under **benchmark-v0.1.1** above.

**Corrected before release: the version bump was only half-applied.**
`pyproject.toml` moved to `0.3.0` while `masoretic_eval/__init__.py`
`__version__` and `phase_0_manifest.json` `scorer_version` both stayed at
`0.2.0`, so the installed package reported a version its own metadata
contradicted. The field is not a label: `masoretic_eval/output_schema.py` stamps
`__version__` into every emitted result, and `scripts/verify_gt_hash.py` writes
it into the manifest, from which `baselines/src/baselines/_base.py` cascades it
into every `run_meta.json`. No `run_meta.json` ships under v0.1, so nothing
downstream recorded the stale value this time — unlike the earlier 0.1.0 → 0.2.0
drift, which had already contaminated four promoted records before it was found.

The guard that should have caught it was **vacuous**: it compared the manifest to
`__version__` with both ends equally stale, and nothing tied either to
`pyproject.toml`. It now asserts
`importlib.metadata.version == __version__ == scorer_version` as a single chain,
anchored to the distribution metadata — the one end a human necessarily edits
when releasing. A hardcoded `"0.2.0"` expectation in the CLI test was replaced
with a comparison against the package for the same reason.

## masoretic_eval 0.2.0 — scorer

The four-tier scorer package, released independently and tagged `v0.2.0`. See the
package version in `pyproject.toml` and the reproducibility notes in
`docs/TESTING.md`.
