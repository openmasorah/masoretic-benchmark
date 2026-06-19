"""F1 ±1 tolerance: bipartite matching with no double-counting.

Pins:
* Exact matches are taken first (a non-greedy "lower offset would be available
  if we re-ran without exact preference" case must score lower F1).
* Each B detection is consumed at most once (an A near two B's gets exactly
  one match).
* Detection-type buckets are isolated (circellus at ord 3 on A vs rafe at
  ord 3 on B never matches).
"""

from __future__ import annotations

from masoretic_eval.iaa.f1 import (
    Detection,
    detections_from_records,
    f1_with_tolerance,
)
from masoretic_eval.iaa.parse import Tier4Record


def _circ(verse, ord_):
    return Detection("circellus", verse, ord_)


def _rafe(verse, ord_):
    return Detection("rafe", verse, ord_)


def test_exact_preferred_over_tolerance_match():
    """A=[3,4] vs B=[4,5]: exact (4,4), 1 unmatched each side. Not (3,4)+(4,5)."""
    a = [_circ("v", 3), _circ("v", 4)]
    b = [_circ("v", 4), _circ("v", 5)]
    res = f1_with_tolerance(a, b, tolerance=1)
    assert res.tp == 1
    assert res.fn == 1
    assert res.fp == 1
    assert len(res.matched) == 1
    assert res.matched[0].is_exact
    assert (res.matched[0].ord_a, res.matched[0].ord_b) == (4, 4)


def test_no_double_counting_b_consumed_once():
    """B has one ord-4; both A-3 and A-5 are within tolerance, but only one wins."""
    a = [_circ("v", 3), _circ("v", 5)]
    b = [_circ("v", 4)]
    res = f1_with_tolerance(a, b, tolerance=1)
    assert res.tp == 1
    # B was matched exactly once — both fp and the "extra A" land as fn.
    assert res.fn == 1
    assert res.fp == 0


def test_tolerance_matches_after_exact_drain():
    """Exact (3,3), (5,5); leftover A=[7] vs B=[8] — tolerance match."""
    a = [_circ("v", 3), _circ("v", 7), _rafe("v", 5)]
    b = [_circ("v", 3), _circ("v", 8), _rafe("v", 5)]
    res = f1_with_tolerance(a, b, tolerance=1)
    assert res.tp == 3
    assert res.fp == 0
    assert res.fn == 0
    matched_pairs = sorted((m.type, m.ord_a, m.ord_b, m.is_exact) for m in res.matched)
    assert matched_pairs == [
        ("circellus", 3, 3, True),
        ("circellus", 7, 8, False),
        ("rafe", 5, 5, True),
    ]


def test_types_isolated_across_buckets():
    """Circellus@3 on A vs rafe@3 on B never matches — type bucket is hard."""
    a = [_circ("v", 3)]
    b = [_rafe("v", 3)]
    res = f1_with_tolerance(a, b, tolerance=1)
    assert res.tp == 0
    assert res.fn == 1
    assert res.fp == 1


def test_zero_tolerance_collapses_to_exact():
    """tolerance=0 ⇒ ±1 phase is skipped; only ordinal-equal pairs match."""
    a = [_circ("v", 3), _circ("v", 7)]
    b = [_circ("v", 3), _circ("v", 8)]
    res = f1_with_tolerance(a, b, tolerance=0)
    assert res.tp == 1
    assert res.fp == 1
    assert res.fn == 1


def test_detections_fold_both_class():
    """Records {circellus@3, rafe@3} collapse to one ``both``-typed detection."""
    records = [
        Tier4Record("circellus", "v", 3),
        Tier4Record("rafe", "v", 3),
    ]
    detections = detections_from_records(records)
    assert len(detections) == 1
    assert detections[0].type == "both"
    assert detections[0].ordinal == 3


def test_detections_canon_folds_double_rafe():
    """``double_rafe`` records canonicalize into ``rafe`` detections."""
    records = [Tier4Record("double_rafe", "v", 5)]
    detections = detections_from_records(records)
    assert len(detections) == 1
    assert detections[0].type == "rafe"
