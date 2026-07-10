# Evaluation Protocol

Append-only. The frozen, pre-registered evaluation methodology for the Masoretic
Pipeline benchmark. Every change writes a new row with date + reason. Newest first.

## Headline metric (v0.1)

| Date | Headline metric | Tiers | Aggregation | Convention |
|---|---|---|---|---|
| 2026-07-10 | *(no headline baseline score published in v0.1)* | — | — | **F118B whole-folio baseline scores RETRACTED; `results/` withdrawn to v0.1.1.** The published numbers scored Kraken's 109 segmented lines — which include the masorah magna/parva apparatus — against 26 physical main-text GT lines, with all bboxes `[0,0,0,0]` so reading order fell back to `line_id`. The ranking they produce is **inverted** (`biblia_kraken` reported weakest; ROI-restricted main-text scoring puts it strongest on consonants). Independently, the `biblia_char_menaked` tier-2/3 predictions were corrupt (unpinned `transformers` → cumulative prefix repetition; tier-2 3.3× tier-1, nikkud on 7/109 lines) and are not model output. Paired with `phase_0_manifest.json` `manifest_changelog` row `2026-07-10T16:05:00Z`. The whole-folio method itself is **not** withdrawn — it is unsuited to a folio whose hypothesis contains apparatus the GT omits. v0.1.1 re-emits under pinned `transformers` + ROI/main-text scoring. |
| 2026-06-15 | Macro-averaged whole-folio CER (tiers 1–3) / F1 (tier 4) *(metric unchanged)* | 1, 2, 3, 4 | *(unchanged)* | **Meteg / ga'ya U+05BD stripped from tier-2, scored at tier-3** — metrical/cantillation-adjacent mark, not phonemic nikkud; exact rafe (U+05BF) precedent, so it removes a tier-2/tier-3 double-count, not signal. Implemented by adding `0x05BD` to `_TIER2_EXTRA_STRIP` in BOTH `masoretic_eval/strip.py` (scorer source of truth) and `masoretic_eval/uxlc_loader.py` (loader copy). **Pure pre-registration — NO tier-2/3 numbers are published/frozen yet (tier-1-only to date), so NO `manifest_changelog`/fuse and gt_hash untouched.** Source: the planning repo's `.planning/DECISIONS.md` 2026-06-15 + `.planning/audits/2026-06-12-METEG-PROBE.md` (meteg ≈ 6–17% of tier-2 errors across the 4 IAA folios, ~1–1.5 pp absolute, ≈10× smaller than maqaf; all 4 baselines emit 0 meteg). Golden fixture tier-2 denominator re-emitted (134→132). |
| 2026-06-11 | Macro-averaged whole-folio CER (tiers 1–3) / F1 (tier 4) *(metric unchanged)* | 1, 2, 3, 4 | *(unchanged)* | **Maqaf U+05BE retained, no trailing space** (makes the always-implemented scorer convention explicit; supersedes the doc's prior "maqaf-strip" misdescription). All GT regenerated to this convention; F118B published tier-1 CERs re-emitted. See "Maqaf convention" §. Paired with `phase_0_manifest.json` `manifest_changelog` row `2026-06-11T19:30:00Z` (hash `c9a578520ce2f4e5`→`062a2a6c8646e831`). |
| 2026-04-30 | **Macro-averaged whole-folio CER (tiers 1–3) / F1 (tier 4)** | 1, 2, 3, 4 | Per frozen folio, then macro-averaged across folios | ICDAR-HTR (Sánchez et al., READ project, HIMANIS) |

This row implements the pre-registered **BL-07** rule verbatim:

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
   to both strings (consonants-only keep set; **maqaf U+05BE is retained as a
   distinct scoring character with no trailing space**; runs of spaces are
   collapsed). This matches the shipped scorer and the canonical tier-1 maqaf
   convention (see "Maqaf convention" note below). *(Corrected 2026-06-11: this
   step previously read "maqaf-strip," which never matched the implementation —
   `Tier1Consonantal._strip_to_consonants` has always kept U+05BE.)*
7. Compute `CER = Levenshtein(gt_norm, pred_norm) / max(len(gt_norm), 1)`.
8. Repeat for tiers 2, 3 (when GT has those tiers populated).
9. Tier 4: F1 over mesora marks (when GT has tier-4 records).
10. Macro-average across tiers 1–3 (per-folio CER) and across folios (when more
    than one folio has been scored).
11. Write per-baseline scores to `results/scores/<fixture_id>.json`.

## Maqaf convention (clarified 2026-06-11)

Canonical tier-1 representation of maqaf (U+05BE, ־): **retained as a distinct
scoring character with no trailing space** (e.g. `אֶת־הַשָּׁמַיִם`). GT and all
baseline predictions use this one convention so tier-1 CER measures recognition,
not transcription style. This is, and always was, what the scorer keep-set
(`tier1_consonantal.py`), the UXLC loader, and the pinned test
`tests/test_uxlc_loader.py:98` implement; the rejected alternative (fold
maqaf→space) breaks that test and corrupts the UXLC lexical path. Rationale and
full decision: `DECISIONS.md` 2026-06-11.

> **Step 2b regeneration (2026-06-11).** Three incompatible maqaf conventions
> had drifted into the GT artifacts (scorer = retain; F118B hand golden =
> maqaf-as-space; the four PAGE-XML exports + the F119A/F119B/F120A goldens =
> maqaf+spurious-space, built by the pre-fix loader). All GT was regenerated to
> the retain-no-space convention: the four exports and the three UXLC-derived
> goldens were rebuilt with the fixed loader, and the F118B hand golden had its
> 25 within-line codex maqaf-joins injected by alignment to UXLC (4 joins that
> straddle a physical-line break are kept as line breaks to preserve
> physical-line fidelity). `results/scores/leningrad_devarim_F118B_fixture.json`
> was re-emitted from the corrected GT (real re-run, not hand-edit). Because this
> moves published tier-1 numbers, it was landed as a formal fuse event: the
> 2026-06-11 methodology-table row above + the paired `phase_0_manifest.json`
> `manifest_changelog` row (`2026-06-11T19:30:00Z`, hash
> `c9a578520ce2f4e5`→`062a2a6c8646e831`), with the 11 hash-bound F118B result
> artifacts rebound to the new manifest hash.

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
- **Tier 4 (mesora marks) F1** — Rule BL-07 declares F1 for tier 4
  as the headline metric; deferred until GT files include `tier4_records` for
  any folio. Operator's hand transcription is tier-1-only; tier 4 awaits Yosef's
  deeper review via the eScriptorium pipeline (Phase 1 GT-INFRA).

The phase 03.1-05 whole-folio CER methodology spike
(`method1_whole_folio`) already computed sensitivity analysis across
whole-folio, zone-restricted, and bucketed-per-line CER under three threshold
settings. That sensitivity table is referenced in the paper's methodology
section; the full diagnostic table is supplementary material in v0.2.

## Methodology defenses

The benchmark's load-bearing claim is **reproducibility**, not metric
sophistication. Defenses against ad-hoc-methodology critiques:

- **Pre-registration.** This file is committed before any folio is scored.
  Methodology attacks land on ad-hoc choices, not pre-registered convention.
- **ICDAR-HTR convention.** Whole-folio CER is the standard for historical-
  document HTR evaluation (Sánchez/READ/HIMANIS). Cite directly in paper.
- **Spec compliance.** Rule BL-07 (above) declares "per folio" not
  "per line." We implement the pre-registered convention, not invent
  methodology.
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
