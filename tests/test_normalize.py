
from masoretic_eval.normalize import normalize_for_scoring, strip_cgj


def test_nfd_produces_decomposed_form():
    # שׁ presentation form (U+FB2A) decomposes to base ש + sin-dot
    composed = "שׁ"
    result = normalize_for_scoring(composed)
    assert result == "שׁ"


def test_nfd_decomposes_shin_with_dagesh():
    # שּׁ (U+FB2C) = shin + dagesh + sin-dot decomposition
    composed = "שּׁ"
    result = normalize_for_scoring(composed)
    # After NFD: base shin + dagesh + shin-dot
    assert "ש" in result
    assert "ּ" in result  # dagesh
    assert "ׁ" in result  # shin-dot


def test_cgj_stripped_during_scoring():
    # CGJ (U+034F) between two graphemes
    text_with_cgj = "א͏ב"  # aleph CGJ bet
    result = normalize_for_scoring(text_with_cgj)
    assert "͏" not in result
    assert result == "אב"


def test_cgj_standalone_strip():
    assert strip_cgj("א͏") == "א"


def test_nfd_is_idempotent():
    text = "בָ"  # bet + qamatz, already NFD
    assert normalize_for_scoring(text) == text


def test_normalize_preserves_consonant_codepoints():
    # NFD must not drop or reorder consonants
    text = "בְרֵאשִית"  # בראשית partially vocalized
    result = normalize_for_scoring(text)
    consonants = [c for c in result if "א" <= c <= "ת"]
    assert consonants == ["ב", "ר", "א", "ש", "י", "ת"]
