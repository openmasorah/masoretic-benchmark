"""Tier 2: CER with nikkud + dagesh + sin/shin dots included.

Strips trop (0591–05AF) AND Hebrew non-letter non-nikkud punctuation
(rafe, paseq, sof pasuq, nun hafukha) to mirror `uxlc_loader.load_tier_strings(tier=2)`.
Sin-dot (05C1) and shin-dot (05C2) are retained per spec.
"""

from __future__ import annotations

from masoretic_eval.metrics.cer import cluster_aligned_cer
from masoretic_eval.normalize import normalize_for_scoring
from masoretic_eval.strip import strip_for_tier2 as _strip_for_tier2
from masoretic_eval.tiers.base import Tier, TierResult


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
