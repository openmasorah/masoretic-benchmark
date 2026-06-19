"""Signed-offset distribution over matched circellus pairs.

Per SPEC 260619-n3u: ``signed_offset = ord_B - ord_A`` for each matched pair
where both sides agreed the detection type was ``circellus``. Report median,
IQR, and a histogram on ``[-3, +3]`` with overflow buckets.

This is the "B-offset" finding from the falsification — a real scholarly
result, not noise — and the histogram is the audit trail behind that claim.
"""

from __future__ import annotations

from masoretic_eval.iaa.f1 import MatchedPair
from masoretic_eval.iaa.result import OffsetDistribution


def _percentile_sorted(sorted_xs: list[int], pct: float) -> float:
    """Linear-interpolation percentile on a sorted list.

    Mirrors ``numpy.percentile`` default (`linear`) so any downstream
    consumer that re-checks the math gets the same value.
    """
    if not sorted_xs:
        return float("nan")
    n = len(sorted_xs)
    if n == 1:
        return float(sorted_xs[0])
    rank = (pct / 100.0) * (n - 1)
    lo = int(rank)
    hi = min(lo + 1, n - 1)
    frac = rank - lo
    return sorted_xs[lo] * (1.0 - frac) + sorted_xs[hi] * frac


def offset_distribution(
    matched: list[MatchedPair], *, hist_range: tuple[int, int] = (-3, 3)
) -> OffsetDistribution:
    """Build the signed-offset distribution over matched circellus pairs.

    Only pairs with ``type == "circellus"`` participate. Pairs whose offset
    falls inside ``hist_range`` are bucketed by integer offset; outside the
    range they land in the ``"<-N"`` / ``">+N"`` overflow buckets.
    """
    lo, hi = hist_range
    offsets = sorted(p.signed_offset for p in matched if p.type == "circellus")

    # Initialise every bucket so the JSON shape is stable across runs even
    # when some bins are empty. Overflow buckets are always present.
    histogram: dict[str, int] = {f"{i:+d}": 0 for i in range(lo, hi + 1)}
    histogram[f"<{lo:+d}"] = 0
    histogram[f">{hi:+d}"] = 0
    for off in offsets:
        if off < lo:
            histogram[f"<{lo:+d}"] += 1
        elif off > hi:
            histogram[f">{hi:+d}"] += 1
        else:
            histogram[f"{off:+d}"] += 1

    n_matched = len(offsets)
    median = _percentile_sorted(offsets, 50.0) if offsets else float("nan")
    iqr_lower = _percentile_sorted(offsets, 25.0) if offsets else float("nan")
    iqr_upper = _percentile_sorted(offsets, 75.0) if offsets else float("nan")

    return OffsetDistribution(
        median=median,
        iqr_lower=iqr_lower,
        iqr_upper=iqr_upper,
        n_matched=n_matched,
        histogram=histogram,
    )
