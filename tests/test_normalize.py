import unicodedata

from masoretic_eval.normalize import normalize_for_scoring, strip_cgj
from masoretic_eval.tiers.tier2_nikkud import Tier2Nikkud


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


# ---------------------------------------------------------------------------
# NFC pre-comparison: canonical-equivalent strings score CER == 0
# (meta-marks schema v0.1 §"Normalization", tracked follow-up §1)
# ---------------------------------------------------------------------------


def _make_canonical_pair() -> tuple[str, str]:
    """Return two byte-distinct strings that are canonical equivalents.

    aleph (U+05D0) + qamats (U+05B8, CCC=17) + upper-dot (U+05C4, CCC=230)
    is the canonical order (ascending CCC).

    The non-canonical variant places upper-dot before qamats:
    aleph + upper-dot (CCC=230) + qamats (CCC=17).

    Both represent the same visual glyph; NFC (and NFD) canonicalize to
    ascending CCC, making the two byte-sequences identical after normalization.
    """
    aleph = "א"
    qamats = "ָ"  # CCC=17
    upper_dot = "ׄ"  # CCC=230
    canonical = aleph + qamats + upper_dot  # ascending CCC — already canonical
    non_canonical = aleph + upper_dot + qamats  # descending CCC — non-canonical
    # Sanity: the two raw strings must differ in bytes.
    assert canonical.encode("utf-8") != non_canonical.encode("utf-8"), (
        "test setup error: pair is not byte-distinct before normalization"
    )
    # Sanity: they must be NFC-equivalent.
    assert unicodedata.normalize("NFC", canonical) == unicodedata.normalize("NFC", non_canonical), (
        "test setup error: pair is not canonical-equivalent"
    )
    return canonical, non_canonical


def test_nfc_canonical_equivalent_strings_normalize_identically():
    """normalize_for_scoring produces byte-identical output for canonical equivalents.

    This confirms the NFC pre-pass canonicalizes combining-mark order so that
    tier-2/4 mark extraction sees the same byte sequence regardless of
    keystroke order at annotation time.
    """
    canonical, non_canonical = _make_canonical_pair()
    assert normalize_for_scoring(canonical) == normalize_for_scoring(non_canonical)


def test_tier2_cer_is_zero_for_canonical_equivalent_strings():
    """Tier-2 CER == 0 when gt and pred differ only in combining-mark order.

    Without the NFC fix, two canonical-equivalent strings score as a
    character-level mismatch (fake CER > 0). With NFC, both sides normalize
    to the same bytes before comparison and CER == 0.
    """
    canonical, non_canonical = _make_canonical_pair()
    t = Tier2Nikkud()
    result = t.score(gt=canonical, pred=non_canonical)
    assert result.cer == 0.0, (
        f"Expected CER 0.0 for canonical-equivalent pair; got {result.cer}. "
        "This indicates the NFC pre-comparison fix is not in effect."
    )
