# results_provisional/ — PROVISIONAL, single-annotator cold-score (quick 260612-prz)

**NOT the frozen public artifact set.** Deliberately separate from `results/` so the
manifest-bound, gt_hash-fused production tree is never touched.

- **SINGLE-ANNOTATOR (David Moster, annotator B) / PRE-ADJUDICATION / PROVISIONAL.**
- `gt_hash` stays **null**. Nothing fused, published, tagged, or pushed public.
- **IAA NOT computed** — needs annotator A (Yosef). This is baseline cold-scoring only.
- Public `phase_0_manifest.json` was **never mutated** (predictions generated via direct
  `infer_folio`, bypassing the promote/manifest-bump path).

Contents:
- `biblia_kraken/`, `biblia_char_menaked/` — provisional predictions for F118B/F119A/F119B/F120A.
- `scores/` — per-folio tier-1 CER vs the Moster B-side interim goldens (both line-orderings).

Blocked (no prediction): `biblia_nakdimon` (pkg not installed), `llm_vision` (API keys unset).

Headline metric = **line_id-order** tier-1 CER (matches the published F118B leaderboard
method, for comparability). Reading-order recorded as a flagged diagnostic; the ordering
sensitivity is a methodology question for Ben/Yosef review, not canonicalized here.
See `.planning/quick/260612-prz-*/260612-prz-NUMBERS.md` in the planning repo for the full table.
