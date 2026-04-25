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

## BL-04: DictaBERT char-menaked — off-label disclaimer

> dictabert-large-char-menaked is trained on modern Hebrew and is off-label for pre-modern Tiberian text. Used here only as a publishable negative-result baseline (Baseline 4). Do not interpret outputs as oracle-grade diacritization.

BL-04 (`baselines/biblia_char_menaked.py`) chains BiblIA Kraken segmentation
with `dictabert-large-char-menaked` (HF revision pinned at
`d311fbf7c403e50b040440e4859ac78064d025d0` per Phase 2 02-04). The realistic
chain emits a leaderboard prediction; the GT-fed diagnostic chain (D-01)
emits a paper-only companion that isolates DictaBERT's error rate on
perfect consonants from Kraken's OCR noise. The two together let the paper
distinguish "diacritizer is bad on Tiberian" (the load-bearing claim) from
"OCR is bad on Tiberian" (a separate result already evident in BL-02).

Per Phase 2 D-26 + Phase 3 A-3, BL-04 imports
`oracles.dictabert.diacritize` only — no `disagreement_rate` (DictaBERT
does not expose one, by design), no `compute_oracle_rates` (Phase 4
score-time, not Phase 3 production). The disclaimer above is pinned in
both this README and the module docstring by
`tests/test_dictabert_disclaimer_invariant.py`; drift in either location
fails CI. Defense in depth: Phase 2 already pins the same disclaimer at the
oracle layer (`oracles/dictabert.py` + `oracles/README.md`).
