<!-- generated-by: gsd-doc-writer -->
# masoretic-eval

![CI](https://github.com/openmesorah/masoretic-benchmark/actions/workflows/ci.yml/badge.svg)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](.python-version)

A 4-tier Character Error Rate (CER) scorer and public benchmark dataset for medieval Hebrew manuscript transcription.

`masoretic-eval` evaluates Hebrew OCR/HTR predictions against ground truth at four tiers — consonants, nikkud, full text, and metamark records — producing reproducible, pre-registered scores for the IAA Leningrad Codex Devarim folio set.

## Installation

```bash
pip install -e ".[dev]"
```

Requires Python 3.11. The repo pins `3.11` via `.python-version`; Python >= 3.12 cannot install the `nakdimon` baseline because its transitive `tensorflow==2.15.0` dependency has no wheel for 3.12 on macOS arm64. Use `pyenv` (or equivalent) to honor the pinned version. CI runs Python 3.11.

## Quick start

1. Install with dev extras (above).
2. Score a prediction against ground truth using the `masoretic-eval` CLI:

   ```bash
   masoretic-eval score \
     --gt path/to/gt.json \
     --pred path/to/prediction.json \
     --folio-id leningrad_devarim_F118B \
     --out result.json
   ```

3. Inspect `result.json` for tier 1–4 CER scores and the composite headline score.

A `phase_0_manifest.json` must be present in the working directory or supplied with `--manifest`.

## Usage

### CLI input shape

Both `--gt` and `--pred` JSON files conform to `masoretic_eval/schemas/scorer_input.schema.json`:

```json
{
  "text": "<Hebrew text — UXLC LC-order for GT; any order for prediction>",
  "metamarks": [{"type": "large_letter", "verse_ref": "Deut.6.4", "ordinal": 1}]
}
```

### Optional oracle pass-through fields

`nakdimon_disagreement_rate` and `dicta_disagreement_rate` are pass-through inputs computed externally by the caller; the scorer emits them unchanged in its output:

```bash
masoretic-eval score \
  --gt gt.json --pred pred.json --folio-id leningrad_devarim_F118B \
  --nakdimon-disagreement-rate 0.041 \
  --dicta-disagreement-rate 0.038 \
  --out result.json
```

### Repository layout

| Path | Purpose |
|---|---|
| `masoretic_eval/` | Scorer Python package (Apache-2.0). |
| `baselines/` | Four independent baselines: BL-01 LLM-vision, BL-02 BiblIA Kraken, BL-03 Kraken→Nakdimon, BL-04 Kraken→DictaBERT char-menaked. |
| `oracles/` | Hebrew diacritization oracle modules consumed externally to populate the scorer's pass-through tier-2 fields. |
| `schemas/` | JSON Schemas + changelogs for `baseline_prediction.schema.json`, `phase_0_manifest.schema.json`, and `run_meta.schema.json`. |
| `results/` | Frozen per-baseline predictions plus `results/scores/` headline CER reports for the IAA folios. |
| `scripts/` | Release and gate scripts (manifest immutability, version-cascade, private-path rejection). |
| `tests/` | Scorer test suite. |
| `docs/` | Architecture, getting-started, development, testing, and configuration guides. |
| `phase_0_manifest.json` | Frozen, append-only fixture manifest hashed into every score report. |

### IAA benchmark fixtures

Hand-transcribed tier-1 ground truth for the 4-folio IAA set (Leningrad Devarim F118B, F119A, F119B, F120A) lives at `baselines/tests/fixtures/iaa_folio_leningrad_devarim_*_fixture.gt_adapter_golden.json`. Text is CC-BY-4.0; only IIIF/archive.org references are stored — no manuscript images are redistributed. Per-baseline headline scores for F118B are in `results/scores/leningrad_devarim_F118B_fixture.json`.

## Methodology

### Normalization

- Inputs are NFD-normalized at scoring time. Ground truth ships as raw UXLC LC-order, byte-for-byte.
- CGJ (U+034F) is stripped during scoring.

### Alignment and edit counting

- **Alignment unit:** UAX #29 grapheme clusters.
- **Edit unit:** codepoints within aligned cluster pairs.
- Unaligned (inserted/deleted) clusters contribute edits equal to their codepoint count.
- Cross-validated in CI against PyICU and against a hand-rolled naive Levenshtein on shared fixtures (anti-self-grading guard).

### Tiered denominator policy

- **Tier 1:** consonant codepoints only (te'amim + nikkud stripped).
- **Tier 2:** consonant + nikkud codepoints (te'amim stripped).
- **Tier 3:** full codepoint count.
- **Tier 4:** F1 over `(type, verse_ref, ordinal)` metamark records — not CER. Partial credit (⅓) when `(type, verse_ref)` matches but ordinal is wrong.

### Composite headline score

`CER₃ = 0.5·cer_consonantal + 0.3·cer_nikkud + 0.2·cer_full`. Tier 4 is reported separately.

### Qere/ketiv

Scored against qere by default (UXLC `<q>` element when present). Ketiv-only words use `<k>`.

## Known limitations (v0.2 scorer)

- Oracle disagreement rates are pass-through only; the scorer does not compute them.
- The UXLC loader is exercised on Deuteronomy fixtures; coverage for other books is pending.
- The tier 4 metamark type taxonomy is the week-1 schema-decision inventory; additions require a scorer version bump.

## License

| Artifact | License |
|---|---|
| Scorer code (`masoretic_eval/`) | Apache 2.0 |
| Benchmark text ground truth | CC-BY-4.0 |
| Manuscript images | Fetched via IIIF from archive.org (PDM 1.0); never redistributed |

See [LICENSE](LICENSE) for the full Apache 2.0 text.

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — Components, data flow, and key abstractions.
- [Getting Started](docs/GETTING-STARTED.md) — Prerequisites and first-run walkthrough.
- [Development](docs/DEVELOPMENT.md) — Local setup, build commands, and code style.
- [Testing](docs/TESTING.md) — Test framework, coverage policy, and CI integration.
- [Configuration](docs/CONFIGURATION.md) — Environment variables, manifest, and runtime settings.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines. A static `leaderboard.json` and PR-based submission flow will land in a follow-up release; in the meantime, new baselines can be scored locally by emitting a prediction JSON that matches `schemas/baseline_prediction.schema.json` and running `masoretic-eval score`.

## Citation

A BibTeX entry will be added at paper submission. For now:

```bibtex
@misc{lamm2026masoretic,
  title  = {masoretic-eval: 4-tier CER scorer for medieval Hebrew},
  author = {Lamm, Ben and Ginsberg, Yosef},
  year   = {2026},
  note   = {v0.2.0, https://github.com/openmesorah/masoretic-benchmark}
}
```
