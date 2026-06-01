"""Normalization: UXLC LC-order → NFD, composition exclusions, CGJ stripping."""

from __future__ import annotations

import unicodedata

CGJ = "͏"  # Combining Grapheme Joiner


def strip_cgj(text: str) -> str:
    """Remove all Combining Grapheme Joiner codepoints."""
    return text.replace(CGJ, "")


def normalize_for_scoring(text: str) -> str:
    """Canonical scoring-side normalization.

    Transforms UXLC byte-for-byte input (which uses custom LC mark order,
    neither NFC nor NFD) into NFD with CGJ stripped. NFD handles shin/sin
    presentation forms (U+FB2A–FB2D) as composition exclusions that decompose
    into base shin (U+05E9) + combining dagesh / sin-dot / shin-dot.

    CGJ (U+034F) is stripped **first**, before the NFC/NFD passes. CGJ has
    canonical combining class 0, so while present it blocks canonical
    reordering of the combining marks around it. UXLC freezes meteg-vs-vowel
    rendering order with CGJ (e.g. Deut 32:50 כַּאֲשֶׁר: kaf·dagesh·meteg·CGJ·patah).
    The benchmark scores mark *presence* per cluster, not byte-order, so a
    reading authored with CGJ and the same reading authored without it must
    normalize identically. Stripping CGJ after normalizing would leave the
    guarded marks in their pre-canonical order, scoring a false CER mismatch
    (meta-marks schema v0.1 §"Normalization", tracked follow-up §1).

    NFC then NFD canonicalize combining-mark order before tier comparison.
    U+05C4/U+05C5 share CCC values with trop accents; without canonicalization
    two canonical-equivalent strings score as character-level mismatches.
    """
    # Strip CGJ first so the marks it guards can canonically reorder.
    text = strip_cgj(text)
    text = unicodedata.normalize("NFC", text)
    return unicodedata.normalize("NFD", text)
