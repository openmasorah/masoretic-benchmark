"""Nakdimon DEC / CHA / WOR / VOC factoring (Gershuni & Pinter, NAACL 2022).

Definitions:
- DEC: fraction of consonants for which the predicted vowel-decision class
  matches GT's. A decision class = the set of combining marks attached to
  that consonant (qamatz, patach, tsere, segol, shva, dagesh, etc.).
- CHA: character-level accuracy over full strings (consonants + nikkud).
- WOR: word-level perfect-match accuracy (whole-token equality).
- VOC: character-level accuracy restricted to vocalization codepoints (nikkud).
"""

from __future__ import annotations

from dataclasses import dataclass

from masoretic_eval.normalize import normalize_for_scoring
from masoretic_eval.segment import segment_clusters

VOWEL_RANGE = (0x05B0, 0x05BD)  # vowel points + dagesh
SIN_SHIN_DOTS = (0x05C1, 0x05C2)


@dataclass
class NakdimonResult:
    dec: float
    cha: float
    wor: float
    voc: float


def _is_vowel_codepoint(c: str) -> bool:
    cp = ord(c)
    if VOWEL_RANGE[0] <= cp <= VOWEL_RANGE[1]:
        return True
    if cp in SIN_SHIN_DOTS:
        return True
    return False


def _vowel_decision_class(cluster: str) -> tuple[int, ...]:
    """Sorted tuple of vowel-codepoints in this cluster (the decision)."""
    return tuple(sorted(ord(c) for c in cluster if _is_vowel_codepoint(c)))


def nakdimon_factoring(gt: str, pred: str) -> NakdimonResult:
    gt_n = normalize_for_scoring(gt)
    pred_n = normalize_for_scoring(pred)

    # DEC: per-cluster decision-class match.
    gt_clusters = list(segment_clusters(gt_n))
    pred_clusters = list(segment_clusters(pred_n))

    # Align 1:1 when cluster counts match; else pad shorter side.
    n = max(len(gt_clusters), len(pred_clusters))
    dec_correct = 0
    dec_total = 0
    for i in range(n):
        g = gt_clusters[i] if i < len(gt_clusters) else ""
        p = pred_clusters[i] if i < len(pred_clusters) else ""
        # Skip purely-punctuation clusters from DEC denominator.
        if g and any(0x05D0 <= ord(c) <= 0x05EA for c in g):
            dec_total += 1
            if _vowel_decision_class(g) == _vowel_decision_class(p):
                dec_correct += 1
    dec = dec_correct / dec_total if dec_total else 1.0

    # CHA: character-level over aligned strings (pad shorter).
    cha_total = max(len(gt_n), len(pred_n))
    cha_correct = sum(1 for a, b in zip(gt_n, pred_n, strict=False) if a == b)
    cha = cha_correct / cha_total if cha_total else 1.0

    # WOR: whole-token equality (space-separated tokens).
    gt_tokens = gt_n.split()
    pred_tokens = pred_n.split()
    wor_total = max(len(gt_tokens), len(pred_tokens))
    wor_correct = sum(1 for a, b in zip(gt_tokens, pred_tokens, strict=False) if a == b)
    wor = wor_correct / wor_total if wor_total else 1.0

    # VOC: char-level restricted to vowel codepoints.
    gt_vowels = [c for c in gt_n if _is_vowel_codepoint(c)]
    pred_vowels = [c for c in pred_n if _is_vowel_codepoint(c)]
    voc_total = max(len(gt_vowels), len(pred_vowels))
    voc_correct = sum(1 for a, b in zip(gt_vowels, pred_vowels, strict=False) if a == b)
    voc = voc_correct / voc_total if voc_total else 1.0

    return NakdimonResult(dec=dec, cha=cha, wor=wor, voc=voc)
