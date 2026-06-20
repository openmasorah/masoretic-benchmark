"""Deterministic verse-resampling bootstrap CI helper.

For every reported metric, we resample verses with replacement B times and
compute the metric on each resample. The 2.5% / 97.5% percentiles form the CI.

Two resampling schemes:

* ``cluster_by=None`` (the original): plain verse-resample with replacement.
  All N verses are exchangeable.
* ``cluster_by=<labels>``: cluster bootstrap. Each iteration samples
  cluster labels with replacement, then samples verses within each drawn
  cluster with replacement. Used for headline CIs in
  :mod:`masoretic_eval.iaa.compute` with the folio as the cluster label —
  the JCDL methodology section calls this out as the correct CI under
  within-folio correlation (scribe hand, page wear, annotator session,
  layout density). Degenerates to plain bootstrap when verses are
  exchangeable.

Determinism contract (per SPEC 260619-n3u):

* RNG is ``random.Random(seed)`` — never the global ``random`` module.
* Same seed + same inputs (including ``cluster_by``) → byte-identical
  output JSON.
* Recompute the full statistic on each resample (no delta-method shortcut —
  α has closed-form variance only under nominal-data assumptions that
  the SPEC reasonably declines to take).

The bootstrap is unit-agnostic: callers pass a list of verse-indexed payloads
and a function that produces the statistic given a list of payloads. The
resampler picks indices, the statistic function does the rest.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Hashable, Sequence
from typing import TypeVar

from masoretic_eval.iaa.result import CI_METHOD, CI_METHOD_CLUSTER, MetricWithCI

T = TypeVar("T")

DEFAULT_SEED = 0xBEEF
DEFAULT_B = 10_000


def _percentile_sorted(sorted_xs: list[float], pct: float) -> float:
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


def bootstrap_metric(
    payloads: Sequence[T],
    statistic: Callable[[list[T]], float],
    *,
    b: int = DEFAULT_B,
    seed: int = DEFAULT_SEED,
    cluster_by: Sequence[Hashable] | None = None,
) -> MetricWithCI:
    """Verse-resample bootstrap of a single scalar statistic.

    ``payloads`` is the per-verse payload (e.g. a list of `(units, type)`
    tuples for an α computation, or a list of per-verse CERs). ``statistic``
    accepts the resampled list and returns a scalar.

    When ``cluster_by`` is provided, it must be a sequence of hashable cluster
    labels parallel to ``payloads`` — one label per payload (for IAA this is
    the folio identifier). The cluster bootstrap then samples cluster labels
    with replacement and, for each drawn cluster, samples its members with
    replacement. Cluster order is the labels' first-appearance order in
    ``cluster_by`` (so the RNG sequence is deterministic regardless of how
    the caller built the label list).

    NaN samples are dropped before computing percentiles. If every resample
    produced NaN the CI bounds come out as NaN — the caller should treat
    that the same as a degenerate point estimate.
    """
    ci_method = CI_METHOD_CLUSTER if cluster_by is not None else CI_METHOD
    point = statistic(list(payloads))
    n = len(payloads)
    if cluster_by is not None and len(cluster_by) != n:
        raise ValueError(f"cluster_by length {len(cluster_by)} != payloads length {n}")

    if b <= 0 or not payloads:
        return MetricWithCI(
            point=point,
            ci_lower=float("nan"),
            ci_upper=float("nan"),
            ci_method=ci_method,
            b=b,
        )

    rng = random.Random(seed)
    samples: list[float] = []

    if cluster_by is None:
        for _ in range(b):
            idxs = [rng.randrange(n) for _ in range(n)]
            resampled = [payloads[i] for i in idxs]
            val = statistic(resampled)
            if val == val:  # filter NaN (NaN != NaN by IEEE 754)
                samples.append(val)
    else:
        # Group payload indices by cluster label, preserving first-appearance
        # order. First-appearance ordering makes the RNG sequence depend only
        # on the input labels' positions — not on dict iteration quirks.
        cluster_order: list[Hashable] = []
        cluster_indices: dict[Hashable, list[int]] = {}
        for i, label in enumerate(cluster_by):
            if label not in cluster_indices:
                cluster_order.append(label)
                cluster_indices[label] = []
            cluster_indices[label].append(i)
        n_clusters = len(cluster_order)
        for _ in range(b):
            resampled: list[T] = []
            for _ in range(n_clusters):
                drawn = cluster_order[rng.randrange(n_clusters)]
                members = cluster_indices[drawn]
                m = len(members)
                for _ in range(m):
                    j = members[rng.randrange(m)]
                    resampled.append(payloads[j])
            val = statistic(resampled)
            if val == val:
                samples.append(val)

    if not samples:
        return MetricWithCI(
            point=point,
            ci_lower=float("nan"),
            ci_upper=float("nan"),
            ci_method=ci_method,
            b=b,
        )
    samples.sort()
    return MetricWithCI(
        point=point,
        ci_lower=_percentile_sorted(samples, 2.5),
        ci_upper=_percentile_sorted(samples, 97.5),
        ci_method=ci_method,
        b=b,
    )
