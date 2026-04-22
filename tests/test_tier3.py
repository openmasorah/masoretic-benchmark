from masoretic_eval.tiers.tier3_trop import Tier3Trop


def test_tier3_full_includes_trop():
    t = Tier3Trop()
    gt = "בָ֑"    # bet + qamatz + etnachta
    pred = "בָ"          # no trop
    r = t.score(gt, pred)
    assert r.edits == 1  # missing trop = 1 codepoint edit
    assert r.denominator == 3


def test_tier3_wrong_trop():
    t = Tier3Trop()
    gt = "בָ֑"    # etnachta
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
