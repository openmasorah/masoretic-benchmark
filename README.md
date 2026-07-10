<!-- generated-by: gsd-doc-writer -->
# masoretic-eval

![CI](https://github.com/openmasorah/masoretic-benchmark/actions/workflows/ci.yml/badge.svg)
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
| `results/` | *(Not in v0.1.)* Automated baselines are deferred to v0.1.1 — see [Baselines](#baselines). |
| `scripts/` | Release and gate scripts (manifest immutability, version-cascade, private-path rejection). |
| `tests/` | Scorer test suite. |
| `docs/` | Architecture, getting-started, development, testing, and configuration guides. |
| `phase_0_manifest.json` | Frozen, append-only fixture manifest hashed into every score report. |

### IAA benchmark fixtures

Tier-1 ground truth for the 4-folio IAA set (Leningrad Devarim F118B, F119A, F119B, F120A) lives at `baselines/tests/fixtures/iaa_folio_leningrad_devarim_*_fixture.gt_adapter_golden.json`. Provenance and licensing differ per folio (see each fixture's `_provenance` block):

- **F118B** — hand-transcribed from PDM 1.0 archive.org photographs of the Leningrad Codex. CC-BY-4.0 (attribution: Open Masorah).
- **F119A, F119B, F120A** — UXLC-derived (UXLC 2.5, [tanach.us](https://tanach.us/)) via `gt_infra.uxlc_import`. The UXLC biblical Hebrew text is distributed by Tanach.us Inc. free to view or copy without restriction (citation to Tanach.us appreciated) — see [tanach.us/License.html](https://tanach.us/License.html). This is a custom permissive grant, **not** a formal CC0-1.0 dedication.

Only IIIF/archive.org references are stored — no manuscript images are redistributed.

### Baselines

**v0.1 publishes no baseline scores.** This release is the benchmark itself: the adjudicated ground truth, the inter-annotator agreement measurement, and the scorer. Automated baselines are deferred to **v0.1.1**.

An earlier draft of this repository carried F118B scores for four baselines. They were **retracted before publication**, for two independent reasons:

- The whole-folio CER was computed over Kraken's 109 segmented lines — which include the masorah magna and parva apparatus — against 26 physical lines of main-text ground truth, with every bounding box `[0,0,0,0]` so reading order fell back to `line_id`. The resulting ranking is *inverted*: it reports `biblia_kraken` as the weakest system when ROI-restricted main-text scoring puts it strongest on consonants.
- The `biblia_char_menaked` tier-2/3 predictions were corrupt — an unpinned `transformers` release produced cumulative prefix repetition (tier-2 output 3.3× the length of tier-1, with nikkud on 7 of 109 lines). Those bytes are not model output and cannot be published with a caveat.

v0.1.1 will re-emit both from real runs, under a pinned `transformers` and an ROI/main-text methodology.

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
| Benchmark text GT — F118B (hand-transcribed) | CC-BY-4.0 (Open Masorah) |
| Benchmark text GT — F119A/F119B/F120A (UXLC-derived) | UXLC 2.5 (tanach.us) — free to copy without restriction, citation appreciated; not CC0 ([license](https://tanach.us/License.html)) |
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

If you use this benchmark or scoring suite, please cite. GitHub renders a "Cite this repository" widget from `CITATION.cff`; the BibTeX form for paper bibliographies is:

```bibtex
@dataset{lamm2026masoretic,
  title        = {Open Masorah Masoretic Benchmark: a 4-tier CER evaluation suite for medieval Tiberian Hebrew},
  author       = {Lamm, Ben and Ginsberg, Yosef and Finkelstein, Ari},
  year         = {2026},
  version      = {0.2.0},
  howpublished = {Hugging Face dataset, \url{https://huggingface.co/datasets/openmasorah/masoretic-benchmark-v0.1}},
  note         = {Code: \url{https://github.com/openmasorah/masoretic-benchmark}}
}
```

A peer-reviewed paper citation will be added when the JCDL 2027 submission lands.

## Acknowledgements

This benchmark builds on openly available sources, gratefully acknowledged (full machine-readable entries are in `CITATION.cff` under `references:`):

- **Leningrad Codex** (Samuel ben Jacob, c. 1008 CE; Firkovich MS Evr. I B19a, National Library of Russia) — the base manuscript, via West Semitic Research Project photographs on the [Internet Archive](https://archive.org/details/Leningrad_Codex_Color_Images) (Public Domain Mark 1.0). Images are referenced by IIIF only, never redistributed.
- **UXLC / Tanach.us** — the Unicode/XML Leningrad Codex 2.5 (Tanach.us Inc.), source of the tier-1 ground truth (F119A/F119B/F120A) and the tier-2 UXLC backbone. Tanach.us asks that citation of the site as the source of the text be made, and we gladly do so — see [tanach.us](https://tanach.us/).
- **Kraken** (B. Kiessling, DH 2019) and the **BiblIA** medieval-Hebrew model + dataset (D. Stökl Ben Ezra et al., HIP '21) — OCR/HTR baselines BL-02 / BL-03.
- **Nakdimon** (E. Gershuni & Y. Pinter, NAACL Findings 2022) — diacritization for baseline BL-03 and the primary oracle.
- **DICTA Nakdan** (A. Shmidman et al., ACL 2020) and **DictaBERT** (S. Shmidman et al., 2023) — the secondary diacritization oracle and the off-label negative-result baseline BL-04.
- **Unicode Standard Annex #29** (The Unicode Consortium) — grapheme-cluster segmentation underlying the scorer's cluster-aligned alignment.
