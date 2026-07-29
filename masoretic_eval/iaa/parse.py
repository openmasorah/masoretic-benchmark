"""Raw round-0 .txt → per-verse `Tier4Record`s for IAA.

The math here mirrors the upstream `tier4_positional` extractor (reproduced,
not imported, per SPEC 260619-n3u's licence-clean rule). The
ordinal of a positional mark is the 1-based offset of the most recent Hebrew
consonant (U+05D0..U+05EA) in the raw verse chunk. Editor tokens (`<MF>`,
`<EF>`, `<L>`, `<C>`, `<BL>`, `<WS>`, `<P>`) do NOT increment the ordinal.

Three positional types are extracted:

* ``circellus``: U+05AF, anchored to the most recent preceding consonant.
* ``rafe``: U+05BF, anchored to the most recent preceding consonant.
* ``double_rafe``: ``<DR>`` editor token, anchored to the consonant immediately
  before the token.

Type folding to {circellus, rafe, both, none} happens later, in
:mod:`masoretic_eval.iaa.alpha` (canon vs raw). This module emits raw
records only.

Per-annotator ordinal anchoring — design + caveat (FINDING 3)
-------------------------------------------------------------

This extractor is run *independently* on each annotator's raw chunk:
ordinals derive from that annotator's own consonant stream. Two consequences:

1. **Design (what this buys).** Each side's tier-4 detections live in the same
   ordinal coordinate system as that side's tier-1 transcription. No
   cross-side alignment computation is required to score F1 / α / κ within
   one annotator's data, and the round-trip equivalence between raw .txt and
   the published positional projection JSONs (see
   :mod:`masoretic_eval.iaa.projection`) holds per-annotator without
   reference to the other side or to an external backbone.

2. **Caveat (the tier-1-into-tier-4 propagation).** If annotator A's chunk
   has N consonants and B's has N+1 for the same verse (a tier-1 insertion,
   deletion, or different irregular-letter convention), every mark on B
   placed after the disagreement sits at an ordinal one step away from the
   matching mark on A. The headline F1's ±1 tolerance phase absorbs the
   offset as "anchor ambiguity," but the offset is in part tier-1 alignment
   noise — not the schema-anchor question the metric is meant to surface.

   Quantification on the v0.2.0 Devarim 4-folio subset (single annotator pair,
   round-0): tier-1 CER is ≤0.57% per folio (0.29% overall). At ~25–60
   consonants per verse, expected insertions/deletions from tier-1
   disagreement are ~0.1–0.3 per verse. The contamination of the F1
   exact-vs-±1 gap (the §6.1 anchor-ambiguity statistic in the paper) is
   bounded by this and is small in proportion, but it is non-zero.

   The optional UXLC-backbone reprojection path (planned for v0.3) removes
   this contamination entirely by deriving both annotators' ordinals from a
   shared reference consonant stream. The current published projection JSONs
   carry per-annotator ordinals; consumers comparing across sides should be
   aware of the caveat. See ``masoretic_eval/iaa/ALIGNMENT.md`` for the full
   algorithm specification and the v0.3 reprojection plan.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Editor tokens emitted by the Moster transcription pipeline. These are stripped
# from the consonant stream but do not consume ordinal slots.
PASSTHRU_TAGS = ("<MF>", "<EF>", "<L>", "<C>", "<BL>", "<WS>", "<P>")
_PASSTHRU_RE = re.compile("|".join(re.escape(t) for t in PASSTHRU_TAGS))
# Generic `<UPPER>` editor token shape — matches anything in the all-caps
# namespace including future additions and the `<DR>` double-rafe token. We
# match `<DR>` first explicitly so it can emit a record before being consumed
# as a generic editor token.
_EDITOR_TOKEN_RE = re.compile(r"<[A-Z]+>")

SOF_PASUQ = "׃"
CIRCELLUS = "֯"
RAFE = "ֿ"
DOUBLE_RAFE_TOKEN = "<DR>"

# U+05D0..U+05EA: Hebrew letters (consonants). Ordinal increments only on
# these codepoints.
_CONSONANT_LO = 0x05D0
_CONSONANT_HI = 0x05EA


def _is_consonant(ch: str) -> bool:
    return _CONSONANT_LO <= ord(ch) <= _CONSONANT_HI


@dataclass(frozen=True)
class Tier4Record:
    """One positional tier-4 detection: (type, verse_ref, ordinal).

    ``type`` ∈ {"circellus", "rafe", "double_rafe"} (raw — pre-canon).
    ``ordinal`` is 1-based Hebrew-consonant offset within the raw verse chunk.
    """

    type: str
    verse_ref: str
    ordinal: int


def split_chunks(text: str) -> list[str]:
    """Split raw round-0 text into per-verse chunks at sof-pasuq.

    Only the **pass-through** tokens in ``PASSTHRU_TAGS`` are replaced with
    spaces, so a token sitting at a chunk boundary cannot glue two verses
    together. ``<DR>`` is deliberately *not* among them: it carries a tier-4
    double-*rafe* record and must survive into the chunk for the extractor to
    consume. Empty chunks are discarded — the input file's final sof-pasuq
    generally produces a trailing empty chunk which we drop.

    (This docstring previously claimed that *editor tokens* are replaced with
    spaces, unqualified. That reading is what produced the ``<DR>`` incident,
    and it was quoted back verbatim by two external reviewers who never ran
    the function. A wrong self-description propagates further than wrong code.)
    """
    cleaned = _PASSTHRU_RE.sub(" ", text).replace("\n", " ")
    return [c.strip() for c in cleaned.split(SOF_PASUQ) if c.strip()]


def count_consonants(chunk: str) -> int:
    """Number of Hebrew consonants in ``chunk`` — defines the ordinal range 1..N."""
    return sum(1 for c in chunk if _is_consonant(c))


def extract_positional(raw_chunk: str, verse_ref: str) -> list[Tier4Record]:
    """Extract positional tier-4 records from one raw verse chunk.

    The returned records use 1-based Hebrew-consonant offsets within
    ``raw_chunk`` and are sorted by ``(type, verse_ref, ordinal)`` for stable
    cross-side comparison. The sort makes the output insensitive to mark
    interleaving (e.g. a circellus followed by a rafe on the next consonant
    sorts deterministically regardless of which side emitted them first).
    """
    records: list[Tier4Record] = []
    consonant_offset = 0
    current_consonant_offset: int | None = None
    i = 0
    while i < len(raw_chunk):
        if raw_chunk.startswith(DOUBLE_RAFE_TOKEN, i):
            if current_consonant_offset is not None:
                records.append(Tier4Record("double_rafe", verse_ref, current_consonant_offset))
            i += len(DOUBLE_RAFE_TOKEN)
            continue

        token = _EDITOR_TOKEN_RE.match(raw_chunk, i)
        if token is not None:
            i = token.end()
            continue

        ch = raw_chunk[i]
        if _is_consonant(ch):
            consonant_offset += 1
            current_consonant_offset = consonant_offset
        elif ch == CIRCELLUS and current_consonant_offset is not None:
            records.append(Tier4Record("circellus", verse_ref, current_consonant_offset))
        elif ch == RAFE and current_consonant_offset is not None:
            records.append(Tier4Record("rafe", verse_ref, current_consonant_offset))
        i += 1

    return sorted(records, key=lambda r: (r.type, r.verse_ref, r.ordinal))
