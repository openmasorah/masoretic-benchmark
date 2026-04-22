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
    """
    return strip_cgj(unicodedata.normalize("NFD", text))
