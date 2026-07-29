"""Tests for the rafe text-rule tier-4 baseline (BL-05).

Covers the rule/parse logic on tiny strings, the ordinal-contract gate, and a
pinned end-to-end number against the committed public consensus gold so a
silent regression (schema drift, matcher change, canon change) is caught.
"""

from __future__ import annotations

import json
from pathlib import Path

from masoretic_eval.iaa.f1 import (
    detections_covering_type,
    detections_from_records,
    f1_with_tolerance,
)
from masoretic_eval.iaa.parse import Tier4Record, count_consonants
from masoretic_eval.metrics.rafe_rule import (
    parse_consonants,
    pooled_rafe_f1,
    predict_rafe,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
CONSENSUS = _REPO_ROOT / "iaa_data" / "devarim_4folio" / "consensus_gold_positional.json"


def test_parse_consonants_counts_and_dagesh():
    # bet(+dagesh) gimel : two consonants, dagesh on the first only.
    cons = parse_consonants("בּג")
    assert [(c.ordinal, c.letter, c.dagesh) for c in cons] == [
        (1, "ב", True),
        (2, "ג", False),
    ]


def test_parse_consonants_skips_editor_tokens_without_incrementing():
    # <DR> and <L> must not consume ordinal slots.
    cons = parse_consonants("ב<DR>ג<L>ד")
    assert [c.letter for c in cons] == ["ב", "ג", "ד"]
    assert [c.ordinal for c in cons] == [1, 2, 3]


def test_parse_consonants_count_matches_count_consonants():
    chunk = "וְאָ֯עִ֣ידָֿה בָּ֔ם אֶת־ הַשָּׁמַ֖יִם"
    assert len(parse_consonants(chunk)) == count_consonants(chunk)


def test_predict_rafe_fires_on_soft_begadkefat_only():
    # bet no-dagesh -> rafe; bet+dagesh -> none; gimel no-dagesh -> rafe;
    # alef (not begadkefat) -> none.
    preds = predict_rafe("בבּגא", "Deut.1.1")
    assert preds == [
        Tier4Record("rafe", "Deut.1.1", 1),
        Tier4Record("rafe", "Deut.1.1", 3),
    ]


def test_pooled_rafe_f1_perfect_and_empty():
    gold = detections_from_records([Tier4Record("rafe", "v", 2)])
    pred = detections_from_records([Tier4Record("rafe", "v", 2)])
    r = pooled_rafe_f1([(gold, pred)], tolerance=0)
    assert r.tp == 1 and r.fp == 0 and r.fn == 0
    assert r.f1 == 1.0
    # Empty-vs-empty is the "no signal" convention (precision=recall=1.0).
    r0 = pooled_rafe_f1([([], [])], tolerance=0)
    assert r0.f1 == 1.0


def test_pooled_rafe_f1_precision_recall_orientation():
    # Asymmetric on purpose (P != R) so a precision/recall swap is caught.
    # gold has rafe at 2, 5, 7; rule predicts only 2 -> 1 TP, 0 FP, 2 FN.
    gold = detections_from_records(
        [Tier4Record("rafe", "v", 2), Tier4Record("rafe", "v", 5), Tier4Record("rafe", "v", 7)]
    )
    pred = detections_from_records([Tier4Record("rafe", "v", 2)])
    r = pooled_rafe_f1([(gold, pred)], tolerance=0)
    assert (r.tp, r.fp, r.fn) == (1, 0, 2)
    assert r.precision == 1.0  # of the 1 prediction, 1 was correct
    assert round(r.recall, 3) == 0.333  # of 3 gold rafe, 1 found


def test_end_to_end_pinned_number_vs_public_consensus():
    """Pin the headline: F1_exact=0.621, and the gate that gold rafe never
    carries a dagesh. If this moves, a data/matcher/canon change happened."""
    data = json.loads(CONSENSUS.read_text())
    payloads = []
    rafe_gold = rafe_with_dagesh = 0
    for v in data["verses"]:
        vref = v["verse_ref"]
        cons = parse_consonants(v["chunk"])
        assert len(cons) == v["consonant_count"]  # ordinal-contract gate
        dagesh_at = {c.ordinal: c.dagesh for c in cons}
        for m in v["tier4_positional"]:
            if m["type"] in ("rafe", "double_rafe"):
                rafe_gold += 1
                rafe_with_dagesh += int(bool(dagesh_at.get(m["ordinal"])))
        gold = detections_from_records(
            [Tier4Record(m["type"], vref, m["ordinal"]) for m in v["tier4_positional"]]
        )
        pred = detections_from_records(predict_rafe(v["chunk"], vref))
        payloads.append((gold, pred))

    assert rafe_gold == 305
    assert rafe_with_dagesh == 0  # GATE 2: no gold rafe co-occurs with a dagesh
    r = pooled_rafe_f1(payloads, tolerance=0)
    assert (r.tp, r.fp, r.fn) == (272, 299, 33)
    assert round(r.f1, 3) == 0.621
    assert round(r.precision, 3) == 0.476
    assert round(r.recall, 3) == 0.892
    # Secondary tol-1 cell reported in the JSON — pin it too.
    assert round(pooled_rafe_f1(payloads, tolerance=1).f1, 3) == 0.662

    # The PUBLISHED precision, 4dp, as it appears in README.md and CHANGELOG.md.
    # The 3dp pins above cannot catch a drift smaller than a thousandth, which
    # is exactly the size of movement that would silently invalidate a printed
    # figure while every existing assertion stayed green.
    assert round(r.f1, 4) == 0.6210
    assert round(r.precision, 4) == 0.4764
    assert round(r.recall, 4) == 0.8918


def test_published_confidence_interval_is_reproducible():
    """Pin the printed interval, not just the printed point estimate.

    README.md publishes `F1 0.6210 (exact) [0.5743, 0.6651]`. The point
    estimate is pinned above, but nothing tied the *interval* to anything --
    and the interval has its own failure mode the point estimate cannot catch:
    a change to `b`, to the seed, or to the resampling itself moves the bounds
    while F1 stays exactly where it was.

    This runs the real 10,000-resample bootstrap (~8s) rather than a cheaper
    approximation, because a reproduction at different settings would not be a
    reproduction of the published number.
    """
    from masoretic_eval.iaa.bootstrap import (  # noqa: PLC0415
        DEFAULT_B,
        DEFAULT_SEED,
        bootstrap_metric,
    )

    data = json.loads(CONSENSUS.read_text())
    payloads = []
    for v in data["verses"]:
        vref = v["verse_ref"]
        gold = detections_from_records(
            [Tier4Record(m["type"], vref, m["ordinal"]) for m in v["tier4_positional"]]
        )
        payloads.append((gold, detections_from_records(predict_rafe(v["chunk"], vref))))

    ci = bootstrap_metric(
        payloads, lambda ps: pooled_rafe_f1(ps, tolerance=0).f1, b=DEFAULT_B, seed=DEFAULT_SEED
    )

    # The settings are part of the published claim: a reproduction at a
    # different b or seed is a different measurement wearing the same number.
    assert (DEFAULT_B, DEFAULT_SEED) == (10000, 0xBEEF)
    assert round(ci.ci_lower, 4) == 0.5743
    assert round(ci.ci_upper, 4) == 0.6651


def _consensus_payloads():
    data = json.loads(CONSENSUS.read_text())
    out = []
    for v in data["verses"]:
        vref = v["verse_ref"]
        gold = detections_from_records(
            [Tier4Record(m["type"], vref, m["ordinal"]) for m in v["tier4_positional"]]
        )
        pred = detections_from_records(predict_rafe(v["chunk"], vref))
        out.append((gold, pred))
    return out


def test_predict_rafe_ignores_the_answer_in_the_chunk():
    """Leakage guard: the rule must read only consonants + dagesh, never the
    inline rafe (U+05BF) / <DR> markings that ARE the answer. Stripping them
    from the chunk must not change a single prediction."""
    data = json.loads(CONSENSUS.read_text())
    for v in data["verses"]:
        vref = v["verse_ref"]
        stripped = v["chunk"].replace("ֿ", "").replace("<DR>", "")
        assert predict_rafe(v["chunk"], vref) == predict_rafe(stripped, vref)


def _max_cardinality(a_ords: list[int], b_ords: list[int], tolerance: int) -> int:
    """Brute-force maximum bipartite matching (Kuhn's augmenting path) for a
    single (verse, type) bucket: a_i ~ b_j iff |a_i - b_j| <= tolerance."""
    adj = {
        i: [j for j, b in enumerate(b_ords) if abs(a - b) <= tolerance]
        for i, a in enumerate(a_ords)
    }
    match_b: dict[int, int] = {}

    def augment(i: int, seen: set[int]) -> bool:
        for j in adj[i]:
            if j in seen:
                continue
            seen.add(j)
            if j not in match_b or augment(match_b[j], seen):
                match_b[j] = i
                return True
        return False

    return sum(augment(i, set()) for i in range(len(a_ords)))


def test_tolerance1_greedy_equals_maxcardinality_on_this_frame():
    """f1.py's exact-first-then-greedy matcher is not guaranteed max-cardinality;
    the existing equivalence test guards only annotator-vs-annotator frames. The
    gold-vs-rule-prediction frame is denser (runs of consecutive soft begadkefat
    are the adversarial {1,2} vs {2,3} shape), so guard it here directly: pooled
    greedy TP at tol=1 must equal the max-cardinality TP, or the reported 0.662
    silently undercounts."""
    from collections import defaultdict

    greedy_tp = 0
    maxcard_tp = 0
    for gold, pred in _consensus_payloads():
        g = detections_covering_type(gold, "rafe")
        p = detections_covering_type(pred, "rafe")
        greedy_tp += f1_with_tolerance(g, p, tolerance=1).tp
        a_by: dict[str, list[int]] = defaultdict(list)
        b_by: dict[str, list[int]] = defaultdict(list)
        for d in g:
            a_by[d.verse_ref].append(d.ordinal)
        for d in p:
            b_by[d.verse_ref].append(d.ordinal)
        for vref in set(a_by) | set(b_by):
            maxcard_tp += _max_cardinality(sorted(a_by[vref]), sorted(b_by[vref]), 1)
    assert greedy_tp == maxcard_tp  # greedy is optimal on this frame today
    assert greedy_tp > 272  # tol-1 recovers strictly more than exact (272)
