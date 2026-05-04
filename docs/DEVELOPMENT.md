<!-- generated-by: gsd-doc-writer -->
# Development

Audience: external contributors and maintainers working on the scorer
(`masoretic_eval/`), the four reference baselines (`baselines/`), the
diacritization oracles (`oracles/`), or the JSON Schemas (`schemas/`).

This guide assumes you have already read [GETTING-STARTED.md](GETTING-STARTED.md)
and [ARCHITECTURE.md](ARCHITECTURE.md). Configuration knobs (env vars, manifest,
pin files) live in [CONFIGURATION.md](CONFIGURATION.md).

## Local setup

The repo is three editable Python packages laid out under one git root, with
the scorer at the root and `oracles/` and `baselines/` as nested packages with
their own `pyproject.toml`. All three are installed in editable mode for
development.

1. **Clone the repo.**

   ```bash
   git clone https://github.com/openmesorah/masoretic-benchmark.git
   cd masoretic-benchmark
   ```

2. **Use Python 3.11.** The repo pins `3.11` via `.python-version`. Python
   3.12 is supported in CI for the scorer but **cannot install the
   `nakdimon` extra** (its transitive `tensorflow==2.15.0` has no 3.12
   wheel — see `.github/workflows/ci.yml` Pitfall 1 comments). Use `pyenv`
   or equivalent to honor the pin.

3. **Create and activate a virtualenv**, then install the scorer with dev
   extras:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

   The `[dev]` extra pulls in `pytest`, `pytest-cov`, `ruff`, `mypy`,
   `pre-commit`, and `PyICU` (non-Windows). PyICU requires `libicu-dev` and
   `pkg-config` system packages on Linux — CI installs them via
   `sudo apt-get install -y libicu-dev pkg-config`.

4. **Install the oracles and baselines packages** (also editable). Each is
   its own distribution with its own pin set; install only the extras you
   need for the area you are working on.

   ```bash
   # Oracles (Phase 2): scorer-light + dev tools
   pip install -e "./oracles[dev,dicta,dictabert]"
   # Add the nakdimon extra only on Python 3.11:
   pip install -e "./oracles[nakdimon]"

   # Baselines (Phase 3): replay tests + unit tests
   pip install -e "./baselines[dev]"
   # Heavy extras for the live tier (real Kraken model, real LLM APIs):
   pip install -e "./baselines[dev,kraken,llm]"
   ```

5. **Install pre-commit hooks.**

   ```bash
   pre-commit install
   ```

   This wires `.pre-commit-config.yaml` into `.git/hooks/pre-commit`. The
   hook set includes `ruff` + `ruff-format`, `gitleaks` secret scanning,
   the standard `pre-commit-hooks` (large-files, merge-conflict, yaml/json,
   `no-commit-to-branch main`), and three local Python hooks:
   `reject_binaries.py`, `reject_private_paths.py`, and
   `manifest_immutable.py` (the D-09 / append-only manifest gate, scoped
   to `phase_0_manifest.json` only).

## The three editable packages

The repo intentionally ships three independent Python distributions sharing
one git root. They are wired together by version pins in their respective
`pyproject.toml` files, not by a monorepo tool.

| Package          | Path                | Imports                                  | Role                                                                 |
|------------------|---------------------|------------------------------------------|----------------------------------------------------------------------|
| `masoretic-eval` | `./` (root)         | (none from siblings)                     | The 4-tier CER scorer. Pure, side-effect-free; depends only on third-party libs. |
| `masoretic-oracles` | `./oracles/`     | `masoretic-eval>=0.2.0,<0.3`             | Hebrew diacritization oracles (Nakdimon OSS, DICTA Nakdan, DictaBERT off-label) used by callers to compute pass-through tier-2 disagreement rates. |
| `masoretic-baselines` | `./baselines/` | `masoretic-eval[page-xml]>=0.2.0,<0.3`, `masoretic-oracles>=0.1.0,<0.2` | The four Phase 3 reference baselines (BL-01 LLM-vision, BL-02 BiblIA Kraken, BL-03 Kraken→Nakdimon, BL-04 Kraken→DictaBERT char-menaked). |

**Dependency direction is one-way.** The scorer never imports oracles or
baselines. Oracles import the scorer for shared normalization helpers.
Baselines import both. Crossing this boundary in the wrong direction is a
design violation — see ARCHITECTURE.md.

**Version-pin contract.** When you bump `masoretic-eval`'s version in the
root `pyproject.toml`, both `oracles/pyproject.toml` and
`baselines/pyproject.toml` may need their `>=X.Y,<Z` pins bumped to match.
The version-cascade workflow (`.github/workflows/version-cascade-check.yml`)
runs `scripts/check_version_cascade.py` on every PR that touches any
`pyproject.toml`; it walks all `pyproject.toml` files via `git ls-files`,
detects `[project].version` changes, and fails if any sibling pin no
longer satisfies the new version. Originating incident: Phase 03.1 W0
bumped `masoretic-eval` 0.1.0 → 0.2.0 while sibling pins read
`>=0.1.0,<0.2`; local tests passed because consumers were not installed.

## The dev loop

The end-to-end pre-commit cycle for any change:

```bash
# 1. Edit code.
# 2. Auto-fix style (matches the pre-commit hook).
ruff check --fix .
ruff format .

# 3. Strict type-check the scorer.
mypy masoretic_eval

# 4. Run the test slice you are touching.
pytest tests/test_tier1.py            # one file
pytest tests/                         # scorer suite
pytest oracles/tests/ -m "not live_oracles"
pytest baselines/tests/ -m "not live_baselines and not live_kraken"

# 5. Final guard: run pre-commit on staged files.
pre-commit run --all-files
```

### Build / dev / lint commands

| Command                                            | What it does                                                                                       |
|----------------------------------------------------|-----------------------------------------------------------------------------------------------------|
| `pip install -e ".[dev]"`                          | Install scorer in editable mode with dev extras.                                                    |
| `pip install -e "./oracles[dev,dicta,dictabert]"`  | Install oracles editable with dev + DICTA + DictaBERT extras.                                       |
| `pip install -e "./baselines[dev]"`                | Install baselines editable, mocked-test set only (no kraken/llm heavy deps).                        |
| `ruff check .`                                     | Lint (rules `E F I W B UP`, line length 100, target `py311`); CI runs without `--fix`.              |
| `ruff format .`                                    | Format. Both ruff and ruff-format run as pre-commit hooks at `v0.15.11`.                            |
| `mypy masoretic_eval`                              | Strict type-check the scorer (`strict = true` in `[tool.mypy]`, `ignore_missing_imports = true`).   |
| `pytest`                                           | Run the scorer test suite (`testpaths = tests` per `pytest.ini`).                                   |
| `pytest --cov=masoretic_eval --cov-report=term-missing` | Scorer coverage (matches the CI invocation in `ci.yml > test`).                                |
| `pytest oracles/tests/ -m "not live_oracles"`      | Mocked oracle tests. Live mode requires `RUN_LIVE_ORACLES=1`.                                       |
| `pytest baselines/tests/ -m "not live_baselines and not live_kraken"` | Mocked baseline unit tests. Live mode requires `RUN_LIVE_BASELINES=1`.           |
| `pytest baselines/tests/test_baseline_replay_llm_vision.py` | The PR-blocking replay-mode tier (D-10 + D-11) — replays committed `llm_calls/*.replay.jsonl`. |
| `pre-commit install`                               | Wire pre-commit hooks into `.git/hooks/pre-commit`.                                                 |
| `pre-commit run --all-files`                       | Run every hook (ruff, ruff-format, gitleaks, manifest immutability, binary/private-path rejection) over the entire tree. |
| `python scripts/check_version_cascade.py --base origin/main` | Manually run the version-cascade gate against a base ref.                                |
| `python scripts/manifest_immutable.py phase_0_manifest.json HEAD~1` | Manually run the manifest append-only gate.                                       |

See [TESTING.md](TESTING.md) for the full test taxonomy (unit / replay / live)
and CI matrix.

### Code style

- **Linter / formatter:** [ruff](https://docs.astral.sh/ruff/), configured
  in `[tool.ruff]` of `pyproject.toml`.
  - Line length: 100.
  - Target: `py311`.
  - Selected rule families: `E F I W B UP`.
- **Per-file ignores (D-27 disclaimer pin).** The verbatim DictaBERT
  off-label disclaimer must match character-for-character across four
  files — wrapping it would break the invariant test. `pyproject.toml`
  therefore disables `E501` (line-too-long) for:
  - `oracles/src/oracles/dictabert.py`
  - `baselines/src/baselines/biblia_char_menaked.py`

  The README copies (`oracles/README.md`, `baselines/README.md`) are
  Markdown blockquotes and are not subject to ruff. See the *D-27 verbatim
  disclaimer invariant* section below.
- **Type-checker:** mypy in strict mode. Strict mode applies to the scorer
  (`mypy masoretic_eval` in CI). Sibling packages are not in the strict
  CI gate today — strict-mode adoption for `oracles/` and `baselines/`
  is a known follow-up.
- **Pre-commit:** all of the above plus gitleaks, the manifest gate, the
  private-path leak check, the binary-extension rejection, and
  `no-commit-to-branch main` are enforced as pre-commit hooks (see
  `.pre-commit-config.yaml`).

## CI parity

CI re-runs every gate that pre-commit runs, plus more. Pre-commit catches
issues locally; CI is the source of truth.

| CI workflow file                                  | Trigger                                                       | Purpose                                                                                                |
|---------------------------------------------------|---------------------------------------------------------------|--------------------------------------------------------------------------------------------------------|
| `.github/workflows/ci.yml`                        | `push: [main]`, `pull_request: [main]`, nightly cron 06:00 UTC, manual | All gates: manifest schema validation, append-only enforcement, binary/private-path rejection, gitleaks, ruff, mypy, scorer pytest (Python 3.11 + 3.12), oracle unit + replay, baseline unit + replay, nightly oracle/baseline live drift, `[YOSEF-REVIEW]` PR-title gate. |
| `.github/workflows/version-cascade-check.yml`     | `pull_request` and `push: [main]` whose paths match `**/pyproject.toml` | Runs `scripts/check_version_cascade.py` to detect a `masoretic-eval` (or any sibling) version bump that violates pin consumers in another `pyproject.toml`. |

The two workflows are intentionally independent — the cascade check has no
test dependencies and runs on every `pyproject.toml` edit, even on direct
push to `main`, so a manual main push cannot bypass it.

## The schemas/ append-only invariant (D-09)

`schemas/` holds the JSON Schemas that constrain prediction files, run-meta
files, and the phase 0 manifest:

- `schemas/baseline_prediction.schema.json` — per-baseline prediction shape.
- `schemas/run_meta.schema.json` — per-baseline run metadata (pins, budget, combine).
- `schemas/phase_0_manifest.schema.json` — root manifest schema.

**Schema changes are append-only at the changelog level.** Every change to
a schema writes a new row at the **top** of the matching changelog file:

- `schemas/PREDICTION_SCHEMA_CHANGELOG.md` (covers both
  `baseline_prediction.schema.json` and `run_meta.schema.json`).
- `schemas/phase_0_manifest.changelog.md` (covers `phase_0_manifest.schema.json`).

Both changelogs are titled "Append-only" in their preamble and document the
D-09 (Phase 2 carry-forward) discipline: *document at bump*. Schema changes
follow these rules:

1. **Every schema is `additionalProperties: false`** at every object level
   (top-level + per-line + per-tier-4 record + pins/budget/combine). New
   keys must therefore be added to the schema, never silently emitted.
2. **Bump the schema version `const`** in the schema file when the shape
   changes; `$id` carries the URN, and a `schema_version` field is pinned
   via `const`.
3. **Append a row** to the relevant `*CHANGELOG.md` (newest first) with
   date, schema name, from/to versions, and the reason. Mirrors
   `oracles/NAKDIMON_PIN.md` format.
4. **Update producer + consumer in the same PR.** The schema is the
   contract; both sides must move together. Fixture files in
   `baselines/tests/fixtures/` should be regenerated (or the regeneration
   path in `baselines/scripts/` re-run) so committed fixtures match.
5. **Validation runs at two layers** — at write time inside the baseline's
   `SandboxRun.write_prediction` / `write_diagnostic` / `write_run_meta`,
   and at score time inside the `masoretic_eval` CLI.

## The frozen `phase_0_manifest.json`

`phase_0_manifest.json` at the repo root is the single coordination point
between the scorer, the baselines, and the IAA folio scope. It is **frozen
and append-only-immutable**, enforced by `scripts/manifest_immutable.py`
(local pre-commit hook) and re-enforced in CI by the `gates` job in
`ci.yml`.

**Allowed mutations** (per the docstring of `scripts/manifest_immutable.py`):

- Append a new `folios[]` entry (new `id`).
- Flip `in_frozen_scope` on an existing folio from `true → false` (a fuse
  event narrowing scope).
- Append to `fuses_fired[]`.
- Update top-level `frozen_at` timestamp (fuse events bump it).
- Remove a folio entry **only** under the narrow fuse-event exemption: the
  same commit appends exactly one new `manifest_changelog` row whose
  `reason` matches `^phase \d+(\.\d+)?: `, and the removed folio in HEAD
  has both `iaa_folio: false` and `gt_hash: null`.

**Rejected mutations**:

- Changing any field in `IMMUTABLE_FIELDS` on an existing folio entry.
- Flipping `in_frozen_scope` from `false → true` (a narrowed scope cannot be
  restored; ship a new folio entry with a new `id` instead).
- Removing a previously-committed folio entry except under the fuse-event
  exemption above.

If you are tempted to edit an existing folio entry, **stop**. Either append
a new folio with a new `id`, or fire a fuse event by appending a row to
`fuses_fired[]` and updating `frozen_at`. The hook will reject anything else.

The manifest is also schema-validated against
`schemas/phase_0_manifest.schema.json` in the CI `gates` job using
`jsonschema.Draft202012Validator`.

## D-27: the verbatim DictaBERT disclaimer invariant

BL-04 (DictaBERT char-menaked) is a deliberately off-label baseline — its
purpose is the paper's negative-result framing. The off-label disclaimer
is the load-bearing contract that captures this. The disclaimer text must
appear **character-for-character** in four locations:

- `oracles/src/oracles/dictabert.py` (module docstring)
- `oracles/README.md` (blockquote)
- `baselines/src/baselines/biblia_char_menaked.py` (module docstring)
- `baselines/README.md` (blockquote)

Tests pin both halves of the contract:

- Phase 2 layer: `oracles/tests/` covers the oracle module + README pair.
- Phase 3 layer: `baselines/tests/test_dictabert_disclaimer_invariant.py`
  covers the consumer module + README pair, normalizing whitespace and
  Markdown blockquote prefixes (`> `) before substring comparison so a
  re-flow of the README does not break the test, but a wording change does.

If you edit the disclaimer wording, all four files must change in the same
commit; the per-file `E501` ignores in `[tool.ruff.lint.per-file-ignores]`
exist precisely because the canonical wording exceeds 100 columns and must
not be wrapped.

## Adding a new baseline

The full evaluation methodology (headline metric, scoring procedure, frozen
scope, per-folio macro averaging) lives in
[`baselines/EVALUATION_PROTOCOL.md`](../baselines/EVALUATION_PROTOCOL.md).
Read it before adding a new baseline — the protocol is itself append-only
and pre-registered.

In broad strokes, a new baseline involves:

1. **Pick a `baseline_id`** and add it to the enum in
   `schemas/baseline_prediction.schema.json` and
   `schemas/run_meta.schema.json` (and append both changelogs — D-09).
2. **Add the implementation** under `baselines/src/baselines/<baseline_id>.py`,
   following the established three-tier discipline (D-10 + D-11 corollary):
   unit (mocked), replay (committed JSONL fixture), live (nightly real
   inference; non-blocking).
3. **Wire CI jobs** in `.github/workflows/ci.yml` mirroring the existing
   `baseline-unit` / `baseline-replay` / `baseline-live` triplet.
4. **Pin model / API versions** in a sibling `*_PIN.md` (compare
   `baselines/KRAKEN_PIN.md`, `baselines/LLM_PIN.md`,
   `oracles/NAKDIMON_PIN.md`).
5. **Provide a CLI entry point** in `baselines.run` so the live-tier CI step
   can invoke `python -m baselines.run --baseline <baseline_id>`.

## Branch and PR conventions

- **Default branch:** `main`. Direct commits to `main` are blocked locally
  by the pre-commit hook `no-commit-to-branch --branch main` and remotely
  by branch protection (CI's `pull_request` event is the required check).
- **Branch naming:** no convention is enforced in `.github/`; the
  `pull_request_template.md` does not specify one. Use a short descriptive
  branch.
- **PR template:** `.github/pull_request_template.md`. The Test plan
  checklist enumerates the required CI gates: `baseline-unit`,
  `baseline-replay`, `baseline-live` (nightly), and
  `check-yosef-review-gate`.
- **First-of-kind BL-01 PRs.** A PR that adds files under
  `results/llm_vision/` while `main` has none **must** carry the
  `[YOSEF-REVIEW]` prefix in its title. The `check-yosef-review-gate` job
  in `ci.yml` enforces this — see Phase 03.1 A-03 in the workflow comments.
  Once one human-blessed BL-01 result exists in `main`, subsequent BL-01
  PRs auto-merge on green CI.
- **Adding `results/<bl>/<folio>.json`.** The PR template requires
  `test_expected_totals.py` D-15 bit-equality verification before merge.

<!-- VERIFY: Whether a CODEOWNERS file or branch-protection rules beyond pull_request CI checks are configured at the GitHub-org level. The repo has no .github/CODEOWNERS as of writing. -->

## Where to look next

- [TESTING.md](TESTING.md) — Full test taxonomy: unit / replay / live tiers,
  marker conventions (`live_oracles`, `live_baselines`, `live_kraken`),
  fixture layout, and the D-15 bit-equality fixture invariant.
- [CONFIGURATION.md](CONFIGURATION.md) — Environment variables
  (`RUN_LIVE_ORACLES`, `RUN_LIVE_BASELINES`, `ANTHROPIC_API_KEY`,
  `GOOGLE_API_KEY`, `PHASE_0_MANIFEST_PATH`), pin files, and CI matrix.
- [ARCHITECTURE.md](ARCHITECTURE.md) — Component diagram, data flow, and
  why the three packages are independent distributions.
- [`baselines/EVALUATION_PROTOCOL.md`](../baselines/EVALUATION_PROTOCOL.md)
  — Frozen, pre-registered evaluation methodology.
