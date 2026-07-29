# Changelog

All notable changes to this project are documented here. Versioning is
independent for the two artifacts this repository holds: the **scorer** Python
package (`masoretic_eval`, currently `0.2.0`) and the **benchmark dataset**
(tagged `benchmark-v*`).

## benchmark-v0.1.1 (unreleased) — corrections to v0.1.0

### ⚠️ Corrected: tier-2 and tier-3 CER were wrong in v0.1.0

**If you cited tier-2 or tier-3 CER from `benchmark-v0.1.0`, the values were too
high. Use these instead:**

| figure | v0.1.0 (withdrawn) | corrected |
|---|---|---|
| tier-2 CER, B vs consensus | 0.0172 [0.0105, 0.0248] | **0.0031 [0.0006, 0.0062]** |
| tier-3 CER, B vs consensus | 0.0234 [0.0166, 0.0309] | **0.0119 [0.0085, 0.0156]** |
| adjudication, tier-2 edits | 165 | **33** |
| adjudication, tier-3 edits | 280 | **148** |

**Cause.** `<DR>`, the annotator-tool token for a double *rafe*, was scored as
four literal ASCII characters (`<`, `D`, `R`, `>`) in the tier-2 and tier-3 CER
path. `masoretic_eval/iaa/cer.py` asserted that editor tokens were "already
stripped during `split_chunks`"; they were not. `split_chunks` strips only
`PASSTHRU_TAGS`, and `<DR>` is deliberately excluded from that list so tier-4
extraction can emit a `double_rafe` record from it — but nothing removed it
afterwards. The three sides carry unequal counts (annotator A 25, annotator B 56,
consensus 27), so every excess token scored as four spurious edits.

The defect was self-contradictory as well as wrong: `strip.py` already excludes
U+05BF (*rafe*) from the tier-2 view precisely "so it is not double-counted
across tiers". The single *rafe* was stripped; the double *rafe*, written in
ASCII, was not.

**Direction.** The error was conservative — it made the two annotators look *less*
consistent than they are. No conclusion in the paper or the README reverses.

**Not affected**, verified field-by-field over the regenerated result JSONs (262
tier-4 and stratification fields compared, zero changed): tier-1 CER 0.0029; all
tier-4 figures including F1 exact 0.9187 and Krippendorff α 0.7470; the BL-05
*rafe* baseline F1 0.6210; every count in the corpus accounting. Tier 1 is immune
because its projection keeps only Hebrew consonants, space and *maqaf*, so ASCII
cannot survive it.

**Fixes.** Editor tokens are now stripped in the CER path for every tier, and a
new `masoretic_eval.iaa.cer.tier_view()` is the single definition of a chunk's
scoring view — `scripts/generate_iaa_report.py` and the release test had each
inlined their own copy of the same sequence and would otherwise have silently
missed the new strip. Regression test: `tests/iaa/test_editor_token_cer_isolation.py`
asserts that a chunk's tier CER is invariant to the presence of editor tokens, and
that tier-4 extraction still consumes `<DR>`.

**Credit.** Found during verification of three independent external reviews of
`benchmark-v0.1.0`. The tier-3 half was flagged by the Codex reviewer; the larger
tier-2 half and the adjudication-count contamination were found while verifying it.

### Other corrections

- Removed an internal `personnel_note` from four public test fixtures. It named a
  collaborator in full alongside an internal personnel correction and referenced a
  file in a private repository. It remains in the immutable `benchmark-v0.1.0` tag.
- Added David Zev Moster (annotator B) to `CITATION.cff`, the README citation, the
  `LICENSE.md` attribution string, and `ACKNOWLEDGMENTS.md`. He produced half the
  inter-annotator agreement this benchmark reports and was previously named only in
  the changelog and the data files, while his projection ships under
  attribution-required terms.
- Corrected the provenance note on `iaa_report.json`, which described the metric as
  code-point Levenshtein on NFC-normalised strings. It is cluster-aligned code-point
  CER on NFD, macro-averaged over verses. The same note wrongly claimed the headline
  CER was not recomputable without the UXLC cache; tiers 1–3 recompute from the three
  committed projections alone.
- Conformed the v0.1.0 licensing table (in the release notes below) to the ratified
  multi-component model in `LICENSE.md`: the earlier table listed the consonantal text
  and the annotation data under CC-BY-4.0, whereas `LICENSE.md` places the consonantal
  text in the public domain and dedicates the annotation data under CC0-1.0 (schema,
  adjudication, and compilation remain CC-BY-4.0; the scorer remains Apache-2.0).
  `LICENSE.md` is authoritative; the immutable `benchmark-v0.1.0` tag keeps the
  superseded table.

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

| Component | License / status |
|---|---|
| Consonantal text (Tier 1, all four folios) | Public Domain |
| Annotation data (Tiers 2–4: nikkud, cantillation, meta-mark positions & labels) | CC0-1.0 |
| Scholarly contributions (positional-encoding schema, two-annotator adjudication protocol & metadata, error taxonomy & guidelines, four-folio benchmark compilation) | CC-BY-4.0 |
| Scorer code (`masoretic_eval/`) | Apache-2.0 |
| Manuscript images | Not distributed; referenced by IIIF URL only. WSRP asserts rights over the photographs. |

This table summarizes; [`LICENSE.md`](LICENSE.md) is authoritative.

---

## masoretic_eval 0.2.0 — scorer

The four-tier scorer package, released independently and tagged `v0.2.0`. See the
package version in `pyproject.toml` and the reproducibility notes in
`docs/TESTING.md`.
