from masoretic_eval.tiers.tier1_consonantal import Tier1Consonantal


def test_tier1_strips_nikkud_and_trop_before_scoring():
    t = Tier1Consonantal()
    gt = "בָרֵ"   # בָרֵ
    pred = "בר"               # בר — consonants only
    r = t.score(gt, pred)
    # Both stripped to consonants → identical after strip → CER = 0.
    assert r.cer == 0.0
    assert r.edits == 0
    assert r.denominator == 2  # 2 consonant codepoints


def test_tier1_detects_consonant_substitution():
    t = Tier1Consonantal()
    gt = "בר"    # בר
    pred = "בד"  # בד — resh replaced by dalet
    r = t.score(gt, pred)
    assert r.edits == 1
    assert r.denominator == 2
    assert r.cer == 0.5


def test_tier1_missing_consonant():
    t = Tier1Consonantal()
    gt = "ברא"
    pred = "בר"
    r = t.score(gt, pred)
    assert r.edits == 1
    assert r.denominator == 3


def test_tier1_tier_number_and_name():
    t = Tier1Consonantal()
    assert t.tier_number == 1
    assert t.name == "consonantal"


def test_tier1_strips_paseq_without_leaving_double_space():
    """When paseq (U+05C0) is removed between words, the adjacent spaces
    must collapse — otherwise alignment sees a spurious extra cluster."""
    t = Tier1Consonantal()
    gt = "יהוה ׀ אחד"
    pred = "יהוה אחד"
    r = t.score(gt, pred)
    assert r.cer == 0.0
    assert r.edits == 0
