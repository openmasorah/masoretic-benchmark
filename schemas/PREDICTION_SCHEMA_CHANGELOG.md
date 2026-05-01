# Baseline Prediction + run_meta Schema Changelog

Append-only. Every change to `schemas/baseline_prediction.schema.json` or
`schemas/run_meta.schema.json` writes a NEW row above the previous one
(newest first). Schema-bump discipline: D-09 carry-forward (Phase 2) — document at bump.
Mirrors `oracles/NAKDIMON_PIN.md` format.

| Date       | Schema                          | From | To     | Reason                                                                                              |
|------------|---------------------------------|------|--------|-----------------------------------------------------------------------------------------------------|
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
- **`tier4_records[].type` enum.** Mirrors the UXLC loader's lowercase descriptive vocabulary (`pe`, `samekh`, `reversednun`, `puncta`, `large_letter`, `small_letter`, `suspended_letter`, `inverted_nun`). `ordinal` is positional per Phase 1 lesson 01-07.
- **Validation runs at TWO layers** per Plan 03-03 design: (1) at write time inside `SandboxRun.write_prediction` / `write_diagnostic` / `write_run_meta`; (2) at score time inside the `masoretic_eval` CLI (Plan 03-08 wires this).
