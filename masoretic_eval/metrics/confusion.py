"""Per-mark confusion matrices for tier 2 (nikkud)."""

from __future__ import annotations

from collections import Counter, defaultdict

from masoretic_eval.metrics.cer import _cluster_align
from masoretic_eval.normalize import normalize_for_scoring
from masoretic_eval.segment import segment_clusters
from masoretic_eval.strip import strip_for_tier2

# Tier-2 retained-mark inventory. Must match the tier-2 *score* view
# (strip_for_tier2): rafe U+05BF is stripped there, so it is NOT listed here;
# qamats qatan U+05C7 is retained there, so it IS listed.
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
    0x05C1: "shin_dot",
    0x05C2: "sin_dot",
    0x05C7: "qamats_qatan",
}

_ABSENT = "__absent__"

# Mark class for leftover pairing: marks that are not exact-name matches are
# paired only within the same class (vowel<->vowel, dot<->dot), so a vowel
# substitution is reported as such while a vowel-vs-dagesh count difference is
# reported as omission/insertion rather than a fabricated substitution.
_VOWEL_NAMES = frozenset(
    {
        "shva",
        "hataf_segol",
        "hataf_patach",
        "hataf_qamatz",
        "hiriq",
        "tsere",
        "segol",
        "patach",
        "qamatz",
        "holam",
        "holam_haser",
        "qubuts",
        "qamats_qatan",
    }
)
_DOT_NAMES = frozenset({"shin_dot", "sin_dot"})


def _mark_class(name: str) -> str:
    if name in _VOWEL_NAMES:
        return "vowel"
    if name in _DOT_NAMES:
        return "dot"
    return name  # dagesh, meteg: each its own class


def _mark_names(cluster: str) -> list[str]:
    return [NIKKUD_NAMES[ord(c)] for c in cluster if ord(c) in NIKKUD_NAMES]


def _record_pair(cm: dict[str, dict[str, int]], g_marks: list[str], p_marks: list[str]) -> None:
    """Attribute per-mark errors for one aligned cluster pair.

    1. exact-name matches (multiset intersection) -> mark->mark.
    2. leftovers paired within the same mark class -> substitution gt->pred.
    3. unpaired leftovers -> mark->__absent__ (GT-only) / __absent__->mark (pred-only).

    A cluster with no marks contributes nothing (a bare consonant on both sides
    is not a nikkud observation).
    """
    gc = Counter(g_marks)
    pc = Counter(p_marks)
    for name, cnt in (gc & pc).items():
        cm[name][name] += cnt
    g_rem = sorted((gc - pc).elements())
    p_rem = sorted((pc - gc).elements())

    by_class_g: dict[str, list[str]] = defaultdict(list)
    by_class_p: dict[str, list[str]] = defaultdict(list)
    for name in g_rem:
        by_class_g[_mark_class(name)].append(name)
    for name in p_rem:
        by_class_p[_mark_class(name)].append(name)

    for cls in set(by_class_g) | set(by_class_p):
        gs = by_class_g.get(cls, [])
        ps = by_class_p.get(cls, [])
        for i in range(max(len(gs), len(ps))):
            gm = gs[i] if i < len(gs) else _ABSENT
            pm = ps[i] if i < len(ps) else _ABSENT
            cm[gm][pm] += 1


def build_nikkud_confusion(gt: str, pred: str) -> dict[str, dict[str, int]]:
    """Confusion matrix keyed [gt_mark][pred_mark] -> count.

    GT and prediction are reduced to the tier-2 view (strip_for_tier2) so the
    diagnostic matches the tier-2 score, then clusters are aligned with the same
    Needleman-Wunsch alignment the tier CER uses (so a single inserted/deleted
    cluster does not cascade-misalign every later pair). Within each aligned
    pair, nikkud marks are compared as multisets (see _record_pair).

    Inner dicts are defaultdict(int) so callers can query m[gt][pred] for unseen
    combinations and get 0 rather than a KeyError.
    """
    gt_n = strip_for_tier2(normalize_for_scoring(gt))
    pred_n = strip_for_tier2(normalize_for_scoring(pred))
    gt_clusters = list(segment_clusters(gt_n))
    pred_clusters = list(segment_clusters(pred_n))

    cm: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for g, p in _cluster_align(gt_clusters, pred_clusters):
        _record_pair(cm, _mark_names(g or ""), _mark_names(p or ""))
    return cm
