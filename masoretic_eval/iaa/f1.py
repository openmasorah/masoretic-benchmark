"""F1 (exact and ±1 tolerance) over tier-4 detections.

A "detection" is a canonicalized `(type, verse_ref, ordinal)` triple where
``type ∈ {"circellus", "rafe", "both"}`` (per SPEC 260619-n3u). The "both"
class fires when an annotator placed both a circellus and a rafe on the same
ordinal. Type folding is applied per-side before matching, so a circellus-only
detection on A vs a rafe-only detection on B never matches.

Matching is bipartite, restricted to identical (verse_ref, type) buckets,
with two phases:

1. **Exact phase:** ordinal-equal pairs match first.
2. **Tolerance phase:** remaining pairs match if ``|ord_A - ord_B| <= tolerance``.

Phase ordering enforces "prefer ord-equal first" from the SPEC. Phase 2 uses
a greedy interval-graph scan (sorted, single advancing pointer); matched
ordinals are removed from the pool before phase 2, so there is no
double-counting.

NOTE — this is exact-first-then-greedy, NOT guaranteed maximum-cardinality.
The forced exact phase can strand a pair that an optimal matcher would have
joined. Minimal counterexample at tolerance 1: A = {1, 2}, B = {2, 3} — the
exact phase consumes 2↔2, leaving 1 and 3 unmatchable (1 TP), whereas a
maximum-cardinality matching achieves 1↔2 and 2↔3 (2 TP). On the released
96-verse corpus this never bites: the greedy result equals true
maximum-cardinality matching on every (verse_ref, type) tolerance-1 bucket,
in both the per-annotator and UXLC-anchored frames. That equivalence is
regression-guarded by ``tests/iaa/test_matcher_maxcard_equiv.py``, so a future
folio containing the adversarial pattern is caught before it could silently
undercount. (Exact F1, tolerance 0, is unaffected either way: ordinal-equal
matching is unique, with no choice to make suboptimally.)
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from masoretic_eval.iaa.parse import Tier4Record


@dataclass(frozen=True)
class Detection:
    """One canonicalized detection.

    ``type`` ∈ {"circellus", "rafe", "both"}. Detections are emitted per
    ``(verse_ref, ordinal)`` group on each side after type folding —
    ``double_rafe`` is always canonicalized into ``rafe`` here (the SPEC's
    "canon" mode is the only universe for F1; raw α is the only place raw
    types survive).
    """

    type: str
    verse_ref: str
    ordinal: int


@dataclass(frozen=True)
class MatchedPair:
    """One bipartite-matched pair of detections, with signed offset."""

    type: str
    verse_ref: str
    ord_a: int
    ord_b: int
    is_exact: bool

    @property
    def signed_offset(self) -> int:
        return self.ord_b - self.ord_a


@dataclass(frozen=True)
class F1Result:
    """F1 numbers + the matched-pair audit trail (for offset distribution).

    ``tp`` / ``fp`` / ``fn`` are detection-level counts; ``f1`` is the
    standard harmonic mean. When both detection sets are empty, F1 is 1.0
    by convention (no signal to disagree on).
    """

    f1: float
    precision: float
    recall: float
    tp: int
    fp: int
    fn: int
    matched: list[MatchedPair]


def detections_from_records(records: list[Tier4Record]) -> list[Detection]:
    """Fold per-mark records into per-ordinal detections (with type canon).

    Multiple records on the same (verse_ref, ordinal) collapse into one
    detection whose type reflects the union:

    * ``{circellus}`` → ``"circellus"``
    * ``{rafe}`` or ``{double_rafe}`` (canon) → ``"rafe"``
    * ``{circellus, rafe}`` or any superset → ``"both"``

    Empty groups yield no detection. Output is sorted by
    ``(verse_ref, ordinal)`` for determinism.
    """
    groups: dict[tuple[str, int], set[str]] = defaultdict(set)
    for r in records:
        canon = "rafe" if r.type == "double_rafe" else r.type
        groups[(r.verse_ref, r.ordinal)].add(canon)

    out: list[Detection] = []
    for (verse_ref, ordinal), types in groups.items():
        if "circellus" in types and "rafe" in types:
            kind = "both"
        elif "circellus" in types:
            kind = "circellus"
        elif "rafe" in types:
            kind = "rafe"
        else:
            # Defensive: only known types are emitted from `extract_positional`,
            # so this branch is unreachable in practice. Bail rather than
            # silently swallowing an unrecognised mark.
            raise ValueError(f"unrecognised type set at {verse_ref}:{ordinal}: {types}")
        out.append(Detection(kind, verse_ref, ordinal))
    return sorted(out, key=lambda d: (d.verse_ref, d.ordinal, d.type))


def _match_one_bucket(
    a_ords: list[int], b_ords: list[int], *, tolerance: int
) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """Match within a single (verse_ref, type) bucket.

    Returns ``(matched_pairs, a_unmatched, b_unmatched)`` where each
    ``matched_pair`` is ``(ord_a, ord_b)``. Ordinals on each side are unique
    by construction (detections are per (verse_ref, ordinal)), so set
    semantics are safe.
    """
    a_set = sorted(a_ords)
    b_set = sorted(b_ords)
    b_present = set(b_set)

    matched: list[tuple[int, int]] = []
    a_used: set[int] = set()
    b_used: set[int] = set()

    # Phase 1: exact (ord_a == ord_b).
    for a in a_set:
        if a in b_present and a not in b_used:
            matched.append((a, a))
            a_used.add(a)
            b_used.add(a)

    # Phase 2: tolerance. Greedy nearest-neighbor scan over the remaining
    # ordinals (both sides sorted). The advancing-pointer scan over B
    # guarantees no double-counting and matches A in deterministic order.
    if tolerance > 0:
        a_unmatched = [a for a in a_set if a not in a_used]
        b_unmatched = [b for b in b_set if b not in b_used]
        b_idx = 0
        for a in a_unmatched:
            # Advance past any B that fell below the tolerance window. These
            # B's had no exact match (phase 1 already drained those) and no
            # earlier A could reach them, so they cannot match anyone.
            while b_idx < len(b_unmatched) and b_unmatched[b_idx] < a - tolerance:
                b_idx += 1
            if b_idx < len(b_unmatched) and abs(b_unmatched[b_idx] - a) <= tolerance:
                matched.append((a, b_unmatched[b_idx]))
                a_used.add(a)
                b_used.add(b_unmatched[b_idx])
                b_idx += 1

    return (
        matched,
        [a for a in a_set if a not in a_used],
        [b for b in b_set if b not in b_used],
    )


def detections_covering_type(detections: list[Detection], t: str) -> list[Detection]:
    """Filter detections to those that "cover" type ``t``.

    A detection covers ``t`` if its kind is ``t`` directly or ``"both"`` —
    the consonant carried both circellus and rafe, which means it carried
    ``t`` along with the other type. All matching detections are
    relabeled to ``t`` so they share a single bipartite-matching bucket
    when handed to :func:`f1_with_tolerance`.

    Used to derive per-type F1 without re-running parsing or coalescing
    the multi-type matcher. A circellus detection on A vs a circellus
    detection on B always matches on the per-type-circellus F1; a "both"
    detection on A vs a circellus on B also matches (both sides agreed
    a circellus is present at that ordinal).
    """
    return [
        Detection(t, d.verse_ref, d.ordinal) for d in detections if d.type == t or d.type == "both"
    ]


def f1_for_type(
    a_detections: list[Detection],
    b_detections: list[Detection],
    *,
    t: str,
    tolerance: int = 1,
) -> F1Result:
    """Per-type F1 with ±tolerance window.

    Equivalent to running :func:`f1_with_tolerance` over the
    ``detections_covering_type(t)`` view of each side. The matched-pair
    audit trail in the returned ``F1Result`` therefore lives in a single
    ``(verse_ref, t)`` bucket per verse, consistent with the headline F1's
    structure.
    """
    a_filt = detections_covering_type(a_detections, t)
    b_filt = detections_covering_type(b_detections, t)
    return f1_with_tolerance(a_filt, b_filt, tolerance=tolerance)


def f1_with_tolerance(
    a_detections: list[Detection],
    b_detections: list[Detection],
    *,
    tolerance: int = 1,
) -> F1Result:
    """Compute F1 with optional ±tolerance ordinal slack.

    ``tolerance=0`` collapses to exact F1. ``tolerance=1`` is the headline
    metric per SPEC; the gap between the two quantifies the B-offset
    finding.
    """
    a_by_bucket: dict[tuple[str, str], list[int]] = defaultdict(list)
    b_by_bucket: dict[tuple[str, str], list[int]] = defaultdict(list)
    for d in a_detections:
        a_by_bucket[(d.verse_ref, d.type)].append(d.ordinal)
    for d in b_detections:
        b_by_bucket[(d.verse_ref, d.type)].append(d.ordinal)

    matched: list[MatchedPair] = []
    tp = 0
    fp = 0
    fn = 0
    for bucket in sorted(set(a_by_bucket) | set(b_by_bucket)):
        verse_ref, type_ = bucket
        pairs, a_un, b_un = _match_one_bucket(
            a_by_bucket.get(bucket, []),
            b_by_bucket.get(bucket, []),
            tolerance=tolerance,
        )
        for ord_a, ord_b in pairs:
            matched.append(
                MatchedPair(
                    type=type_,
                    verse_ref=verse_ref,
                    ord_a=ord_a,
                    ord_b=ord_b,
                    is_exact=(ord_a == ord_b),
                )
            )
        tp += len(pairs)
        fn += len(a_un)  # A had it, B didn't — false negative when A is reference
        fp += len(b_un)

    # Precision / recall / F1. Use the (TP + FP), (TP + FN) denominators with
    # the standard "no signal, no error" convention when both sides are empty.
    if tp + fp == 0:
        precision = 1.0 if tp + fn == 0 else 0.0
    else:
        precision = tp / (tp + fp)
    if tp + fn == 0:
        recall = 1.0 if tp + fp == 0 else 0.0
    else:
        recall = tp / (tp + fn)
    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return F1Result(
        f1=f1,
        precision=precision,
        recall=recall,
        tp=tp,
        fp=fp,
        fn=fn,
        matched=matched,
    )
