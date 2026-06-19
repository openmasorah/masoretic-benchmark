"""Per-type F1 breakouts (circellus / rafe).

Per-type F1 is computed by filtering each side's detections to those
covering the type of interest (with ``both`` expanding to cover both
types), relabeling them to a single bucket, and reusing the headline
bipartite matcher.

Pins:
* Per-type filtering does not double-count across types — a circellus
  detection consumed by the circellus F1 doesn't leak into the rafe F1
  because the type buckets are isolated.
* The ±1 tolerance window matches the headline F1's behaviour.
* The per-type bootstrap CIs are deterministic under a fixed seed.
"""

from __future__ import annotations

from pathlib import Path

from masoretic_eval.iaa.cli import serialize_result
from masoretic_eval.iaa.compute import compute_iaa
from masoretic_eval.iaa.f1 import (
    Detection,
    detections_covering_type,
    f1_for_type,
)


def _circ(verse, ord_):
    return Detection("circellus", verse, ord_)


def _rafe(verse, ord_):
    return Detection("rafe", verse, ord_)


def _both(verse, ord_):
    return Detection("both", verse, ord_)


def test_per_type_filtering_isolates_buckets():
    """Filtering by type changes the F1 view — the union view sees all
    detection types simultaneously, the per-type view sees only one.

    Headline F1 (all types together) on this fixture is 1.0 (perfect
    agreement across types). Per-type circellus F1 is also 1.0; per-type
    rafe F1 is 1.0. Crucially, swapping a circellus on A for a rafe
    drops only the relevant per-type number without touching the other.
    """
    a = [_circ("v", 3), _rafe("v", 5)]
    b = [_circ("v", 3), _rafe("v", 5)]
    assert f1_for_type(a, b, t="circellus", tolerance=0).f1 == 1.0
    assert f1_for_type(a, b, t="rafe", tolerance=0).f1 == 1.0

    # Now break only the rafe agreement (A has rafe@5, B has circellus@5):
    a2 = [_circ("v", 3), _rafe("v", 5)]
    b2 = [_circ("v", 3), _circ("v", 5)]
    # Circellus per-type still sees the @3 exact match; B's stray
    # circellus@5 lands as a circellus FP, NOT as a rafe match.
    res_circ = f1_for_type(a2, b2, t="circellus", tolerance=0)
    assert res_circ.tp == 1  # @3 match
    assert res_circ.fp == 1  # B's circellus@5
    assert res_circ.fn == 0
    # Rafe per-type sees A's rafe@5 with no counterpart on B.
    res_rafe = f1_for_type(a2, b2, t="rafe", tolerance=0)
    assert res_rafe.tp == 0
    assert res_rafe.fp == 0
    assert res_rafe.fn == 1  # A's rafe@5


def test_per_type_no_double_count_against_both():
    """A ``both`` detection covers BOTH circellus and rafe per-type buckets
    but is not double-counted within a single per-type bucket."""
    a = [_both("v", 3)]
    b = [_both("v", 3)]
    # Per-type circellus sees the both detections as circellus-presence.
    res_c = f1_for_type(a, b, t="circellus", tolerance=0)
    assert res_c.tp == 1
    assert res_c.fp == 0
    assert res_c.fn == 0
    # Per-type rafe sees the same detections as rafe-presence.
    res_r = f1_for_type(a, b, t="rafe", tolerance=0)
    assert res_r.tp == 1
    assert res_r.fp == 0
    assert res_r.fn == 0


def test_per_type_both_matches_single_type_on_other_side():
    """A=both@3 vs B=circellus@3: per-type circellus F1 = 1.0 (both sides
    agree circellus is present); per-type rafe F1 = 0 (only A has rafe)."""
    a = [_both("v", 3)]
    b = [_circ("v", 3)]
    res_c = f1_for_type(a, b, t="circellus", tolerance=0)
    assert res_c.tp == 1
    assert res_c.fp == 0
    assert res_c.fn == 0
    res_r = f1_for_type(a, b, t="rafe", tolerance=0)
    # A's both → has rafe; B has nothing for rafe.
    assert res_r.tp == 0
    assert res_r.fp == 0
    assert res_r.fn == 1


def test_per_type_tolerance_matches_headline_behaviour():
    """±1 tolerance behaves identically to the headline F1's ±1 logic
    when the input is restricted to a single type."""
    a = [_circ("v", 3), _circ("v", 7)]
    b = [_circ("v", 3), _circ("v", 8)]
    res0 = f1_for_type(a, b, t="circellus", tolerance=0)
    res1 = f1_for_type(a, b, t="circellus", tolerance=1)
    assert res0.tp == 1  # @3 exact only
    assert res1.tp == 2  # @3 exact + (7,8) tolerance


def test_detections_covering_type_relabels_both():
    """``detections_covering_type`` relabels ``both``-typed detections to the
    target type so they share a bucket with native-type detections."""
    dets = [_circ("v", 3), _rafe("v", 4), _both("v", 5)]
    circ_view = detections_covering_type(dets, "circellus")
    assert {d.ordinal for d in circ_view} == {3, 5}
    assert all(d.type == "circellus" for d in circ_view)
    rafe_view = detections_covering_type(dets, "rafe")
    assert {d.ordinal for d in rafe_view} == {4, 5}
    assert all(d.type == "rafe" for d in rafe_view)


_A_SIDE = "אבגד֯ה׃\nוזחט<DR>י׃\nכלמנֿס׃\n"
_B_SIDE = "אבג֯דה׃\nוזחטֿי׃\nכלמנֿס׃\n"
_VERSE_FOLIO_MAP = [
    ("Deut.99.1", "F999A"),
    ("Deut.99.2", "F999A"),
    ("Deut.99.3", "F999B"),
]


def test_per_type_f1_bootstrap_deterministic(tmp_path: Path):
    """Same seed → byte-identical per-type F1 + CIs in the serialized JSON."""
    a_path = tmp_path / "a.txt"
    b_path = tmp_path / "b.txt"
    a_path.write_text(_A_SIDE, encoding="utf-8")
    b_path.write_text(_B_SIDE, encoding="utf-8")
    r1 = compute_iaa(a_path, b_path, _VERSE_FOLIO_MAP, bootstrap_b=64, bootstrap_seed=7)
    r2 = compute_iaa(a_path, b_path, _VERSE_FOLIO_MAP, bootstrap_b=64, bootstrap_seed=7)
    s1 = serialize_result(r1)
    s2 = serialize_result(r2)
    assert s1 == s2

    # Spot-check the JSON shape: f1_by_type present with the expected nesting.
    import json

    j = json.loads(s1)
    assert "f1_by_type" in j["tier4"]
    assert set(j["tier4"]["f1_by_type"].keys()) == {"circellus", "rafe"}
    for t in ("circellus", "rafe"):
        assert set(j["tier4"]["f1_by_type"][t].keys()) == {"exact", "tolerance_1"}
        for k in ("exact", "tolerance_1"):
            metric = j["tier4"]["f1_by_type"][t][k]
            assert "point" in metric
            assert "ci_lower" in metric
            assert "ci_upper" in metric

    # κ keys gone.
    assert "kappa_circellus" not in j["tier4"]
    assert "kappa_rafe" not in j["tier4"]
