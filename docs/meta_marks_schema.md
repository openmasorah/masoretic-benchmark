# Tier-4 Meta-Marks Schema

**Status:** v0.1 PROPOSED — pending ratification by primary scholar collaborator.
Annotators may begin tagging against this schema; pre-ratification revisions are
tracked in the CHANGELOG at the bottom of this document.

**Scope authority:** `phase_0_manifest.json` v0.2.0 (4 IAA folios from Leningrad
Codex Devarim, Ha'azinu through Torah end: F118B, F119A, F119B, F120A).

---

## What this document defines

The capture conventions for **tier-4 meta-marks** in PAGE-XML ground truth
produced via eScriptorium. Tier-4 covers body-text-internal scribal annotation:
parashah breaks, sof pasuq, nequdot/dotted letters, large/small letters, inverted
nun. Tier-4 ≠ marginal masorah; Mp/Mg are deferred to v0.3.

Consumers of this schema:

- **annotators** producing GT in eScriptorium
- **`masoretic_eval/page_xml.py`** — PAGE-XML 2019-07-15 parser; per-mark extraction
- **`masoretic_eval`** — CER scoring with tier-4 vocabulary alignment
  (`tier4_records.type` enum)

---

## Capture mechanism

Two mechanisms with a principled split.

| Mechanism | When to use | Where it lives in PAGE-XML |
|---|---|---|
| **Unicode-in-text** | The mark has an official Unicode codepoint and is a character | `<TextEquiv><Unicode>` text content |
| **`@custom` on `TextLine`** | The mark has no codepoint, **or** is a line/paragraph property rather than a character | `<TextLine custom="...">` attribute, semicolon-separated `key:value` tokens |

Annotators enter Unicode marks via the supplemental virtual keyboard
(`docs/keyboards/openmasorah_tier4.json`). `@custom` marks are entered via
eScriptorium's per-line metadata panel.

---

## Normalization (mandatory)

**All GT must be normalized to Unicode Normalization Form C (NFC) before export.**
This applies to the text content of every `<Unicode>` element.

**Why.** The combining marks U+05C4 (HEBREW MARK UPPER DOT, CCC=230) and U+05C5
(HEBREW MARK LOWER DOT, CCC=220) share Canonical Combining Class values with
several trop accents in the U+0591–U+05AF range. Annotators entering the same
visual mark in different keystroke order produce byte-distinct strings that
score as character-level mismatches without normalization. NFC canonicalizes
the order.

**Scorer side.** `masoretic_eval` applies `unicodedata.normalize("NFC", s)` to
both reference and prediction strings before tier-1/2/3/4 CER computation.
(Tracked follow-up — see *v0.1 follow-ups* below.)

**Annotation workflow.** At GT export, run text through
`unicodedata.normalize("NFC", s)` (or eScriptorium's normalize-on-export
setting if enabled). The GT pipeline pre-commit gate must verify NFC.

The `masoretic_eval/page_xml.py` parser preserves bytes verbatim by design
(*Pitfall 2*); NFC is the only sanctioned normalization, applied at export
and at scoring, never silently inside the parser.

---

## Per-mark specifications

Each row below is the **authoritative encoding rule** for that mark. The
visual reference column will be populated with manuscript image crops once
F118B annotation is settled; PROPOSED rows show codepoint or token only.

### 1. Sof pasuq — verse-end colon

| Field | Value |
|---|---|
| Mechanism | Unicode-in-text |
| Codepoint | **U+05C3** `HEBREW PUNCTUATION SOF PASUQ` (`׃`) |
| Where | At end of every verse, in body-text region |
| Example PAGE-XML | `<TextEquiv><Unicode>בְּרֵאשִׁית בָּרָא … הָאָֽרֶץ׃</Unicode></TextEquiv>` |
| Visual | <!-- IMAGE: F118B sof-pasuq crop pending --> |
| Rule | One U+05C3 per verse, immediately after the final word's punctuation/cantillation. Do not enter U+003A (ASCII colon). |

### 2. Nequdot / dotted letters — puncta extraordinaria

| Field | Value |
|---|---|
| Mechanism | Unicode-in-text (combining marks) |
| Codepoints | **U+05C4** `HEBREW MARK UPPER DOT`, **U+05C5** `HEBREW MARK LOWER DOT` |
| Where | Combining onto a base consonant marked in the manuscript with a dot above (U+05C4) or below (U+05C5) |
| Example PAGE-XML | `<Unicode>אֵלָֽיו̇</Unicode>` (dot above the vav: vav + U+05C4) |
| Visual | <!-- IMAGE: F119B nequdot crop pending --> |
| Rule | The combining mark is appended after the base consonant **and after any nikkud or trop on the same letter**. NFC handles canonical ordering — annotators do not need to memorize CCC. |

### 3. Inverted nun — nun hafukha

| Field | Value |
|---|---|
| Mechanism | Unicode-in-text (single character) |
| Codepoint | **U+05C6** `HEBREW PUNCTUATION NUN HAFUKHA` (`׆`) |
| Where | Wherever the manuscript shows an inverted/reversed nun as a punctuation marker (e.g., before/after Numbers 10:35–36 in MT tradition) |
| Example PAGE-XML | `<Unicode>… ׆ וַיְהִי בִּנְסֹעַ הָאָרֹן …</Unicode>` |
| Visual | <!-- IMAGE: not applicable for Devarim end-of-Torah folios --> |
| Rule | U+05C6 encodes the masoretic punctuation only. **For F118B–F120A specifically, inverted nun does not appear in body text;** the codepoint is included in the supplemental keyboard for corpus completeness across the broader Open Masorah benchmark. |

### 4. Large letters — litterae majusculae

| Field | Value |
|---|---|
| Mechanism | `@custom` on `TextLine` |
| Token | `letter_size:large@<index>` |
| Index | Zero-based Unicode code-unit index into the TextLine's text content (after NFC) |
| Multiple per line | Comma-separated indices: `letter_size:large@5,large@12` |
| Example PAGE-XML | `<TextLine id="..." custom="parashah:none; letter_size:large@7">` |
| Visual | <!-- IMAGE: F118B Deut 32:6 ל-large pending --> |
| Rule | The base consonant is entered as a normal letter in the text content. Size is recorded as a per-line `@custom` annotation, not via codepoint. |

**Char-index fragility — tag-last workflow rule.** Indices are resolved at
annotation export. If TextLine text content is edited after a `letter_size`
tag is applied, indices silently drift. Tag large/small letters as the
**final** step on each line, after all text content is settled. If the text
is edited after tagging, **re-tag from scratch** — do not patch indices.

#### Ha'azinu inclusio (Deut 32:6, 32:18)

The masoretic convention frames the Song of Moses with two enlarged letters
forming an inclusio: **ל** in Deut 32:6 and **ת** in Deut 32:18. Both are
encoded as `letter_size:large@<index>` on their respective TextLines.

### 5. Small letters — litterae minusculae

| Field | Value |
|---|---|
| Mechanism | `@custom` on `TextLine` |
| Token | `letter_size:small@<index>` |
| Index, multiplicity, fragility | Same as large letters (§4) |
| Visual | <!-- IMAGE: pending --> |
| Rule | Same as large letters but `small`. |

### 6. Parashah breaks — petuhah / setumah

| Field | Value |
|---|---|
| Mechanism | `@custom` on `TextLine` where the break begins |
| Tokens | `parashah:petuhah` (open section) <br> `parashah:setumah` (closed section) |
| Where | On the TextLine that *opens* the new section (i.e., the line after the visual gap, not the line where the previous section ends) |
| Example PAGE-XML | `<TextLine id="..." custom="parashah:petuhah">` |
| Visual | <!-- IMAGE: F118B parashah crop pending --> |
| Rule | Do **not** enter inline `פ` or `ס` characters in body text to mark a break — those would be scored as tier-1 consonants. Use `@custom` only. |

**Why not inline פ/ס in text.** UXLC encodes parashah breaks as structural
`MetaMarkRecord` entries via `META_MARK_TAGS`, never as text-stream
characters. Inline `פ`/`ס` would conflate section markers with the letters
peh/samekh as they actually appear in body text.

---

## Layout encoding — Ha'azinu stichography

Deuteronomy 32 (Song of Moses) is laid out in two columns of stichs (poetic
half-lines) in Tiberian codices, including Leningrad. Folios F118B–F120A
include the full Ha'azinu unit.

| Field | Value |
|---|---|
| Mechanism | `@custom` on `TextLine` |
| Token | `layout:stichographic_column@<n>` where `<n>` ∈ {`1`, `2`} |
| Convention | `1` = first column (right, given Hebrew RTL); `2` = second column (left). Lines outside the stichographic block carry no `layout:` token (default = single-column body). |
| Example PAGE-XML | `<TextLine id="..." custom="layout:stichographic_column@1">` |
| Visual | <!-- IMAGE: F118B Ha'azinu two-column layout pending --> |
| Rule | Line geometry (segmentation polygon) reflects the visual column position; the `layout:` token records the logical column. Decoupling layout from text content keeps tier-1 consonantal CER independent of typesetting variation. |

---

## Annotation completeness contract

Before committing a TextLine, the annotator confirms presence/absence of
**each** tier-4 category. Without this discipline, two annotators consistently
missing the same rare mark produces artificially high IAA — a benchmark that
quietly understates tier-4 difficulty. The contract structures **recall
checking**; it does not constrain interpretation.

Per-line checklist:

- [ ] **Sof pasuq** — present? (if yes, U+05C3 in text)
- [ ] **Nequdot / dotted letters** — present? (if yes, U+05C4/U+05C5 combining on the dotted letter)
- [ ] **Inverted nun** — present? (if yes, U+05C6 in text)
- [ ] **Large letters** — present? (if yes, `letter_size:large@<idx>` in `@custom`)
- [ ] **Small letters** — present? (if yes, `letter_size:small@<idx>` in `@custom`)
- [ ] **Parashah break beginning on this line?** (if yes, `parashah:petuhah|setumah` in `@custom`)
- [ ] **Stichographic layout** (Ha'azinu only) — applies? (if yes, `layout:stichographic_column@<n>` in `@custom`)

---

## Out of scope for v0.1

| Item | Status | Future home |
|---|---|---|
| Marginal masorah — Mp/Mg content transcription | Deferred | v0.3 |
| Qere/ketiv | Deferred — requires PAGE-XML schema extension (`<TextEquiv dataType="qere">`) which changes the parser contract | v0.3 |
| Scribal corrections (erasures, supralinear additions) | Deferred — IAA protocol distinct from tier-4 character capture | v0.3 |
| Sof pasuq vs final-letter ambiguity | Flag for adjudication; schema treats U+05C3 as the punctuation mark | v0.1 — adjudication queue |

---

## Tracked follow-ups

### Shipped in v0.1 (PR #20)

1. **Scorer NFC pre-comparison fix** — `masoretic_eval/normalize.py` applies
   `unicodedata.normalize("NFC", s)` before NFD+CGJ-strip in
   `normalize_for_scoring()`. All tier scorers route through this function.
2. **PAGE-XML parser extraction for `@custom` tier-4 fields** —
   `masoretic_eval/page_xml.py::_parse_custom` extracts `parashah:*`,
   `letter_size:*`, `layout:stichographic_column@*` into typed `LineRecord`
   fields. Strict-everywhere policy: unknown top-level keys and unknown
   sub-keys both raise `ValueError`.

### Deferred to v0.2 (cross-AI review on PR #20)

These were raised by codex + cursor reviewers on the v0.1 follow-up PR. None
block tier-4 scoring; track them so they don't evaporate.

1. **Tier-1 / tier-3 / tier-4 NFC-equivalence tests + idempotence guard** —
   the v0.1 NFC test covers tier-2 only. Add coverage that two NFC-equivalent
   strings produce CER == 0 for tier-1, tier-3, and tier-4, and that
   `normalize_for_scoring` is a no-op on already-NFC input (idempotence).
   *Status (v0.2): tier-3 now covered by the CGJ-ordering regression
   (`tests/test_normalize.py::test_tier3_cer_is_zero_for_cgj_equivalent_strings`),
   added alongside the strip-CGJ-first ordering fix. Idempotence is guarded by
   `test_nfd_is_idempotent`. Tier-1 is mark-insensitive (consonants only), so its
   equivalence is trivially satisfied. Tier-4 remains open — it needs a meta-mark
   fixture, not a meteg+vowel cluster.*
2. **Duplicate-scalar-token detection in `_parse_custom`** — repeated tokens
   for scalar fields (e.g. two `parashah:` or two
   `layout:stichographic_column@`) silently overwrite (last wins). Promote to
   `ValueError` for consistency with the strict-everywhere policy.
3. **`letter_size` index bounds validation** — `large@9999` parses
   successfully and propagates malformed metadata. Validate indices against
   `len(text)` after both are known (in `parse_page_xml`, post-parse).
4. **`letter_size` ordering / dedup policy clarification** — schema §4 does
   not specify whether multiple `large@<idx>` entries must be sorted or
   deduplicated. Implementation today: insertion order, no dedup. Decide
   canonical posture and update both the schema doc and the parser
   accordingly.
5. **Parser strict-mode flag** (optional) — if forward-compatibility for new
   schema versions becomes a real need, expose `_parse_custom(strict=True)` as
   the default with `strict=False` opt-in for permissive reads. Don't add
   unless a concrete use case appears.

---

## References

- `phase_0_manifest.json` v0.2.0 — frozen scope authority
- `masoretic_eval/page_xml.py` — PAGE-XML 2019-07-15 parser; ground-truth round-trip target. Pitfall 2 (no parser-side normalization) is intentional — NFC is applied at export and at scoring, not inside the parser.
- `masoretic_eval` — tier-4 vocabulary enum (`tier4_records.type`) and `META_MARK_TAGS`
- Unicode 16.0, Hebrew block U+0590–U+05FF — codepoint authority
- SegmOnto Region vocabulary — `MainZone` / `MarginTextZone:Mm|Mp` precedent (Mp/Mg deferred)
- `docs/keyboards/openmasorah_tier4.json` — supplemental virtual keyboard (4 codepoints)

---

## CHANGELOG

- **2026-05-10** — v0.1 follow-ups shipped (PR #20): NFC pre-comparison in scorer, `@custom` tier-4 field extraction with strict-everywhere parser policy, Pitfall 2 regression guard via non-canonical combining-mark order test. Cross-AI review (codex + cursor) deferred 5 items to v0.2 — see "Deferred to v0.2" above.
- **2026-05-09** — v0.1 PROPOSED drafted. Pre-ratification design review by FAMP architect (AMBER, 4 adjustments applied: NFC mandate, parashah `@custom` precision, char-index fragility note, U+05C6 scope note) and FAMP matt (3 changes applied: Ha'azinu encodings front-loaded, completeness contract added, quick reference folded inline). Pending ratification.
