import logging
from pathlib import Path

from masoretic_eval.uxlc_loader import (
    MetaMarkRecord,
    load_tier_strings,
    load_uxlc,
)

FIXTURE = Path(__file__).parent / "fixtures" / "uxlc_deut_6.xml"


def test_load_uxlc_returns_verses():
    doc = load_uxlc(FIXTURE)
    assert "Deut.6.4" in doc.verses
    assert "Deut.6.5" in doc.verses


def test_tier1_strips_nikkud_and_trop():
    strings = load_tier_strings(FIXTURE, tier=1)
    # Tier 1 = consonants only
    text = strings["Deut.6.4"]
    assert all("א" <= c <= "ת" or c == " " or c == "־" for c in text), (
        f"tier 1 contained non-consonantal codepoint: {text!r}"
    )


def test_tier1_deut_6_4_exact_string():
    """Lock in consonant-only extraction for the Shema verse.

    Guards against regressions like paseq double-spacing, large-letter
    dropping, or nikkud leaking through the strip.
    """
    strings = load_tier_strings(FIXTURE, tier=1)
    # Deut 6:4 Shema: שמע ישראל יהוה אלהינו יהוה אחד
    # Expected: ayin from <s> child included; paseq and sof pasuq stripped;
    # no double-space between יהוה and אחד after paseq strip.
    assert strings["Deut.6.4"] == "שמע ישראל יהוה אלהינו יהוה אחד"


def test_tier2_includes_nikkud_strips_trop():
    strings = load_tier_strings(FIXTURE, tier=2)
    text = strings["Deut.6.4"]
    # qamatz (U+05B8) and patach (U+05B7) are nikkud — should be present
    # Trop marks (U+0591–05AF) should be absent
    assert all(not ("֑" <= c <= "֯") for c in text), f"tier 2 contained trop codepoint: {text!r}"


def test_tier3_includes_full():
    strings = load_tier_strings(FIXTURE, tier=3)
    text = strings["Deut.6.4"]
    # Full: consonants + nikkud + trop all present
    # Assert at least one trop mark exists (the fixture has trop)
    assert any("֑" <= c <= "֯" for c in text), "tier 3 should retain trop"


def test_qere_selected_by_default():
    # If the fixture has a k/q word, default selection is qere.
    # For the Deut 6 fixture without k/q, loader default is qere (unchanged).
    doc = load_uxlc(FIXTURE)
    assert doc.qere_ketiv_policy == "qere"


def test_tier4_metamarks_extracted_as_records():
    records = load_tier_strings(FIXTURE, tier=4)
    assert isinstance(records, list)
    assert all(isinstance(r, MetaMarkRecord) for r in records)

    # Deut 6:4 contains 2 large letters (ע in שמע and ד in אחד), each
    # encoded as <x>5</x> inside their respective <w> elements.
    large = [r for r in records if r.type == "large_letter" and r.verse_ref == "Deut.6.4"]
    assert len(large) == 2, f"expected 2 large_letter records in Deut.6.4, got {len(large)}"
    ordinals = sorted(r.ordinal for r in large)
    assert ordinals == [1, 2]

    # Deut 6:3 has a <pe/> paragraph marker (confirmed in fixture).
    pe_records = [r for r in records if r.type == "pe"]
    assert len(pe_records) >= 1, "expected at least one pe record in fixture"
    assert all(r.ordinal >= 1 for r in pe_records)


def test_qere_wins_over_ketiv(tmp_path):
    """When a verse has <k> and <q> siblings, the loader emits qere."""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<Tanach><tanach><book>
  <names><name>Deuteronomy</name></names>
  <c n="1">
    <v n="1"><w>דָּבָר</w><k>כְּתִיב</k><q>קְרֵי</q></v>
  </c>
</book></tanach></Tanach>"""
    path = tmp_path / "kq.xml"
    path.write_text(xml, encoding="utf-8")
    doc = load_uxlc(path)
    assert "קְרֵי" in doc.verses["Deut.1.1"]
    assert "כְּתִיב" not in doc.verses["Deut.1.1"]


def test_word_text_keeps_tail_after_x_element(tmp_path):
    """UXLC places <x> mid-word; the word remainder is the <x> element's tail.

    The tail must not be dropped (real example: the Decalogue תרצח, encoded
    <w>תִּֿרְצָ֖<x>c</x>ח׃</w>, must not truncate to תִּֿרְצָ֖). The <x> code
    character itself is still excluded from the word text.
    """
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<Tanach><tanach><book>
  <names><name>Deuteronomy</name></names>
  <c n="6">
    <v n="3"><w>אב<x>5</x>גד</w></v>
  </c>
</book></tanach></Tanach>"""
    path = tmp_path / "xtail.xml"
    path.write_text(xml, encoding="utf-8")

    doc = load_uxlc(path)
    assert doc.verses["Deut.6.3"] == "אבגד", f"dropped <x> tail: {doc.verses['Deut.6.3']!r}"


def test_ketiv_fallback_when_no_qere(tmp_path, caplog):
    """When <k> has no <q> sibling, the loader falls back to ketiv and warns."""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<Tanach><tanach><book>
  <names><name>Deuteronomy</name></names>
  <c n="1">
    <v n="1"><w>דָּבָר</w><k>כְּתִיב</k></v>
  </c>
</book></tanach></Tanach>"""
    path = tmp_path / "k_only.xml"
    path.write_text(xml, encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="masoretic_eval.uxlc_loader"):
        doc = load_uxlc(path)
    assert "כְּתִיב" in doc.verses["Deut.1.1"]
    # At least one warning about ketiv fallback.
    assert any("ketiv" in rec.message.lower() for rec in caplog.records)
