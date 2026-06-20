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

    Per-type Cohen's κ was deliberately omitted: under the extreme
    positive-class skew (~5% prevalence) seen on Devarim, Cohen's κ
    prevalence-paradox produces spuriously negative values even when F1
    is high. Under a binary recode against the full universe the per-type
    κ also collapses to α in this regime, so it adds no information beyond
    what α already reports. Per-type F1 gives DH/philology reviewers an
    interpretable per-type detection number without κ's chance-model
    baggage. See SPEC 260619-n3u upstream for the decision rationale.

    The α fields pair ``{full|positive}`` universe × ``{canon|raw}``
    canonicalization, matching the falsification's 4-cell layout.
    ``offset_distribution`` summarizes the signed-offset histogram over
    matched circellus pairs.
    """

    f1_exact: MetricWithCI
    f1_tolerance_1: MetricWithCI
    f1_by_type: dict[str, dict[str, MetricWithCI]]
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
