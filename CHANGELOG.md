# Changelog

All notable changes to this project are documented here. Versioning is
independent for the two artifacts this repository holds: the **scorer** Python
package (`masoretic_eval`, currently `0.2.0`) and the **benchmark dataset**
(tagged `benchmark-v*`).

## benchmark-v0.1.0 — Open Masorah Devarim pilot benchmark

First public release of the benchmark: a four-tier inter-annotator-agreement
dataset for medieval Tiberian Hebrew, on four folio sides of the Leningrad Codex
Devarim (F118B, F119A, F119B, F120A; Deut 31:28–34:12, 96 verses), together with
the four-tier scorer.

### Included

- **Adjudicated consensus reference** (four-tier positional projection), CC-BY-4.0.
- **Both annotators' round-0 four-tier projections** (Ginsberg, Moster) —
  consonants, nikkud, trop, and tier-4 meta-marks (circellus + rafe), CC-BY-4.0.
- **The four-tier scorer** (`masoretic_eval`), Apache 2.0 — cluster-aligned
  code-point CER for tiers 1–3, detection F1 for tier 4, with deterministic
  verse-bootstrap confidence intervals.
- **`iaa_report.json`** — the published reference numbers.
- **`phase_0_manifest.json`** — the frozen scope, append-only and hash-pinned.
- The masoretic-editor annotator convention sheet and the reproducibility surface.

### Reference numbers

- Tier-4 pair-level agreement (meta-marks): **F1 exact 0.9187** [0.8969, 0.9397];
  F1 ±1-consonant tolerance 0.9472 [0.9299, 0.9631]; Krippendorff α (positive,
  canonicalised) 0.7470 [0.6891, 0.8051].
- Annotator B round-0 vs the adjudicated consensus, tiers 1/2/3:
  **CER 0.0029 / 0.0172 / 0.0234**. The consensus is not independent of either
  annotator (it is A's round-1 revision, byte-identical to B's round-2
  endorsement); this is a descriptive round-0-to-consensus comparison, not an
  independent human-vs-reference baseline.

All benchmark metrics reproduce from the released public surface; the tier-1/2/3
figures reproduce from the three committed projection files alone.

### Deferred to v0.1.1

- Automated OCR/HTR baselines (Kraken, Kraken→Nakdimon, Kraken→DictaBERT) and any
  leaderboard. No baseline scores ship in v0.1 — see the README "Baselines"
  section for why the earlier draft scores were withdrawn.

### Licensing

| Artifact | License |
|---|---|
| Scorer (`masoretic_eval/`) | Apache 2.0 |
| Annotator projections + adjudicated consensus | CC-BY-4.0 |
| Tier-1 GT — F118B (hand-transcribed) | CC-BY-4.0 (Open Masorah) |
| Tier-1 GT — F119A/F119B/F120A (UXLC-derived) | UXLC 2.5 (Tanach.us) — free to copy, citation appreciated; not CC0 |
| Manuscript images | IIIF reference to archive.org PDM 1.0; never redistributed |

---

## masoretic_eval 0.2.0 — scorer

The four-tier scorer package, released independently and tagged `v0.2.0`. See the
package version in `pyproject.toml` and the reproducibility notes in
`docs/TESTING.md`.
