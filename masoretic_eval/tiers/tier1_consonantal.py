"""Tier 1: consonantal CER. Strips nikkud, trop, sin/shin dots, rafe before scoring."""

from __future__ import annotations

import re

from masoretic_eval.metrics.cer import cluster_aligned_cer
from masoretic_eval.normalize import normalize_for_scoring
from masoretic_eval.tiers.base import Tier, TierResult

_MULTISPACE = re.compile(r"  +")


def _strip_to_consonants(text: str) -> str:
    """Keep only codepoints in consonant range + space + maqaf.

    Collapses resulting runs of spaces (e.g., when paseq-adjacent whitespace
    survives stripping) so alignment doesn't see spurious gap edits. Mirrors
    the whitespace hygiene applied by `uxlc_loader.load_tier_strings` and
    `Tier2Nikkud`.
    """
    def keep(c: str) -> bool:
        cp = ord(c)
        if 0x05D0 <= cp <= 0x05EA:  # consonants
            return True
        if c in (" ", "־"):  # space, maqaf
            return True
        return False

    kept = "".join(c for c in text if keep(c))
    return _MULTISPACE.sub(" ", kept).strip()


class Tier1Consonantal(Tier):
    tier_number = 1
    name = "consonantal"

    def score(self, gt: str, pred: str) -> TierResult:
        gt_n = _strip_to_consonants(normalize_for_scoring(gt))
        pred_n = _strip_to_consonants(normalize_for_scoring(pred))
        r = cluster_aligned_cer(gt_n, pred_n)
        return TierResult(
            tier=1,
            name="consonantal",
            cer=r.cer,
            edits=r.edits,
            denominator=r.denominator,
        )
