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
reference, not a third independent annotation. It exists so the human-vs-gold
CER decomposition (`headline.tier{1,2,3}.cer_vs_gold.{a,b}` in
`paper_iaa_results.json`) reproduces from this public surface alone: each
annotator's round-0 chunk scored against the gold chunk, with **gold as the CER
reference** (denominator = gold length) — the same orientation as the
Nakdimon-vs-UXLC tier-2 baseline, so the two are directly comparable.

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
* **These JSON files**: CC-BY-4.0 (the projection content — UXLC-derived
  Hebrew text + the operator's positional annotations).
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
