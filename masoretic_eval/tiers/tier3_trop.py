"""Tier 3: full cluster-aligned codepoint CER. All codepoints retained."""

from __future__ import annotations

from masoretic_eval.metrics.cer import cluster_aligned_cer
from masoretic_eval.normalize import normalize_for_scoring
from masoretic_eval.tiers.base import Tier, TierResult


class Tier3Trop(Tier):
    tier_number = 3
    name = "trop"

    def score(self, gt: str, pred: str) -> TierResult:
        gt_n = normalize_for_scoring(gt)
        pred_n = normalize_for_scoring(pred)
        r = cluster_aligned_cer(gt_n, pred_n)
        return TierResult(
            tier=3,
            name="trop",
            cer=r.cer,
            edits=r.edits,
            denominator=r.denominator,
        )
