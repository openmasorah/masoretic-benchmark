"""Serializer for ScoreResult → spec-compliant JSON shape."""

from __future__ import annotations

from typing import Any

from masoretic_eval import __version__
from masoretic_eval.composite import ScoreResult

DEFAULT_CAVEATS = [
    (
        "nakdimon_disagreement_rate is the reproducible canonical signal;"
        " indicative, not ground truth"
    ),
    (
        "dicta_disagreement_rate is a proprietary best-available comparison;"
        " not reproducible due to rotating endpoint + no version header"
    ),
]


def _plain_dict(cm: dict[str, Any]) -> dict[str, Any]:
    """Flatten nested defaultdicts to plain dicts for JSON serialization."""
    return {k: dict(v) for k, v in cm.items()}


def serialize(
    *,
    result: ScoreResult,
    prediction_id: str,
    gt_version: str,
) -> dict[str, Any]:
    t1 = result.tiers["tier1"]
    t2 = result.tiers["tier2"]
    t3 = result.tiers["tier3"]
    t4 = result.tiers["tier4"]

    return {
        "prediction_id": prediction_id,
        "gt_version": gt_version,
        "scorer_version": __version__,
        "normalization": "NFD (scoring) / LC-order (raw GT)",
        "denominator_policy": {
            "tier1": "consonants_only",
            "tier2": "consonants+nikkud",
            "tier3": "full",
        },
        "qere_ketiv_policy": "score_against_qere",
        "tiers": {
            "tier1": {"cer": t1.cer, "edits": t1.edits, "denominator": t1.denominator},
            "tier2": {
                "cer": t2.cer,
                "edits": t2.edits,
                "denominator": t2.denominator,
                "dec": t2.diagnostics.get("dec"),
                "cha": t2.diagnostics.get("cha"),
                "wor": t2.diagnostics.get("wor"),
                "voc": t2.diagnostics.get("voc"),
                "nakdimon_disagreement_rate": t2.diagnostics.get("nakdimon_disagreement_rate"),
                "dicta_disagreement_rate": t2.diagnostics.get("dicta_disagreement_rate"),
            },
            "tier3": {"cer": t3.cer, "edits": t3.edits, "denominator": t3.denominator},
            "tier4": {
                "f1": t4.f1,
                "precision": t4.precision,
                "recall": t4.recall,
                "tp_exact": t4.diagnostics.get("tp_exact"),
                "tp_partial": t4.diagnostics.get("tp_partial"),
                "fp": t4.diagnostics.get("fp"),
                "fn": t4.diagnostics.get("fn"),
            },
        },
        "composite": {"cer3": result.composite_cer3},
        "confusion_matrices": {
            k: _plain_dict(v) for k, v in result.confusion_matrices.items()
        },
        "caveats": DEFAULT_CAVEATS,
    }
