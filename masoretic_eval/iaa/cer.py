"""Per-tier CER for IAA (annotator A vs annotator B, per verse, aggregated by folio).

The tier strip rules mirror the existing scorer:

* **Tier 1**: consonants + space + maqaf only (`tier1_consonantal._strip_to_consonants`).
* **Tier 2**: `strip_for_tier2` (trop + meteg/rafe/paseq/sof-pasuq/nun-hafukha stripped).
* **Tier 3**: full text (everything except editor tokens — those are already
  stripped during `split_chunks`).

A-side text is treated as the reference, B-side as the comparison. CER is the
cluster-aligned codepoint CER from `masoretic_eval.metrics.cer` (the canonical
scoring path for this repo).
"""

from __future__ import annotations

import re

from masoretic_eval.metrics.cer import cluster_aligned_cer
from masoretic_eval.normalize import normalize_for_scoring
from masoretic_eval.strip import strip_for_tier2

_MULTISPACE = re.compile(r"  +")


def _strip_for_tier1(text: str) -> str:
    """Keep only consonants, space, and maqaf. Mirrors tier1_consonantal."""

    def keep(c: str) -> bool:
        cp = ord(c)
        if 0x05D0 <= cp <= 0x05EA:
            return True
        if c in (" ", "־"):
            return True
        return False

    kept = "".join(c for c in text if keep(c))
    return _MULTISPACE.sub(" ", kept).strip()


def _strip_for_tier3(text: str) -> str:
    """Tier 3 retains everything (the strip equivalent is `normalize_for_scoring`).

    Defined as its own function so the per-tier strip table reads consistently.
    """
    return text


_STRIPPERS = {1: _strip_for_tier1, 2: strip_for_tier2, 3: _strip_for_tier3}


def per_verse_cer(a_chunk: str, b_chunk: str, *, tier: int) -> float:
    """CER between annotator-A and annotator-B raw text chunks at a given tier.

    Both chunks pass through `normalize_for_scoring` (CGJ-strip + NFC→NFD)
    before tier-specific stripping. CER comes out of `cluster_aligned_cer` —
    the canonical scoring path.
    """
    if tier not in _STRIPPERS:
        raise ValueError(f"unsupported tier for IAA CER: {tier}")
    strip = _STRIPPERS[tier]
    a_view = strip(normalize_for_scoring(a_chunk))
    b_view = strip(normalize_for_scoring(b_chunk))
    return cluster_aligned_cer(a_view, b_view).cer
