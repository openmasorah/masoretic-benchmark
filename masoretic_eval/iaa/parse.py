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

    Editor tokens are replaced with spaces (so a token at chunk boundaries
    does not glue verses together). Empty chunks are discarded — the input
    file's final sof-pasuq generally produces a trailing empty chunk which
    we drop.
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
