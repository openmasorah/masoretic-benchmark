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

    def score(
        self, gt: list[MetaMarkRecord], pred: list[MetaMarkRecord]
    ) -> TierResult:
        gt_exact = {(r.type, r.verse_ref, r.ordinal) for r in gt}
        pred_exact = {(r.type, r.verse_ref, r.ordinal) for r in pred}

        # Build index of GT ordinals per (type, verse_ref) key.
        gt_partial: dict[tuple[str, str], list[int]] = {}
        for r in gt:
            gt_partial.setdefault((r.type, r.verse_ref), []).append(r.ordinal)

        tp_exact = len(gt_exact & pred_exact)

        # Partial matches: pred records that share (type, verse_ref) with GT
        # but have an ordinal not in the exact intersection.
        # One partial credit per (type, verse_ref) remainder — no double-counting.
        pred_remaining = pred_exact - gt_exact
        tp_partial = 0
        matched_pred_keys: set[tuple[str, str, int]] = set()
        consumed_gt_partial: set[tuple[str, str]] = set()
        for key in pred_remaining:
            t, v, _o = key
            tv = (t, v)
            if tv in gt_partial and gt_partial[tv] and tv not in consumed_gt_partial:
                tp_partial += 1
                matched_pred_keys.add(key)
                consumed_gt_partial.add(tv)

        # FP = pred records not matched exactly and not partial-credited.
        fp = len(pred_remaining - matched_pred_keys)

        # FN = GT records not matched exactly, minus those represented by a partial.
        gt_unmatched_exact_count = len(gt_exact - pred_exact)
        fn_full = gt_unmatched_exact_count - tp_partial

        precision_tp = tp_exact + PARTIAL_CREDIT * tp_partial
        recall_tp = tp_exact + PARTIAL_CREDIT * tp_partial
        pred_total = len(pred_exact)
        gt_total = len(gt_exact)

        precision = (
            precision_tp / pred_total
            if pred_total
            else (1.0 if gt_total == 0 else 0.0)
        )
        recall = (
            recall_tp / gt_total
            if gt_total
            else (1.0 if pred_total == 0 else 0.0)
        )
        f1 = (
            (2 * precision * recall / (precision + recall))
            if (precision + recall)
            else 0.0
        )

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
