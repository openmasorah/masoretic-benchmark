"""Nakdimon DEC / CHA / WOR / VOC factoring (Gershuni & Pinter, NAACL 2022).

Definitions:
- DEC: fraction of consonants for which the predicted vowel-decision class
  matches GT's. A decision class = the set of combining marks attached to
  that consonant (qamatz, patach, tsere, segol, shva, dagesh, etc.).
- CHA: character-level accuracy over full strings (consonants + nikkud).
- WOR: word-level perfect-match accuracy (whole-token equality).
- VOC: character-level accuracy restricted to vocalization codepoints (nikkud).

All four are tier-2 diagnostics, so they are computed on the tier-2 view
(strip_for_tier2) — matching the tier-2 score, which excludes trop (tier 3) and
rafe (tier 4). DEC/CHA/VOC pair clusters via the same Needleman-Wunsch alignment
the tier CER uses, so a single inserted/deleted cluster does not cascade-misalign
every later pair (the prior implementation paired by raw positional index).
"""

from __future__ import annotations

from dataclasses import dataclass

from masoretic_eval.metrics.cer import _cluster_align
from masoretic_eval.normalize import normalize_for_scoring
from masoretic_eval.segment import segment_clusters
from masoretic_eval.strip import strip_for_tier2

VOWEL_RANGE = (0x05B0, 0x05BD)  # vowel points + dagesh + meteg
SIN_SHIN_DOTS = (0x05C1, 0x05C2)
QAMATS_QATAN = 0x05C7  # retained by the tier-2 view; classed as a vowel here


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
    if cp == QAMATS_QATAN:
        return True
    return False


def _vowel_decision_class(cluster: str) -> tuple[int, ...]:
    """Sorted tuple of vowel-codepoints in this cluster (the decision)."""
    return tuple(sorted(ord(c) for c in cluster if _is_vowel_codepoint(c)))


def _has_consonant(cluster: str) -> bool:
    return any(0x05D0 <= ord(c) <= 0x05EA for c in cluster)


def nakdimon_factoring(gt: str, pred: str) -> NakdimonResult:
    gt_n = strip_for_tier2(normalize_for_scoring(gt))
    pred_n = strip_for_tier2(normalize_for_scoring(pred))

    gt_clusters = list(segment_clusters(gt_n))
    pred_clusters = list(segment_clusters(pred_n))
    alignment = _cluster_align(gt_clusters, pred_clusters)

    dec_correct = dec_total = 0
    cha_correct = cha_total = 0
    voc_correct = voc_total = 0
    for g, p in alignment:
        g = g or ""
        p = p or ""
        # DEC: per GT consonant cluster, decision-class match.
        if _has_consonant(g):
            dec_total += 1
            if _vowel_decision_class(g) == _vowel_decision_class(p):
                dec_correct += 1
        # CHA: codepoint accuracy within the aligned pair (clusters are NFD
        # canonical-ordered, so positional comparison inside a cluster is valid;
        # alignment across clusters prevents insertion/deletion cascade).
        cha_total += max(len(g), len(p))
        cha_correct += sum(1 for a, b in zip(g, p, strict=False) if a == b)
        # VOC: same, restricted to vocalization codepoints.
        g_v = [c for c in g if _is_vowel_codepoint(c)]
        p_v = [c for c in p if _is_vowel_codepoint(c)]
        voc_total += max(len(g_v), len(p_v))
        voc_correct += sum(1 for a, b in zip(g_v, p_v, strict=False) if a == b)

    dec = dec_correct / dec_total if dec_total else 1.0
    cha = cha_correct / cha_total if cha_total else 1.0
    voc = voc_correct / voc_total if voc_total else 1.0

    # WOR: whole-token equality on the tier-2 view (space-separated tokens).
    gt_tokens = gt_n.split()
    pred_tokens = pred_n.split()
    wor_total = max(len(gt_tokens), len(pred_tokens))
    wor_correct = sum(1 for a, b in zip(gt_tokens, pred_tokens, strict=False) if a == b)
    wor = wor_correct / wor_total if wor_total else 1.0

    return NakdimonResult(dec=dec, cha=cha, wor=wor, voc=voc)
