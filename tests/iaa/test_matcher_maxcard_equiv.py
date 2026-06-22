"""Regression guard: the tier-4 ±1 matcher equals maximum-cardinality on the corpus.

The headline tier-4 F1 uses ``_match_one_bucket`` — an exact-first-then-greedy
bipartite matcher (see ``masoretic_eval/iaa/f1.py``). Exact-first-greedy is NOT
guaranteed maximum-cardinality in general: the forced exact phase can strand a
pair an optimal matcher would have joined (minimal counterexample at tolerance
1: A={1,2}, B={2,3} → greedy 1 TP vs maximum-cardinality 2 TP).

The published F1 ±1 numbers rely on the empirical fact that this never happens
on the released 96-verse Devarim corpus: greedy == maximum-cardinality on every
(verse_ref, type) tolerance-1 bucket. This test pins that equivalence so that a
future folio containing the adversarial pattern is caught (CI red) before it can
silently undercount the headline F1.

Hermetic: uses the committed CC-BY per-annotator positional projections only
(no UXLC cache required). The matcher is frame-independent, so per-annotator
coverage guards the UXLC-anchored headline path too — the adversarial pattern,
if introduced by a future folio, would surface in the committed projections.
"""

from __future__ import annotations

from pathlib import Path

from masoretic_eval.iaa.f1 import (
    Detection,
    _match_one_bucket,
    detections_covering_type,
    detections_from_records,
)
from masoretic_eval.iaa.projection import load_projection

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA = _REPO_ROOT / "iaa_data" / "devarim_4folio"
_A_PROJ = _DATA / "ginsberg_round0_positional.json"
_B_PROJ = _DATA / "moster_round0_positional.json"


def _max_cardinality(a_ords: list[int], b_ords: list[int], *, tolerance: int) -> int:
    """True maximum-cardinality bipartite matching on the ±tolerance graph.

    Reference implementation (Kuhn's augmenting-path). Edge (a, b) exists iff
    ``|a - b| <= tolerance``. Independent of ``_match_one_bucket`` so the two
    can be cross-checked.
    """
    a_nodes = sorted(set(a_ords))
    b_nodes = sorted(set(b_ords))
    adj = {a: [b for b in b_nodes if abs(a - b) <= tolerance] for a in a_nodes}
    match_b: dict[int, int] = {}

    def _augment(a: int, seen: set[int]) -> bool:
        for b in adj[a]:
            if b in seen:
                continue
            seen.add(b)
            if b not in match_b or _augment(match_b[b], seen):
                match_b[b] = a
                return True
        return False

    return sum(1 for a in a_nodes if _augment(a, set()))


def _greedy(a_ords: list[int], b_ords: list[int], *, tolerance: int) -> int:
    return len(_match_one_bucket(a_ords, b_ords, tolerance=tolerance)[0])


def test_reference_maxcard_discriminates_the_known_counterexample():
    """The guard must DETECT suboptimality, else equivalence proves nothing.

    Pins the reviewer's minimal counterexample and a longer chain: the shipped
    greedy matcher undercounts both, and ``_max_cardinality`` exceeds it. If
    this ever stops holding, the guard below is no longer meaningful.
    """
    # A={1,2}, B={2,3}: exact consumes 2↔2, strands 1 and 3.
    assert _greedy([1, 2], [2, 3], tolerance=1) == 1
    assert _max_cardinality([1, 2], [2, 3], tolerance=1) == 2
    # Longer ±1 chain.
    assert _greedy([1, 2, 3], [2, 3, 4], tolerance=1) == 2
    assert _max_cardinality([1, 2, 3], [2, 3, 4], tolerance=1) == 3


def _buckets_for(a_det: list[Detection], b_det: list[Detection]):
    a_by: dict[tuple[str, str], list[int]] = {}
    b_by: dict[tuple[str, str], list[int]] = {}
    for d in a_det:
        a_by.setdefault((d.verse_ref, d.type), []).append(d.ordinal)
    for d in b_det:
        b_by.setdefault((d.verse_ref, d.type), []).append(d.ordinal)
    return a_by, b_by


def _all_detections(proj) -> list[Detection]:
    out: list[Detection] = []
    for v in proj.verses:
        out += detections_from_records(list(v.tier4_positional))
    return out


def test_greedy_equals_maxcardinality_on_committed_corpus():
    """Greedy == maximum-cardinality on every tier-4 bucket in the committed corpus.

    Covers the combined-type buckets ({circellus, rafe, both}) that drive the
    headline F1 ±1, AND the per-type covering buckets that drive the per-type
    ±1 cells. Any divergence (e.g. a future folio with the adversarial pattern)
    fails CI.
    """
    a_det = _all_detections(load_projection(_A_PROJ))
    b_det = _all_detections(load_projection(_B_PROJ))

    # Combined-type buckets (headline F1).
    a_by, b_by = _buckets_for(a_det, b_det)
    divergent: list[tuple] = []
    for bucket in sorted(set(a_by) | set(b_by)):
        a_ords = a_by.get(bucket, [])
        b_ords = b_by.get(bucket, [])
        g = _greedy(a_ords, b_ords, tolerance=1)
        m = _max_cardinality(a_ords, b_ords, tolerance=1)
        if g != m:
            divergent.append((bucket, a_ords, b_ords, g, m))

    # Per-type covering buckets (per-type F1 cells).
    for t in ("circellus", "rafe"):
        a_by_t, b_by_t = _buckets_for(
            detections_covering_type(a_det, t), detections_covering_type(b_det, t)
        )
        for bucket in sorted(set(a_by_t) | set(b_by_t)):
            a_ords = a_by_t.get(bucket, [])
            b_ords = b_by_t.get(bucket, [])
            g = _greedy(a_ords, b_ords, tolerance=1)
            m = _max_cardinality(a_ords, b_ords, tolerance=1)
            if g != m:
                divergent.append((("per-type", t, *bucket), a_ords, b_ords, g, m))

    assert not divergent, (
        "greedy matcher diverges from maximum-cardinality on "
        f"{len(divergent)} bucket(s) — headline/per-type F1 ±1 would undercount. "
        f"First: {divergent[0]}"
    )
