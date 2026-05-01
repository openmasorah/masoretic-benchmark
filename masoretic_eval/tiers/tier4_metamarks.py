"""Tier 4: F1 over MetaMarkRecord 3-tuples (type, verse_ref, ordinal).

Matching rules (spec Section 4):
- Exact (type, verse_ref, ordinal) match → 1 TP.
- Partial (type, verse_ref) match with wrong ordinal → 1/3 TP.
- GT-only record → FN.
- Pred-only record → FP.
"""

from __future__ import annotations

from masoretic_eval.tiers.base import Tier, TierResult
from masoretic_eval.uxlc_loader import MetaMarkRecord

PARTIAL_CREDIT = 1.0 / 3.0


class Tier4MetaMarks(Tier):
    tier_number = 4
    name = "metamarks"

    def score(self, gt: list[MetaMarkRecord], pred: list[MetaMarkRecord]) -> TierResult:
        gt_exact = {(r.type, r.verse_ref, r.ordinal) for r in gt}
        pred_exact = {(r.type, r.verse_ref, r.ordinal) for r in pred}

        tp_exact = len(gt_exact & pred_exact)

        # Partial matches: pred records that share (type, verse_ref) with GT
        # but have an ordinal not in the exact intersection.
        # Index only unmatched GT records; exact matches have no remaining
        # partial-credit slot for over-produced predictions to consume.
        unmatched_gt_exact = gt_exact - pred_exact
        unmatched_gt_partial: dict[tuple[str, str], list[int]] = {}
        for t, v, o in unmatched_gt_exact:
            unmatched_gt_partial.setdefault((t, v), []).append(o)

        pred_remaining = pred_exact - gt_exact
        tp_partial = 0
        matched_pred_keys: set[tuple[str, str, int]] = set()
        for key in pred_remaining:
            t, v, _o = key
            tv = (t, v)
            unmatched_ordinals = unmatched_gt_partial.get(tv)
            if unmatched_ordinals:
                tp_partial += 1
                matched_pred_keys.add(key)
                unmatched_ordinals.pop()

        # FP = pred records not matched exactly and not partial-credited.
        fp = len(pred_remaining - matched_pred_keys)

        # FN = GT records not matched exactly, minus those represented by a partial.
        fn_full = len(unmatched_gt_exact) - tp_partial

        precision_tp = tp_exact + PARTIAL_CREDIT * tp_partial
        recall_tp = tp_exact + PARTIAL_CREDIT * tp_partial
        pred_total = len(pred_exact)
        gt_total = len(gt_exact)

        precision = precision_tp / pred_total if pred_total else (1.0 if gt_total == 0 else 0.0)
        recall = recall_tp / gt_total if gt_total else (1.0 if pred_total == 0 else 0.0)
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

        return TierResult(
            tier=4,
            name="metamarks",
            f1=f1,
            precision=precision,
            recall=recall,
            diagnostics={
                "tp_exact": tp_exact,
                "tp_partial": tp_partial,
                "fp": fp,
                "fn": fn_full,
            },
        )
