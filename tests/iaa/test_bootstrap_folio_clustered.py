"""Folio-clustered bootstrap (paper-grade IAA SPEC 260619-n3u follow-up).

The plain verse-bootstrap treats 96 verses as exchangeable, which understates
CI width when scribe hand / page wear / annotator session / layout density
induce within-folio correlation. The folio-clustered bootstrap samples folios
with replacement, then samples verses within each drawn folio with
replacement. This raises CI width when within-folio correlation is present
and degenerates to the plain bootstrap when verses are exchangeable.

These tests are hermetic — no external data dependency. They pin the three
properties the paper relies on:

1. ``cluster_by=None`` matches the pre-existing plain-bootstrap RNG sequence
   (the backward-compat contract).
2. Same seed + same ``cluster_by`` → byte-identical ``MetricWithCI`` (the
   determinism contract; consumers can cite SHAs).
3. With injected within-folio correlation, folio-clustered CIs are strictly
   wider than verse-only CIs (the mechanism check — otherwise the new
   sampler is silently equivalent to the old one).
"""

from __future__ import annotations

from masoretic_eval.iaa.bootstrap import bootstrap_metric
from masoretic_eval.iaa.result import CI_METHOD


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def test_cluster_by_none_matches_existing_behavior():
    """``cluster_by=None`` is the identity case — same RNG sequence as before."""
    payloads = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
    a = bootstrap_metric(payloads, _mean, b=500, seed=42)
    b = bootstrap_metric(payloads, _mean, b=500, seed=42, cluster_by=None)
    assert a == b
    assert a.ci_method == CI_METHOD


def test_cluster_by_folio_same_seed_deterministic():
    """Same seed + same cluster_by → byte-identical ``MetricWithCI``."""
    payloads = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
    folios = ["F1", "F1", "F1", "F2", "F2", "F2"]
    a = bootstrap_metric(payloads, _mean, b=200, seed=7, cluster_by=folios)
    b = bootstrap_metric(payloads, _mean, b=200, seed=7, cluster_by=folios)
    assert a == b


def test_cluster_by_folio_widens_ci_under_within_folio_correlation():
    """Folio-clustered CIs are strictly wider when verses correlate within folio.

    Construct 4 folios × 5 verses with the within-folio values constant and
    the between-folio means spread out. Plain verse-bootstrap mixes folios
    freely on every resample and ends up with a narrow CI around the grand
    mean. Folio-clustered bootstrap can draw the same folio 4× and produce a
    resample mean far from the grand mean, widening the CI. The widening is
    the whole point of clustering.
    """
    payloads = (
        [0.9, 0.9, 0.9, 0.9, 0.9]
        + [0.1, 0.1, 0.1, 0.1, 0.1]
        + [0.7, 0.7, 0.7, 0.7, 0.7]
        + [0.3, 0.3, 0.3, 0.3, 0.3]
    )
    folios = ["A"] * 5 + ["B"] * 5 + ["C"] * 5 + ["D"] * 5

    verse_only = bootstrap_metric(payloads, _mean, b=2000, seed=0xBEEF)
    folio_clustered = bootstrap_metric(payloads, _mean, b=2000, seed=0xBEEF, cluster_by=folios)

    verse_width = verse_only.ci_upper - verse_only.ci_lower
    folio_width = folio_clustered.ci_upper - folio_clustered.ci_lower
    assert folio_width > verse_width, (
        f"folio-clustered CI ({folio_width:.4f}) should be strictly wider than "
        f"verse-only CI ({verse_width:.4f}) under injected within-folio correlation"
    )


def test_cluster_by_folio_point_estimate_unchanged():
    """Point estimate is independent of resampling scheme — only CIs differ."""
    payloads = [0.9, 0.9, 0.1, 0.1, 0.7, 0.3]
    folios = ["A", "A", "B", "B", "C", "C"]
    verse_only = bootstrap_metric(payloads, _mean, b=128, seed=1)
    folio_clustered = bootstrap_metric(payloads, _mean, b=128, seed=1, cluster_by=folios)
    assert verse_only.point == folio_clustered.point


def test_cluster_by_length_mismatch_raises():
    """``cluster_by`` length must equal payloads length — caller bug otherwise."""
    import pytest

    payloads = [0.1, 0.2, 0.3]
    with pytest.raises(ValueError, match="cluster_by"):
        bootstrap_metric(payloads, _mean, b=10, seed=1, cluster_by=["A", "B"])


def test_cluster_by_ci_method_label_distinguishes_modes():
    """The ``ci_method`` label tells downstream consumers which sampler ran."""
    payloads = [0.1, 0.2, 0.3, 0.4]
    folios = ["A", "A", "B", "B"]
    verse_only = bootstrap_metric(payloads, _mean, b=64, seed=1)
    folio_clustered = bootstrap_metric(payloads, _mean, b=64, seed=1, cluster_by=folios)
    assert verse_only.ci_method != folio_clustered.ci_method
    assert "cluster" in folio_clustered.ci_method
