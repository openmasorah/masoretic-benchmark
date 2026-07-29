# Devarim 4-folio positional projections (CC-BY-4.0)

This directory holds the **CC-BY-4.0 reproducibility surface** for the paper-
grade IAA over the Devarim 4-folio benchmark (SPEC 260619-n3u). The raw
round-0 .txt transcriptions are gitignored upstream (Yosef's private layout-
preserving format); these positional projections strip the layout and expose
the per-verse data a third party needs to reproduce the published α / F1 / CER
cells.

## Files

| File                               | Side                     | Source                                                 |
| ---------------------------------- | ------------------------ | ------------------------------------------------------ |
| `ginsberg_round0_positional.json`  | A (Ginsberg / operator)  | `MASORETIC_IAA_DATA_DIR/a_side.txt` projection         |
| `moster_round0_positional.json`    | B (Moster)               | `MASORETIC_IAA_DATA_DIR/b_side.txt` projection         |
| `consensus_gold_positional.json`   | Consensus gold           | `MASORETIC_IAA_DATA_DIR/gold_side.txt` projection      |

The two round-0 files are produced by the regeneration script below from the
gitignored round-0 .txt files. The script is deterministic — same input bytes →
byte-identical projection JSON.

`consensus_gold_positional.json` is the **consensus gold standard**: Annotator
A's round-1 revised transcription (Yosef/Ginsberg FINAL 2026-06-19), which is
byte-identical to Annotator B's (Moster) round-2 endorsement — a single-source
reference, not a third independent annotation.

**Reproducibility boundary** — exactly what each number needs, no more:

* `headline.tier{1,2,3}.cer_vs_gold.{a,b}` (human-vs-gold CER) reproduces from
  **these three committed CC-BY projection JSONs alone**: each annotator's
  round-0 `chunk` is scored against the gold `chunk` (gold as the CER
  reference, denominator = gold length) via the cluster-aligned CER. No UXLC
  distribution and no private raw `.txt` are required.
* `headline.tier2.cer_vs_uxlc.{a,b}` and the UXLC-anchored tier-4 metrics
  **additionally** require the UXLC 2.5 distribution (publicly available from
  tanach.us). Still no raw `.txt`.
* Only re-*deriving* the projection JSONs from source requires the private
  round-0 `.txt` (gitignored). The published numbers above do not.

`cer_vs_uxlc` shares a *scoring surface* with the Nakdimon-vs-UXLC tier-2
baseline (same UXLC reference, same tier-2 strip, same `cluster_aligned_cer`
path), which is why they can sit in one table. They are **not directly
comparable as systems**, though: Nakdimon diacritizes given UXLC's exact
consonants, whereas the human CER also absorbs consonant-transcription
divergence from UXLC. The shared surface is the comparison; the systems'
input tasks differ.

## Schema (per-side projection)

```json
{
  "format_version": 1,
  "side_label": "ginsberg",
  "license": "CC-BY-4.0",
  "source": "Round-0 raw transcription, layout-free projection",
  "verses": [
    {
      "verse_ref": "Deut.32.1",
      "folio": "F118B",
      "chunk": "<post-split Hebrew text — circellus, rafe, <DR>, spaces>",
      "consonant_count": 47,
      "tier4_positional": [
        {"type": "circellus", "ordinal": 5},
        {"type": "rafe", "ordinal": 12}
      ]
    }
  ]
}
```

`chunk` is the source of truth. `consonant_count` and `tier4_positional` are
derived convenience fields that `masoretic_eval.iaa.load_projection`
re-validates on load: if either drifts from what the chunk produces under
`extract_positional` / `count_consonants`, the loader raises
`PositionalProjectionInvalid`. This invariant prevents hand-edits from
silently shifting any downstream number.

## Licensing

* **Code that produces / consumes these files**: Apache-2.0 (the
  `masoretic-eval` scorer).
* **These JSON files**: CC-BY-4.0 as a compiled projection. The consonantal text
  within is public domain and the annotation data is CC0-1.0 — see
  [`../../LICENSE.md`](../../LICENSE.md) for the complete rights statement.
* **The private round-0 .txt sources**: NOT in this repo. Layout-preserving
  per Yosef's private format. Even the operator does not commit them upstream.

The projection's content (Hebrew chunks + positional tuples) is fully
publishable under CC-BY-4.0 because the layout-bearing portion of Yosef's
private format is stripped by `split_chunks` before projection.

## Regenerating

When the round-0 .txt files are available (set `MASORETIC_IAA_DATA_DIR` to
the directory holding `a_side.txt`, `b_side.txt`, `verse_folio_map.json`):

```bash
python scripts/regenerate_devarim_positional.py
```

The script:

1. Reads the raw round-0 .txt files and the verse_folio_map JSON.
2. Projects each side via `masoretic_eval.iaa.project_side`.
3. Writes `ginsberg_round0_positional.json` and `moster_round0_positional.json`
   here.
4. Re-loads them through `load_projection` to verify the invariants hold.

A determinism + cross-path round-trip test lives at
`tests/iaa/test_positional_projection_round_trip.py` — gated on
`MASORETIC_IAA_DATA_DIR` for the Devarim cells.

## Reproducing the published IAA numbers

```bash
# From projections (CC-BY-4.0 reproducibility surface)
python -m masoretic_eval.iaa \
  --a-positional iaa_data/devarim_4folio/ginsberg_round0_positional.json \
  --b-positional iaa_data/devarim_4folio/moster_round0_positional.json \
  --output paper_iaa_results.json

# From raw .txt (Yosef-private — operator only)
python -m masoretic_eval.iaa \
  --a-side  $MASORETIC_IAA_DATA_DIR/a_side.txt \
  --b-side  $MASORETIC_IAA_DATA_DIR/b_side.txt \
  --verse-folio-map $MASORETIC_IAA_DATA_DIR/verse_folio_map.json \
  --output paper_iaa_results.json
```

Both invocations produce a byte-identical `paper_iaa_results.json` (modulo
the `metadata.a_sha256` / `metadata.b_sha256` pins, which identify the
input file and so differ by construction).

## Tier-4 scoring specification (self-contained)

Until v0.1.1 the authoritative statement of these rules lived only in the
project's unpublished paper draft, cited as "DRAFT_v4 §5.1 / App. A.3–A.4".
That made the published figures unverifiable from the tag alone: a citer could
obtain the numbers but not the definitions behind them. The rules are therefore
restated here, in the repository, as the shipped specification.

### Canonicalisation

Tier-4 records carry three raw types: `circellus`, `rafe` and `double_rafe`
(the last from the annotator tool's `<DR>` editor token). Before agreement is
computed, **`{rafe, double_rafe} → rafe`**. The two are the same scribal
phenomenon at different stroke counts, and the annotators did not apply the
distinction consistently — A marked 25 doubles, B marked 56 — so scoring them
as distinct types would measure notation habit rather than reading.

The raw types survive in the committed projections and in the scorer's input
vocabulary, so this fold is reversible by anyone who wants the finer view. It
happens in `masoretic_eval/iaa/alpha.py`, downstream of extraction.

### Matching

A predicted record matches a reference record when `(type, verse_ref, ordinal)`
agree exactly, where `ordinal` is the 1-based Hebrew-consonant offset of the
anchoring consonant within its verse. The headline F1 is **exact**; a ±1
consonant tolerance variant is reported separately and is always the larger
number. Matching is exact-first-greedy, verified equivalent to maximum-cardinality
matching on every bucket in this corpus.

### Dropped records

**4 annotator records are excluded** from the UXLC-frame figures — 1 from
annotator A, 3 from annotator B — because their anchoring consonant could not
be aligned to the UXLC backbone (the annotator's consonant stream diverged from
UXLC at that point, so the ordinal has no referent in the shared frame). They
are dropped symmetrically, not counted as errors against either annotator, and
they remain present in the committed projections.

(The exclusion applies to the two annotators' round-0 records, which is the
population the tier-4 agreement figures are computed over. It is unrelated to
the 516 tier-4 records in the adjudicated consensus gold, a different file.)

### Frames

Two frames are reported, and they are not interchangeable:

- **UXLC-frame** (the published headline, F1 0.9187): ordinals resolved against
  the UXLC 2.5 consonant backbone. Requires the pinned UXLC cache to regenerate
  — see `baselines/UXLC_PIN.md`.
- **Committed-data-only frame** (F1 exact 0.8988): ordinals resolved against
  each annotator's own consonant stream. Regenerates from the files in this
  directory alone. It is the lower number because per-annotator ordinal drift is
  not reconciled against a shared backbone.

Krippendorff α in the committed-data-only frame, with the **universe stated**,
because the two universes differ by more than 0.2 and an unlabelled "α" is
ambiguous between them:

| α | canon (`{rafe,double_rafe}→rafe`) | raw |
|---|---|---|
| positive universe *(marked positions only)* | **0.6957** | 0.6583 |
| full universe *(every consonant position)* | 0.8974 | 0.8726 |

The published headline α 0.7470 is the **positive-universe canon** figure in the
**UXLC frame**; its committed-data-only counterpart is the 0.6957 above. Compare
like with like — the full-universe values are higher because the overwhelming
majority of consonant positions carry no mark and both annotators agree on that
trivially.

Tiers 1–3 need no such distinction: every CER figure in `iaa_report.json`
recomputes from the three projections in this directory with no external input.
