"""A2a — human-vs-consensus-gold CER decomposition.

Covers the ``TierCERResult.cer_vs_gold`` field added for the v3.1/v4 paper:
each annotator's round-0 chunk scored against a consensus-gold reference, with
**gold as the CER reference** (denominator = gold length). The decomposition is
computed in the shared ``_compute_from_verse_data`` kernel, so these hermetic
tests exercise it directly with synthetic chunks (no UXLC / projection I/O).

Invariants pinned here:

1. ``cer_vs_gold`` is ``None`` when no gold reference is supplied (the default;
   keeps the pair-CER path and the byte-identity cross-path contract intact).
2. When supplied, ``cer_vs_gold`` is ``{"a": TierCERResult, "b": TierCERResult}``
   on each of tier 1/2/3, and the nested sub-results are themselves ``None`` for
   ``cer_vs_gold`` (no recursion in practice).
3. An annotator whose chunk equals the gold chunk scores CER 0 against gold.
4. Gold-as-reference orientation: a single side-only insertion yields
   CER = 1 / len(gold_consonants), not 1 / len(side_consonants).
"""

from __future__ import annotations

from masoretic_eval.iaa.compute import _compute_from_verse_data
from masoretic_eval.iaa.result import TierCERResult

# Two-verse, single-folio synthetic. Consonants only (tier-1 view keeps
# U+05D0..U+05EA + space + maqaf). Verse 1: A == gold; B has one extra
# consonant inserted. Verse 2: all three identical.
_GOLD = {
    "Deut.1.1": "אבגדה והזחט",  # 8 consonants
    "Deut.1.2": "כלמנ",  # 4 consonants
}
_A = {
    "Deut.1.1": "אבגדה והזחט",  # identical to gold
    "Deut.1.2": "כלמנ",
}
_B = {
    "Deut.1.1": "אבגדה ווהזחט",  # one extra ו inserted → +1 consonant vs gold
    "Deut.1.2": "כלמנ",
}

_VERSE_FOLIO_MAP = [("Deut.1.1", "F1"), ("Deut.1.2", "F1")]


def _kernel(with_gold: bool):
    a_records = {v: [] for v, _ in _VERSE_FOLIO_MAP}
    b_records = {v: [] for v, _ in _VERSE_FOLIO_MAP}
    n_cons = {v: len([c for c in _GOLD[v] if "א" <= c <= "ת"]) for v, _ in _VERSE_FOLIO_MAP}
    chunks = {v: (f, _A[v], _B[v]) for v, f in _VERSE_FOLIO_MAP}
    return _compute_from_verse_data(
        verse_folio_map=_VERSE_FOLIO_MAP,
        a_records_by_verse=a_records,
        b_records_by_verse=b_records,
        n_cons_by_verse=n_cons,
        chunks_by_verse=chunks,
        bootstrap_b=200,
        bootstrap_seed=0xBEEF,
        metadata_extra={},
        gold_chunks_by_verse={v: _GOLD[v] for v, _ in _VERSE_FOLIO_MAP} if with_gold else None,
    )


def test_cer_vs_gold_none_by_default():
    res = _kernel(with_gold=False)
    for tier in (res.tier1, res.tier2, res.tier3):
        assert tier.cer_vs_gold is None


def test_cer_vs_gold_shape_and_no_recursion():
    res = _kernel(with_gold=True)
    for tier in (res.tier1, res.tier2, res.tier3):
        assert tier.cer_vs_gold is not None
        assert set(tier.cer_vs_gold) == {"a", "b"}
        for side in ("a", "b"):
            sub = tier.cer_vs_gold[side]
            assert isinstance(sub, TierCERResult)
            # No recursion: nested sub-results don't carry their own gold block.
            assert sub.cer_vs_gold is None
            assert set(sub.cer_per_folio) == {"F1"}


def test_annotator_equal_to_gold_scores_zero():
    res = _kernel(with_gold=True)
    # A is byte-identical to gold on both verses → CER 0 at every tier.
    for tier in (res.tier1, res.tier2, res.tier3):
        assert tier.cer_vs_gold["a"].cer_overall.point == 0.0


def test_gold_is_the_cer_reference_denominator():
    res = _kernel(with_gold=True)
    # Verse-1 gold tier-1 view "אבגדה והזחט" = 10 consonants + 1 space = 11
    # clusters; B inserts one consonant → 1 edit. CER = 1/11. Verse 2 identical
    # → CER 0. Macro overall = (1/11 + 0) / 2 = 0.0454545…
    # If the denominator were the 12-cluster B side, verse-1 CER would be 1/12
    # and the macro overall 0.041667 — this asserts GOLD is the reference.
    overall = res.tier1.cer_vs_gold["b"].cer_overall.point
    assert abs(overall - (1.0 / 11.0) / 2.0) < 1e-9
    assert abs(overall - (1.0 / 12.0) / 2.0) > 1e-3  # not B-as-reference
