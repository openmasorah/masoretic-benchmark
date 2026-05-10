<!-- generated-by: gsd-doc-writer -->
# Contributing to masoretic-benchmark

Thank you for your interest in contributing. `masoretic-benchmark` is a public,
pre-registered evaluation benchmark for medieval Hebrew OCR/HTR. Because the
benchmark's load-bearing claim is **reproducibility**, contribution rules are
stricter than a typical open-source library — methodology stability, append-only
provenance, and licensing discipline are all enforced by CI gates.

This guide covers what we accept, how to submit it, and the invariants you must
preserve.

## Code of conduct

Contributors are expected to be respectful and professional. There is no
separate `CODE_OF_CONDUCT.md` at this time; please open a GitHub issue if you
encounter unacceptable behavior.

## Development setup

Setup, pinned versions, and run-locally instructions live in the project's
documentation tree:

- [README.md](README.md) — install + first scoring run
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md) — Python pin, optional extras,
  manifest, and runtime settings
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — how the scorer, baselines,
  oracles, schemas, and manifest fit together

In short: Python 3.11 (pinned via `.python-version`), `pip install -e ".[dev]"`,
then `pytest` to confirm the scorer suite is green before you change anything.

## Scope of contributions accepted

The benchmark is split into two stability classes:

### Welcomed contributions

- **Scorer bug fixes** — corrections to alignment, normalization, denominator
  policy, or tier-4 F1 logic in `masoretic_eval/` that align the implementation
  with the methodology declared in [`baselines/EVALUATION_PROTOCOL.md`](baselines/EVALUATION_PROTOCOL.md)
  and `README.md` "Methodology" section.
- **New baselines** — additional OCR/HTR systems scored against the IAA folio
  set. Land a new module under `baselines/src/baselines/`, add it to the
  `BASELINE_ID` enum if needed, and emit predictions conforming to
  `schemas/baseline_prediction.schema.json`.
- **New oracle integrations** — additional Hebrew diacritization back-ends
  under `oracles/src/oracles/`, exposed to the scorer's optional pass-through
  fields (`--nakdimon-disagreement-rate`, `--dicta-disagreement-rate`).
- **Fixture additions** — new IAA folios, new synthetic test fixtures, or
  expanded coverage of UXLC books beyond Deuteronomy.
- **Documentation improvements** — clarifications, typo fixes, expanded
  examples, and additional protocol explanation.

### Out of scope (for v0.2)

The following changes are **discouraged** until a tagged release explicitly
reopens them, because v0.1 results are pre-registered against the methodology
frozen on 2026-04-30:

- Changing the headline metric, tier denominators, alignment unit, or composite
  weighting (`CER₃ = 0.5·cer_consonantal + 0.3·cer_nikkud + 0.2·cer_full`).
- Changing the metamark type taxonomy without a scorer version bump. Note: tier 4
  ("metamark records") covers **body-text-internal** marks only — sof pasuq,
  paseq, maqqef, puncta extraordinaria, gershayim, and similar in-line marks. The
  full marginal masorah apparatus (Masorah parva, Masorah magna) is a separate
  research milestone and is **not** a tier of this benchmark; do not propose
  expanding tier 4 to cover Mp/Mg.
- Re-scoring an existing folio with a tweaked methodology and overwriting prior
  results.

If you believe an evaluation methodology change is necessary, open an issue
first, and read the **Methodology stability covenant** below before submitting
a PR.

## Methodology stability covenant

The scorer's evaluation methodology is **pre-registered**. Concretely:

- [`baselines/EVALUATION_PROTOCOL.md`](baselines/EVALUATION_PROTOCOL.md) is
  append-only. Every methodology change writes a new row at the top with date
  and reason; historical rows are never edited.
- Any change to scoring methodology (alignment, normalization, tier denominators,
  composite weighting, metamark taxonomy) requires:
  1. A new row in `EVALUATION_PROTOCOL.md` with date + reason.
  2. A `pyproject.toml` `[project].version` bump on `masoretic-eval`.
  3. A corresponding `manifest_changelog` entry in `phase_0_manifest.json`.
- The `version-cascade-check.yml` CI workflow enforces that scorer version
  bumps do not silently break the pin constraints in
  `oracles/pyproject.toml` and `baselines/pyproject.toml`.

PRs that change scoring behavior without a version bump will fail CI.

## Baseline submission flow

A static `leaderboard.json` and a fully automated PR-based leaderboard
submission flow are planned for a follow-up release. **The current path** for
contributing a new baseline is:

1. Add a new baseline module under `baselines/src/baselines/<baseline_id>.py`.
   Subclass the patterns in `_base.py` and follow the structure of an existing
   baseline (`biblia_kraken.py`, `llm_vision.py`, `biblia_nakdimon.py`,
   `biblia_char_menaked.py`).
2. If the baseline introduces a new ground-truth fixture, add it under
   `baselines/tests/fixtures/iaa_folio_<fixture_id>.gt_adapter_golden.json`,
   following the existing F118B / F119A / F119B / F120A schema. Only IIIF /
   archive.org references are stored; no manuscript images are ever
   redistributed.
3. Generate predictions per folio and commit them to
   `results/<baseline_id>/<fixture_id>.json`, conforming to
   `schemas/baseline_prediction.schema.json`.
4. Score locally with the `masoretic-eval` CLI; commit the score report to
   `results/scores/<fixture_id>.json` if your baseline materially changes the
   leaderboard for that folio.
5. Open a PR. The `baseline-unit` and `baseline-replay` jobs are PR-blocking;
   `baseline-live` runs nightly and is non-blocking.

### First-of-kind LLM-vision PRs

If your PR adds the **first** file under `results/llm_vision/` to `main`, the
PR title must start with `[YOSEF-REVIEW]` per Phase 03.1 A-03. The
`check-yosef-review-gate` CI job enforces this. Subsequent BL-01 folio PRs do
not require the prefix and auto-merge on green CI.

## D-27 verbatim disclaimer invariant

Baselines and oracles that wrap external services with a known off-label or
licensing-sensitive use must carry the **D-27 disclaimer** verbatim in source
and READMEs. The disclaimer text appears character-for-character in all four
of these locations and is enforced by an invariant test:

- `oracles/src/oracles/dictabert.py`
- `oracles/README.md`
- `baselines/src/baselines/biblia_char_menaked.py`
- `baselines/README.md`

Wrapping, paraphrasing, or reformatting the disclaimer breaks the D-27 invariant
test. The `tool.ruff.lint.per-file-ignores` block in the root `pyproject.toml`
suppresses E501 line-length on these two source files specifically because the
disclaimer must not be wrapped.

If you add a new baseline or oracle that integrates with DICTA or any other
external service whose terms require an off-label / licensing notice, replicate
the D-27 pattern: emit the disclaimer verbatim across the four matching
locations and add an invariant test that pins the byte-equality.

## Append-only artifacts

The following files are **append-only**. Pull requests that modify or remove
existing entries (rather than appending new ones) will fail CI gates:

| Path | Gate |
|---|---|
| `phase_0_manifest.json` | `scripts/manifest_immutable.py` (CI: Repository gates → Enforce manifest append-only immutability) |
| `baselines/EVALUATION_PROTOCOL.md` | Convention; reviewers enforce |
| `schemas/phase_0_manifest.changelog.md` | Convention; reviewers enforce |
| `schemas/PREDICTION_SCHEMA_CHANGELOG.md` | Convention; reviewers enforce |

JSON Schemas under `schemas/` are versioned. Breaking changes to a schema
require a new schema file (or explicit `$id` version bump) plus an entry in
the corresponding changelog; existing baselines must keep validating against
their pinned schema version.

## Licensing rules

Different artifacts in the repo carry different licenses. PRs that add content
must respect this split:

| Artifact | License | Notes |
|---|---|---|
| Scorer code (`masoretic_eval/`, `baselines/src/`, `oracles/src/`, `scripts/`, `schemas/`) | Apache-2.0 | Match the root `LICENSE` file. |
| New ground-truth Hebrew text (e.g., new IAA fixtures) | CC-BY-4.0 | Attribution required. State the source in the fixture file or accompanying `*_PIN.md`. |
| Manuscript images | **Never redistributed** | Reference only via IIIF or archive.org URLs. |
| External model artifacts (Kraken weights, Nakdimon checkpoints, DictaBERT models) | Upstream license | Pin a hash and source URL in the corresponding `*_PIN.md` file (e.g., `KRAKEN_PIN.md`, `NAKDIMON_PIN.md`, `LLM_PIN.md`); never check binary weights into git. |

The `gates` CI job runs `scripts/reject_binaries.py` and
`scripts/reject_private_paths.py`; PRs that add binaries, oversized files, or
references to private paths will fail before tests run. Gitleaks runs on every
PR.

## Code style

- **Linter:** [ruff](https://docs.astral.sh/ruff/) with `select = ["E", "F", "I", "W", "B", "UP"]` and `line-length = 100`. Run locally with `ruff check .`.
- **Type-checker:** mypy in `strict` mode against the `masoretic_eval` package. Run locally with `mypy masoretic_eval`.
- **Formatter:** ruff's import sorting (`I`) is enforced; there is no separate Black step.
- **Pre-commit:** install with `pre-commit install` (after `pip install -e ".[dev]"`); the same checks run in CI as a pre-merge gate.
- The D-27 disclaimer files (`oracles/src/oracles/dictabert.py` and `baselines/src/baselines/biblia_char_menaked.py`) carry a per-file `E501` ignore — do not wrap their disclaimer blocks to "fix" line length.

## CI gates summary

Every PR runs the following jobs (PR-blocking unless noted). See
`.github/workflows/ci.yml` for the full definitions:

- `gates` — manifest schema validation, manifest append-only enforcement, binary/private-path rejection, gitleaks
- `test` — ruff, mypy, pytest with coverage, external cross-validation, manifest schema validation (Python 3.11 + 3.12)
- `oracle-unit` — oracle unit tests (Python 3.11 + 3.12)
- `baseline-unit` — baseline unit tests including structural invariants (D-12, D-15, BASELINE_ID enum, DictaBERT D-27 disclaimer, KRAKEN_PIN provenance)
- `baseline-replay` — replay-mode tests against committed `llm_calls/*.replay.jsonl` fixtures (no live API calls)
- `check-yosef-review-gate` — first-of-kind BL-01 PR title check
- `cascade-check` (separate workflow) — pyproject pin cascade across the three packages
- `oracle-live` and `baseline-live` — nightly drift detectors; non-blocking, run on schedule and `workflow_dispatch` only

## Pull request conventions

- **Branch naming:** no enforced convention; descriptive `feat/...`, `fix/...`, `docs/...` are recommended.
- **Title:** keep PR titles short and descriptive. Prefix with `[YOSEF-REVIEW]` only when the gate applies (see above).
- **Body:** the repository ships a PR template at `.github/pull_request_template.md` with a checklist for CI green, Yosef-review approval (when applicable), and D-15 bit-equality verification (when adding `results/<bl>/<folio>.json`). Fill the template honestly — reviewers rely on it.
- **Atomic changes:** one logical change per PR. Methodology changes do not share a PR with bug fixes.
- **CI:** PRs must be green before merge. Do not bypass with `--no-verify` or `continue-on-error`.

## Reporting issues

Open issues at <https://github.com/openmasorah/masoretic-benchmark/issues>. There
is no formal bug template; please include:

- What you ran (CLI invocation, Python version, OS).
- What you expected (cite the spec — `EVALUATION_PROTOCOL.md`, `README.md` methodology, or a schema).
- What you observed (full traceback, score report, or diff).
- Reproduction steps against a committed fixture if possible (e.g., `iaa_folio_leningrad_devarim_F118B_fixture.gt_adapter_golden.json`).

For methodology questions or proposed evaluation changes, open an issue
**before** opening a PR — methodology changes require pre-registration in
`EVALUATION_PROTOCOL.md` and a coordinated version bump.

## License

By contributing, you agree that your contributions to scorer / baseline /
oracle code are licensed under Apache-2.0 (see [LICENSE](LICENSE)) and that
ground-truth text contributions are licensed under CC-BY-4.0.
