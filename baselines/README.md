# baselines

Phase 3 baselines for the Masoretic CER benchmark.

Four baselines: BL-01 (`llm_vision`, Claude+Gemini), BL-02 (`biblia_kraken`),
BL-03 (`biblia_nakdimon`), BL-04 (`biblia_char_menaked`).

Shared infrastructure:
- `BaselineBase` template-method ABC (D-12) — locked `run()`, abstract `infer_folio()`
- `ScopeViolation` two-layer preflight (D-13)
- Sandbox-then-promote atomic writes (D-14)
- `expected_total_reports` bit-equality check (D-15)

Reads `phase_0_manifest.json` as single source of truth (BL-05).
Refuses non-Leningrad folios via `ScopeViolation` (BL-08).
Append-only pin logs: `KRAKEN_PIN.md`, `LLM_PIN.md`, `PREDICTION_SCHEMA_CHANGELOG.md`.
