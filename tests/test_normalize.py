import unicodedata

from masoretic_eval.normalize import normalize_for_scoring, strip_cgj
from masoretic_eval.tiers.tier2_nikkud import Tier2Nikkud
from masoretic_eval.tiers.tier3_trop import Tier3Trop


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


# ---------------------------------------------------------------------------
# CGJ ordering: a reading authored WITH the Combining Grapheme Joiner and the
# SAME reading authored WITHOUT it must score CER == 0 for tiers 2 and 3.
#
# CGJ (U+034F, CCC=0) blocks canonical reordering of the marks around it. UXLC
# freezes meteg-vs-vowel *rendering* order with CGJ; the benchmark scores mark
# presence per cluster, not byte-order, so the two orderings are the same
# reading. Stripping CGJ AFTER normalizing leaves the guarded marks
# unreordered and scores a false mismatch — this guards the strip-CGJ-first
# fix. Covers the tier-3 portion of meta_marks_schema.md "Deferred to v0.2 §1"
# (the v0.1 NFC test covered tier-2 only; idempotence is guarded separately by
# test_nfd_is_idempotent). Tier-1 is mark-insensitive (consonants only), so its
# equivalence is trivially satisfied; tier-4 NFC-equivalence stays deferred —
# it needs a meta-mark fixture, not a meteg+vowel cluster.
#
# SCHOLAR NOTE: both real corpus sites — F118B הָרָעָה and F119A כַּאֲשֶׁר
# (Deut 32:50) — freeze meteg-vs-vowel placement only. If a future site ever
# intends CGJ-frozen order as a *scored* distinction, the fix must change to
# "require annotators to reproduce CGJ," not strip it.
# ---------------------------------------------------------------------------


def _make_cgj_pair() -> tuple[str, str]:
    """Return (with_cgj, without_cgj) for the real Deut 32:50 site כַּאֲשֶׁר.

    First cluster: kaf · dagesh(U+05BC) · meteg(U+05BD) · CGJ(U+034F) · patah(U+05B7).
    The CGJ-free variant is the same multiset of marks without the joiner.
    Both are the identical reading; only the frozen byte-order differs.
    """
    kaf = "כ"
    dagesh = "ּ"
    meteg = "ֽ"
    cgj = "͏"
    patah = "ַ"
    with_cgj = kaf + dagesh + meteg + cgj + patah
    without_cgj = kaf + dagesh + meteg + patah
    # Sanity: byte-distinct before normalization.
    assert with_cgj.encode("utf-8") != without_cgj.encode("utf-8"), (
        "test setup error: CGJ pair is not byte-distinct"
    )
    return with_cgj, without_cgj


def test_cgj_pair_normalizes_identically():
    """strip-CGJ-first lets the guarded marks canonicalize to the same bytes."""
    with_cgj, without_cgj = _make_cgj_pair()
    assert normalize_for_scoring(with_cgj) == normalize_for_scoring(without_cgj)


def test_tier2_cer_is_zero_for_cgj_equivalent_strings():
    """Tier-2 CER == 0 for a CGJ reading vs its CGJ-free equivalent."""
    with_cgj, without_cgj = _make_cgj_pair()
    result = Tier2Nikkud().score(gt=with_cgj, pred=without_cgj)
    assert result.cer == 0.0, (
        f"Expected tier-2 CER 0.0 for CGJ-equivalent pair; got {result.cer}. "
        "CGJ must be stripped BEFORE NFC/NFD so guarded marks canonicalize."
    )


def test_tier3_cer_is_zero_for_cgj_equivalent_strings():
    """Tier-3 CER == 0 for a CGJ reading vs its CGJ-free equivalent."""
    with_cgj, without_cgj = _make_cgj_pair()
    result = Tier3Trop().score(gt=with_cgj, pred=without_cgj)
    assert result.cer == 0.0, (
        f"Expected tier-3 CER 0.0 for CGJ-equivalent pair; got {result.cer}. "
        "CGJ must be stripped BEFORE NFC/NFD so guarded marks canonicalize."
    )
