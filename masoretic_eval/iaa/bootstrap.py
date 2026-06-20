"""Deterministic verse-resampling bootstrap CI helper.

For every reported metric, we resample verses (or folios) with replacement B
times and compute the metric on each resample. The CI bounds come from one
of two interval methods:

* ``ci_method="percentile"``: vanilla 2.5% / 97.5% percentiles of the
  bootstrap distribution. Honest in label, but with small numbers of outer
  resampling units (e.g. G=4 folios) the bootstrap distribution can be
  biased away from the point estimate, and the percentile CI then fails to
  contain the point — a known small-G artifact of cluster bootstrap.
* ``ci_method="bca"``: bias-corrected and accelerated (BCa) percentile
  bootstrap (Efron 1987). Adjusts the percentile cutoffs using a bias
  term ``z_0`` (computed from the fraction of bootstrap samples below the
  point estimate) and an acceleration term ``a`` (from a leave-one-out
  jackknife on the resampling units). BCa produces intervals that contain
  the point estimate for finite samples and have second-order coverage
  properties.

Resampling schemes:

* ``cluster_by=None``: plain verse-resample with replacement. All N verses
  are exchangeable. Verse-level jackknife for BCa.
* ``cluster_by=<labels>``: cluster bootstrap. Each iteration samples
  cluster labels with replacement, then samples verses within each drawn
  cluster with replacement. Cluster-level jackknife for BCa
  (leave-one-cluster-out — G jackknife replicates).

Default ``ci_method`` is ``"auto"``: ``"bca"`` when ``cluster_by`` is set,
``"percentile"`` otherwise. This preserves backward-compat for verse-only
callers (where percentile is well-behaved) while making BCa the headline
default for cluster-bootstrapped metrics (where it correctly handles the
small-G bias documented above).

Determinism contract (per SPEC 260619-n3u):

* RNG is ``random.Random(seed)`` — never the global ``random`` module.
* Same seed + same inputs (including ``cluster_by`` and ``ci_method``) →
  byte-identical output JSON.
* BCa adjustments are deterministic functions of the bootstrap samples plus
  the jackknife values; no additional randomness.

The bootstrap is unit-agnostic: callers pass a list of verse-indexed payloads
and a function that produces the statistic given a list of payloads. The
resampler picks indices, the statistic function does the rest.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Hashable, Sequence
from statistics import NormalDist
from typing import TypeVar

from masoretic_eval.iaa.result import (
    CI_METHOD,
    CI_METHOD_BCA,
    CI_METHOD_CLUSTER,
    CI_METHOD_CLUSTER_BCA,
    MetricWithCI,
)

T = TypeVar("T")

DEFAULT_SEED = 0xBEEF
DEFAULT_B = 10_000

_STD_NORMAL = NormalDist()


def _percentile_sorted(sorted_xs: list[float], pct: float) -> float:
    if not sorted_xs:
        return float("nan")
    pct = max(0.0, min(100.0, pct))
    n = len(sorted_xs)
    if n == 1:
        return float(sorted_xs[0])
    rank = (pct / 100.0) * (n - 1)
    lo = int(rank)
    hi = min(lo + 1, n - 1)
    frac = rank - lo
    return sorted_xs[lo] * (1.0 - frac) + sorted_xs[hi] * frac


def _bca_bounds(
    samples_sorted: list[float],
    point: float,
    jackknife_values: list[float],
    alpha: float = 0.05,
) -> tuple[float, float]:
    """Return (ci_lower, ci_upper) under BCa adjustment.

    Falls back to plain percentile bounds when BCa is undefined (no samples,
    no jackknife variance, etc.) — see the inline comments for each
    degeneracy.
    """
    n = len(samples_sorted)
    if n == 0:
        return (float("nan"), float("nan"))

    # Bias correction z_0: Φ^(-1) of fraction of bootstrap samples < point.
    # Use < (not ≤): ties at the point shouldn't bias z_0 in either
    # direction. Clamp the fraction off the open interval (0,1) so the
    # inverse normal CDF stays finite.
    n_below = sum(1 for x in samples_sorted if x < point)
    p_below = n_below / n
    eps = 0.5 / n
    p_below = min(max(p_below, eps), 1.0 - eps)
    z_0 = _STD_NORMAL.inv_cdf(p_below)

    # Acceleration a via leave-one-out jackknife on the resampling units.
    # Numerator: Σ (jk_mean - jk_i)^3; denominator: 6 * [Σ (jk_mean - jk_i)^2]^(3/2).
    # When the jackknife is degenerate (all equal, single replicate) we fall
    # back to a=0, which makes BCa collapse to bias-corrected percentile.
    jk_clean = [j for j in jackknife_values if not math.isnan(j)]
    if len(jk_clean) < 2:
        a = 0.0
    else:
        jk_mean = sum(jk_clean) / len(jk_clean)
        diffs = [jk_mean - j for j in jk_clean]
        denom_sq = sum(d * d for d in diffs)
        if denom_sq <= 0.0:
            a = 0.0
        else:
            numer = sum(d * d * d for d in diffs)
            denom = 6.0 * (denom_sq**1.5)
            a = numer / denom

    z_lo = _STD_NORMAL.inv_cdf(alpha / 2.0)
    z_hi = _STD_NORMAL.inv_cdf(1.0 - alpha / 2.0)

    def _adjust(z: float) -> float:
        # Adjusted percentile per Efron (1987) eq. (14):
        #   α_adj = Φ( z_0 + (z_0 + z) / (1 - a*(z_0 + z)) )
        # Guard against the denominator going non-positive (rare at finite
        # a, would mean the acceleration is large enough to invert the
        # quantile). Fall back to z_0 + z (no acceleration) in that case.
        denom = 1.0 - a * (z_0 + z)
        if denom <= 0.0:
            return _STD_NORMAL.cdf(z_0 + z)
        return _STD_NORMAL.cdf(z_0 + (z_0 + z) / denom)

    q_lo = _adjust(z_lo)
    q_hi = _adjust(z_hi)
    return (
        _percentile_sorted(samples_sorted, q_lo * 100.0),
        _percentile_sorted(samples_sorted, q_hi * 100.0),
    )


def _cluster_groups(
    cluster_by: Sequence[Hashable],
) -> tuple[list[Hashable], dict[Hashable, list[int]]]:
    """Group payload indices by cluster label, preserving first-appearance order."""
    order: list[Hashable] = []
    indices: dict[Hashable, list[int]] = {}
    for i, label in enumerate(cluster_by):
        if label not in indices:
            order.append(label)
            indices[label] = []
        indices[label].append(i)
    return order, indices


def _cluster_jackknife(
    payloads: Sequence[T],
    statistic: Callable[[list[T]], float],
    cluster_by: Sequence[Hashable],
) -> list[float]:
    """Leave-one-cluster-out jackknife. One replicate per distinct cluster."""
    order, indices = _cluster_groups(cluster_by)
    out: list[float] = []
    for skip in order:
        keep = [payloads[i] for label, idxs in indices.items() if label != skip for i in idxs]
        if keep:
            out.append(statistic(keep))
    return out


def _verse_jackknife(
    payloads: Sequence[T],
    statistic: Callable[[list[T]], float],
) -> list[float]:
    """Leave-one-verse-out jackknife (N replicates)."""
    n = len(payloads)
    out: list[float] = []
    pl = list(payloads)
    for i in range(n):
        keep = pl[:i] + pl[i + 1 :]
        if keep:
            out.append(statistic(keep))
    return out


def bootstrap_metric(
    payloads: Sequence[T],
    statistic: Callable[[list[T]], float],
    *,
    b: int = DEFAULT_B,
    seed: int = DEFAULT_SEED,
    cluster_by: Sequence[Hashable] | None = None,
    ci_method: str = "auto",
) -> MetricWithCI:
    """Bootstrap CI for a single scalar statistic.

    ``ci_method``:

    * ``"auto"`` (default): ``"bca"`` if ``cluster_by`` is set, else
      ``"percentile"``. Preserves backward-compatible behavior for callers
      that don't pass ``cluster_by``; opts cluster-bootstrap callers into
      BCa so that small-G bias is corrected.
    * ``"percentile"``: vanilla 2.5/97.5 percentile bootstrap.
    * ``"bca"``: bias-corrected and accelerated bootstrap (Efron 1987).

    NaN samples are dropped before computing percentiles. If every resample
    produced NaN the CI bounds come out as NaN — the caller should treat
    that the same as a degenerate point estimate.
    """
    n = len(payloads)
    if cluster_by is not None and len(cluster_by) != n:
        raise ValueError(f"cluster_by length {len(cluster_by)} != payloads length {n}")

    if ci_method == "auto":
        ci_method = "bca" if cluster_by is not None else "percentile"
    if ci_method not in ("percentile", "bca"):
        raise ValueError(f"unknown ci_method: {ci_method!r}")

    if ci_method == "percentile":
        ci_method_label = CI_METHOD_CLUSTER if cluster_by is not None else CI_METHOD
    else:
        ci_method_label = CI_METHOD_CLUSTER_BCA if cluster_by is not None else CI_METHOD_BCA

    point = statistic(list(payloads))

    if b <= 0 or not payloads:
        return MetricWithCI(
            point=point,
            ci_lower=float("nan"),
            ci_upper=float("nan"),
            ci_method=ci_method_label,
            b=b,
        )

    rng = random.Random(seed)
    samples: list[float] = []

    if cluster_by is None:
        for _ in range(b):
            idxs = [rng.randrange(n) for _ in range(n)]
            resampled: list[T] = [payloads[i] for i in idxs]
            val = statistic(resampled)
            if val == val:  # filter NaN (NaN != NaN by IEEE 754)
                samples.append(val)
    else:
        cluster_order, cluster_indices = _cluster_groups(cluster_by)
        n_clusters = len(cluster_order)
        for _ in range(b):
            cluster_resampled: list[T] = []
            for _ in range(n_clusters):
                drawn = cluster_order[rng.randrange(n_clusters)]
                members = cluster_indices[drawn]
                m = len(members)
                for _ in range(m):
                    j = members[rng.randrange(m)]
                    cluster_resampled.append(payloads[j])
            val = statistic(cluster_resampled)
            if val == val:
                samples.append(val)

    if not samples:
        return MetricWithCI(
            point=point,
            ci_lower=float("nan"),
            ci_upper=float("nan"),
            ci_method=ci_method_label,
            b=b,
        )
    samples.sort()

    if ci_method == "percentile":
        ci_lower = _percentile_sorted(samples, 2.5)
        ci_upper = _percentile_sorted(samples, 97.5)
    else:
        # BCa: compute jackknife at the resampling-unit level
        # (folio for cluster, verse for verse-bootstrap).
        if cluster_by is None:
            jk = _verse_jackknife(payloads, statistic)
        else:
            jk = _cluster_jackknife(payloads, statistic, cluster_by)
        ci_lower, ci_upper = _bca_bounds(samples, point, jk)

    return MetricWithCI(
        point=point,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        ci_method=ci_method_label,
        b=b,
    )
