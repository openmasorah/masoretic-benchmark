# masoretic-benchmark

![CI](https://github.com/thebenlamm/masoretic-benchmark/actions/workflows/ci.yml/badge.svg)

4-tier CER scorer + public benchmark dataset for medieval Hebrew manuscripts.

## Components

- **`masoretic_eval/`** — Scorer Python package (this plan). Apache 2.0.
- **`data/`** — Frozen benchmark data (CC-BY-4.0 text; IIIF image refs only). Populated by follow-up GT-infra plan.
- **`baselines/`** — Four independent baseline scripts. Populated by follow-up baseline plan.
- **`leaderboard/`** — Static `leaderboard.json` + PR-based submission (optional-polish Gradio deferred). Populated by follow-up release plan.

## Install

    pip install -e ".[dev]"

### Python version

This project pins to Python 3.11 (`.python-version`). Local dev on Python >= 3.12 will fail to import `nakdimon` because its transitive `tensorflow==2.15.0` dependency has no wheel for 3.12 on macOS arm64. CI runs 3.11. Use pyenv or your equivalent to honor the `.python-version` file.

## Usage

    masoretic-eval score \
      --gt path/to/gt.json \
      --pred path/to/prediction.json \
      --folio-id leningrad_devarim_f237b \
      --out result.json

Input JSON shape (both `gt` and `pred`):

```json
{
  "text": "<Hebrew text — UXLC LC-order for GT; any order for prediction>",
  "metamarks": [{"type": "large_letter", "verse_ref": "Deut.6.4", "ordinal": 1}]
}
```

## Methodology

### Normalization
- All inputs NFD-normalized at scoring time. GT ships raw UXLC LC-order byte-for-byte.
- CGJ (U+034F) stripped during scoring.

### Alignment and edit counting
- **Alignment unit:** UAX #29 grapheme clusters.
- **Edit unit:** codepoints within aligned cluster pairs.
- Unaligned (inserted / deleted) clusters contribute edits equal to their codepoint count.
- Cross-validated against PyICU in CI and against a hand-rolled naive Levenshtein on shared fixtures (anti-self-grading).

### Tiered denominator policy
- **Tier 1:** consonant codepoints only (te'amim + nikkud stripped).
- **Tier 2:** consonant + nikkud codepoints (te'amim stripped).
- **Tier 3:** full codepoint count.
- **Tier 4:** F1 over `(type, verse_ref, ordinal)` records, not CER. Partial credit (⅓) for `(type, verse_ref)` match with wrong ordinal.

### Composite headline score
`CER₃ = 0.5·cer_consonantal + 0.3·cer_nikkud + 0.2·cer_full`. Tier 4 reported separately.

### Qere/ketiv
Scored against qere by default (UXLC `<q>` element when present). Ketiv-only words use `<k>`.

### Oracle fields (v0.1 scorer)
`nakdimon_disagreement_rate` and `dicta_disagreement_rate` are **pass-through inputs**: callers compute them externally and supply them via CLI flags or `Scorer.score()` kwargs. The scorer emits them unchanged in the output JSON. Oracle integration (Nakdimon OSS pip install, DICTA API client, dictabert) is covered by a follow-up plan.

## Known limitations (v0.1 scorer)

- Oracle disagreement rates are pass-through only; no built-in computation.
- UXLC loader is tested on Deuteronomy fixtures; coverage for other books pending follow-up plan expansion.
- Tier 4 type taxonomy is the week-1 schema-decision inventory; additions require a scorer version bump.

## Submission instructions

Deferred to the release follow-up plan. Current v0.1 scorer is a standalone library + CLI.

## IAA results

Populated by the GT-infra follow-up plan at v0.1 ship.

## License table

| Artifact | License |
|---|---|
| Scorer code (`masoretic_eval/`) | Apache 2.0 |
| Benchmark text GT | CC-BY-4.0 (released by follow-up plan) |
| Manuscript images | Fetched via IIIF from archive.org (PDM 1.0); never redistributed |

## Citation

BibTeX entry will be added at paper submission. For now:

```bibtex
@misc{lamm2026masoretic,
  title  = {masoretic-eval: 4-tier CER scorer for medieval Hebrew},
  author = {Lamm, Ben and Ginsberg, Yosef},
  year   = {2026},
  note   = {v0.1.0, https://github.com/thebenlamm/masoretic-benchmark}
}
```
