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

## CI

Three sibling-repo CI jobs cover Phase 3 baselines (mirroring the Phase 2
oracle pattern; full workflow at `.github/workflows/ci.yml`):

| Job              | Runs                            | Blocks PR? | Cost          |
|------------------|---------------------------------|------------|---------------|
| `baseline-unit`  | every PR + push                 | yes        | $0 (mocked)   |
| `baseline-replay`| every PR + push                 | yes        | $0 (replay)   |
| `baseline-live`  | nightly cron 06:00 UTC + manual | no (continue-on-error) | $$$ (real API) |

**Three-tier discipline (D-10 + D-11 corollary):**

- **Mocked unit:** `pytest -m "not live_baselines and not live_kraken"` — clients fully patched at the `sys.modules` boundary; no network, no Kraken model load, no Pillow needed. Includes the three structural invariants (contamination, A-3 grep, D-15 declarations) plus the 5 AST invariants (D-12 locked-`run()`, BASELINE_ID enum) plus the DictaBERT disclaimer + KRAKEN_PIN provenance invariants.
- **Replay mode:** `pytest baselines/tests/test_baseline_replay_llm_vision.py` — exercises the real combine logic against the committed `tests/fixtures/llm_calls/<folio>.replay.jsonl`. No API spend; `LLMVisionBaseline(replay=True)` raises `ReplayMissError` on hash miss rather than falling through to a live call.
- **Live:** `RUN_LIVE_BASELINES=1 pytest -m live_baselines` — exercises real Anthropic / Google / Kraken / Nakdimon / DictaBERT inference. Nightly cron on Linux + Python 3.11 (Phase 2 Pitfall 1: `nakdimon==0.1.2` pins TF 2.15, no Python 3.12 wheel). API keys via repository secrets (`ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`); BiblIA Kraken model cached in GitHub Actions cache keyed on `KRAKEN_MODEL_HASH = 8514a0c7cc2b5b45` (canonical-from-`KRAKEN_PIN.md`).

**Structural invariants always-on (in `baseline-unit`):**

- `test_contamination.py` — greps `llm_calls.jsonl` for UXLC fragments (D-05 boundary)
- `test_no_compute_oracle_rates.py` — A-3 zero-reference enforcement
- `test_expected_totals.py` — D-15 declaration check (manifest's `expected_reports_per_baseline` keyset)
- `test_invariants.py` — D-12 locked-`run()` AST walk + BASELINE_ID enum
- `test_dictabert_disclaimer_invariant.py` — D-27 verbatim disclaimer in code + README
- `test_kraken_pin_provenance.py` — `KRAKEN_PIN.md` row vs cached `BiblIA_01.mlmodel` sha256

**Deferred for Phase 3.1:** the `baseline-live` job's "real fixture generation" step is currently a no-op echo. Real predictions on the 5 IAA folios for BL-01..BL-04 (estimated ~$5–$25 LLM spend + Kraken/Nakdimon/DictaBERT inference) are deferred to a Phase 3.1 gap-closure plan. CI infrastructure (cache key, secrets, install pattern) is ready for Phase 3.1 to populate the live tier without further wiring work.

**Phase 1 F8 gate is NOT in sibling CI** — Pitfall 8 carry-forward. The sibling
repo must be independently verifiable; F8 is baalshem's gate.
