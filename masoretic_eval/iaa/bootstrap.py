"""Deterministic verse-resampling bootstrap CI helper.

For every reported metric, we resample verses with replacement B times and
compute the metric on each resample. The 2.5% / 97.5% percentiles form the CI.

Determinism contract (per SPEC 260619-n3u):

* RNG is ``random.Random(seed)`` — never the global ``random`` module.
* Same seed + same inputs → byte-identical output JSON.
* Recompute the full statistic on each resample (no delta-method shortcut —
  α and κ have closed-form variance only under nominal-data assumptions that
  the SPEC reasonably declines to take).

The bootstrap is unit-agnostic: callers pass a list of verse-indexed payloads
and a function that produces the statistic given a list of payloads. The
resampler picks indices, the statistic function does the rest.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from typing import TypeVar

from masoretic_eval.iaa.result import CI_METHOD, MetricWithCI

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
) -> MetricWithCI:
    """Verse-resample bootstrap of a single scalar statistic.

    ``payloads`` is the per-verse payload (e.g. a list of `(units, type)`
    tuples for an α computation, or a list of per-verse CERs). ``statistic``
    accepts the resampled list and returns a scalar.

    NaN samples are dropped before computing percentiles. If every resample
    produced NaN the CI bounds come out as NaN — the caller should treat
    that the same as a degenerate point estimate.
    """
    point = statistic(list(payloads))
    if b <= 0 or not payloads:
        return MetricWithCI(
            point=point,
            ci_lower=float("nan"),
            ci_upper=float("nan"),
            ci_method=CI_METHOD,
            b=b,
        )

    rng = random.Random(seed)
    n = len(payloads)
    samples: list[float] = []
    for _ in range(b):
        idxs = [rng.randrange(n) for _ in range(n)]
        resampled = [payloads[i] for i in idxs]
        val = statistic(resampled)
        if val == val:  # filter NaN (NaN != NaN by IEEE 754)
            samples.append(val)

    if not samples:
        return MetricWithCI(
            point=point,
            ci_lower=float("nan"),
            ci_upper=float("nan"),
            ci_method=CI_METHOD,
            b=b,
        )
    samples.sort()
    return MetricWithCI(
        point=point,
        ci_lower=_percentile_sorted(samples, 2.5),
        ci_upper=_percentile_sorted(samples, 97.5),
        ci_method=CI_METHOD,
        b=b,
    )
