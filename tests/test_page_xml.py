"""Tests for masoretic_eval.page_xml — verbatim move of gt-infra parser (A-04).

These tests pin the four parser-correctness invariants:
  1. Shape: line_num/verse_ref/text/conf round-trip on a minimal 2-line tree.
  2. Pitfall 2 byte preservation: CGJ (U+034F) survives lxml's parse path
     unchanged. No Unicode normalization anywhere in this file or in
     ``masoretic_eval.page_xml``.
  3. Skip branch: a ``TextLine`` missing its ``TextEquiv`` child is dropped
     (parser line ``if te is None: continue``).
  4. Missing-conf branch: ``TextEquiv`` without ``@conf`` → ``conf=None``.
  5. Synthetic Devarim-Shema golden: a hand-authored multi-region fixture
     packs four edge cases (empty TextEquiv, non-integer @id sort-first,
     multi-region recursive descent, diacritics roundtrip) — parser
     correctness only, NOT a GT-validation artifact (real-folio fixtures
     land in Phase 03.1 W4).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from lxml import etree

from masoretic_eval.page_xml import PAGE_NS, parse_page_xml


def _minimal_page_xml(lines: list[tuple[int, str, str, float | None]]) -> bytes:
    """Build a minimal valid PAGE-XML 2019 tree with the given lines.

    Each tuple is ``(line_num, verse_ref, text, conf)``; pass ``conf=None``
    to omit the @conf attribute.
    """
    nsmap = {None: PAGE_NS}
    pcgts = etree.Element(f"{{{PAGE_NS}}}PcGts", nsmap=nsmap)
    page = etree.SubElement(
        pcgts,
        f"{{{PAGE_NS}}}Page",
        imageFilename="BIB_LENCDX_F118B.jpg",
        imageWidth="1200",
        imageHeight="1800",
    )
    region = etree.SubElement(page, f"{{{PAGE_NS}}}TextRegion", id="r1")
    etree.SubElement(region, f"{{{PAGE_NS}}}Coords", points="0,0 0,0")
    for line_num, verse_ref, text, conf in lines:
        tl = etree.SubElement(
            region,
            f"{{{PAGE_NS}}}TextLine",
            id=f"line_{line_num}",
            custom=f"verse_ref:{verse_ref}",
        )
        etree.SubElement(tl, f"{{{PAGE_NS}}}Coords", points="0,0 0,0")
        te_attrs = {"index": "0"}
        if conf is not None:
            te_attrs["conf"] = f"{conf:.4f}"
        te = etree.SubElement(tl, f"{{{PAGE_NS}}}TextEquiv", **te_attrs)
        etree.SubElement(te, f"{{{PAGE_NS}}}Unicode").text = text
    return etree.tostring(pcgts, xml_declaration=True, encoding="UTF-8")


# ---------------------------------------------------------------------------
# 1. Shape
# ---------------------------------------------------------------------------


def test_parse_page_xml_shape(tmp_path: Path) -> None:
    xml_bytes = _minimal_page_xml(
        [
            (1, "Deut.6.4", "שְׁמַע יִשְׂרָאֵל", 0.95),
            (2, "Deut.6.5", "וְאָהַבְתָּ", 0.87),
        ]
    )
    p = tmp_path / "F118B.xml"
    p.write_bytes(xml_bytes)
    lines = parse_page_xml(p)
    assert len(lines) == 2
    assert lines[0].line_num == 1
    assert lines[0].verse_ref == "Deut.6.4"
    assert lines[0].text == "שְׁמַע יִשְׂרָאֵל"
    assert lines[0].conf == pytest.approx(0.95)
    assert lines[1].verse_ref == "Deut.6.5"


# ---------------------------------------------------------------------------
# 2. Pitfall 2 byte preservation (CGJ)
# ---------------------------------------------------------------------------


def test_parse_preserves_bytes(tmp_path: Path) -> None:
    """Pitfall 2: text bytes round-trip through lxml unchanged.

    Includes CGJ (U+034F) which has historically been lost to NFC.
    """
    original = "וַיֹּ֜אמֶר͏יְהוָה"  # CGJ between mem-sofit and yod
    xml_bytes = _minimal_page_xml([(1, "Deut.1.19", original, None)])
    p = tmp_path / "cgj.xml"
    p.write_bytes(xml_bytes)
    lines = parse_page_xml(p)
    assert len(lines) == 1
    assert (
        hashlib.sha256(lines[0].text.encode("utf-8")).hexdigest()
        == hashlib.sha256(original.encode("utf-8")).hexdigest()
    )
    # CGJ specifically survived
    assert "͏" in lines[0].text


# ---------------------------------------------------------------------------
# 3. Skip-branch: TextLine missing TextEquiv
# ---------------------------------------------------------------------------


def test_parse_skips_textline_without_textequiv(tmp_path: Path) -> None:
    # Hand-construct XML with one TextLine that has NO TextEquiv child.
    nsmap = {None: PAGE_NS}
    pcgts = etree.Element(f"{{{PAGE_NS}}}PcGts", nsmap=nsmap)
    page = etree.SubElement(
        pcgts,
        f"{{{PAGE_NS}}}Page",
        imageFilename="x.jpg",
        imageWidth="1",
        imageHeight="1",
    )
    region = etree.SubElement(page, f"{{{PAGE_NS}}}TextRegion", id="r1")
    etree.SubElement(region, f"{{{PAGE_NS}}}Coords", points="0,0 0,0")
    # TextLine WITH TextEquiv (will be parsed)
    tl1 = etree.SubElement(
        region,
        f"{{{PAGE_NS}}}TextLine",
        id="line_1",
        custom="verse_ref:Deut.1.1",
    )
    etree.SubElement(tl1, f"{{{PAGE_NS}}}Coords", points="0,0 0,0")
    te1 = etree.SubElement(tl1, f"{{{PAGE_NS}}}TextEquiv", index="0")
    etree.SubElement(te1, f"{{{PAGE_NS}}}Unicode").text = "א"
    # TextLine WITHOUT TextEquiv (will be skipped)
    tl2 = etree.SubElement(
        region,
        f"{{{PAGE_NS}}}TextLine",
        id="line_2",
        custom="verse_ref:Deut.1.2",
    )
    etree.SubElement(tl2, f"{{{PAGE_NS}}}Coords", points="0,0 0,0")
    p = tmp_path / "skip.xml"
    p.write_bytes(etree.tostring(pcgts, xml_declaration=True, encoding="UTF-8"))
    lines = parse_page_xml(p)
    assert len(lines) == 1
    assert lines[0].line_num == 1


# ---------------------------------------------------------------------------
# 4. Missing-conf branch
# ---------------------------------------------------------------------------


def test_parse_handles_missing_conf_attr(tmp_path: Path) -> None:
    xml_bytes = _minimal_page_xml([(1, "Deut.1.1", "א", None)])
    p = tmp_path / "noconf.xml"
    p.write_bytes(xml_bytes)
    lines = parse_page_xml(p)
    assert lines[0].conf is None


# ---------------------------------------------------------------------------
# 5. Synthetic Devarim-Shema golden (4 packed edge cases)
# ---------------------------------------------------------------------------


def test_parse_synthetic_devarim_shema_golden() -> None:
    """Parser correctness, not GT validation. Asserts parse_page_xml
    handles four packed edge cases on a hand-authored PAGE-XML fixture
    that mirrors eScriptorium nightly-export structure: empty TextEquiv,
    non-integer @id sort-first, multi-region recursive descent, and
    Hebrew-diacritics Unicode-clean roundtrip (Pitfall 2)."""
    fixture = Path(__file__).parent / "fixtures" / "synthetic_devarim_shema.page.xml"
    records = parse_page_xml(fixture)

    # Total count in the spec'd range (5-10 TextLines authored).
    assert 5 <= len(records) <= 10, f"unexpected line count: {len(records)}"

    # Edge case (b''): non-integer @id ("line_xyz") -> line_num=0 via try/except,
    # AND sorts first in output (pins both the ValueError fallback AND the
    # subsequent lines.sort behavior — if try/except regressed to raise,
    # records[] would be missing this entry; if sort regressed, line_num=0
    # would no longer be at index 0).
    assert records[0].line_num == 0, (
        f"non-integer-@id line should sort first with line_num=0; "
        f"got records[0].line_num={records[0].line_num}"
    )
    assert records[0].verse_ref == "Deut.6.4_pre", (
        f"records[0] should be the line with id='line_xyz'; got verse_ref={records[0].verse_ref!r}"
    )

    # Edge case (a): empty <TextEquiv> (no <Unicode> child) -> text=""
    deut_6_5 = next((r for r in records if r.verse_ref == "Deut.6.5"), None)
    assert deut_6_5 is not None, "Deut.6.5 line missing from fixture parse"
    assert deut_6_5.text == "", f"empty TextEquiv should produce text=''; got {deut_6_5.text!r}"

    # Edge case (c): multi-region — Deut.6.7 lives in region_2; recursive-descent
    # path must reach it.
    deut_6_7 = next((r for r in records if r.verse_ref == "Deut.6.7"), None)
    assert deut_6_7 is not None, (
        "Deut.6.7 line (in region_2) missing — recursive-descent .//p:TextLine "
        "is failing to traverse multi-region documents"
    )
    assert "וְשִׁנַּנְתָּ" in deut_6_7.text, f"Deut.6.7 text content unexpected: {deut_6_7.text!r}"

    # Edge case (d): diacritics roundtrip — Deut.6.4 carries the canonical
    # Shema text with cantillation + nikkud; assert the bytes survived parse
    # via sha256 equality with the source text.
    deut_6_4 = next((r for r in records if r.verse_ref == "Deut.6.4"), None)
    assert deut_6_4 is not None, "Deut.6.4 line missing from fixture parse"
    expected = "שְׁמַ֥ע יִשְׂרָאֵ֖ל יְהוָ֣ה אֱלֹהֵ֑ינוּ יְהוָ֖ה ׀ אֶחָֽד׃"
    assert (
        hashlib.sha256(deut_6_4.text.encode("utf-8")).hexdigest()
        == hashlib.sha256(expected.encode("utf-8")).hexdigest()
    ), (
        f"Deut.6.4 diacritics roundtrip FAILED — Pitfall 2 violation. "
        f"got bytes: {deut_6_4.text.encode('utf-8')!r}"
    )

    # Type invariant: all texts are str (never None).
    for r in records:
        assert isinstance(r.text, str), f"line_num={r.line_num} text not str"
