from masoretic_eval.tiers.tier2_nikkud import Tier2Nikkud


def test_tier2_includes_nikkud_strips_trop():
    t = Tier2Nikkud()
    # GT has trop U+0591 (etnachta); pred omits it — should NOT count as edit for tier 2.
    gt = "בָ֑"
    pred = "בָ"
    r = t.score(gt, pred)
    assert r.cer == 0.0


def test_tier2_counts_nikkud_substitution():
    """Partial cluster example from spec: bet+qamatz vs bet+patach = 1 codepoint edit over 2."""
    t = Tier2Nikkud()
    gt = "בָ"   # bet + qamatz
    pred = "בַ"  # bet + patach
    r = t.score(gt, pred)
    assert r.edits == 1
    assert r.denominator == 2
    assert r.cer == 0.5


def test_tier2_counts_dagesh():
    t = Tier2Nikkud()
    gt = "בָּ"   # bet + dagesh + qamatz
    pred = "בָ"         # bet + qamatz (dagesh dropped)
    r = t.score(gt, pred)
    assert r.edits == 1
    assert r.denominator == 3


def test_tier2_tier_number_and_name():
    t = Tier2Nikkud()
    assert t.tier_number == 2
    assert t.name == "nikkud"


def test_tier2_strips_paseq_and_sof_pasuq():
    """Mirror loader behavior: paseq (U+05C0) and sof pasuq (U+05C3) are not
    part of the tier-2 scoring surface and must be stripped from both sides."""
    t = Tier2Nikkud()
    gt = "בָ ׀ בַ"   # bet-qamatz, paseq (with space), bet-patach
    pred = "בָ בַ"   # same minus paseq
    r = t.score(gt, pred)
    # After stripping paseq + collapsing no-ops, identical → CER 0.
    assert r.cer == 0.0


def test_tier2_strips_rafe_and_nun_hafukha():
    """Rafe (U+05BF) and nun hafukha (U+05C6) also stripped from tier 2."""
    t = Tier2Nikkud()
    gt = "בָֿ"   # bet + rafe + qamatz
    pred = "בָ"       # bet + qamatz
    r = t.score(gt, pred)
    assert r.cer == 0.0
