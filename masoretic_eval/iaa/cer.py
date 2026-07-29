"""Per-tier CER for IAA (annotator A vs annotator B, per verse, aggregated by folio).

The tier strip rules mirror the existing scorer:

* **Tier 1**: consonants + space + maqaf only (`tier1_consonantal._strip_to_consonants`).
* **Tier 2**: `strip_for_tier2` (trop + meteg/rafe/paseq/sof-pasuq/nun-hafukha stripped).
* **Tier 3**: full text, minus editor tokens (stripped here — see below).

A-side text is treated as the reference, B-side as the comparison. CER is the
cluster-aligned codepoint CER from `masoretic_eval.metrics.cer` (the canonical
scoring path for this repo).

Editor tokens
-------------
This module used to state that editor tokens "are already stripped during
``split_chunks``". That was **false for ``<DR>``** (the double-rafe token), and
the error reached published numbers.

``split_chunks`` removes only ``PASSTHRU_TAGS``; ``<DR>`` is deliberately
excluded from that list so ``extract_positional`` can emit a tier-4
``double_rafe`` record from it. But nothing removed it afterwards, so the
literal four ASCII characters ``<``, ``D``, ``R``, ``>`` entered the tier-2 and
tier-3 character streams and were scored as text. Because the sides carry
different token counts (A=25, B=56, consensus=27 on the Devarim 4-folio set),
every excess token scored as four spurious edits.

This was self-contradictory as well as wrong: ``strip.py`` puts U+05BF (rafe)
in ``_TIER2_EXTRA_STRIP`` precisely "so it is not double-counted across tiers",
so the *single* rafe was stripped at tier 2 while the *double* rafe, written in
ASCII, was not.

Editor tokens are therefore stripped here, in the CER path, at every tier.
Tier-4 extraction (``iaa.parse.extract_positional``) and the BL-05 rafe
baseline (``metrics.rafe_rule``) still consume the raw chunk and are
unaffected — ``<DR>`` consumes no consonant ordinal, so tier-4 F1 and the
UXLC-frame reprojection are untouched by this change.
"""

from __future__ import annotations

import re

from masoretic_eval.iaa.parse import _EDITOR_TOKEN_RE
from masoretic_eval.metrics.cer import cluster_aligned_cer
from masoretic_eval.normalize import normalize_for_scoring
from masoretic_eval.strip import strip_for_tier2

_MULTISPACE = re.compile(r"  +")


def strip_editor_tokens(text: str) -> str:
    """Remove ``<UPPER>`` editor tokens (``<DR>``, ``<MF>``, …) from a chunk.

    Removed rather than replaced with a space: ``<DR>`` sits immediately
    adjacent to the consonant it annotates, so substituting a space would
    split a word. ``split_chunks`` has already space-substituted the
    boundary-safe ``PASSTHRU_TAGS`` by the time a chunk exists, so no
    word-gluing hazard remains here.
    """
    return _EDITOR_TOKEN_RE.sub("", text)


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


def tier_view(chunk: str, *, tier: int) -> str:
    """The scoring view of ``chunk`` at ``tier``: the ONE place this is defined.

    ``strip_editor_tokens`` -> ``normalize_for_scoring`` -> tier strip.

    Every consumer that scores a projection chunk must go through this, not
    through ``_STRIPPERS`` directly. ``scripts/generate_iaa_report.py`` used to
    inline this sequence and so silently missed the editor-token strip when it
    was added — the reason this helper exists rather than the steps being
    repeated at each call site.
    """
    if tier not in _STRIPPERS:
        raise ValueError(f"unsupported tier for IAA CER: {tier}")
    return _STRIPPERS[tier](normalize_for_scoring(strip_editor_tokens(chunk)))


def per_verse_cer(a_chunk: str, b_chunk: str, *, tier: int) -> float:
    """CER between annotator-A and annotator-B raw text chunks at a given tier.

    Both chunks have editor tokens removed (see the module docstring), then
    pass through `normalize_for_scoring` (CGJ-strip + NFC→NFD) before
    tier-specific stripping. CER comes out of `cluster_aligned_cer` — the
    canonical scoring path.
    """
    return cluster_aligned_cer(tier_view(a_chunk, tier=tier), tier_view(b_chunk, tier=tier)).cer
