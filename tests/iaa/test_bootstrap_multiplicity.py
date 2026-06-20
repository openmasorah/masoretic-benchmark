"""Regression test for FINDING 1 — bootstrap matcher multiplicity bug.

External-reviewer #1 hypothesised the point-outside-CI anomaly on F1 exact
(0.8988 vs CI upper 0.8961) was a code bug, not a finite-n property. Audit
``BOOTSTRAP_AUDIT.md`` (2026-06-20) confirmed: ``f1._match_one_bucket`` used
``a_used: set[int]`` / ``b_used: set[int]`` to track matched ordinals, so a
verse drawn N times in a bootstrap resample contributed at most one match per
ordinal — the duplicates collapsed silently and TP under-counted.

This file pins the per-verse aggregation pattern (compute.py::_aggregate_f1)
that pushes verse-multiplicity *outside* the matcher. The matcher still
assumes unique ordinals per verse (its design invariant); the orchestrator
runs it once per resampled verse and sums TP/FP/FN across the list. A verse
drawn N times therefore contributes its counts N times.

Failing this test under a future refactor is a methodology-grade regression
(invalidates the headline F1 CIs in ``paper_iaa_results.json``); treat it
the same as breaking the determinism contract.
"""

from __future__ import annotations

from masoretic_eval.iaa.compute import _aggregate_f1, _f1_for_type_over_verses, _f1_over_verses
from masoretic_eval.iaa.f1 import Detection, f1_with_tolerance


def _circ(verse: str, ord_: int) -> Detection:
    return Detection("circellus", verse, ord_)


def test_single_verse_resampled_n_times_scales_tp_fp_fn():
    """A=[ord 5, ord 7], B=[ord 5] @ tol=0 → tp=1, fn=1, fp=0, F1=2/3.

    Drawing the same verse 5× must give tp=5, fn=5, fp=0 — the same F1.
    Under the FINDING 1 bug, dup TP collapsed (tp stayed at 1 while
    fn=5), biasing F1 downward in resamples.
    """
    a_dets = [_circ("V:1", 5), _circ("V:1", 7)]
    b_dets = [_circ("V:1", 5)]

    single = _f1_over_verses([(a_dets, b_dets)], tolerance=0)
    assert (single.tp, single.fp, single.fn) == (1, 0, 1)

    dup = _f1_over_verses([(a_dets, b_dets)] * 5, tolerance=0)
    assert (dup.tp, dup.fp, dup.fn) == (5, 0, 5), (
        "verse-multiplicity lost in matcher (FINDING 1 regression): "
        f"expected tp=5/fp=0/fn=5, got tp={dup.tp}/fp={dup.fp}/fn={dup.fn}"
    )
    assert single.f1 == dup.f1

    # Pin: the old global-flatten path (used pre-fix) IS still wrong on this
    # input — passing the duplicated detections directly into the matcher
    # collapses dup TP. This is the FINDING 1 bug surface; the per-verse
    # aggregator's job is to never expose dup-ord input to the matcher.
    a_flat = a_dets * 5
    b_flat = b_dets * 5
    flat_buggy = f1_with_tolerance(a_flat, b_flat, tolerance=0)
    assert flat_buggy.tp == 1 and flat_buggy.fn == 5, (
        "Matcher invariant changed — the FINDING 1 set-semantics dedup is "
        "the very behaviour this test pins against. If you fixed the matcher "
        "to be multiplicity-safe internally, update this assertion and the "
        "module docstring."
    )


def test_resample_preserves_f1_under_tolerance_window():
    """Same scale-invariance must hold for the ±1 tolerance F1.

    A=[5,7], B=[6,9] @ tol=1: pair (5,6) matches under tolerance, (7) and (9)
    don't. tp=1, fn=1, fp=1. Drawing the verse 3× must scale to tp=3, fn=3,
    fp=3 — preserving F1 = 2/(2+1+1) = 0.5.
    """
    a_dets = [_circ("V:1", 5), _circ("V:1", 7)]
    b_dets = [_circ("V:1", 6), _circ("V:1", 9)]

    single = _f1_over_verses([(a_dets, b_dets)], tolerance=1)
    assert (single.tp, single.fp, single.fn) == (1, 1, 1)

    dup = _f1_over_verses([(a_dets, b_dets)] * 3, tolerance=1)
    assert (dup.tp, dup.fp, dup.fn) == (3, 3, 3)
    assert single.f1 == dup.f1


def test_per_type_resample_also_scales():
    """The per-type F1 routes through the same aggregator and must scale too.

    Per-type F1 was the second bootstrap surface under FINDING 1; the fix
    pushes multiplicity through ``_f1_for_type_over_verses`` identically.
    """
    a_dets = [_circ("V:1", 3), _circ("V:1", 8)]
    b_dets = [_circ("V:1", 3)]

    single = _f1_for_type_over_verses([(a_dets, b_dets)], t="circellus", tolerance=0)
    dup = _f1_for_type_over_verses([(a_dets, b_dets)] * 4, t="circellus", tolerance=0)
    assert (single.tp, single.fp, single.fn) == (1, 0, 1)
    assert (dup.tp, dup.fp, dup.fn) == (4, 0, 4)
    assert single.f1 == dup.f1


def test_aggregate_preserves_unique_verse_equivalence():
    """On unique-verse inputs (the original data), per-verse aggregation must
    produce the same TP/FP/FN as a single global-flatten call. This pins the
    point-estimate-unchanged property (FINDING 1 only affected resamples)."""
    payloads = [
        ([_circ("V:1", 3), _circ("V:1", 7)], [_circ("V:1", 3)]),
        ([_circ("V:2", 4)], [_circ("V:2", 5)]),
        ([], [_circ("V:3", 2)]),
    ]
    aggregated = _f1_over_verses(payloads, tolerance=1)

    # Global flatten (the old behaviour) is still correct on unique verses
    # because every (verse_ref, type, ordinal) triple is unique by construction.
    a_all = [d for a, _ in payloads for d in a]
    b_all = [d for _, b in payloads for d in b]
    global_result = f1_with_tolerance(a_all, b_all, tolerance=1)

    assert (aggregated.tp, aggregated.fp, aggregated.fn) == (
        global_result.tp,
        global_result.fp,
        global_result.fn,
    )
    assert aggregated.f1 == global_result.f1


def test_aggregate_empty_inputs_match_singleton_contract():
    """``_aggregate_f1`` on an empty list mirrors the matcher's empty contract:
    tp+fp+fn = 0 ⇒ F1 = 1.0 (no signal, no error)."""
    result = _aggregate_f1([])
    assert (result.tp, result.fp, result.fn) == (0, 0, 0)
    assert result.f1 == 1.0
    assert result.precision == 1.0
    assert result.recall == 1.0
