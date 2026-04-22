"""Cluster-aligned codepoint CER.

Algorithm:
1. Segment GT and prediction into UAX #29 grapheme clusters.
2. Align clusters via Needleman–Wunsch with cluster-identity match score
   (matching cluster base consonant = match; else substitution/insert/delete).
3. Within each aligned cluster pair (gt_cluster, pred_cluster), compute
   Levenshtein distance at codepoint level.
4. For each unaligned (inserted/deleted) cluster, contribute edits equal to
   the cluster's codepoint count.
5. Sum edits / total GT codepoints = CER.
6. If GT codepoints == 0 and edits == 0, CER = 0.0. If GT codepoints == 0 and
   edits > 0, CER = 1.0 (cap).
"""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz.distance import Levenshtein

from masoretic_eval.segment import segment_clusters


@dataclass
class CERResult:
    cer: float
    edits: int
    denominator: int


def _cluster_align(
    gt_clusters: list[str], pred_clusters: list[str]
) -> list[tuple[str | None, str | None]]:
    """Needleman–Wunsch alignment over clusters.

    Returns list of (gt_cluster, pred_cluster) pairs. None on a side indicates
    a gap (insertion or deletion).
    """
    n = len(gt_clusters)
    m = len(pred_clusters)
    # DP table of (score, pointer). Pointer: 0=diag, 1=up (delete from gt), 2=left (insert into gt).
    score = [[0.0] * (m + 1) for _ in range(n + 1)]
    back = [[0] * (m + 1) for _ in range(n + 1)]

    # Gap cost = cluster's codepoint count (the "cost" of unaligned cluster).
    for i in range(1, n + 1):
        score[i][0] = score[i - 1][0] + len(gt_clusters[i - 1])
        back[i][0] = 1
    for j in range(1, m + 1):
        score[0][j] = score[0][j - 1] + len(pred_clusters[j - 1])
        back[0][j] = 2

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            g = gt_clusters[i - 1]
            p = pred_clusters[j - 1]
            # Diagonal cost = codepoint-level Levenshtein between the two clusters.
            diag = score[i - 1][j - 1] + Levenshtein.distance(g, p)
            up = score[i - 1][j] + len(g)  # delete gt cluster
            left = score[i][j - 1] + len(p)  # insert pred cluster
            best = min(diag, up, left)
            score[i][j] = best
            if best == diag:
                back[i][j] = 0
            elif best == up:
                back[i][j] = 1
            else:
                back[i][j] = 2

    # Traceback.
    i, j = n, m
    alignment: list[tuple[str | None, str | None]] = []
    while i > 0 or j > 0:
        if i > 0 and j > 0 and back[i][j] == 0:
            alignment.append((gt_clusters[i - 1], pred_clusters[j - 1]))
            i -= 1
            j -= 1
        elif i > 0 and back[i][j] == 1:
            alignment.append((gt_clusters[i - 1], None))
            i -= 1
        else:
            alignment.append((None, pred_clusters[j - 1]))
            j -= 1
    alignment.reverse()
    return alignment


def cluster_aligned_cer(gt: str, pred: str) -> CERResult:
    """Compute cluster-aligned codepoint CER for two strings.

    Edits and denominators are at codepoint level; alignment is at cluster level.
    """
    gt_clusters = list(segment_clusters(gt))
    pred_clusters = list(segment_clusters(pred))
    alignment = _cluster_align(gt_clusters, pred_clusters)
    edits = 0
    for g, p in alignment:
        if g is None:
            edits += len(p or "")
        elif p is None:
            edits += len(g)
        else:
            edits += Levenshtein.distance(g, p)
    denominator = sum(len(c) for c in gt_clusters)
    if denominator == 0:
        cer = 0.0 if edits == 0 else 1.0
    else:
        cer = edits / denominator
    return CERResult(cer=cer, edits=edits, denominator=denominator)
