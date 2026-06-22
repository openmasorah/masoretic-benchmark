<!-- generated-by: gsd-doc-writer -->
# Getting Started

This guide walks a researcher or ML engineer through installing `masoretic-eval`
and scoring a Hebrew OCR/HTR prediction against the IAA Leningrad Codex Devarim
ground-truth fixtures shipped with this repository.

Two audiences are covered:

1. **Score your own baseline.** You have a Hebrew OCR/HTR system and want a
   reproducible CER₃ number against the same folios published baselines used.
2. **Reproduce existing baseline scores.** You want to re-run the scorer over
   the frozen predictions in `results/` and confirm the headline numbers.

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | `3.11` | Pinned in `.python-version`; declared as `requires-python = ">=3.11"` in `pyproject.toml`. CI runs Python 3.11. |
| `pip` | recent | Bundled with the Python install. |
| `git` | any | To clone the repository. |
| C build toolchain | platform-default | Required for `PyICU` (dev extra) and `lxml` wheels on some platforms. |

### Why Python 3.11 and not 3.12+

The `nakdimon` baseline (BL-03 in `baselines/`) transitively depends on
`tensorflow==2.15.0`, which has no wheel for Python 3.12 on macOS arm64. The
top-level scorer package will install on 3.12, but the baselines package will
not, and CI is pinned to 3.11. Use `pyenv` (or any equivalent version manager)
to honor the pinned interpreter:

```bash
pyenv install 3.11
pyenv local 3.11   # writes .python-version, already committed
```

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/openmasorah/masoretic-benchmark.git
   cd masoretic-benchmark
   ```

2. Create and activate a virtual environment:

   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   ```

3. Install the scorer with the dev extras:

   ```bash
   pip install -e ".[dev]"
   ```

   This installs the `masoretic_eval` package in editable mode plus `pytest`,
   `pytest-cov`, `ruff`, `mypy`, `pre-commit`, and `PyICU` (the latter is
   skipped on Windows). Runtime dependencies are `grapheme`, `click`, `lxml`,
   `rapidfuzz`, and `jsonschema`.

4. Verify the install:

   ```bash
   masoretic-eval --help
   ```

   You should see:

   ```
   Usage: masoretic-eval [OPTIONS] COMMAND [ARGS]...

     masoretic-eval: 4-tier CER scorer for medieval Hebrew.
   ```

   And:

   ```bash
   masoretic-eval score --help
   ```

   Lists the `--gt`, `--pred`, `--folio-id`, `--gt-version`, `--out`,
   `--manifest`, `--nakdimon-disagreement-rate`, and
   `--dicta-disagreement-rate` flags.

## First run: end-to-end scoring example

The CLI takes two JSON files conforming to
`masoretic_eval/schemas/scorer_input.schema.json`:

```json
{
  "text": "<Hebrew text>",
  "metamarks": [
    {"type": "large_letter", "verse_ref": "Deut.6.4", "ordinal": 1}
  ]
}
```

The smallest end-to-end run uses the CLI fixtures shipped under
`tests/fixtures/`. From the repository root:

```bash
masoretic-eval score \
  --gt tests/fixtures/cli_gt.json \
  --pred tests/fixtures/cli_pred.json \
  --folio-id leningrad_devarim_f237b \
  --manifest tests/fixtures/phase_0_manifest_sample.json \
  --out result.json
```

The scorer will print `wrote result.json`. `result.json` will contain the
4-tier scores plus the composite `cer3` headline.

### CLI flags at a glance

| Flag | Required | Default | Purpose |
|---|---|---|---|
| `--gt` | yes | — | Path to ground-truth JSON. Schema-validated. |
| `--pred` | yes | — | Path to prediction JSON. Same schema. |
| `--folio-id` | yes | — | Identifier written into `prediction_id` in the output. |
| `--out` | yes | — | Output path for the JSON score report. |
| `--gt-version` | no | `v0.1.0` | GT version stamp written into the output. |
| `--manifest` | no | `./phase_0_manifest.json` if present | Phase 0 manifest; its hash is embedded in every score report. The CLI fails if no manifest is found and none is passed. |
| `--nakdimon-disagreement-rate` | no | `None` | Pass-through diagnostic copied into `tier2.diagnostics`. Does not affect any tier CER. |
| `--dicta-disagreement-rate` | no | `None` | Pass-through diagnostic copied into `tier2.diagnostics`. Same semantics. |

The full flag reference, including configuration files and per-baseline
configuration, is in [CONFIGURATION.md](CONFIGURATION.md).

## Interpreting the output

`result.json` shape (from `masoretic_eval/output_schema.py`):

```json
{
  "prediction_id": "leningrad_devarim_f237b",
  "gt_version": "v0.1.0",
  "manifest_hash": "<16-hex>",
  "scorer_version": "0.2.0",
  "normalization": "NFD (scoring) / LC-order (raw GT)",
  "denominator_policy": {
    "tier1": "consonants_only",
    "tier2": "consonants+nikkud",
    "tier3": "full"
  },
  "qere_ketiv_policy": "score_against_qere",
  "tiers": {
    "tier1": {"cer": ..., "edits": ..., "denominator": ...},
    "tier2": {"cer": ..., "edits": ..., "denominator": ...,
              "dec": ..., "cha": ..., "wor": ..., "voc": ...,
              "nakdimon_disagreement_rate": null,
              "dicta_disagreement_rate": null},
    "tier3": {"cer": ..., "edits": ..., "denominator": ...},
    "tier4": {"f1": ..., "precision": ..., "recall": ...,
              "tp_exact": ..., "tp_partial": ..., "fp": ..., "fn": ...}
  },
  "composite": {"cer3": ...},
  "confusion_matrices": { ... },
  "caveats": [ ... ]
}
```

What each number means:

- **`composite.cer3`** — Headline score. `0.5·tier1 + 0.3·tier2 + 0.2·tier3`.
  Lower is better. This is the single number to compare baselines on.
- **`tiers.tier1.cer`** — Consonant-only CER. Te'amim and nikkud stripped
  before scoring. Use this if your system only emits consonants.
- **`tiers.tier2.cer`** — Consonants + nikkud CER (te'amim stripped).
  `dec`/`cha`/`wor`/`voc` are nikkud-substitution diagnostics surfaced from
  `masoretic_eval/tiers/`.
- **`tiers.tier3.cer`** — Full-text CER over every codepoint, including
  te'amim.
- **`tiers.tier4.f1`** — F1 over `(type, verse_ref, ordinal)` metamark
  records. Tier 4 is **not** a CER. Partial credit (⅓) when `(type, verse_ref)`
  matches but ordinal disagrees. `precision`/`recall`/`tp_exact`/`tp_partial`
  are the underlying counts.
- **`manifest_hash`** — Hash of the `phase_0_manifest.json` used. Re-running
  with a different manifest produces a different hash and is therefore not
  comparable.

Alignment is over UAX #29 grapheme clusters; edits are counted in codepoints
within aligned cluster pairs. CGJ (U+034F) is stripped at scoring time. See
[ARCHITECTURE.md](ARCHITECTURE.md) for the full data flow.

## Where the IAA benchmark fixtures live

Hand-transcribed tier-1 ground truth for the four Leningrad Codex Devarim
folios is stored at:

```
baselines/tests/fixtures/
├── iaa_folio_leningrad_devarim_F118B_fixture.gt_adapter_golden.json
├── iaa_folio_leningrad_devarim_F119A_fixture.gt_adapter_golden.json
├── iaa_folio_leningrad_devarim_F119B_fixture.gt_adapter_golden.json
└── iaa_folio_leningrad_devarim_F120A_fixture.gt_adapter_golden.json
```

These are the per-line GT golden files (shape: `folio_id` + `lines` array) that
the baseline pipelines consume. They are **not** the direct CLI scorer input
shape — the CLI takes the `text` + `metamarks` JSON described above. The
IAA-folio fixtures are converted into scorer-input shape during the baseline
evaluation pipeline; the methodology is documented in
[`baselines/EVALUATION_PROTOCOL.md`](../baselines/EVALUATION_PROTOCOL.md).

Frozen baseline predictions and the headline scores per folio live in
`results/`:

- `results/biblia_kraken/`, `results/biblia_nakdimon/`,
  `results/biblia_char_menaked/`, `results/llm_vision/` — per-baseline raw
  prediction artifacts plus `run_meta.json`.
- `results/scores/leningrad_devarim_F118B_fixture.json` — published headline
  scores for F118B across all four baselines.

Benchmark text licensing differs per folio: F118B tier-1 GT is hand-transcribed
(CC-BY-4.0); F119A/F119B/F120A tier-1 GT is UXLC-derived (UXLC 2.5, tanach.us —
free to copy without restriction, citation appreciated; not CC0). See the
README "IAA benchmark fixtures" section and each fixture's
`_provenance` block. Only IIIF/archive.org references are stored for the
manuscript images; no manuscript images are redistributed in this repository.

## Common setup issues

- **`pip install` fails on Python 3.12+ when adding the baselines package.**
  Cause: `nakdimon` → `tensorflow==2.15.0` has no wheel for Python 3.12 on
  macOS arm64. Fix: install Python 3.11 via `pyenv` and reinstall in a fresh
  venv. The top-level `masoretic-eval` package alone will install on 3.12, but
  the baselines and CI are 3.11-only.
- **`masoretic-eval --help` prints `command not found`.** Cause: virtual
  environment is not activated, or `pip install -e .` was run without the
  active venv. Fix: `source .venv/bin/activate`, then re-run
  `pip install -e ".[dev]"`.
- **CLI fails with `manifest required: pass --manifest or run from a directory
  containing phase_0_manifest.json`.** Cause: every score report embeds the
  manifest hash for reproducibility. Fix: either run from the repository root
  (where `phase_0_manifest.json` lives) or pass `--manifest path/to/manifest.json`
  explicitly. The test fixture at `tests/fixtures/phase_0_manifest_sample.json`
  is a valid minimal manifest for experimentation.
- **`schema validation failed for --gt ...` or `--pred ...`.** Cause: the input
  JSON does not match `masoretic_eval/schemas/scorer_input.schema.json`. Fix:
  ensure the file has top-level `text` (string) and `metamarks` (array of
  `{type, verse_ref, ordinal}` objects) keys — `additionalProperties` is
  `false`, so extra top-level keys will also fail validation.
- **`PyICU` build fails during `pip install -e ".[dev]"`.** Cause: missing
  ICU system library headers. Fix on macOS: `brew install icu4c` and export
  `PKG_CONFIG_PATH` per Homebrew's instructions before re-running `pip
  install`. `PyICU` is dev-only (used for the cross-validation alignment
  guard in `tests/test_external_crossval.py`); the runtime scorer does not
  require it.

## Next steps

- [ARCHITECTURE.md](ARCHITECTURE.md) — Components, data flow, and the
  scorer's tier abstractions.
- [CONFIGURATION.md](CONFIGURATION.md) — Full CLI flag reference, baseline
  configuration files, and the `phase_0_manifest.json` schema.
- [`baselines/EVALUATION_PROTOCOL.md`](../baselines/EVALUATION_PROTOCOL.md) —
  How the published headline scores were computed (whole-folio CER methodology,
  per-baseline reproducibility tier).
- `CONTRIBUTING.md` (root) — How to submit a new baseline. A static
  `leaderboard.json` plus PR-based submission flow is on the v0.3 roadmap; for
  now, score locally by emitting a prediction JSON that matches
  `schemas/baseline_prediction.schema.json` and running `masoretic-eval score`.
