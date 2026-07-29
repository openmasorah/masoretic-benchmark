# Baseline Prediction + run_meta Schema Changelog

Append-only. Every change to `schemas/baseline_prediction.schema.json` or
`schemas/run_meta.schema.json` writes a NEW row above the previous one
(newest first). Schema-bump discipline: D-09 carry-forward (Phase 2) — document at bump.
Mirrors `oracles/NAKDIMON_PIN.md` format.

| Date       | Schema                          | From | To     | Reason                                                                                              |
|------------|---------------------------------|------|--------|-----------------------------------------------------------------------------------------------------|
| 2026-07-29 | baseline_prediction.schema.json, scorer_input.schema.json, manuscript.schema.json | v0.1.0 | v0.1.0 | **BREAKING (scorer 0.2.0 → 0.3.0).** Tier-4 vocabulary unification, for real this time — see "The 2026-07-29 unification" below. `tier4_records[].type` / `metamarks[].type` enum becomes `pe`, `samekh`, `large_letter`, `small_letter`, `suspended_letter`, `inverted_nun`, `puncta_extraordinaria`, `circellus`, `rafe`, `double_rafe`. Retired: `reversednun` (→ `inverted_nun`), `puncta` (→ `puncta_extraordinaria`). |
| 2026-05-01 | baseline_prediction.schema.json, run_meta.schema.json | v0.1.0 | v0.1.0 | Phase 03.3 C-6 manifest provenance binding: `manifest_hash` is a required non-empty string, never `null`. |
| 2026-05-01 | baseline_prediction.schema.json | v0.1.0 | v0.1.0 | Phase 03.3 C-2 metamark vocabulary unification: `pe`, `samekh`, `reversednun`, `puncta`, `large_letter`, `small_letter`, `suspended_letter`, `inverted_nun`. |
| 2026-04-25 | baseline_prediction.schema.json | —    | v0.1.0 | Phase 3 BASELINES launch (D-16, D-17). Per-line shape: tier1..4, optional provenance fields per BL. |
| 2026-04-25 | run_meta.schema.json            | —    | v0.1.0 | Phase 3 BASELINES launch (D-18, D-19). Per-baseline pins + budget + combine + per-folio nested.     |

## Notes

- **draft-2020-12 dialect.** Both schemas declare `$schema: https://json-schema.org/draft/2020-12/schema` and pass `jsonschema.Draft202012Validator.check_schema()`.
- **`$id` namespace.** Mirrors `phase_0_manifest.schema.json`'s `urn:masoretic:*` convention. Versioned via `$id` URL + a `schema_version` field pinned via `const` in each schema.
- **`baseline_id` enum.** Both schemas restrict `baseline_id` to the four Phase 3 baseline ids per A-2 (AbbyyFR dropped): `llm_vision`, `biblia_kraken`, `biblia_nakdimon`, `biblia_char_menaked`.
- **`additionalProperties: false`** at every object level (top-level + per-line + per-tier4-record + pins/budget/combine/folio entries) to reject typo'd keys before they hit `results/<bl>/`. Folio-id keys inside `folios` are user-defined and use `additionalProperties: <object schema>` to constrain the value shape.
- **`combine.tie_break_winners`** uses `oneOf: [null, {claude, gemini}]`. BL-02/03/04 emit `null`; BL-01 emits the object with `claude` + `gemini` integer counts (per A-2; AbbyyFR removed from this object's required keys).
- **`pins` keys are all required, values nullable.** Each baseline populates the relevant subset and emits `null` for the rest. Missing key fails validation; null value passes.
- **`budget` and `combine` inner keys all required.** Same null-value convention as `pins` for BL-02/03/04 which have neither budget nor combine semantics.
- **`tier4_records[].type` enum.** Defined once in `masoretic_eval/tier4_vocabulary.py::TIER4_TYPES`; this schema's enum is asserted equal to it by `tests/test_tier4_vocabulary_consistency.py`. `ordinal` is positional per Phase 1 lesson 01-07.

## The 2026-07-29 unification

The 2026-05-01 row above calls itself a "metamark vocabulary unification." It
was not one. It aligned the prediction schema with the **UXLC loader** and
stopped there, leaving four vocabularies in the repo:

| Site | Vocabulary |
|---|---|
| `scorer_input.schema.json`, `baseline_prediction.schema.json` | `pe, samekh, reversednun, puncta, large_letter, small_letter, suspended_letter, inverted_nun` |
| `iaa_data/devarim_4folio/*.json` (the shipped ground truth) | `circellus, rafe, double_rafe` |
| `manuscript.schema.json` `mark_type_enum` | `…, puncta_extraordinaria, circellus, line_filler, stichographic_layout, dotted_letter, rashe_tevot` |
| `docs/meta_marks_schema.md` | PAGE-XML capture tokens; no mention of rafe or circellus at all |

The first two share **no term**. `masoretic-eval score` therefore rejected
all 516 tier-4 records the benchmark ships as its own gold — every one, on the
enum check — and no test noticed, because no test had ever fed the shipped
gold to the shipped CLI.

`tests/test_metamark_vocab_alignment.py` made this worse rather than better.
It asserted the schema enum **equal** the UXLC loader's vocabulary, which
actively forbade the schema from admitting `circellus`/`rafe`: a correct fix
would have failed CI as a regression. Its assertion is now containment
(loader ⊆ canonical), with the reasoning recorded in the file.

Two spellings collapsed. `reversednun` was UXLC's XML *tag* name for the mark
that `<x>8</x>` encoded as `inverted_nun` — one phenomenon, two enum slots.
`puncta` and `puncta_extraordinaria` were the scorer's and the catalog's names
for the same thing; the scholarly term wins. Neither collapse could move a
published number: both retired spellings occur **zero** times in the v0.1
corpus (UXLC Deuteronomy yields `{samekh: 136, pe: 32, large_letter: 2,
puncta_extraordinaria: 2}`, and nun hafukha sits at Num 10:35-36, outside the
frozen Devarim scope). Verified empirically — `iaa_report.json` is
byte-identical across this change.

**Migration.** Pre-0.3.0 prediction files using a retired spelling now fail
validation. `masoretic_eval.tier4_vocabulary.canonicalize()` maps old → new.
No shipped artifact needed rewriting; the retired spellings appear in no data
file in this repo.
- **Validation runs at TWO layers** per Plan 03-03 design: (1) at write time inside `SandboxRun.write_prediction` / `write_diagnostic` / `write_run_meta`; (2) at score time inside the `masoretic_eval` CLI (Plan 03-08 wires this).
