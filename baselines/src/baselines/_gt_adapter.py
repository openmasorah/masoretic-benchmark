"""Per-line tier-1 GT projection for BL-03 / BL-04 GT-fed diagnostic chain.

Consumes masoretic_eval.page_xml.parse_page_xml (extracted upstream per
Phase 03.1 A-04 -- see masoretic_eval v0.2.0 release).

The diagnostic chain (Phase 3 D-01) feeds GT consonants -- not Kraken
output -- into the diacritizer; this adapter projects PAGE-XML LineRecord
-> tier-1 strings (consonantal-only) to be the diacritizer's input.

Tier-1 keep-set: U+05D0..U+05EA (Hebrew aleph..tav) + ASCII space (U+0020)
+ maqaf (U+05BE). Mirrors the Phase 3 D-07 contamination boundary
intent: keep readable consonantal text + Hebrew word/phrase separators
that the diacritizer needs, drop everything else (nikkud U+05B0..U+05BD,
trop U+0591..U+05AF, sof pasuq U+05C3, etc.).

Inlined here to avoid masoretic_eval scoring imports at module load
(keeps pytest collection fast for the mocked-unit tier per
baselines/_llm_clients.py lazy-import pattern).
"""

from __future__ import annotations

from pathlib import Path

from masoretic_eval.page_xml import parse_page_xml

# Tier-1 keep-set -- Hebrew letters + ASCII space + maqaf (U+05BE).
TIER1_KEEP_LO = 0x05D0  # Hebrew aleph
TIER1_KEEP_HI = 0x05EA  # Hebrew tav
TIER1_KEEP_CHARS = frozenset(" ־")  # ASCII space + maqaf U+05BE


def load_tier1_per_line(folio_id: str, page_xml_path: Path) -> list[str]:
    """Return the tier-1 (consonantal-only) text per line in folio order.

    Args:
        folio_id: manifest folio id (used only for error context).
        page_xml_path: path to the IAA-blessed PAGE-XML for this folio.

    Returns:
        Per-line consonantal strings, in line_num order. Length equals
        the number of TextLine elements in the PAGE-XML AFTER the
        parser's missing-TextEquiv skip (parse_page_xml drops lines
        without TextEquiv).
    """
    records = parse_page_xml(page_xml_path)
    return [_strip_tier1(r.text) for r in records]


def _strip_tier1(text: str) -> str:
    """Codepoint filter: keep U+05D0..U+05EA + space + maqaf (U+05BE).

    Mirrors the spirit of baselines._llm_combine._tier1_strip (the
    combine-equality keep-set) but additionally retains the two
    Hebrew word/phrase separators (space, maqaf) that the diacritizer
    needs to segment its input. The scorer (D-22 untouched) re-runs
    its own tier-strip at score time.
    """
    return "".join(
        c for c in text if TIER1_KEEP_LO <= ord(c) <= TIER1_KEEP_HI or c in TIER1_KEEP_CHARS
    )
