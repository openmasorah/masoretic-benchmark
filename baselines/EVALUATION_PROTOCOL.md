# Evaluation Protocol

Append-only. The frozen, pre-registered evaluation methodology for the Masoretic
Pipeline benchmark. Every change writes a new row with date + reason. Newest first.

## Headline metric (v0.1)

| Date | Headline metric | Tiers | Aggregation | Convention |
|---|---|---|---|---|
| 2026-04-30 | **Macro-averaged whole-folio CER (tiers 1–3) / F1 (tier 4)** | 1, 2, 3, 4 | Per frozen folio, then macro-averaged across folios | ICDAR-HTR (Sánchez et al., READ project, HIMANIS) |

This row implements REQUIREMENTS.md **BL-07** verbatim:

> **BL-07**: Macro-averaged CER (tiers 1–3) / F1 (tier 4) is reported per frozen
> folio for every baseline; totals match `expected_total_reports` in the manifest.

**Per folio, not per line.** Predictions and ground truth are concatenated in
reading order (top-to-bottom, right-to-left within a row for Hebrew) and CER is
computed over the concatenated strings. This is segmentation-invariant — the
reported number does not depend on whether the OCR system produces line-level
or word-level segmentation.

Tier-1 GT for each folio is hand-transcribed by the operator (Ben) from the
public-domain photograph (archive.org PDM 1.0). Hand transcription is committed
to `baselines/tests/fixtures/iaa_folio_<fixture_id>.gt_adapter_golden.json`
and frozen in `phase_0_manifest.json`. Yosef (the scholar) provides a
~5 min tier-1 spot-check; deeper review (tiers 2, 3, 4) lands in subsequent
phases.

## Scoring procedure

1. Load GT lines from `baselines/tests/fixtures/iaa_folio_<fixture_id>.gt_adapter_golden.json`
   `lines[]` (one string per physical main-text line, hand-transcribed).
2. Load prediction lines from `results/<baseline_id>/<fixture_id>.json` `lines[]`
   (each entry has `bbox`, `tier1`, optional higher tiers).
3. Sort prediction lines in reading order: `(bbox.y_min asc, bbox.x_max desc)`
   for Hebrew (top-to-bottom, right-to-left). Fall back to `line_id` order
   when bboxes are absent (degraded baseline).
4. Concatenate GT lines with single-space separator → `gt_full`.
5. Concatenate prediction `tier1` strings with single-space separator → `pred_full`.
6. Apply `masoretic_eval.tiers.tier1_consonantal.Tier1Consonantal` normalization
   to both strings (consonants-only keep set, maqaf-strip, etc.).
7. Compute `CER = Levenshtein(gt_norm, pred_norm) / max(len(gt_norm), 1)`.
8. Repeat for tiers 2, 3 (when GT has those tiers populated).
9. Tier 4: F1 over mesora marks (when GT has tier-4 records).
10. Macro-average across tiers 1–3 (per-folio CER) and across folios (when more
    than one folio has been scored).
11. Write per-baseline scores to `results/scores/<fixture_id>.json`.

## Pre-registration commitment

The methodology above is **pre-registered before any folio is scored**. Score
computations on F119A, F119B, F120A apply this exact procedure cold — no
per-folio tuning, no metric variants chosen post-hoc to flatter results. If a
folio reveals a methodology gap (e.g., GT contains tier 2 nikkud but prediction
emits tier 1 only), the gap is REPORTED as a known limitation; a new row in
this file is appended with a date and reason before any methodology change is
applied to subsequent folios.

## Deferred to v0.2 (supplementary diagnostics)

The following are **not headline metrics** for v0.1. They will be reported as
supplementary diagnostics in v0.2 once second-annotator inter-annotator
agreement (IAA) is established and Yosef has bandwidth for tier 2/3/4 review.

- **Per-line CER** — requires line-level alignment between predictions and GT.
  Default Kraken segmentation produces word-level fragments; line reconstruction
  via y-clustering merge is documented in plan 03.1-04.7 (deferred). Per-line
  CER without IAA is more attackable than whole-folio CER, not less, because
  line segmentation becomes a free parameter the benchmark author tuned.
- **Zone-restricted CER** — geometric main-text-block filtering. Spike showed
  a 0.70 pp delta vs whole-folio CER on F118B (intra-zone fragmentation, not
  inter-zone marginalia capture); insufficient methodological gain to justify
  v0.1 inclusion.
- **Segmentation-merge variants** — y-clustering merge with τ ∈ {0.7×, 1.0×, 1.5×}
  median(bbox_height) as a sensitivity analysis. Plan 03.1-04.7 carries the
  prepared spec; deferred until per-line CER is itself promoted to headline.
- **Tier 4 (mesora marks) F1** — REQUIREMENTS.md BL-07 declares F1 for tier 4
  as the headline metric; deferred until GT files include `tier4_records` for
  any folio. Operator's hand transcription is tier-1-only; tier 4 awaits Yosef's
  deeper review via the eScriptorium pipeline (Phase 1 GT-INFRA).

The spike at `/Users/benlamm/Workspace/baalshem/spikes/03.1-05-cer-methodology/`
already computed sensitivity analysis across whole-folio, zone-restricted, and
bucketed-per-line CER under three threshold settings. Per Hamming's
recommendation, that data is the "Reviewer-2 sensitivity number" referenced in
the paper's methodology section; full diagnostic table is supplementary
material in v0.2.

## Reviewer-2 mitigations

The benchmark's load-bearing claim is **reproducibility**, not metric
sophistication. Defenses:

- **Pre-registration.** This file is committed before any folio is scored.
  Reviewers attack ad-hoc methodology, not pre-registered convention.
- **ICDAR-HTR convention.** Whole-folio CER is the standard for historical-
  document HTR evaluation (Sánchez/READ/HIMANIS). Cite directly in paper.
- **Spec compliance.** REQUIREMENTS.md BL-07 declares "per folio" not
  "per line." We implement the spec, not invent methodology.
- **Sensitivity reporting.** When per-line CER is added in v0.2, the
  pre-registered τ-derivation rule + sensitivity sweep at τ × {0.7, 1.0, 1.5}
  closes the "tunable-parameter" attack surface.
- **Scope honesty.** v0.1 ships 4 IAA folios × 4 baselines = 16 (folio,
  baseline) cells. IAA n is small; CIs will be wide; this is documented as a
  known limitation in PAP-09. v0.2 expands.

## Known limitations (v0.1)

- **Tier-1 GT only on the IAA set.** Tier 2/3/4 reviews deferred to subsequent
  phases. v0.1 reports tier-1 CER as the only headline metric.
- **BL-02 zero-bbox regression on commit `b319b81`.** The committed BL-02
  predictions for F118B carry `bbox: [0,0,0,0]` for every line because that
  commit pre-dates `_kraken.py`'s boundary-polygon-derivation fix at `477ea68`.
  This does NOT affect whole-folio CER (text concatenation does not consume
  bboxes; reading-order falls back to `line_id` order when all bboxes are
  zero). The bbox regression is fixable via re-promotion under a non-D-15-tripping
  manifest state and lands in v0.2 alongside per-line CER (which does require
  bboxes).
- **Single annotator (Ben) on tier-1 GT for F118B.** No second-annotator IAA
  yet. F8 gate (per GT-12) gates the multi-annotator pipeline. v0.2 adds the
  second annotator and bidirectional CER per GT-11.

## Notes

- This file is **append-only**. New rows go at the top of the methodology
  table; never edit historical rows.
- A row in this file implies a `manifest_changelog` entry in
  `phase_0_manifest.json` — evaluation methodology is part of the frozen
  reproducibility contract.
- Future v0.2 calibration studies (per-line CER methodology, segmentation IAA,
  zone-restricted variants) add new rows; v0.1 results are computed against
  the 2026-04-30 row only.
