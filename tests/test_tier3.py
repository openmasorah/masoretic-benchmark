from masoretic_eval.tiers.tier3_trop import Tier3Trop


def test_tier3_full_includes_trop():
    t = Tier3Trop()
    gt = "בָ֑"  # bet + qamatz + etnachta
    pred = "בָ"  # no trop
    r = t.score(gt, pred)
    assert r.edits == 1  # missing trop = 1 codepoint edit
    assert r.denominator == 3


def test_tier3_retains_meteg():
    """Meteg / ga'ya (U+05BD) is RETAINED at tier 3 (stripped only at tier 2 —
    DECISIONS.md 2026-06-15). Tier 3 = all-codepoints, so dropping meteg is a
    scored edit here. Counterpart to test_tier2.test_tier2_strips_meteg."""
    t = Tier3Trop()
    bet, qamatz, meteg = "ב", "ָ", "ֽ"
    gt = bet + qamatz + meteg  # bet + qamatz + meteg
    pred = bet + qamatz  # meteg dropped
    r = t.score(gt, pred)
    assert r.edits == 1  # missing meteg = 1 codepoint edit at tier 3
    assert r.denominator == 3


def test_tier3_wrong_trop():
    t = Tier3Trop()
    gt = "בָ֑"  # etnachta
    pred = "בָ֒"  # segolta
    r = t.score(gt, pred)
    assert r.edits == 1
    assert r.denominator == 3


def test_tier3_identity():
    t = Tier3Trop()
    gt = "בָ֑"
    pred = "בָ֑"
    r = t.score(gt, pred)
    assert r.cer == 0.0
