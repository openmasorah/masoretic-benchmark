"""Tests for baselines._gt_adapter.

Synthetic tests pin the tier-1 codepoint filter (Hebrew letters + space +
maqaf only). Golden test pins the executor-generated projection of the
hand-authored synthetic Devarim-Shema PAGE-XML fixture (committed by
Plan 03.1-01 W0 -- per Plan 03.1-01 amendment d6cc9f4, the W0 fixture
is synthetic, NOT a real IAA folio; real-folio fixtures land in W4
plan 03.1-05 per the Phase 03.1 execution gate). The grep-style
single-source-of-truth invariant pins A-04: zero alternate parse_page_xml
definitions in baselines/.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from baselines._gt_adapter import load_tier1_per_line
from lxml import etree

# Re-use the synthetic XML helper pattern from tests/test_page_xml.py
# (Plan 03.1-01 W0 Task 2). Inlined here so this baselines test module
# stays self-contained (no cross-module fixture import).
PAGE_NS = "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"


def _minimal_page_xml(lines: list[tuple[int, str, str, float | None]]) -> bytes:
    nsmap = {None: PAGE_NS}
    pcgts = etree.Element(f"{{{PAGE_NS}}}PcGts", nsmap=nsmap)
    page = etree.SubElement(
        pcgts,
        f"{{{PAGE_NS}}}Page",
        imageFilename="x.jpg",
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


def test_load_tier1_per_line_strips_nikkud_and_trop(tmp_path: Path) -> None:
    xml_bytes = _minimal_page_xml([(1, "Deut.6.4", "שְׁמַ֖ע יִשְׂרָאֵ֑ל", 0.95)])
    p = tmp_path / "f.xml"
    p.write_bytes(xml_bytes)
    out = load_tier1_per_line("test_folio", p)
    assert out == ["שמע ישראל"]


def test_load_tier1_per_line_preserves_maqaf(tmp_path: Path) -> None:
    # Maqaf U+05BE is in the keep-set (Hebrew word/phrase separator).
    xml_bytes = _minimal_page_xml([(1, "Deut.1.1", "אֲבִי־הוּא", None)])
    p = tmp_path / "f.xml"
    p.write_bytes(xml_bytes)
    out = load_tier1_per_line("test_folio", p)
    assert out == ["אבי־הוא"]


def test_load_tier1_per_line_drops_punctuation(tmp_path: Path) -> None:
    # Sof pasuq U+05C3 is outside the keep-range; must be dropped.
    xml_bytes = _minimal_page_xml([(1, "Deut.6.4", "שְׁמַע׃", None)])
    p = tmp_path / "f.xml"
    p.write_bytes(xml_bytes)
    out = load_tier1_per_line("test_folio", p)
    assert out == ["שמע"]


def test_load_tier1_per_line_returns_line_order(tmp_path: Path) -> None:
    # Lines submitted out of order; parser sorts by line_num so projection
    # is also in line_num order.
    xml_bytes = _minimal_page_xml(
        [
            (2, "Deut.6.5", "ב", None),
            (1, "Deut.6.4", "א", None),
            (3, "Deut.6.6", "ג", None),
        ]
    )
    p = tmp_path / "f.xml"
    p.write_bytes(xml_bytes)
    out = load_tier1_per_line("test_folio", p)
    assert out == ["א", "ב", "ג"]


def test_load_tier1_per_line_synthetic_devarim_shema_golden() -> None:
    """A-04 + D-14: golden against the W0 hand-authored synthetic
    Devarim-Shema PAGE-XML.

    Per Plan 03.1-01 amendment d6cc9f4, the W0 fixture is synthetic
    (NOT a real IAA folio); real-folio goldens land in W4 plan 03.1-05
    per the Phase 03.1 execution gate. The golden JSON shipped here is
    the executor's load_tier1_per_line() output against the synthetic
    fixture; Yosef's hand-verification of a real-folio golden happens
    later, in plan 03.1-05's folio-1 [YOSEF-REVIEW] PR.
    """
    page_xml = Path(__file__).parent / "fixtures" / "synthetic_devarim_shema.page.xml"
    golden = Path(__file__).parent / "fixtures" / "synthetic_devarim_shema.gt_adapter_golden.json"
    out = load_tier1_per_line("synthetic_devarim_shema", page_xml)
    expected = json.loads(golden.read_text(encoding="utf-8"))
    # Shape-level invariants:
    assert isinstance(out, list)
    assert all(isinstance(s, str) for s in out)
    assert len(out) == len(expected["lines"])
    # Tightened-equality against committed golden:
    assert out == expected["lines"]


@pytest.mark.parametrize(
    "fid",
    [
        "leningrad_devarim_F118B_fixture",
        "leningrad_devarim_F119A_fixture",
        "leningrad_devarim_F119B_fixture",
        "leningrad_devarim_F120A_fixture",
    ],
)
def test_load_tier1_per_line_iaa_folio_provisional_golden(fid: str) -> None:
    """Phase 03.2 R4 provisional golden -- UXLC-derived, NO Yosef sign-off yet.

    The 4 IAA folios (last 4 sides of Leningrad Devarim, Ha'azinu through
    end of Torah, per Yosef written confirmation 2026-04-30) carry
    provisional gt_adapter goldens generated by feeding UXLC verse ranges
    through gt_infra.uxlc_import.build_baseline_page_xml and then through
    baselines._gt_adapter.load_tier1_per_line. Yosef hand-tightens during
    Plan 03.1-05's [YOSEF-REVIEW] PR (folio #1 = F118B); folios 2-4 in
    their respective downstream first-folio plans.

    The test passes both before and after Yosef edits the goldens --
    load_tier1_per_line is deterministic over its PAGE-XML input. If
    Yosef edits both the PAGE-XML AND the golden together (e.g. corrects
    a verse-range break or a tier-1 strip edge case), the test
    re-asserts against the corrected pair.

    The 'provisional': true field in each golden makes the status
    structural -- when Yosef is satisfied, that field flips to false
    (or the field is removed) and a corresponding manifest_changelog
    row records the freeze.
    """
    page_xml = Path(__file__).parent / "fixtures" / f"iaa_folio_{fid}.page.xml"
    golden_path = Path(__file__).parent / "fixtures" / f"iaa_folio_{fid}.gt_adapter_golden.json"
    assert page_xml.exists(), f"PAGE-XML fixture missing for {fid}"
    assert golden_path.exists(), f"golden fixture missing for {fid}"

    out = load_tier1_per_line(fid, page_xml)
    expected = json.loads(golden_path.read_text(encoding="utf-8"))

    # Provisional contract per Phase 03.2 R4.
    assert expected.get("provisional") is True, (
        f"Phase 03.2 R4 -- golden for {fid} must carry 'provisional': true; "
        "remove this assertion only when Yosef tightens during [YOSEF-REVIEW]."
    )
    assert expected["folio_id"] == fid

    # Shape + content equality.
    assert isinstance(out, list)
    assert all(isinstance(s, str) for s in out)
    assert len(out) == len(expected["lines"])
    assert out == expected["lines"]


def test_no_alt_parser_in_baselines() -> None:
    """A-04 single-source-of-truth invariant: zero alternate
    parse_page_xml definitions in baselines/. Adapter MUST delegate
    to masoretic_eval.page_xml.parse_page_xml.
    """
    baselines_root = Path(__file__).parent.parent / "src" / "baselines"
    result = subprocess.run(
        ["grep", "-rn", "def parse_page_xml", str(baselines_root)],
        capture_output=True,
        text=True,
    )
    # Return code 1 means grep found nothing (the success case).
    assert result.returncode == 1, f"alternate parse_page_xml found in baselines/:\n{result.stdout}"
