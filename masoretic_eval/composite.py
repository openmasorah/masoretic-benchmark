"""Top-level Scorer: runs 4 tiers + Nakdimon factoring + confusion matrices + composite."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from masoretic_eval.metrics.confusion import build_nikkud_confusion
from masoretic_eval.metrics.nakdimon import nakdimon_factoring
from masoretic_eval.tiers.base import TierResult
from masoretic_eval.tiers.tier1_consonantal import Tier1Consonantal
from masoretic_eval.tiers.tier2_nikkud import Tier2Nikkud
from masoretic_eval.tiers.tier3_trop import Tier3Trop
from masoretic_eval.tiers.tier4_metamarks import Tier4MetaMarks

CER3_WEIGHTS = (0.5, 0.3, 0.2)


def compute_cer3(cer1: float, cer2: float, cer3: float) -> float:
    w1, w2, w3 = CER3_WEIGHTS
    return w1 * cer1 + w2 * cer2 + w3 * cer3


@dataclass
class ScoreResult:
    tiers: dict[str, TierResult] = field(default_factory=dict)
    composite_cer3: float | None = None
    confusion_matrices: dict[str, Any] = field(default_factory=dict)


@dataclass
class Scorer:
    config: str

    @classmethod
    def from_config(cls, config: str) -> Scorer:
        if config != "v0.1":
            raise ValueError(f"unknown config: {config}")
        return cls(config=config)

    def score(
        self,
        *,
        pred: dict[str, Any],
        ground_truth: dict[str, Any],
        nakdimon_disagreement_rate: float | None = None,
        dicta_disagreement_rate: float | None = None,
    ) -> ScoreResult:
        gt_text = ground_truth["text"]
        pred_text = pred["text"]
        gt_meta = ground_truth.get("metamarks", [])
        pred_meta = pred.get("metamarks", [])

        t1 = Tier1Consonantal().score(gt_text, pred_text)
        t2 = Tier2Nikkud().score(gt_text, pred_text)
        t3 = Tier3Trop().score(gt_text, pred_text)
        t4 = Tier4MetaMarks().score(gt_meta, pred_meta)

        # Nakdimon factoring for tier 2 diagnostics.
        nak = nakdimon_factoring(gt_text, pred_text)
        t2.diagnostics["dec"] = nak.dec
        t2.diagnostics["cha"] = nak.cha
        t2.diagnostics["wor"] = nak.wor
        t2.diagnostics["voc"] = nak.voc
        t2.diagnostics["nakdimon_disagreement_rate"] = nakdimon_disagreement_rate
        t2.diagnostics["dicta_disagreement_rate"] = dicta_disagreement_rate

        confusion = {
            "tier2_nikkud": build_nikkud_confusion(gt_text, pred_text),
        }

        composite = compute_cer3(t1.cer or 0.0, t2.cer or 0.0, t3.cer or 0.0)

        return ScoreResult(
            tiers={"tier1": t1, "tier2": t2, "tier3": t3, "tier4": t4},
            composite_cer3=composite,
            confusion_matrices=confusion,
        )
