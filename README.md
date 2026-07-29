<!-- generated-by: gsd-doc-writer -->
# masoretic-eval

![CI](https://github.com/openmasorah/masoretic-benchmark/actions/workflows/ci.yml/badge.svg)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](.python-version)

> **Licensing:** the Apache-2.0 badge above covers the scorer *code* only. The dataset is multi-component — consonantal text is Public Domain, annotation data (Tiers 2–4) is CC0-1.0, and Open Masorah's schema, adjudication, and compilation are CC-BY-4.0. See [`LICENSE.md`](LICENSE.md) for the authoritative statement.

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
| `baselines/` | Baseline code. Automated BL-01 LLM-vision, BL-02 BiblIA Kraken, BL-03 Kraken→Nakdimon, BL-04 Kraken→DictaBERT char-menaked (scores deferred to v0.1.1); BL-05 rafe text-rule is scored — see [Baselines](#baselines). |
| `oracles/` | Hebrew diacritization oracle modules consumed externally to populate the scorer's pass-through tier-2 fields. |
| `schemas/` | JSON Schemas + changelogs for `baseline_prediction.schema.json`, `phase_0_manifest.schema.json`, and `run_meta.schema.json`. |
| `results/` | *(Not in v0.1.)* Automated baselines are deferred to v0.1.1 — see [Baselines](#baselines). |
| `scripts/` | Release and gate scripts (manifest immutability, version-cascade, private-path rejection). |
| `tests/` | Scorer test suite. |
| `docs/` | Architecture, getting-started, development, testing, and configuration guides. |
| `phase_0_manifest.json` | Frozen, append-only fixture manifest hashed into every score report. |

### IAA benchmark fixtures

The 4-folio IAA set (Leningrad Devarim F118B, F119A, F119B, F120A) ships in `iaa_data/devarim_4folio/` (each folio's `gt_source` is pinned in `phase_0_manifest.json`). It is a **multi-component artifact** with per-component rights: the consonantal text (Tier 1) is public domain, the annotation data (Tiers 2–4) is CC0-1.0, and Open Masorah's schema, adjudication, and compilation are CC-BY-4.0. See [`LICENSE.md`](LICENSE.md) for the authoritative statement, and [`ACKNOWLEDGMENTS.md`](ACKNOWLEDGMENTS.md) for text-source credits (UXLC/Tanach.us for F119A/B/120A; WSRP photographs for F118B).

Note: each ground-truth JSON carries an embedded `"license": "CC-BY-4.0"` field that refers to the file **as a compiled projection**, not to the public-domain text or CC0 data it contains (see [`LICENSE.md`](LICENSE.md)). No manuscript images are redistributed — only IIIF references are stored.

### Baselines

**v0.1 publishes no automated OCR/HTR baseline scores.** The release is the benchmark itself — the adjudicated ground truth, the inter-annotator agreement measurement, and the scorer — plus one parameter-free text-rule baseline (BL-05, below) that needs no model, image, or network. The automated OCR/HTR baselines (BL-01–BL-04) are deferred to **v0.1.1**.

An earlier draft of this repository carried F118B scores for four baselines. They were **retracted before publication**, for two independent reasons:

- The whole-folio CER was computed over Kraken's 109 segmented lines — which include the masorah magna and parva apparatus — against 26 physical lines of main-text ground truth, with every bounding box `[0,0,0,0]` so reading order fell back to `line_id`. The resulting ranking is *inverted*: it reports `biblia_kraken` as the weakest system when ROI-restricted main-text scoring puts it strongest on consonants.
- The `biblia_char_menaked` tier-2/3 predictions were corrupt — an unpinned `transformers` release produced cumulative prefix repetition (tier-2 output 3.3× the length of tier-1, with nikkud on 7 of 109 lines). Those bytes are not model output and cannot be published with a caveat.

v0.1.1 will re-emit both from real runs, under a pinned `transformers` and an ROI/main-text methodology.

#### Tier-4 detection baseline: rafe text-rule (BL-05)

The first rule scored on this benchmark's tier-4 axis. A parameter-free linguistic rule — predict a *rafe* on every begadkefat consonant (ב ג ד כ ך פ ף ת) that lacks a dagesh — recovers the Leningrad scribe's actual rafe placement with **F1 0.621 (exact) [0.574, 0.665]**, precision 0.476, recall 0.892, scored against the adjudicated consensus `tier4_positional` rafe set with the same matcher the IAA panel uses.

This is an **oracle-text** baseline: it reads consonants and dagesh from the consensus transcription itself (perfect tier-1/tier-2 in), so it measures only how discriminative the tier-4 rafe axis is under a deterministic rule — it is **not** an end-to-end image→tier-4 system, which remains open. Recall is definitionally the share of the scribe's rafe on begadkefat letters (272/305; the other 33 sit on א/ה/ו, which the rule structurally cannot reach), so all discriminative variation lives in precision (rafe is placed selectively, not on every eligible consonant) — that gap is the headroom a context-aware system would close. It demonstrates the tier-4 rafe axis is scoreable and discriminative.

Fully reproducible from public CC-BY data — no images, no model, no network:

```
python scripts/regenerate_rafe_tier4_baseline.py   # writes rafe_tier4_baseline.json (gitignored)
```

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

Open Masorah v0.1 is multi-component. [`LICENSE.md`](LICENSE.md) is the authoritative per-component statement; summary:

| Component | License / status |
|---|---|
| Consonantal text (Tier 1, all folios) | **Public Domain** (Leningrad Codex, ~1008 CE; no copyright exists) |
| Annotation data (Tiers 2–4: nikkud, cantillation, meta-marks) | **CC0-1.0** (factual observations) |
| Scholarly framework (JSON schema, adjudication protocol, error taxonomy) | **CC-BY-4.0** (Open Masorah — attribution required) |
| Four-folio benchmark compilation (selection + structure) | **CC-BY-4.0** (Open Masorah — attribution required) |
| Scorer code (`masoretic_eval/`) | **Apache-2.0** |
| Manuscript images | Not licensed by Open Masorah — WSRP photographs, IIIF-reference-only, never redistributed |

Text-source credits (UXLC/Tanach.us, WSRP) are in [`ACKNOWLEDGMENTS.md`](ACKNOWLEDGMENTS.md). The [`LICENSE`](LICENSE) file holds the Apache-2.0 text for the scorer code.

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
  author       = {Lamm, Ben and Ginsberg, Yosef and Moster, David Zev and Finkelstein, Ari},
  year         = {2026},
  version      = {0.1.0},
  howpublished = {Hugging Face dataset, \url{https://huggingface.co/datasets/openmasorah/masoretic-benchmark-v0.1}},
  note         = {Code: \url{https://github.com/openmasorah/masoretic-benchmark}}
}
```

A peer-reviewed paper citation will be added when the JCDL 2027 submission lands.

## Acknowledgements

This benchmark builds on openly available sources, gratefully acknowledged (full machine-readable entries are in `CITATION.cff` under `references:`):

- **Leningrad Codex** (Samuel ben Jacob, c. 1008 CE; Firkovich MS Evr. I B19a, National Library of Russia) — the base manuscript. Color photographs by the **West Semitic Research Project** (B. Zuckerman et al.), referenced via IIIF from the [Internet Archive](https://archive.org/details/Leningrad_Codex_Color_Images) and never redistributed. Rights in the photographs are asserted by WSRP; consult the rights holder before reuse. (The Internet Archive item carries an uploader-applied Public Domain Mark, which is not a WSRP dedication.)
- **UXLC / Tanach.us** — the Unicode/XML Leningrad Codex 2.5 (Tanach.us Inc.), source of the tier-1 ground truth (F119A/F119B/F120A) and the tier-2 UXLC backbone. Tanach.us asks that citation of the site as the source of the text be made, and we gladly do so — see [tanach.us](https://tanach.us/).
- **Kraken** (B. Kiessling, DH 2019) and the **BiblIA** medieval-Hebrew model + dataset (D. Stökl Ben Ezra et al., HIP '21) — OCR/HTR baselines BL-02 / BL-03.
- **Nakdimon** (E. Gershuni & Y. Pinter, NAACL Findings 2022) — diacritization for baseline BL-03 and the primary oracle.
- **DICTA Nakdan** (A. Shmidman et al., ACL 2020) and **DictaBERT** (S. Shmidman et al., 2023) — the secondary diacritization oracle and the off-label negative-result baseline BL-04.
- **Unicode Standard Annex #29** (The Unicode Consortium) — grapheme-cluster segmentation underlying the scorer's cluster-aligned alignment.
