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


def test_parse_preserves_non_canonical_combining_mark_order(tmp_path: Path) -> None:
    """Pitfall 2: non-canonical combining-mark order survives parse byte-identical.

    A parser that silently NFC-normalised would canonically reorder U+05C4
    (HEBREW MARK UPPER DOT, CCC=230) below U+05B8 (QAMATS, CCC=18) and this
    assertion would fail. This is the regression guard the F118B fixture-roundtrip
    test does NOT provide — that test only checks types and tier-4 defaults.
    """
    import unicodedata

    # א + U+05C4 (HEBREW MARK UPPER DOT, CCC=230) + U+05B8 (QAMATS, CCC=18).
    # NFC reorders by CCC ascending, so canonical form has QAMATS first.
    # \u escapes used to keep the literals byte-explicit; visually-similar
    # combining-mark literals are unsafe to copy/paste in source.
    non_canonical = "\u05d0\u05c4\u05b8"
    canonical = "\u05d0\u05b8\u05c4"
    assert non_canonical != canonical, "test setup invalid \u2014 strings must differ in bytes"
    assert unicodedata.normalize("NFC", non_canonical) == canonical, (
        "test setup invalid \u2014 NFC must reorder these combining marks"
    )

    xml_bytes = _minimal_page_xml([(1, "Deut.1.1", non_canonical, None)])
    p = tmp_path / "non_canonical.xml"
    p.write_bytes(xml_bytes)
    lines = parse_page_xml(p)
    assert len(lines) == 1
    assert lines[0].text == non_canonical, (
        f"Pitfall 2 violation — parser reordered combining marks. "
        f"Expected {non_canonical!r}, got {lines[0].text!r}"
    )
    assert lines[0].text != canonical, "Parser silently produced canonical order — Pitfall 2 broken"


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


# ---------------------------------------------------------------------------
# @custom field extraction (meta-marks schema v0.1, tracked follow-up §2)
# ---------------------------------------------------------------------------


def _page_xml_with_custom(
    lines: list[tuple[int, str, str, float | None]],
) -> bytes:
    """Build minimal PAGE-XML with caller-supplied ``custom`` attributes.

    Each tuple is ``(line_num, custom_attr, text, conf)``.
    """
    nsmap = {None: PAGE_NS}
    pcgts = etree.Element(f"{{{PAGE_NS}}}PcGts", nsmap=nsmap)
    page = etree.SubElement(
        pcgts,
        f"{{{PAGE_NS}}}Page",
        imageFilename="test.jpg",
        imageWidth="1200",
        imageHeight="1800",
    )
    region = etree.SubElement(page, f"{{{PAGE_NS}}}TextRegion", id="r1")
    etree.SubElement(region, f"{{{PAGE_NS}}}Coords", points="0,0 0,0")
    for line_num, custom_attr, text, conf in lines:
        tl = etree.SubElement(
            region,
            f"{{{PAGE_NS}}}TextLine",
            id=f"line_{line_num}",
            custom=custom_attr,
        )
        etree.SubElement(tl, f"{{{PAGE_NS}}}Coords", points="0,0 0,0")
        te_attrs = {"index": "0"}
        if conf is not None:
            te_attrs["conf"] = f"{conf:.4f}"
        te = etree.SubElement(tl, f"{{{PAGE_NS}}}TextEquiv", **te_attrs)
        etree.SubElement(te, f"{{{PAGE_NS}}}Unicode").text = text
    return etree.tostring(pcgts, xml_declaration=True, encoding="UTF-8")


def test_custom_parashah_petuhah(tmp_path: Path) -> None:
    xml_bytes = _page_xml_with_custom([(1, "verse_ref:Deut.32.1; parashah:petuhah", "הַאֲזִ֥ינוּ", 0.9)])
    p = tmp_path / "petuhah.xml"
    p.write_bytes(xml_bytes)
    lines = parse_page_xml(p)
    assert len(lines) == 1
    assert lines[0].parashah == "petuhah"
    assert lines[0].verse_ref == "Deut.32.1"


def test_custom_parashah_setumah(tmp_path: Path) -> None:
    xml_bytes = _page_xml_with_custom([(1, "verse_ref:Deut.6.5; parashah:setumah", "וְאָהַבְתָּ", None)])
    p = tmp_path / "setumah.xml"
    p.write_bytes(xml_bytes)
    lines = parse_page_xml(p)
    assert lines[0].parashah == "setumah"


def test_custom_large_letter_single(tmp_path: Path) -> None:
    xml_bytes = _page_xml_with_custom(
        [(1, "verse_ref:Deut.32.6; letter_size:large@7", "הֲ־ לַיְהוָה", None)]
    )
    p = tmp_path / "large.xml"
    p.write_bytes(xml_bytes)
    lines = parse_page_xml(p)
    assert lines[0].large_letters == (7,)
    assert lines[0].small_letters == ()


def test_custom_large_letter_multi(tmp_path: Path) -> None:
    xml_bytes = _page_xml_with_custom(
        [(1, "verse_ref:Deut.32.6; letter_size:large@5,large@12", "הֲ־ לַיְהוָה", None)]
    )
    p = tmp_path / "large_multi.xml"
    p.write_bytes(xml_bytes)
    lines = parse_page_xml(p)
    assert lines[0].large_letters == (5, 12)


def test_custom_small_letter(tmp_path: Path) -> None:
    xml_bytes = _page_xml_with_custom(
        [(1, "verse_ref:Deut.32.4; letter_size:small@3", "הַצּוּר֙", None)]
    )
    p = tmp_path / "small.xml"
    p.write_bytes(xml_bytes)
    lines = parse_page_xml(p)
    assert lines[0].small_letters == (3,)
    assert lines[0].large_letters == ()


def test_custom_stichographic_column(tmp_path: Path) -> None:
    xml_bytes = _page_xml_with_custom(
        [(1, "verse_ref:Deut.32.2; layout:stichographic_column@1", "יַעֲרֹ֤ף", None)]
    )
    p = tmp_path / "stich.xml"
    p.write_bytes(xml_bytes)
    lines = parse_page_xml(p)
    assert lines[0].stichographic_column == 1


def test_custom_stichographic_column_two(tmp_path: Path) -> None:
    xml_bytes = _page_xml_with_custom(
        [(1, "verse_ref:Deut.32.2; layout:stichographic_column@2", "תִּזַּ֥ל", None)]
    )
    p = tmp_path / "stich2.xml"
    p.write_bytes(xml_bytes)
    lines = parse_page_xml(p)
    assert lines[0].stichographic_column == 2


def test_custom_all_fields_combined(tmp_path: Path) -> None:
    """All three @custom field types on one TextLine parse correctly together."""
    custom = (
        "verse_ref:Deut.32.6; "
        "parashah:petuhah; "
        "letter_size:large@5,large@12; "
        "layout:stichographic_column@1"
    )
    xml_bytes = _page_xml_with_custom([(1, custom, "הֲ לַיְהוָה", None)])
    p = tmp_path / "combined.xml"
    p.write_bytes(xml_bytes)
    lines = parse_page_xml(p)
    assert len(lines) == 1
    r = lines[0]
    assert r.verse_ref == "Deut.32.6"
    assert r.parashah == "petuhah"
    assert r.large_letters == (5, 12)
    assert r.small_letters == ()
    assert r.stichographic_column == 1


def test_custom_no_custom_tokens_gives_defaults(tmp_path: Path) -> None:
    """TextLine with only verse_ref → all new fields are default (None/empty)."""
    xml_bytes = _page_xml_with_custom([(1, "verse_ref:Deut.1.1", "א", None)])
    p = tmp_path / "no_custom.xml"
    p.write_bytes(xml_bytes)
    lines = parse_page_xml(p)
    assert lines[0].parashah is None
    assert lines[0].large_letters == ()
    assert lines[0].small_letters == ()
    assert lines[0].stichographic_column is None


def test_custom_malformed_parashah_raises(tmp_path: Path) -> None:
    import pytest

    from masoretic_eval.page_xml import _parse_custom

    with pytest.raises(ValueError, match="parashah"):
        _parse_custom("parashah:open", "line_99")


def test_custom_malformed_letter_size_raises(tmp_path: Path) -> None:
    import pytest

    from masoretic_eval.page_xml import _parse_custom

    with pytest.raises(ValueError, match="letter_size"):
        _parse_custom("letter_size:huge@5", "line_99")


def test_custom_malformed_stichographic_column_raises(tmp_path: Path) -> None:
    import pytest

    from masoretic_eval.page_xml import _parse_custom

    with pytest.raises(ValueError, match="stichographic_column"):
        _parse_custom("layout:stichographic_column@3", "line_99")


def test_custom_unknown_top_level_token_raises() -> None:
    """Strict-everywhere policy: unknown top-level keys raise ValueError.

    Annotator typos like ``parasha:petuhah`` (missing 'h') must surface
    immediately rather than being silent-skipped through to scoring.
    """
    import pytest

    from masoretic_eval.page_xml import _parse_custom

    with pytest.raises(ValueError, match="unrecognised top-level key"):
        _parse_custom("parasha:petuhah", "line_99")

    with pytest.raises(ValueError, match="unrecognised top-level key"):
        _parse_custom("verse_ref:Deut.1.1; bogus_key:value", "line_99")


def test_f118b_fixture_roundtrip_no_regression() -> None:
    """Smoke test on the real F118B fixture: parses without error, tier-4 fields default.

    NOT a byte-faithfulness proof — that lives in:
      - test_parse_preserves_bytes (CGJ regression guard)
      - test_parse_preserves_non_canonical_combining_mark_order (Pitfall 2 guard)

    This test only confirms (a) the F118B fixture remains parseable,
    (b) types are correct on every record, and (c) the new tier-4 fields
    default to their empty values for a GT export that contains only
    ``verse_ref`` tokens.

    Skipped if the fixture file is not accessible (operator-local sibling repo).
    The path is supplied via the MASORETIC_F118B_FIXTURE environment variable so
    the source file embeds no operator-local path or private-codename literal
    (the private-path scanner rejects both as leaks).
    """
    import os

    import pytest

    fixture_env = os.environ.get("MASORETIC_F118B_FIXTURE")
    if not fixture_env:
        pytest.skip(
            "F118B fixture path not set; export MASORETIC_F118B_FIXTURE to the "
            "operator-local sibling-repo PAGE-XML export to run this smoke test"
        )
    fixture = Path(fixture_env)
    if not fixture.exists():
        pytest.skip("F118B fixture not accessible from this environment")

    records = parse_page_xml(fixture)
    assert len(records) > 0, "F118B fixture parsed zero lines — check file path"

    for r in records:
        assert isinstance(r.verse_ref, str), f"line {r.line_num}: verse_ref is not str"
        assert isinstance(r.text, str), f"line {r.line_num}: text is not str"
        # New fields must default safely — none of the existing F118B GT has @custom tokens
        # beyond verse_ref, so all tier-4 fields should be at their defaults.
        assert r.parashah is None, f"line {r.line_num}: unexpected parashah {r.parashah!r}"
        assert r.large_letters == (), (
            f"line {r.line_num}: unexpected large_letters {r.large_letters!r}"
        )
        assert r.small_letters == (), (
            f"line {r.line_num}: unexpected small_letters {r.small_letters!r}"
        )
        assert r.stichographic_column is None, (
            f"line {r.line_num}: unexpected stichographic_column {r.stichographic_column!r}"
        )
