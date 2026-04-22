"""Tier 2: CER with nikkud + dagesh + sin/shin dots included.

Strips trop (0591–05AF) AND Hebrew non-letter non-nikkud punctuation
(rafe, paseq, sof pasuq, nun hafukha) to mirror `uxlc_loader.load_tier_strings(tier=2)`.
Sin-dot (05C1) and shin-dot (05C2) are retained per spec.
"""

from __future__ import annotations

import re

from masoretic_eval.metrics.cer import cluster_aligned_cer
from masoretic_eval.normalize import normalize_for_scoring
from masoretic_eval.tiers.base import Tier, TierResult

_TIER2_EXTRA_STRIP = frozenset({0x05BF, 0x05C0, 0x05C3, 0x05C6})

# Collapse runs of 2+ spaces produced when stripped codepoints were adjacent to
# spaces (e.g. paseq U+05C0 in "word ׀ word").  Mirrors uxlc_loader behavior.
_MULTISPACE = re.compile(r"  +")


def _strip_for_tier2(text: str) -> str:
    """Strip trop + tier-2-extra Hebrew punctuation, then collapse whitespace."""
    out: list[str] = []
    for c in text:
        cp = ord(c)
        if 0x0591 <= cp <= 0x05AF:  # trop (taamim)
            continue
        if cp in _TIER2_EXTRA_STRIP:
            continue
        out.append(c)
    return _MULTISPACE.sub(" ", "".join(out)).strip()


class Tier2Nikkud(Tier):
    tier_number = 2
    name = "nikkud"

    def score(self, gt: str, pred: str) -> TierResult:
        gt_n = _strip_for_tier2(normalize_for_scoring(gt))
        pred_n = _strip_for_tier2(normalize_for_scoring(pred))
        r = cluster_aligned_cer(gt_n, pred_n)
        return TierResult(
            tier=2,
            name="nikkud",
            cer=r.cer,
            edits=r.edits,
            denominator=r.denominator,
        )
