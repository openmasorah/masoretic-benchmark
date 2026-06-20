# Cross-side ordinal alignment for the IAA module

This document specifies how tier-4 positional marks are anchored to a
1-based ordinal coordinate, how those coordinates relate across the two
annotator sides under the IAA bipartite matcher, and where the per-annotator
algorithm leaks tier-1 transcription error into tier-4 metrics.

It exists because the algorithm is load-bearing for the paper's §6.1
anchor-ambiguity finding (the F1 exact-vs-±1 gap claim) and because the
audit at `.planning/quick/260619-paper-draft-jcdl-2027/BOOTSTRAP_AUDIT.md`
identified the per-annotator-ordinal design as MF-6 / FINDING 3.

## What gets a tier-4 record

`parse.extract_positional(chunk, verse_ref)` walks a single annotator's raw
verse chunk left to right, maintaining a 1-based consonant counter
(`consonant_offset`) and the ordinal of the most recently seen consonant
(`current_consonant_offset`). On each character it sees:

1. `<DR>` token — emit `Tier4Record("double_rafe", verse_ref, current_consonant_offset)`.
2. Other `<UPPER>` editor tokens (`<MF>`, `<EF>`, `<L>`, `<C>`, `<BL>`, `<WS>`, `<P>`) — consume without effect on the consonant counter.
3. Hebrew consonant (U+05D0..U+05EA) — increment `consonant_offset`, set `current_consonant_offset` to the new value.
4. `U+05AF` circellus — emit `Tier4Record("circellus", verse_ref, current_consonant_offset)`.
5. `U+05BF` rafe — emit `Tier4Record("rafe", verse_ref, current_consonant_offset)`.
6. Everything else — pass through silently.

The ordinal coordinate is therefore **the 1-based offset of the most recent
Hebrew consonant in this annotator's chunk** — derived solely from this
side's consonant stream, with no reference to the other annotator or to any
external backbone (UXLC, Leningrad facsimile pixel positions, etc.).

## What the matcher does with ordinals

`f1._match_one_bucket` matches detections at the `(verse_ref, type)`
granularity. Within a bucket it runs two phases:

1. **Exact (phase 1).** Pairs with `ord_A == ord_B` match first.
2. **Tolerance (phase 2).** Remaining pairs match if `|ord_A − ord_B| ≤ tolerance` (1 for the headline metric, 0 for "F1 exact").

The matcher accepts ordinals at face value; it does not adjust for a tier-1
disagreement that might have shifted B's coordinate frame relative to A's.

## Where this leaks tier-1 error into tier-4

Concretely: if annotator A wrote N consonants and annotator B wrote N+1 for
the same verse — because of a one-letter insertion/deletion, a different
irregular-letter convention (e.g. whether a final-form variant is counted
as a separate letter), or any other tier-1 disagreement — every mark on B
placed *after* the disagreement sits at an ordinal one higher than the
matching mark on A.

The headline F1 ±1 tolerance phase absorbs that offset as "anchor
ambiguity," scoring the pair as a tolerance match rather than an exact one.
But the offset is in part tier-1 alignment noise, not the
schema-representation question the metric is meant to surface. The §6.1
anchor-ambiguity claim in the paper rests on the F1 exact-vs-±1 gap; this
contamination biases the gap *upward* (more pairs are tolerance-only than
the schema question alone would predict).

## Quantification on Devarim v0.2.0 (single annotator pair)

* Tier-1 CER per folio: 0–0.57% (overall 0.29%) on the 96-verse round-0 data.
* Consonants per verse: ~25–60.
* Expected insertions/deletions per verse from tier-1 disagreement: ~0.1–0.3.
* Upper bound on tier-4 ordinal offsets from tier-1 disagreement: bounded
  by the per-verse insertion/deletion count above.

This is small in proportion to the 183 matched circellus pairs in the
unresampled offset distribution, but it is non-zero. The paper qualifies
the anchor-ambiguity claim accordingly.

## The v0.3 fix path — UXLC-backbone reprojection (planned)

Routing both annotators' ordinals through a shared UXLC consonant backbone
would remove the contamination entirely:

1. For each verse, compute the canonical UXLC consonant stream.
2. Compute the alignment from each annotator's consonant stream to UXLC
   via Hebrew-letter Levenshtein with grapheme-cluster awareness.
3. Project each annotator's tier-4 marks to UXLC-frame ordinals.
4. Run the bipartite matcher on UXLC-frame ordinals.

Under this projection a tier-1 disagreement no longer shifts tier-4
ordinals — the disagreement surfaces only in the tier-1 alignment step,
where it belongs.

Implementation cost: ~3–4 hr of sibling-repo work + an extended schema for
the published positional projection JSONs (`tier1_consonants`,
`tier2_nikkud_overlay`, `tier3_trop_overlay` fields, so consumers can
re-project from the public artifact without the raw .txt). Tracked as
Phase A4 / D4 of the JCDL 2027 paper revision plan; see also the
`open-masorah-convention-divergence-finding` and
`open-masorah-paper-purpose` operator memory notes for the upstream
motivation.

## Why per-annotator ordinals stay the default until v0.3

* **Reproducibility round-trip.** The per-annotator algorithm round-trips
  cleanly between raw .txt and the published positional projection JSON
  (no external backbone required). The cross-path byte-equivalence tests
  in `tests/iaa/test_positional_projection_round_trip.py` pin this.
* **License surface.** Per-annotator ordinals do not require shipping any
  third-party text (UXLC); the published projection stays CC-BY-4.0 over
  annotator-authored material only.
* **Bounded harm.** Tier-1 CER on this subset is low (≤0.57% per folio).
  The contamination of the §6.1 statistic is bounded by that error rate
  times an upper bound on per-verse insertions/deletions; the paper
  qualifies the claim with this caveat rather than blocking publication on
  the reprojection work.

The reprojection lands when the public projection schema is extended to
cover tiers 1–3 — at that point the UXLC backbone is already a load-bearing
piece of the artifact, so the cost-benefit on the tier-4 ordinal change
flips.

## See also

* `masoretic_eval/iaa/parse.py` — the per-annotator ordinal implementation
  (module docstring carries the runtime-visible version of this caveat).
* `masoretic_eval/iaa/f1.py` — the bipartite matcher whose ±1 tolerance
  phase absorbs the offsets.
* `tests/iaa/test_bootstrap_multiplicity.py` — FINDING 1 regression test.
* `tests/iaa/test_positional_projection_round_trip.py` — pins the
  per-annotator round-trip equivalence.
