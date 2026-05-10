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

    NFC is applied first (meta-marks schema v0.1 §"Normalization", tracked
    follow-up §1) to canonicalize combining-mark order before the NFD pass.
    U+05C4/U+05C5 share CCC values with trop accents; without NFC, two
    canonical-equivalent strings score as character-level mismatches.
    """
    # NFC mandate — meta-marks schema v0.1 §"Normalization": canonicalize
    # combining-mark order before tier comparison (scorer-side requirement).
    text = unicodedata.normalize("NFC", text)
    return strip_cgj(unicodedata.normalize("NFD", text))
