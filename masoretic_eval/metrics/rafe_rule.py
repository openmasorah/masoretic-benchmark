"""Deterministic rafe detector — a text-rule tier-4 baseline (BL-05).

The Tiberian *rafe* stroke (U+05BF) marks the soft (spirantized) realization of
a begadkefat consonant. A parameter-free linguistic rule therefore predicts a
rafe wherever a begadkefat letter (ב ג ד כ ך פ ף ת) carries **no** dagesh
(U+05BC), whose presence marks the hard (plosive) realization.

This is an *oracle-text* baseline: it reads consonants and dagesh from the
adjudicated consensus transcription itself, so it measures how far a
deterministic rule reproduces the scribe's actual rafe placement given perfect
consonants+dagesh — it is NOT an end-to-end image→tier-4 system. It is the
tier-4 analogue of the gt-fed diacritizer floor: it demonstrates that the
tier-4 rafe axis is scoreable and discriminative, and quantifies the headroom a
context-aware system would have to beat.

Ordinal contract: consonant offsets are the 1-based Hebrew-consonant offsets of
:mod:`masoretic_eval.iaa.parse` (editor tokens do not consume slots). This
module mirrors that walk exactly and asserts its consonant count against
:func:`masoretic_eval.iaa.parse.count_consonants`, so its predicted ordinals
share the coordinate system of the gold ``tier4_positional`` records by
construction.
"""

from __future__ import annotations

from dataclasses import dataclass

from masoretic_eval.iaa.f1 import Detection, detections_covering_type, f1_with_tolerance
from masoretic_eval.iaa.parse import (
    _EDITOR_TOKEN_RE,
    DOUBLE_RAFE_TOKEN,
    Tier4Record,
    _is_consonant,
    count_consonants,
)

# begadkefat consonants (base + final forms). Rafe attaches to the soft variant.
BEGADKEFAT = frozenset("בגדכךפףת")
DAGESH = "ּ"  # Hebrew Point Dagesh Or Mapiq — marks the hard (plosive) variant


@dataclass(frozen=True)
class Consonant:
    """One Hebrew consonant in a verse chunk: 1-based ordinal, letter, dagesh flag."""

    ordinal: int
    letter: str
    dagesh: bool


def parse_consonants(chunk: str) -> list[Consonant]:
    """Walk ``chunk`` into per-consonant ``Consonant`` records.

    Mirrors :func:`masoretic_eval.iaa.parse.extract_positional`'s consonant
    walk (same editor-token skipping, same U+05D0..U+05EA range) so ordinals
    coincide with the gold records', and additionally records the dagesh flag.
    A trailing assert pins the count to :func:`count_consonants` — a divergence
    means the walk drifted from the ordinal contract and must fail loudly.
    """
    out: list[Consonant] = []
    i = 0
    ordinal = 0
    while i < len(chunk):
        if chunk.startswith(DOUBLE_RAFE_TOKEN, i):
            i += len(DOUBLE_RAFE_TOKEN)
            continue
        token = _EDITOR_TOKEN_RE.match(chunk, i)
        if token is not None:
            i = token.end()
            continue
        ch = chunk[i]
        if _is_consonant(ch):
            ordinal += 1
            out.append(Consonant(ordinal=ordinal, letter=ch, dagesh=False))
        elif ch == DAGESH and out:
            # Dagesh attaches to the most recent consonant.
            last = out[-1]
            out[-1] = Consonant(ordinal=last.ordinal, letter=last.letter, dagesh=True)
        i += 1
    assert len(out) == count_consonants(chunk), (
        f"rafe-rule walk drifted from the ordinal contract: "
        f"{len(out)} != count_consonants={count_consonants(chunk)}"
    )
    return out


def predict_rafe(chunk: str, verse_ref: str) -> list[Tier4Record]:
    """Predict rafe records for one verse via the begadkefat / no-dagesh rule."""
    return [
        Tier4Record("rafe", verse_ref, c.ordinal)
        for c in parse_consonants(chunk)
        if c.letter in BEGADKEFAT and not c.dagesh
    ]


@dataclass(frozen=True)
class PrecisionRecallF1:
    """Micro-averaged precision / recall / F1 with the pooled confusion counts."""

    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int


def pooled_rafe_f1(
    payloads: list[tuple[list[Detection], list[Detection]]], *, tolerance: int = 0
) -> PrecisionRecallF1:
    """Micro-average rafe F1 over per-verse ``(gold_detections, predictions)``.

    ``gold`` is side A (reference) and ``predictions`` side B, matching
    :func:`masoretic_eval.iaa.f1.f1_with_tolerance`'s FN=reference-missed
    convention, so recall is over the gold rafe set and precision over the
    rule's predictions. Confusion counts are pooled across verses before the
    ratio — the same micro-average the headline tier-4 panel uses.
    """
    tp = fp = fn = 0
    for gold, pred in payloads:
        g = detections_covering_type(gold, "rafe")
        p = detections_covering_type(pred, "rafe")
        r = f1_with_tolerance(g, p, tolerance=tolerance)
        tp += r.tp
        fp += r.fp
        fn += r.fn
    # Same "no signal, no error" convention as masoretic_eval.iaa.stratify._f1_over:
    # empty-vs-empty scores 1.0; one side empty against a non-empty other scores 0.0.
    if tp + fp == 0:
        precision = 1.0 if tp + fn == 0 else 0.0
    else:
        precision = tp / (tp + fp)
    if tp + fn == 0:
        recall = 1.0 if tp + fp == 0 else 0.0
    else:
        recall = tp / (tp + fn)
    f1 = 0.0 if (precision + recall) == 0 else 2 * precision * recall / (precision + recall)
    return PrecisionRecallF1(precision=precision, recall=recall, f1=f1, tp=tp, fp=fp, fn=fn)
