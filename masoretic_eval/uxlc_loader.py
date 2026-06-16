"""UXLC XML parser: verse extraction, tier-specific stripping, meta-mark extraction.

Structural notes (observed from UXLC 2.5, tanach.us):
- Root: <Tanach> → <book> (with <names><name>…</name>) → <c n="N"> → <v n="N">
- <pe/> / <samekh/> / <reversednun/>: children of <v> (the verse they close),
  not siblings between <v> elements.
- <k> / <q>: siblings of <w> inside <v>, NOT children of <w>.
  A k/q pair represents a ketiv/qere word; policy default is to use qere.
  If <k> appears without a following <q>, the ketiv is used as a fallback
  (with a warning); the word is never silently dropped.
- <w>: may contain plain text (w.text) plus child <s t="large|small|…"> for
  special-letter markup.  <x>N</x> children carry tier-4 codes and must be
  excluded from the word's text string.
- <x>N</x>: child of <w>; codes 4–8 are tier-4 meta-marks.
  Codes c/t/q/m/d are scribal annotation marks (not scored in tiers 1–3).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

_log = logging.getLogger(__name__)

# Collapse two-or-more consecutive ASCII spaces (produced after stripping
# codepoints that were preceded/followed by spaces, e.g. paseq U+05C0).
_MULTISPACE = re.compile(r"  +")

NIKKUD_RANGE = (0x05B0, 0x05BD)  # vowel points (includes dagesh U+05BC)
# SIN_SHIN_DOTS kept because it documents the range; NOT used as a strip target
# (sin-dot 0x05C1 and shin-dot 0x05C2 are retained in tier 2 per spec).
SIN_SHIN_DOTS = (0x05C1, 0x05C2)  # shin-dot, sin-dot (informational constant)
# Hebrew punctuation / marks between sin/shin dots and the consonant block:
# U+05C0 paseq, U+05C3 sof-pasuq, U+05C4 upper-dot, U+05C5 lower-dot,
# U+05C6 nun-hafukha, U+05C7 qamats-qatan.  Maqaf (U+05BE) is kept in
# tier 1 as a word-joiner; rafe (U+05BF) is stripped separately.
HEBREW_PUNCT_MARKS = (0x05BF, 0x05C7)  # rafe through qamats-qatan (excl. maqaf 0x05BE)
TROP_RANGE = (0x0591, 0x05AF)  # taamim / cantillation marks

# Codepoints stripped from tier 2 that fall outside TROP_RANGE but are also
# not consonants or nikkud: meteg/ga'ya (U+05BD), rafe (U+05BF), paseq (U+05C0),
# sof-pasuq (U+05C3), nun-hafukha (U+05C6).  Sin-dot (U+05C1) and shin-dot
# (U+05C2) are retained.  Meteg added per DECISIONS.md 2026-06-15 (scored at
# tier 3, not tier 2).  MUST stay in sync with strip.py::_TIER2_EXTRA_STRIP.
_TIER2_EXTRA_STRIP = (0x05BD, 0x05BF, 0x05C0, 0x05C3, 0x05C6)

META_MARK_TAGS = {"pe", "samekh", "reversednun"}


@dataclass(frozen=True)
class MetaMarkRecord:
    type: str  # e.g. "pe", "samekh", "reversednun", "large_letter", "puncta", …
    verse_ref: str  # OSIS-style, e.g. "Deut.6.4"
    ordinal: int  # 1-indexed position within the verse for this type
    codepoints: str | None = None  # optional — for large/small letter, which letter


@dataclass
class UXLCDoc:
    verses: dict[str, str]  # verse_ref -> raw verse text (all codepoints preserved)
    metamarks: list[MetaMarkRecord]
    # Informational only: the loader currently hardcodes qere selection with
    # ketiv-as-fallback when no qere sibling exists. Not configurable in v0.1.
    qere_ketiv_policy: str = "qere"


_BOOK_NAME_MAP = {
    "Deuteronomy": "Deut",
    "Genesis": "Gen",
    "Exodus": "Exod",
    "Leviticus": "Lev",
    "Numbers": "Num",
    "Samuel 1": "1Sam",
    "Samuel 2": "2Sam",
    "Isaiah": "Isa",
    # Extend as needed.
}


def _verse_ref(book: str, chapter: str, verse: str) -> str:
    return f"{_BOOK_NAME_MAP.get(book, book)}.{chapter}.{verse}"


def _word_text(w_el: etree._Element) -> str:
    """Extract the Hebrew text from a <w>, <k>, or <q> element.

    Concatenates element.text with text from child <s> elements (special-letter
    markup), skipping <x> children which carry tier-4/annotation codes.
    """
    parts: list[str] = []
    if w_el.text:
        parts.append(w_el.text)
    for child in w_el:
        localname = etree.QName(child).localname
        if localname == "x":
            # The <x> code char itself is not part of the word's text, but UXLC
            # places <x> mid-word, so the word remainder is the element's TAIL
            # and must be kept (else e.g. the Decalogue תרצח truncates).
            if child.tail:
                parts.append(child.tail)
            continue
        # <s t="large|small"> or other markup: include its text.
        if child.text:
            parts.append(child.text)
        # tails after inline elements (rare in UXLC but handle defensively)
        if child.tail:
            parts.append(child.tail)
    return "".join(parts).strip()


_MAQAF = "־"  # word-joiner (U+05BE); no space follows it in the codex


def _join_word_parts(parts: list[str]) -> str:
    """Join verse words with single spaces, except after a maqaf-joined part.

    UXLC encodes a maqaf group as separate <w> elements with a trailing U+05BE
    and no following space (e.g. אֶת־ + יְהוָ֣ה). A naive " ".join inserts a
    spurious space that survives normalization (maqaf is retained in tiers 1-3
    and _MULTISPACE only collapses 2+ spaces), scoring one bogus edit per maqaf.
    """
    out: list[str] = []
    for part in parts:
        out.append(part)
        if not part.endswith(_MAQAF):
            out.append(" ")
    return "".join(out).rstrip()


def _xcode_to_type(code: str) -> str | None:
    """Map UXLC <x> code to a tier-4 type. Codes 4–8 per spec Section 4 #9."""
    mapping = {
        "4": "puncta",
        "5": "large_letter",
        "6": "small_letter",
        "7": "suspended_letter",
        "8": "inverted_nun",
    }
    return mapping.get(code)


def load_uxlc(path: Path | str) -> UXLCDoc:
    """Parse a UXLC XML file into verse strings and meta-mark records."""
    tree = etree.parse(str(path))
    root = tree.getroot()
    verses: dict[str, str] = {}
    metamarks: list[MetaMarkRecord] = []

    for book_el in root.iter("book"):
        name_el = book_el.find("names/name")
        book_name = name_el.text.strip() if name_el is not None and name_el.text else "?"

        for c_el in book_el.iter("c"):
            chapter = c_el.get("n", "?")

            for v_el in c_el:
                localname_v = etree.QName(v_el).localname
                if localname_v != "v":
                    # Paragraph markers at the chapter level (not observed in
                    # UXLC 2.5 but guard defensively).
                    continue

                verse_num = v_el.get("n", "?")
                ref = _verse_ref(book_name, chapter, verse_num)
                ordinal_by_type: dict[tuple[str, str], int] = {}

                # Iterate direct children of <v>: <w>, <k>, <q>, <pe/>, etc.
                word_parts: list[str] = []
                pending_ketiv: str | None = None

                for child in v_el:
                    localname = etree.QName(child).localname

                    if localname == "w":
                        # Flush any pending ketiv before processing a regular word.
                        if pending_ketiv is not None:
                            _log.warning(
                                "UXLC: ketiv %r has no qere sibling at verse %s;"
                                " using ketiv as fallback",
                                pending_ketiv,
                                ref,
                            )
                            word_parts.append(pending_ketiv)
                            pending_ketiv = None
                        word_parts.append(_word_text(child))

                    elif localname == "k":
                        # Flush any previously stashed ketiv without qere.
                        if pending_ketiv is not None:
                            _log.warning(
                                "UXLC: ketiv %r has no qere sibling at verse %s;"
                                " using ketiv as fallback",
                                pending_ketiv,
                                ref,
                            )
                            word_parts.append(pending_ketiv)
                        # Stash this ketiv; qere sibling should follow.
                        pending_ketiv = _word_text(child)

                    elif localname == "q":
                        # Qere: default policy is to use qere text.
                        # Route through _word_text to handle <s> children in qere.
                        word_parts.append(_word_text(child))
                        pending_ketiv = None

                    elif localname in META_MARK_TAGS:
                        # Flush pending ketiv before a paragraph marker.
                        if pending_ketiv is not None:
                            _log.warning(
                                "UXLC: ketiv %r has no qere sibling at verse %s;"
                                " using ketiv as fallback",
                                pending_ketiv,
                                ref,
                            )
                            word_parts.append(pending_ketiv)
                            pending_ketiv = None
                        n = ordinal_by_type.get((ref, localname), 0) + 1
                        ordinal_by_type[(ref, localname)] = n
                        metamarks.append(MetaMarkRecord(type=localname, verse_ref=ref, ordinal=n))

                # Flush any ketiv left at end of verse (no more siblings).
                if pending_ketiv is not None:
                    _log.warning(
                        "UXLC: ketiv %r has no qere sibling at verse %s; using ketiv as fallback",
                        pending_ketiv,
                        ref,
                    )
                    word_parts.append(pending_ketiv)

                # Collect <x> meta-marks from within <w> elements.
                for w_el in v_el.iter("w"):
                    for x_el in w_el:
                        if etree.QName(x_el).localname != "x":
                            continue
                        code = (x_el.text or "").strip()
                        mark_type = _xcode_to_type(code)
                        if mark_type is not None:
                            n = ordinal_by_type.get((ref, mark_type), 0) + 1
                            ordinal_by_type[(ref, mark_type)] = n
                            metamarks.append(
                                MetaMarkRecord(type=mark_type, verse_ref=ref, ordinal=n)
                            )

                verses[ref] = _join_word_parts(word_parts)

    return UXLCDoc(verses=verses, metamarks=metamarks)


def _strip_range(text: str, lo: int, hi: int) -> str:
    return "".join(c for c in text if not (lo <= ord(c) <= hi))


def load_tier_strings(path: Path | str, tier: int) -> dict[str, str] | list[MetaMarkRecord]:
    """Return the tier-specific view of a UXLC document.

    - tier 1: consonants only (nikkud + trop + rafe + sin/shin dots stripped).
    - tier 2: consonants + nikkud + dagesh + sin/shin dots (trop stripped;
              also strips rafe, paseq, sof-pasuq, nun-hafukha).
    - tier 3: full (all Hebrew codepoints retained).
    - tier 4: list of MetaMarkRecord.
    """
    if tier not in (1, 2, 3, 4):
        raise ValueError(f"tier must be 1..4, got {tier}")

    doc = load_uxlc(path)
    if tier == 4:
        return doc.metamarks

    result: dict[str, str] = {}
    for ref, raw in doc.verses.items():
        text = raw
        if tier == 1:
            text = _strip_range(text, *TROP_RANGE)
            text = _strip_range(text, *NIKKUD_RANGE)
            # Strip rafe, paseq, sin/shin dots, sof-pasuq, and other
            # Hebrew punct/marks in U+05BF–U+05C7 (maqaf U+05BE is kept).
            text = _strip_range(text, *HEBREW_PUNCT_MARKS)
        elif tier == 2:
            text = _strip_range(text, *TROP_RANGE)
            # Strip Hebrew non-letter, non-nikkud punctuation codepoints.
            # Sin-dot (U+05C1) and shin-dot (U+05C2) are retained per spec.
            for cp in _TIER2_EXTRA_STRIP:
                text = text.replace(chr(cp), "")
        # tier 3: no stripping

        # Collapse internal whitespace runs produced by stripping codepoints
        # that were adjacent to spaces (e.g. paseq U+05C0 in "יהוה ׀").
        text = _MULTISPACE.sub(" ", text).strip()

        result[ref] = text
    return result
