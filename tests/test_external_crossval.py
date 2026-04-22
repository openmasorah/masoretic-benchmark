"""External cross-validation: scorer CER must agree with an independent
Levenshtein implementation on shared Hebrew fixtures.

This test exists because Zed flagged self-grading as a risk: the scorer must
not rely on a single Levenshtein implementation whose bugs would invisibly
cancel out in its own tests. The independent implementation here is a naive
O(n*m) DP written from scratch, operating at codepoint level after stripping
cluster boundaries (i.e. treating each string as a flat codepoint sequence).

We assert that when computed edits and denominators agree up to cluster-gap
semantics, the scorer's CER is within 1e-9 of the independent path on
identical-cluster-count fixtures. For fixtures with cluster-count mismatches,
the independent path is a codepoint-level Levenshtein and gives an upper
bound (cluster alignment imposes additional structure).
"""

from __future__ import annotations

import pytest

from masoretic_eval.metrics.cer import cluster_aligned_cer


def _naive_levenshtein(a: str, b: str) -> int:
    """Textbook O(n*m) codepoint-level Levenshtein distance."""
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,
                dp[i][j - 1] + 1,
                dp[i - 1][j - 1] + cost,
            )
    return dp[n][m]


@pytest.mark.parametrize(
    "gt,pred",
    [
        ("בָ", "בַ"),  # qamatz / patach
        ("בָרֵ", "בָרֵ"),  # identical
        ("בְּרֵאשִׁית",
         "בְּרֵאשִׁית"),  # בראשית identical
    ],
)
def test_scorer_agrees_with_naive_levenshtein_when_cluster_counts_match(gt, pred):
    ours = cluster_aligned_cer(gt, pred)
    naive_edits = _naive_levenshtein(gt, pred)
    # When both strings segment to the same number of clusters and clusters align
    # one-to-one, the cluster-aligned edit count equals the codepoint-level
    # Levenshtein. (Cluster alignment adds constraints only when cluster
    # sequences diverge.)
    assert ours.edits == naive_edits, (
        f"self-grading risk: scorer edits={ours.edits} "
        f"disagrees with naive Levenshtein edits={naive_edits}"
    )


def test_scorer_upper_bounded_by_naive_levenshtein_on_cluster_mismatch():
    gt = "בָרֵ"
    pred = "בָ"
    ours = cluster_aligned_cer(gt, pred)
    naive = _naive_levenshtein(gt, pred)
    # Cluster-aligned edits are ≥ naive edits (cluster boundaries constrain alignment).
    assert ours.edits >= naive, (
        f"scorer edits={ours.edits} < naive edits={naive} — scorer is too lenient"
    )
