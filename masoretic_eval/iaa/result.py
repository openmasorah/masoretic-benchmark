"""Frozen dataclasses for the IAA result tree.

These shapes are the public contract — they are what `compute_iaa()` returns
and what the CLI serializes to JSON. Order of fields matters for the JSON
output's stability (`asdict()` preserves insertion order).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CI_METHOD = "verse_bootstrap_2.5_97.5"
CI_METHOD_CLUSTER = "folio_clustered_bootstrap_2.5_97.5"
CI_METHOD_BCA = "verse_bootstrap_BCa_95"
CI_METHOD_CLUSTER_BCA = "folio_clustered_bootstrap_BCa_95"


@dataclass(frozen=True)
class MetricWithCI:
    """One scalar metric with a bootstrap confidence interval.

    ``point``: point estimate on the full (unresampled) data.
    ``ci_lower`` / ``ci_upper``: 2.5%/97.5% percentiles over ``b`` resamples.
    ``ci_method``: pinned string so consumers can dispatch on the CI source.
    ``b``: number of bootstrap resamples that produced the CI.
    """

    point: float
    ci_lower: float
    ci_upper: float
    ci_method: str = CI_METHOD
    b: int = 10_000


@dataclass(frozen=True)
class OffsetDistribution:
    """Signed-offset distribution over bipartite-matched circellus pairs.

    ``signed_offset = ord_B - ord_A`` for each matched pair. The histogram is
    bucketed on ``[-3, +3]`` inclusive; offsets outside that range fall into
    the overflow buckets ``"<-3"`` / ``">+3"``. Counts in the histogram sum
    to ``n_matched``.
    """

    median: float
    iqr_lower: float  # 25th percentile
    iqr_upper: float  # 75th percentile
    n_matched: int
    histogram: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Tier4Result:
    """All tier-4 metrics for the headline IAA table.

    ``f1_exact`` / ``f1_tolerance_1`` are the all-types-combined headline
    numbers. ``f1_by_type`` reports per-type detection performance — outer
    key ∈ ``{"circellus", "rafe"}``, inner key ∈ ``{"exact", "tolerance_1"}``,
    each value is a ``MetricWithCI`` from the same verse-bootstrap.

    ``kappa_by_type`` reports per-type chance-corrected agreement
    coefficients alongside the per-type F1 — outer key ∈ ``{"circellus",
    "rafe"}``, inner key ∈ ``{"cohen", "pabak", "ac1"}``, each value is a
    ``MetricWithCI``. Cohen's κ is reported for comparability with prior
    IAA literature; PABAK and Gwet's AC1 are reported to surface the
    prevalence-paradox interaction explicitly (Cohen's κ understates
    agreement under extreme positive-class skew, while PABAK and AC1
    are stable in that regime). The paper-methodology prose should call
    out the three coefficients together so the reader sees the chance-
    corrected story end-to-end. Headline framing still uses F1 because
    F1 reads directly for DH/philology audiences without the chance-
    model baggage.

    The α fields pair ``{full|positive}`` universe × ``{canon|raw}``
    canonicalization, matching the falsification's 4-cell layout.
    ``offset_distribution`` summarizes the signed-offset histogram over
    matched circellus pairs.
    """

    f1_exact: MetricWithCI
    f1_tolerance_1: MetricWithCI
    f1_by_type: dict[str, dict[str, MetricWithCI]]
    kappa_by_type: dict[str, dict[str, MetricWithCI]]
    alpha_full_canon: MetricWithCI
    alpha_positive_canon: MetricWithCI
    alpha_full_raw: MetricWithCI
    alpha_positive_raw: MetricWithCI
    offset_distribution: OffsetDistribution


@dataclass(frozen=True)
class TierCERResult:
    """Tier 1/2/3 CER: per-folio + overall, each with a bootstrap CI.

    Per-folio CIs resample verses within that folio; overall CI resamples
    over the full verse pool. This is symmetric with how the F1/α CIs are
    constructed in tier-4 — the bootstrap unit is always the verse.
    """

    cer_per_folio: dict[str, MetricWithCI]
    cer_overall: MetricWithCI


@dataclass(frozen=True)
class IaaResult:
    """Top-level IAA result, including provenance metadata."""

    tier1: TierCERResult
    tier2: TierCERResult
    tier3: TierCERResult
    tier4: Tier4Result
    metadata: dict[str, Any]
