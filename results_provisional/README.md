# results_provisional/ — PROVISIONAL cold-score, NOT the public artifact set

**NOT the frozen public artifact set.** Deliberately separate from `results/` so the
manifest-bound, gt_hash-fused production tree is never touched.

> **Updated 2026-07-09.** This file previously stated that `biblia_nakdimon` and `llm_vision` were
> blocked with no predictions, and that IAA was uncomputed pending annotator A. Both statements are
> obsolete: the prz run completed all four baselines, and IAA was adjudicated on 2026-06-19.

## Provenance

Two runs are layered in this tree:

- **2026-06-12/15 (quick 260612-prz)** — single-annotator (David Moster, annotator B),
  pre-adjudication. **Generated the predictions for all four baselines** across
  F118B/F119A/F119B/F120A.
- **2026-06-23 (quick 260623-h8r)** — re-scored **three of the four** (`biblia_kraken`,
  `llm_vision`, `biblia_char_menaked`) plus a GT-fed diagnostic against the **post-adjudication
  verified consensus**, on the main-text ROI. **`biblia_nakdimon` was explicitly out of scope** —
  it is the tier-2 diacritization reference, not an image-based system. **No new API spend**
  (`llm_vision` replayed from cache), but the run *did* regenerate DictaBERT predictions locally
  under a pinned `transformers==4.46.3`, because the **committed `biblia_char_menaked` predictions
  are corrupt** — an unpinned `transformers` 5.6.2 introduced offset-repetition on multi-word
  lines. The h8r `char_menaked` and `gt_fed` figures rest on those regenerated predictions, which
  live in the private planning repo, not here.

> ⚠ **`biblia_char_menaked/*.json` in this tree are the CORRUPT predictions.** They must be
> re-emitted, removed, or loudly caveated before this repo is made public.

The `verified_consensus/` goldens supersede the earlier Moster B-side interim goldens. They are a
**projection** of `iaa_data/devarim_4folio/consensus_gold_positional.json` into the cold-score
driver's `lines[]` form — that file, not this projection, is the source consensus artifact.

## Status invariants (all still hold)

- `gt_hash` stays **null**. Nothing fused, promoted, published, or tagged.
- Public `phase_0_manifest.json` was **never mutated** (predictions generated via direct
  `infer_folio`, bypassing the promote/manifest-bump path).
- Most of this tree is committed to `main`. Only `verified_consensus/` and this README's rewrite
  currently sit on the branch `provisional/phase1-cold-score`. Nothing here has been **promoted**
  to `results/`.

## Contents

- `biblia_kraken/`, `biblia_nakdimon/`, `biblia_char_menaked/`, `llm_vision/` — provisional
  predictions for F118B/F119A/F119B/F120A. **All four baselines × all four folios.**
- `verified_consensus/` — **MOVED 2026-07-10** to `iaa_data/devarim_4folio/goldens/`.
  Canonical ground truth must not live in a tree whose README opens "NOT the frozen
  public artifact set." The goldens are a projection of
  `iaa_data/devarim_4folio/consensus_gold_positional.json`; `phase_0_manifest.json`
  hashes them into each folio's `gt_hash`, and they carry no `gt_hash` of their own.
- `scores/` — per-folio tier-1 CER (both line-orderings), prz-era, vs the Moster B-side goldens.
  The h8r ROI tier-2/3 figures exist only in that run's markdown record; there are no committed
  machine-readable score JSONs for them.

## IAA

**Adjudicated to consensus 2026-06-19** (Ginsberg = annotator A, Moster = annotator B).
The earlier "IAA NOT computed — needs annotator A" note is obsolete. Nothing is owed by an annotator.

## The unresolved methodology question

Headline metric = **line_id-order** tier-1 CER (matches the published F118B leaderboard method,
for comparability). Reading-order is recorded as a flagged diagnostic.

**Whole-folio CER is line-order-sensitive**, and the ordering sensitivity remains **a methodology
question for Ben/Yosef review — deliberately not canonicalized here.** This is the reason these
results are quarantined rather than promoted: promoting a leaderboard forces the convention call.

See `.planning/quick/260612-prz-*/260612-prz-NUMBERS.md` and `.planning/quick/260623-h8r-*/`
in the private planning repo for the full tables.
