<!-- generated-by: gsd-doc-writer -->
# Configuration

This document describes every configuration surface of the `masoretic-benchmark`
repository: Python version pins, optional dependency extras, CLI flags, model /
version pin files, schemas, environment variables, and the linter / type-checker /
pre-commit / CI configuration.

The repository ships **three installable Python packages** that each carry their
own `pyproject.toml`:

| Package | Path | Purpose |
|---|---|---|
| `masoretic-eval` | `pyproject.toml` (repo root) | 4-tier CER scorer + `masoretic-eval` CLI |
| `masoretic-oracles` | `oracles/pyproject.toml` | Diacritization oracles (Nakdimon OSS, DICTA Nakdan, DictaBERT) |
| `masoretic-baselines` | `baselines/pyproject.toml` | Phase 3 baselines (BL-01 through BL-04) |

## Python Version

- **Pinned to `3.11`** at the repo level via `.python-version` (single line: `3.11`).
- `pyproject.toml` declares `requires-python = ">=3.11"` for the scorer and the
  oracles package; `baselines/pyproject.toml` tightens this to
  `requires-python = ">=3.11,<3.13"`.
- `tool.ruff.target-version = "py311"` and `tool.mypy.python_version = "3.11"`
  in the root `pyproject.toml`.

### Nakdimon / TensorFlow 3.12 incompatibility

`nakdimon==0.1.2` (the pinned diacritization oracle, see `oracles/NAKDIMON_PIN.md`)
transitively pins `tensorflow==2.15.0`, which has **no wheel for Python ≥ 3.12 on
macOS arm64** (verified 2026-04-24). Consequences across the repo:

- The CI matrix tests `["3.11", "3.12"]` for the scorer / oracle / baseline unit
  jobs, but installs `oracles[nakdimon]` **best-effort** on 3.12 — failure prints
  a `::warning::` and tests continue (mocked tests still cover Nakdimon paths via
  `sys.modules` injection). See `.github/workflows/ci.yml` jobs `oracle-unit`,
  `baseline-unit`.
- The `oracle-live` and `baseline-live` nightly drift jobs run on **`3.11` only**
  because they need the real Nakdimon TF 2.15 stack.
- Other phases of the pipeline (scorer, GT infra) are free to run on 3.12+;
  only the Nakdimon path is hard-pinned to 3.11.

## Optional Dependency Extras

### `masoretic-eval` (root `pyproject.toml`)

| Extra | Contents | Purpose |
|---|---|---|
| `dev` | `pytest>=8.0`, `pytest-cov>=4.0`, `ruff>=0.5`, `mypy>=1.8`, `pre-commit>=3.5`, `PyICU>=2.11` (non-Windows) | Full developer toolchain |
| `page-xml` | `lxml>=5.0` | Documentation-only gate per Phase 03.1 RESEARCH.md Pitfall 1. `lxml` is **already** a hard dependency via `masoretic_eval/uxlc_loader.py`; this extra exists to mark consumer intent (`gt-infra` and `baselines` opt in explicitly via `masoretic-eval[page-xml]`) and is currently a no-op. |

Install: `pip install -e ".[dev]"` (matches CI step "Install package + dev deps").

### `masoretic-oracles` (`oracles/pyproject.toml`)

| Extra | Contents |
|---|---|
| `dev` | `pytest>=8.0`, `pytest-mock>=3.12`, `pytest-cov>=4.0` |
| `dicta` | (empty — core deps already cover `requests` + `tenacity`) |
| `dictabert` | `transformers>=4.44,<6`, `torch>=2.2,<3`, `safetensors>=0.4` |
| `nakdimon` | `nakdimon==0.1.2` (TF 2.15; Python 3.11 only — see Pitfall above) |
| `all` | union of `nakdimon`, `dictabert` deps |

Typical install: `pip install -e "./oracles[dev,dicta,dictabert]"`.

### `masoretic-baselines` (`baselines/pyproject.toml`)

| Extra | Contents |
|---|---|
| `dev` | `pytest>=7`, `pytest-mock>=3`, `pytest-cov>=4.0`, `jsonschema>=4.0`, `PyYAML>=6.0` |
| `kraken` | `kraken==7.0.1` |
| `llm` | `anthropic==0.97.0`, `google-genai==1.73.1`, `PyYAML>=6.0` |
| `all` | `masoretic-baselines[kraken,llm]` |

Typical install: `pip install -e "./baselines[dev]"` (mocked tests). Live
baselines (BL-01, BL-02) require `kraken` + `llm` extras.

## CLI: `masoretic-eval score`

Defined in `masoretic_eval/cli.py` and exposed via the
`[project.scripts] masoretic-eval = "masoretic_eval.cli:main"` entry point.

```
masoretic-eval score \
  --gt PATH \
  --pred PATH \
  --folio-id ID \
  --out PATH \
  [--gt-version v0.1.0] \
  [--manifest PATH] \
  [--nakdimon-disagreement-rate FLOAT] \
  [--dicta-disagreement-rate FLOAT]
```

| Flag | Required | Default | Description |
|---|---|---|---|
| `--gt` | yes | — | Path to ground-truth JSON; validated against `masoretic_eval/schemas/scorer_input.schema.json`. |
| `--pred` | yes | — | Path to prediction JSON; same schema. |
| `--folio-id` | yes | — | Folio identifier written into the report's `prediction_id`. |
| `--out` | yes | — | Output path for the JSON score report. |
| `--gt-version` | no | `v0.1.0` | GT version stamp written into the output. |
| `--manifest` | no | `./phase_0_manifest.json` if present | Phase 0 manifest used for this scoring run. Manifest hash is loaded via `Manifest.load(...).manifest_hash` and embedded in the output. CLI fails if no manifest is found and none is passed. |
| `--nakdimon-disagreement-rate` | no | `None` | Pass-through diagnostic written to `tier2.diagnostics.nakdimon_disagreement_rate`. Does NOT affect any tier CER; **diagnostic only**. |
| `--dicta-disagreement-rate` | no | `None` | Pass-through diagnostic written to `tier2.diagnostics.dicta_disagreement_rate`. Same semantics. |

### Scoring kwargs that affect output

The two `--*-disagreement-rate` flags propagate through
`Scorer.score(..., nakdimon_disagreement_rate=..., dicta_disagreement_rate=...)`
in `masoretic_eval/composite.py`. They are passed through verbatim into the Tier 2
diagnostics dict — the scorer never re-derives them. They are the **only**
optional inputs that change the contents of the output report; all other tier
metrics are deterministic functions of `--gt` and `--pred`.

The fixed scorer config is `Scorer.from_config("v0.1")`. Any other value raises
`ValueError("unknown config: ...")`.

## Configuration files

### `baselines/llm_vision.config.yaml`

BL-01 (LLM Vision) configuration. Loaded by
`baselines/src/baselines/_llm_clients.py::_load_config()` which reads
`baselines/llm_vision.config.yaml` relative to the repo root.

Top-level keys (all required by current consumers; values shown are pinned):

```yaml
models:
  claude:
    id: "claude-opus-4-7"
    input_per_mtok_usd: 5.00
    output_per_mtok_usd: 25.00
  gemini:
    id: "gemini-2.5-pro"
    input_per_mtok_usd: 1.25
    output_per_mtok_usd: 10.00

cost_caps_usd:
  per_folio: 5.00
  per_run:   30.00

inference:
  max_output_tokens: 2048
  temperature: 0
  seed: 0  # forward-compat; not deterministic on gemini-2.5-pro

combine:
  tie_break: "alphabetical"   # Claude < Gemini -> Claude wins ties (D-07)
```

**Authority precedence**: `phase_0_manifest.json.cost_caps_usd` is
authoritative at runtime; this YAML seeds the manifest at first promotion.
Any provider price change is a **re-pin event**: same commit must update both
the YAML and append a row to `baselines/LLM_PIN.md`.

### `phase_0_manifest.json` (frozen)

Single source of truth for the frozen Phase 0 scope. Validated against
`schemas/phase_0_manifest.schema.json` (draft-2020-12, `$id:
urn:masoretic:phase_0_manifest.schema:v0.2`).

The manifest is **append-only-immutable**: pre-commit hook
`manifest-append-only` (running `scripts/manifest_immutable.py`) and the CI
"Enforce manifest append-only immutability" gate reject any modification that
changes existing fields without appending a `manifest_changelog` row.

Required top-level keys (excerpt; full list in the schema's `required` array):
`version`, `frozen_at`, `folios`, `scorer_version`, `expected_total_reports`,
`iaa_subset`, `baselines_seeded`, `expected_reports_per_baseline`,
`nakdimon_model_hash`. `additionalProperties: false` rejects typo'd keys at
write time.

Cost caps: `cost_caps_usd.{per_folio, per_run}` numeric, `minimum: 0`. Current
values: `5.0` and `30.0` USD respectively.

## Model / version pin files

The repository uses three append-only Markdown pin logs. Every change writes a
**new row** above the previous one (newest first). The pre-commit / CI gates do
not parse these files, but they bind into the manifest and run-meta hashes:

| Pin file | Hash field surfaced in run_meta / manifest | Current pin |
|---|---|---|
| `oracles/NAKDIMON_PIN.md` | `nakdimon_model_hash` (manifest) | `nakdimon==0.1.2`, MODEL_HASH `8fd7722b8002a690` |
| `baselines/KRAKEN_PIN.md` | `kraken_model_hash` (manifest) | `kraken==7.0.1`, BiblIA_01.mlmodel sha256 `bb48c481…`, derived hash `8514a0c7cc2b5b45` |
| `baselines/LLM_PIN.md` | `run_meta.pins.llm_pin_md_hash` (sha256 of the file's bytes) | `claude-opus-4-7` (anthropic 0.97.0) + `gemini-2.5-pro` (google-genai 1.73.1) |

DictaBERT model revision pin: `phase_0_manifest.json.dictabert_model_revision`
= `d311fbf7c403e50b040440e4859ac78064d025d0`. The schema requires this field to
be a non-empty string.

The Kraken pin formula is
`sha256(f"kraken=={version}:{mlmodel_sha256}").hexdigest()[:16]`, mirroring
`oracles._hashing.compute_nakdimon_model_hash`. The derivation is computed by
`baselines/scripts/fetch_biblia_kraken_model.py` and re-derived at module
import time in `baselines/_kraken.py` so the `KRAKEN_MODEL_HASH` constant is
canonical-from-the-pin.

## Schemas

Located in `schemas/`. All declare `$schema:
https://json-schema.org/draft/2020-12/schema` and pass
`Draft202012Validator.check_schema()`. `additionalProperties: false` is set at
every object level.

| Schema | Current version | `$id` namespace |
|---|---|---|
| `phase_0_manifest.schema.json` | v0.2 | `urn:masoretic:phase_0_manifest.schema:v0.2` |
| `baseline_prediction.schema.json` | v0.1.0 | `urn:masoretic:*` |
| `run_meta.schema.json` | v0.1.0 | `urn:masoretic:*` |

### Versioning policy

Schema bumps follow **D-09 carry-forward**: every change appends a NEW row
(newest first) to the corresponding changelog:

- `schemas/phase_0_manifest.changelog.md` for the manifest schema.
- `schemas/PREDICTION_SCHEMA_CHANGELOG.md` for `baseline_prediction.schema.json`
  and `run_meta.schema.json` (combined).

Each schema is versioned via the `$id` URL **and** a `schema_version` field
pinned via `const`. The most recent change (2026-05-01, Phase 03.3 C-6) made
`manifest_hash` a required non-empty string in both the prediction and
run_meta schemas — never `null`.

Validation runs at **two layers**: (1) at write time inside
`SandboxRun.write_prediction` / `write_diagnostic` / `write_run_meta`; (2) at
score time inside the `masoretic-eval` CLI.

### Frozen `phase_0_manifest.json` contract

The manifest file at the repo root is a **frozen artifact**. Mutability is
constrained as follows:

- Append-only: every change must add a `manifest_changelog` entry with
  `prev_frozen_at` / `new_frozen_at` / `reason` fields. The
  `scripts/manifest_immutable.py` hook diffs against `HEAD~1` (push-to-main) or
  `origin/<base_ref>` (PR) and rejects deletions or mutations of historical
  rows.
- Schema-validated: CI gate "Validate root phase_0_manifest.json" runs
  `jsonschema.Draft202012Validator(...).validate(manifest)` against
  `schemas/phase_0_manifest.schema.json`.
- The current frozen values include 4 IAA folios from the Leningrad Codex
  Devarim quire (F118B, F119A, F119B, F120A), `version: v0.2.0`, and
  `scorer_version: 0.2.0`. Each frozen folio carries a `gt_hash` (sha256[:16] of
  the consensus golden it pins) and a `gt_source` naming those bytes.

## Environment variables

All env-var consumption in production code paths uses
`os.environ[KEY]` (KeyError on missing) or `os.environ.get(KEY, default)`
explicitly.

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | when running BL-01 live | — | Read via `os.environ["ANTHROPIC_API_KEY"]` in `baselines/_llm_clients.py::claude_client()`; **no `.get()` fallback** (Phase 1 B-4). Missing key raises `KeyError` and exits non-zero by design. Plumbed in CI via `secrets.ANTHROPIC_API_KEY` for live jobs. |
| `GOOGLE_API_KEY` | when running BL-01 live | — | Same pattern as above (`gemini_client()`). |
| `RUN_LIVE_BASELINES` | for live baseline tests / scripts | unset | Setting to `"1"` opts in to `pytest.mark.live_baselines` tests. Default behavior: tests are skipped. Gate enforced in `baselines/tests/conftest.py`. |
| `RUN_LIVE_ORACLES` | for live oracle tests / scripts | unset | Setting to `"1"` opts in to `pytest.mark.live_oracles` tests, gated in `oracles/tests/conftest.py`. Also required by `oracles/scripts/regenerate_golden_oracle_cache.py`. |
| `PHASE_0_MANIFEST_PATH` | optional | `<repo_root>/phase_0_manifest.json` | Override the manifest path used by `BaselineBase.run` and the `python -m baselines.run` CLI. Set in CI live jobs to `${{ github.workspace }}/phase_0_manifest.json`. |
| `OPENMESORAH_GT_EXPORT_JSON` | optional | unset | Constant `GT_EXPORT_PATH_ENV` in `baselines/_chain.py`. When set, points at an explicit GT export JSON; otherwise the chain searches default candidate paths. |
| `SCORER_RUN_ID` | optional | `"unknown"` | Read by `oracles/nakdan_hybrid.py` for telemetry context. |
| `SCORER_FOLIO_ID` | optional | `"unknown"` | Same. |

There is no `.env.example` in the repo. Tests that need keys are env-gated and
skip cleanly when the keys are absent.

## Tooling configuration

### Ruff (`[tool.ruff]` in root `pyproject.toml`)

```toml
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "W", "B", "UP"]
```

Per-file ignores (`E501` long-line) are applied to two files that contain the
**D-27 verbatim disclaimer** which must match character-for-character across:

- `oracles/src/oracles/dictabert.py`
- `oracles/README.md`
- `baselines/src/baselines/biblia_char_menaked.py`
- `baselines/README.md`

Wrapping the disclaimer would break the D-27 invariant test, so the linter is
muted on the two source files (the READMEs are not linted by ruff).

### Mypy (`[tool.mypy]` in root `pyproject.toml`)

```toml
python_version = "3.11"
strict = true
ignore_missing_imports = true
```

`strict = true` enables the full mypy strict-mode flag bundle. CI invokes
`mypy masoretic_eval` (does not type-check the oracles or baselines packages —
they are tested via pytest only).

### Pytest (`pytest.ini`, repo root)

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -ra --strict-markers --strict-config --import-mode=importlib
```

`--strict-markers` makes any unregistered `pytest.mark.*` an error.
`--strict-config` rejects unknown ini options.

The baselines package registers two custom markers in
`baselines/pyproject.toml`:

- `live_baselines` — real network/model calls, gated by `RUN_LIVE_BASELINES=1`.
- `live_kraken` — real Kraken model + archive.org image fetch (BL-02);
  sub-marker of `live_baselines`.

The oracles package registers `live_oracles` in `oracles/tests/conftest.py`.

### Pre-commit (`.pre-commit-config.yaml`)

| Hook | Source | Purpose |
|---|---|---|
| `check-added-large-files` | `pre-commit/pre-commit-hooks v5.0.0` | Reject files > 5000 KB (`--maxkb=5000`) |
| `check-merge-conflict`, `check-yaml`, `check-json`, `end-of-file-fixer`, `trailing-whitespace` | same | Standard hygiene |
| `no-commit-to-branch` | same | Block direct commits to `main` |
| `ruff` (`--fix`) + `ruff-format` | `astral-sh/ruff-pre-commit v0.15.11` | Lint + format Python |
| `reject-binary-extensions` | local (`scripts/reject_binaries.py`) | Reject `*.jpg`, `*.pdf`, `*.png`, etc., and anything under `scans/` |
| `reject-private-paths` | local (`scripts/reject_private_paths.py`) | Reject leaks of the private `openmasorah` workspace path or local user paths |
| `manifest-append-only` | local (`scripts/manifest_immutable.py`) | Enforce `phase_0_manifest.json` append-only immutability (only fires on changes to that exact file) |
| `gitleaks` | `gitleaks/gitleaks v8.20.0` | Detect hardcoded secrets |

### MCP (`.mcp.json`)

The repository's `.mcp.json` is gitignored (see `.gitignore`) and holds an
optional, developer-local Model Context Protocol server entry. CI does not
consume it; downstream consumers do not need it.

## CI matrix (`.github/workflows/ci.yml`)

Two workflows live in `.github/workflows/`:

- `ci.yml` — main test / gates pipeline.
- `version-cascade-check.yml` — pre-merge gate that detects `pyproject.toml`
  `[project].version` bumps that silently violate pin consumers in sibling
  `pyproject.toml` files inside this repo. Runs `scripts/check_version_cascade.py`
  on Python 3.11.

### `ci.yml` triggers

- `push` to `main` (only)
- `pull_request` against `main`
- `schedule` cron `0 6 * * *` UTC (nightly drift, non-blocking)
- `workflow_dispatch`

### Job graph

| Job | Python matrix | Blocks PR? | Notes |
|---|---|---|---|
| `gates` | `3.11` | yes | Manifest schema validation, append-only immutability, binary/path/secret rejection, gitleaks |
| `test` | `3.11`, `3.12` | yes | Lint (ruff) + type-check (mypy) + pytest with coverage; needs `gates` |
| `oracle-unit` | `3.11`, `3.12` | yes | Mocked oracle tests + ORA-06 contract test; `nakdimon` extra installed best-effort on 3.12 |
| `oracle-live` | `3.11` | no (`continue-on-error: true`) | Cron + `workflow_dispatch` only; sets `RUN_LIVE_ORACLES=1` |
| `baseline-unit` | `3.11`, `3.12` | yes | Mocked baseline tests; `nakdimon` extra installed only on 3.11 |
| `baseline-replay` | `3.11`, `3.12` | yes | Replays committed `llm_calls.jsonl` fixtures (no API keys, no live calls) |
| `baseline-live` | `3.11` | no (`continue-on-error: true`) | Cron + manual only; uses `secrets.ANTHROPIC_API_KEY`, `secrets.GOOGLE_API_KEY`; caches Kraken model keyed on `kraken-biblia-8514a0c7cc2b5b45` |
| `check-yosef-review-gate` | n/a | yes (PR only) | Enforces `[YOSEF-REVIEW]` prefix on the first-of-kind BL-01 PR (Phase 03.1 A-03) |

CI installs system dependency `libicu-dev pkg-config` (for `PyICU`) before any
pip install on Linux runners. Sibling repo CI does **not** invoke the private
`openmasorah` repo in any form (no vendoring, cloning, or submodules) — Pitfall 8
carry-forward.

## Per-environment overrides

There is no environment-specific config layering in the source (no
`.env.development` / `.env.production`, no `NODE_ENV`-style switch). The only
runtime override mechanism is the env-var set documented above:

- Local development: omit `RUN_LIVE_*`; tests run mocked.
- Replay tier (deterministic, no API spend): `pytest baselines/tests/test_baseline_replay_llm_vision.py`.
- Live tier (real spend, drift surfacing): export `RUN_LIVE_BASELINES=1` /
  `RUN_LIVE_ORACLES=1` plus the two API keys; CI restricts this to the nightly
  cron job and `workflow_dispatch`, never on PRs.
