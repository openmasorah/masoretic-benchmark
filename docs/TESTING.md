<!-- generated-by: gsd-doc-writer -->
# Testing

This repo contains three independently-installable Python packages, each with
its own pytest suite and pin contract:

- `masoretic_eval` (root) — the 4-tier scorer
- `oracles/` — Hebrew diacritization oracles (Nakdimon, DICTA Nakdan, DictaBERT)
- `baselines/` — the four Phase 3 baselines (BL-01..BL-04)

The three suites share fixtures (the F118B IAA folio, the golden Deut 6:4-5
fragment) but are gated by independent env vars and run as independent jobs
in CI. A clean PR runs only mocked / replay tests; live network calls are
opt-in via `RUN_LIVE_ORACLES=1` or `RUN_LIVE_BASELINES=1` and are nightly,
non-blocking in CI.

## Test framework and setup

All three suites use **pytest** (`>=8.0` for the scorer and oracles,
`>=7` for baselines per `baselines/pyproject.toml`). The scorer
declares pytest config in `pytest.ini`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -ra --strict-markers --strict-config --import-mode=importlib
```

`--strict-markers` means an unregistered `@pytest.mark.foo` is a hard error,
not a warning — every custom marker must be declared in
`pyproject.toml` `[tool.pytest.ini_options].markers` or in a
`pytest_configure` hook in `conftest.py`.

Initial setup for all three suites:

```bash
# 1. System prereq for the scorer (used by the PyICU cross-validation test).
sudo apt-get install -y libicu-dev pkg-config       # Linux
brew install icu4c pkg-config                       # macOS

# 2. Install the scorer + dev extras (pytest, pytest-cov, ruff, mypy, PyICU).
pip install -e ".[dev]"

# 3. Install oracles (dev + dicta + dictabert; nakdimon best-effort on Py 3.11).
pip install -e "./oracles[dev,dicta,dictabert]"
pip install -e "./oracles[nakdimon]"   # Python 3.11 only; TF 2.15 has no 3.12 wheel

# 4. Install baselines (dev only is enough for unit + replay tiers).
pip install -e "./baselines[dev]"
```

The scorer's `[dev]` extra pins `PyICU>=2.11` on non-Windows; the
`test_pyicu_agrees_with_grapheme_on_hebrew_fixture` test in
`tests/test_segment.py` uses `pytest.importorskip("icu")` so PyICU is a
soft dependency at runtime — missing PyICU skips that single test rather
than failing the suite.

## Repository layout

### `tests/` — scorer suite (root package)

Flat directory of unit tests for the `masoretic_eval` package, plus the
top-level golden-fixture and manifest gates. Key files:

- `test_segment.py` — UAX #29 grapheme cluster segmentation, including the
  PyICU cross-validation test.
- `test_external_crossval.py` — independent naive Levenshtein
  cross-validation of the scorer's `cluster_aligned_cer` (see
  "Cross-validation tests" below).
- `test_golden_fixture.py` — end-to-end byte-identity gate against
  `tests/fixtures/golden/expected_result.json`.
- `test_tier1.py` … `test_tier4.py` — per-tier scorer correctness.
- `test_composite.py`, `test_cer.py`, `test_confusion.py`,
  `test_normalize.py` — scorer math + normalization.
- `test_manifest.py`, `test_manifest_immutable.py`,
  `test_manifest_v02_fields.py`, `test_manifest_hash_artifacts.py` —
  Phase 0 manifest schema + append-only invariants.
- `test_uxlc_loader.py`, `test_page_xml.py` — GT loaders.
- `test_cli.py`, `test_output_schema.py` — CLI surface and emitted
  scorer-output schema.
- `test_metamark_vocab_alignment.py`, `test_nakdimon.py` — Phase 1/2 contracts
  surfaced from the scorer side.
- `test_reject_private_paths.py`, `test_check_version_cascade.py`,
  `test_release_smoke.py` — repo-level gates (private-path leaks, version
  cascade, package-tree-only smoke).
- `tests/release/` — release-gate tests (license table, leaderboard schema,
  IAA report schema, manifest release invariants, README brand compliance,
  HF roundtrip, audit release red-team, release workflow smoke).
  <!-- VERIFY: at the time this doc was written, only compiled `__pycache__`
  artifacts were present in `tests/release/`; the source files are
  excluded from the public sibling repo via the private-path policy. -->
- `tests/fixtures/` — shared scorer fixtures: `golden/` (gt.json,
  prediction.json, expected_result.json), `cli_gt.json`,
  `cli_pred.json`, `synthetic_devarim_shema.page.xml`,
  `phase_0_manifest_sample.json`, `uxlc_deut_6.xml`.

### `oracles/tests/` — oracle suite

Independently-installable subpackage (`oracles/pyproject.toml` declares
`masoretic-oracles`). Tests:

- `test_nakdimon_oss.py`, `test_nakdan_hybrid.py`, `test_dictabert.py` —
  per-oracle unit tests (mocked at the network/transformers boundary).
- `test_compute_oracles.py` — score-time oracle-rate computation contract.
- `test_oracle_golden_fixture.py` — **ORA-06 contract test**: the oracle
  pipeline output roundtrips through the unmodified scorer CLI without
  changing any tier score (D-25, Pitfall 5). Reads pre-cached oracle
  outputs from `oracles/tests/fixtures/oracle_cache/golden_fixture_oracles.json`;
  never hits live DICTA.
- `test_live_oracle_drift.py` — gated by `RUN_LIVE_ORACLES=1`; compares
  fresh live oracle outputs against the committed golden cache. Drift means
  a re-pin happened without a corresponding `NAKDIMON_PIN.md` update.
- `test_invariants.py`, `test_audit.py`, `test_hashing.py`,
  `test_throttle.py` — structural and provenance invariants.
- `conftest.py` — installs a fake `nakdimon` package at import time when
  `RUN_LIVE_ORACLES != 1` so mocked tests can import
  `oracles.nakdimon_oss` on Python 3.12 (where TensorFlow 2.15 has no wheel).

### `baselines/tests/` — baseline suite

Independently-installable subpackage (`baselines/pyproject.toml` declares
`masoretic-baselines`). Three test tiers per the D-10 + D-11 corollary:

- **Mocked unit** (`test_baseline_unit_*.py` and structural invariants):
  clients fully patched at the `sys.modules` boundary; no network, no
  Kraken model load, no Pillow needed.
- **Replay** (`test_baseline_replay_llm_vision.py`): exercises the real
  combine logic against committed
  `baselines/tests/fixtures/llm_calls/<folio>.replay.jsonl` fixtures.
  `LLMVisionBaseline(replay=True)` raises `ReplayMissError` on hash miss
  rather than falling through to a live API call.
- **Live** (`test_baseline_live_*.py`, `test_baseline_live_kraken.py`):
  real Anthropic / Google / Kraken / Nakdimon / DictaBERT inference; gated
  by `RUN_LIVE_BASELINES=1`.

Structural invariant tests always run in the unit tier:
`test_contamination.py`, `test_no_compute_oracle_rates.py`,
`test_no_private_paths.py`, `test_dictabert_disclaimer_invariant.py`
(D-27), `test_kraken_pin_provenance.py`, `test_invariants.py`,
`test_scope_violation.py`, `test_expected_totals.py` (D-15),
`test_atomic_promote.py`, `test_atomic_run.py` (sandbox-then-promote),
`test_replay_spend_record.py`, `test_budget.py`,
`test_prediction_schema.py`, `test_run_meta_schema.py`,
`test_schema_module.py`, `test_scaffold.py`, `test_gt_adapter.py`,
`test_kraken_module.py`, `test_llm_clients.py`, `test_llm_combine.py`,
`test_llm_replay.py`.

`baselines/tests/conftest.py` installs an autouse fixture that points
`PHASE_0_MANIFEST_PATH` at a tmp-path manifest before every test (Phase 03.1
A-01 safety net), so a forgotten `monkeypatch.setenv` cannot mutate the
real in-repo manifest.

`baselines/tests/fixtures/` holds the four IAA folio PAGE-XML fixtures
(`F118B`, `F119A`, `F119B`, `F120A`) plus their gt-adapter golden files,
the dry-run synthetic Shema folio, the UXLC fragment cache, and the
`llm_calls/` replay JSONL.

## Custom pytest markers

| Marker             | Defined in                                  | Default       | Opt-in env var           |
|--------------------|---------------------------------------------|---------------|--------------------------|
| `live_oracles`     | `oracles/tests/conftest.py` + `oracles/pyproject.toml`<!-- VERIFY: oracles/pyproject.toml does not currently declare `[tool.pytest.ini_options].markers`; the marker is registered via `pytest_configure` in `oracles/tests/conftest.py` only. --> | skipped       | `RUN_LIVE_ORACLES=1`     |
| `live_baselines`   | `baselines/tests/conftest.py` + `baselines/pyproject.toml` | skipped       | `RUN_LIVE_BASELINES=1`   |
| `live_kraken`      | `baselines/pyproject.toml` (sub-marker of `live_baselines`) | skipped       | `RUN_LIVE_BASELINES=1` (and a cached `BiblIA_01.mlmodel`) |

The `live_*` markers work via a `pytest_collection_modifyitems` hook in each
package's `conftest.py` that adds `pytest.mark.skip` to every item carrying
the marker unless the corresponding env var is set to `1`. The scorer's
root `tests/` directory does **not** define any custom markers — it has no
live-network tests.

`live_kraken` is declared as a sub-marker of `live_baselines` so the live
job can opt-in/out per baseline (e.g.,
`pytest -m "live_baselines and not live_kraken"`).

## Cross-validation tests

The benchmark explicitly defends against self-grading by cross-validating
each Hebrew-text primitive against an independent implementation:

- **PyICU vs. internal segmenter** —
  `tests/test_segment.py::test_pyicu_agrees_with_grapheme_on_hebrew_fixture`
  drives `icu.BreakIterator.createCharacterInstance(icu.Locale("he"))`
  over `בְּרֵאשִׁית` and asserts byte-identical cluster boundaries with
  the internal `segment_clusters()`. Skipped (not failed) when PyICU is
  unavailable via `pytest.importorskip("icu")`.
- **Naive Levenshtein vs. cluster-aligned CER** —
  `tests/test_external_crossval.py` ships a textbook O(n*m)
  codepoint-level Levenshtein DP and asserts that
  `masoretic_eval.metrics.cer.cluster_aligned_cer` agrees on
  identical-cluster-count Hebrew fixtures (qamatz/patach pair, identical
  pair, full `בְּרֵאשִׁית`) and is upper-bounded by it on
  cluster-mismatch fixtures (cluster alignment can only add edits, never
  remove them).

The naive Levenshtein lives in `_naive_levenshtein()` in the same test
file — written from scratch to share zero code with the production CER
path, so any common bug would have to exist in both implementations
independently.

## D-27 verbatim invariant test

`baselines/tests/test_dictabert_disclaimer_invariant.py` pins the BL-04
off-label disclaimer character-for-character at four locations:

- `oracles/src/oracles/dictabert.py` (module docstring) — Phase 2 pin
- `oracles/README.md` — Phase 2 pin
- `baselines/src/baselines/biblia_char_menaked.py` (module docstring) — Phase 3 pin
- `baselines/README.md` — Phase 3 pin

The test reads each file and asserts the canonical string

> dictabert-large-char-menaked is trained on modern Hebrew and is off-label
> for pre-modern Tiberian text. Used here only as a publishable
> negative-result baseline (Baseline 4). Do not interpret outputs as
> oracle-grade diacritization.

is present after a `_normalize()` step that collapses whitespace and
strips markdown blockquote prefixes (`> `). Drift in any of the four
locations fails CI. The scorer's `pyproject.toml` adds a
`per-file-ignores` entry exempting the two pinned module files from
ruff's E501 line-length check, because wrapping the disclaimer would
break the invariant.

## F118B fixture-based scoring tests

The Leningrad Codex folio `F118B` (Devarim/Deuteronomy 6) is the canonical
end-to-end fixture. Two scoring tests bind it to the manifest:

- `tests/test_manifest_hash_artifacts.py` — for every promoted baseline
  (`biblia_char_menaked`, `biblia_kraken`, `biblia_nakdimon`,
  `llm_vision`), every produced artifact under `results/` carries a
  `manifest_hash` field that matches the current
  `phase_0_manifest.json::manifest_hash`. The artifact set is computed
  deterministically (per-baseline `<FOLIO_ID>.json`, `run_meta.json`,
  diagnostic glob, `results/scores/<FOLIO_ID>.json`) and compared
  set-equal to what's actually on disk — extra files or missing files
  both fail.
- `tests/test_manifest_immutable.py`, `tests/test_manifest_v02_fields.py` —
  exercise the same folio-id (`leningrad_devarim_F118B_fixture`) through
  the manifest schema validator and the append-only changelog rules.

The realistic predictions for these tests live under `results/<baseline>/`
and are committed to the repo; they were generated by the live cron job
(see "How to run" below). Mocked unit tests use the smaller IAA folio
fixtures under `baselines/tests/fixtures/iaa_folio_leningrad_devarim_*`.

## Cross-cutting golden fixture (ORA-06)

`tests/fixtures/golden/` holds three files that are byte-stable across the
scorer + oracle layers:

- `gt.json` — GT for Deut 6:4-5 fragment
- `prediction.json` — synthetic prediction with one known FN (the large ע)
- `expected_result.json` — the canonical scorer output

`tests/test_golden_fixture.py` runs `python -m masoretic_eval.cli score`
end-to-end and asserts byte-equality on `scorer_version`, `normalization`,
`denominator_policy`, every `tiers.tier{1..4}` block, and `composite`.
`oracles/tests/test_oracle_golden_fixture.py` (ORA-06) runs the same CLI
twice — once with rates absent, once with rates populated from
`oracles/tests/fixtures/oracle_cache/golden_fixture_oracles.json` — and
asserts that every byte of `tier1`/`tier3`/`tier4` + `composite` +
`confusion_matrices` is identical between the two runs (`tier2` differs
only in the two disagreement-rate fields). This is the load-bearing
contract that the oracle pipeline cannot drift the scorer.

## How to run

### Full local suite

```bash
# 1. Scorer suite + cross-validation (PyICU + naive Levenshtein).
pytest -v --cov=masoretic_eval --cov-report=term-missing
pytest tests/test_external_crossval.py -v

# 2. Oracle suite (mocked tier — never hits the network).
pytest oracles/tests/ -x -q -m "not live_oracles" \
    --cov=oracles --cov-report=term-missing

# 3. Baseline suite — mocked + replay tiers (no API spend).
pytest baselines/tests/ -x -q -m "not live_baselines and not live_kraken" \
    --cov=baselines --cov-report=term-missing
pytest baselines/tests/test_baseline_replay_llm_vision.py -x -q
```

### Live tests (opt-in, hits real APIs / models)

```bash
# Oracle drift detector (DICTA + Nakdimon + DictaBERT).
RUN_LIVE_ORACLES=1 pytest oracles/tests/ -q -m "live_oracles"

# Baseline live tier — needs API keys + cached Kraken model.
python baselines/scripts/fetch_biblia_kraken_model.py   # one-time
RUN_LIVE_BASELINES=1 \
ANTHROPIC_API_KEY=... GOOGLE_API_KEY=... \
PHASE_0_MANIFEST_PATH=$PWD/phase_0_manifest.json \
  pytest baselines/tests/ -q -m "live_baselines or live_kraken" --tb=short
```

The Kraken live test additionally requires the cached
`baselines/.cache/kraken/BiblIA_01.mlmodel` (~16 MB) — the test is
skipped (not failed) when the file is absent.

### CI matrix

`.github/workflows/ci.yml` runs five jobs on every PR plus a nightly cron:

| Job              | Trigger                    | Python      | Blocks PR? | Cost            |
|------------------|----------------------------|-------------|------------|-----------------|
| `gates`          | push / PR                  | 3.11        | yes        | $0              |
| `test`           | push / PR (after `gates`)  | 3.11, 3.12  | yes        | $0              |
| `oracle-unit`    | push / PR (after `test`)   | 3.11, 3.12  | yes        | $0              |
| `oracle-live`    | nightly cron + manual only | 3.11        | no (continue-on-error) | hits DICTA / DictaBERT / Nakdimon |
| `baseline-unit`  | push / PR (after `oracle-unit`) | 3.11, 3.12 | yes    | $0              |
| `baseline-replay`| push / PR (after `baseline-unit`) | 3.11, 3.12 | yes  | $0              |
| `baseline-live`  | nightly cron + manual only | 3.11        | no (continue-on-error) | real API spend |
| `check-yosef-review-gate` | PR only           | n/a         | yes (only when first BL-01 PR) | $0  |

The nightly cron runs at `0 6 * * *` (06:00 UTC). `baseline-live` always
caches the BiblIA Kraken model in GitHub Actions cache keyed on
`kraken-biblia-8514a0c7cc2b5b45` (the canonical `KRAKEN_MODEL_HASH` from
`baselines/KRAKEN_PIN.md`), and runs a `preflight_cost_caps.py` step
before any live API call.

A separate workflow, `.github/workflows/version-cascade-check.yml`, runs
`scripts/check_version_cascade.py` against any PR that touches a
`pyproject.toml` and detects scorer-version bumps that would silently
break the `oracles/` and `baselines/` pin contracts. The originating
incident: a `0.1.0 -> 0.2.0` bump that passed local tests because
consumers were not installed.

### Env vars that gate live tests

| Var                     | Effect                                                              | Required for                              |
|-------------------------|---------------------------------------------------------------------|-------------------------------------------|
| `RUN_LIVE_ORACLES=1`    | Removes `skip` from `live_oracles` items + skips fake-nakdimon installation in `oracles/tests/conftest.py`. | `oracles/tests/test_live_oracle_drift.py` and any other `@pytest.mark.live_oracles` test. |
| `RUN_LIVE_BASELINES=1`  | Removes `skip` from `live_baselines` and `live_kraken` items.       | All `baselines/tests/test_baseline_live_*.py`. |
| `PHASE_0_MANIFEST_PATH` | Path the production code reads to know where to write per-folio manifest bumps. The baselines `conftest.py` autouse-fixture sets this to a tmp file by default; live runs override it to the real `$PWD/phase_0_manifest.json`. | `baselines/tests/test_baseline_live_*.py` and the `baseline-live` CI job. |
| `ANTHROPIC_API_KEY`     | Claude Sonnet API access for BL-01 live calls.                       | `baselines/tests/test_baseline_live_*` LLM-vision tests. |
| `GOOGLE_API_KEY`        | Gemini API access for BL-01 live calls.                              | `baselines/tests/test_baseline_live_*` LLM-vision tests. |

## Adding a test

### …for a scorer change

1. Add a unit test under `tests/` named `test_<area>.py` following the
   existing pattern. Use `tests/fixtures/` for shared inputs; create a
   subdirectory there if your test needs more than one file.
2. If your change affects scorer output bytes, regenerate
   `tests/fixtures/golden/expected_result.json` by running the CLI on
   `gt.json` + `prediction.json` and committing the new expected. The
   `test_golden_fixture.py` and `test_oracle_golden_fixture.py` tests
   will both fail until the new expected is committed — this is the
   intended behavior; the failure is the load-bearing notification that
   downstream consumers must update too.
3. If your change affects the scorer-output shape, update
   `masoretic_eval/output_schema.py` and add a case to
   `tests/test_output_schema.py`.
4. Run `pytest -v --cov=masoretic_eval`. Add coverage for the new code
   path if `--cov-report=term-missing` shows uncovered lines.

### …for a new oracle

1. Add `oracles/src/oracles/<your_oracle>.py` and matching
   `oracles/tests/test_<your_oracle>.py`. Mock the network/transformers
   boundary at `sys.modules` patching level (see existing
   `test_nakdan_hybrid.py` for the pattern).
2. If the oracle is reproducibly pinned (model hash + code version),
   add a `<YOUR_ORACLE>_PIN.md` append-only log next to `NAKDIMON_PIN.md`
   and add a provenance test (see
   `baselines/tests/test_kraken_pin_provenance.py` as a template).
3. If the oracle has a verbatim disclaimer (off-label use), pin it at
   four locations and add an invariant test modeled on
   `test_dictabert_disclaimer_invariant.py`.
4. Add a live drift test guarded by `@pytest.mark.live_oracles` that
   compares fresh output against a committed cache fixture under
   `oracles/tests/fixtures/oracle_cache/`. The pattern is:
   `RUN_LIVE_ORACLES=1` regenerates the cache, mocked tests read from
   it, the nightly cron flags drift.
5. Verify ORA-06 still holds: scorer output bytes must be identical
   when your oracle's rates are absent vs. populated for everything
   except the oracle's own `disagreement_rate` field.

### …for a new baseline

1. Add `baselines/src/baselines/<your_baseline>.py` extending
   `BaselineBase` (D-12 locked-`run()` ABC).
2. Set the new subclass's `BASELINE_ID` class attribute (see
   `baselines/src/baselines/_base.py`), register the class in
   `BASELINE_REGISTRY` in `baselines/src/baselines/run.py`, and update
   `expected_total_reports` declarations (D-15).
3. Add three test files mirroring the existing pattern:
   - `test_baseline_unit_<your_baseline>.py` — mocked,
     PR-blocking. Patch oracle/client modules at `sys.modules` level.
   - `test_baseline_replay_<your_baseline>.py` — only if the baseline
     has expensive non-deterministic external calls (LLMs); commit a
     `baselines/tests/fixtures/llm_calls/<folio>.replay.jsonl`.
   - `test_baseline_live_<your_baseline>.py` — guarded by
     `pytestmark = [pytest.mark.live_baselines, pytest.mark.skipif(...)]`.
4. Update `baselines/README.md` "## CI" table and the structural
   invariant lists. If your baseline imports a new oracle, the
   `test_no_compute_oracle_rates.py` A-3 grep test will fail if the new
   import touches `compute_oracle_rates` — that's intentional (Phase 3
   production never reads score-time oracle rates).
5. Generate real predictions via the live cron job
   (`python -m baselines.run --baseline <your_baseline>` under
   `RUN_LIVE_BASELINES=1`) and commit the resulting
   `results/<your_baseline>/leningrad_devarim_F118B_fixture.json` plus
   `run_meta.json`. `tests/test_manifest_hash_artifacts.py` will fail
   until both files are present and carry the current `manifest_hash`.

### …for a scorer normalization or tier change

Any change to normalization or tier weights MUST come with:

1. An updated `tests/fixtures/golden/expected_result.json` (golden roundtrip).
2. A version bump in `masoretic_eval/__init__.py::__version__` (which
   `output_schema.py` re-exports as the `scorer_version` output field) and a
   matching update in the golden fixture's `scorer_version` field.
3. Regenerated `oracles/tests/fixtures/oracle_cache/golden_fixture_oracles.json`
   (run `RUN_LIVE_ORACLES=1 python oracles/scripts/regenerate_golden_oracle_cache.py`).
4. A new entry in `PREDICTION_SCHEMA_CHANGELOG.md` if the prediction
   shape changed.
5. A new entry in `phase_0_manifest.json::manifest_changelog` if the
   change is post-freeze (the manifest is append-only — see
   `tests/test_manifest_immutable.py`).

The version-cascade workflow will surface cases where the scorer version
moves outside the `>=0.2.0,<0.3` pin in `oracles/pyproject.toml` and
`baselines/pyproject.toml` — bump those pins in the same PR.

## Coverage requirements

No numeric coverage threshold is configured in `pytest.ini`,
`pyproject.toml`, or any `conftest.py` (the `pytest-cov` plugin runs in
all three CI jobs but only emits `term-missing`, not a fail-under
threshold). Coverage is reviewed manually on PRs. The structural
invariant tests act as a stronger gate than line coverage: they fail on
*absence* of expected behavior, not just absence of line execution.
