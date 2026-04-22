"""Per-mark confusion matrices for tier 2 (nikkud) and tier 3 (trop)."""

from __future__ import annotations

from collections import defaultdict

from masoretic_eval.normalize import normalize_for_scoring
from masoretic_eval.segment import segment_clusters

NIKKUD_NAMES = {
    0x05B0: "shva",
    0x05B1: "hataf_segol",
    0x05B2: "hataf_patach",
    0x05B3: "hataf_qamatz",
    0x05B4: "hiriq",
    0x05B5: "tsere",
    0x05B6: "segol",
    0x05B7: "patach",
    0x05B8: "qamatz",
    0x05B9: "holam",
    0x05BA: "holam_haser",
    0x05BB: "qubuts",
    0x05BC: "dagesh",
    0x05BD: "meteg",
    0x05BF: "rafe",
    0x05C1: "shin_dot",
    0x05C2: "sin_dot",
}

_ABSENT = "__absent__"


def _mark_names(cluster: str) -> list[str]:
    return [NIKKUD_NAMES[ord(c)] for c in cluster if ord(c) in NIKKUD_NAMES]


def build_nikkud_confusion(
    gt: str, pred: str
) -> dict[str, dict[str, int]]:
    """Confusion matrix keyed [gt_mark][pred_mark] -> count.

    For each aligned cluster pair, extract nikkud mark names from both sides.
    An empty mark list on one side = __absent__. Inner dicts are
    defaultdict(int) so callers can query m[gt_mark][pred_mark] for unseen
    combinations and get 0 rather than a KeyError.

    The return type annotation is dict[str, dict[str, int]] but the actual
    runtime type is defaultdict[str, defaultdict[str, int]], which is a
    structural subtype — no cast needed. mypy accepts this under standard
    (non-strict) checking because defaultdict is a subclass of dict.
    """
    gt_n = normalize_for_scoring(gt)
    pred_n = normalize_for_scoring(pred)
    gt_clusters = list(segment_clusters(gt_n))
    pred_clusters = list(segment_clusters(pred_n))
    n = max(len(gt_clusters), len(pred_clusters))

    cm: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for i in range(n):
        g = gt_clusters[i] if i < len(gt_clusters) else ""
        p = pred_clusters[i] if i < len(pred_clusters) else ""
        g_marks = _mark_names(g) or [_ABSENT]
        p_marks = _mark_names(p) or [_ABSENT]
        padded_p = p_marks + [_ABSENT] * max(0, len(g_marks) - len(p_marks))
        for gm, pm in zip(g_marks, padded_p, strict=False):
            cm[gm][pm] += 1
    return cm
