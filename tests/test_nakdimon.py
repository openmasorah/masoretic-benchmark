from masoretic_eval.metrics.nakdimon import nakdimon_factoring


def test_identical_strings_all_metrics_perfect():
    gt = "בָרֵ"
    pred = "בָרֵ"
    r = nakdimon_factoring(gt, pred)
    assert r.dec == 1.0
    assert r.cha == 1.0
    assert r.wor == 1.0
    assert r.voc == 1.0


def test_single_nikkud_substitution_lowers_dec():
    # bet+qamatz vs bet+patach — DEC counts vowel-decision accuracy.
    gt = "בָ"  # bet + qamatz
    pred = "בַ"  # bet + patach
    r = nakdimon_factoring(gt, pred)
    # One consonant, one wrong decision → DEC = 0.
    assert r.dec == 0.0
    # CHA at char level: same shape — one char right (bet), one char wrong (nikkud).
    # Denominator 2, correct 1 → 0.5.
    assert r.cha == 0.5


def test_wor_is_zero_if_any_token_mismatch():
    # Two "words" (space-separated), only one matches.
    gt = "בָ רֵ"
    pred = "בָ רַ"  # second word nikkud differs
    r = nakdimon_factoring(gt, pred)
    assert r.wor == 0.5


def test_voc_counts_vocalization_chars_only():
    # VOC is char accuracy restricted to vowel/dagesh codepoints.
    gt = "בָרֵ"  # 2 vowel chars
    pred = "בַרֵ"  # 1 vowel wrong
    r = nakdimon_factoring(gt, pred)
    assert r.voc == 0.5


def test_trop_only_difference_is_perfect_at_tier2():
    # A trop (tier-3) mark present in GT but absent in pred is NOT a tier-2
    # error: the tier-2 CER is 0, so the tier-2 diagnostics must agree. Before
    # the fix, CHA/WOR were computed on raw text and counted the trop.
    gt = "בָ֣"  # bet+qamatz+munach (trop U+05A3)
    pred = "בָ"  # same minus the trop
    r = nakdimon_factoring(gt, pred)
    assert r.dec == 1.0
    assert r.cha == 1.0
    assert r.wor == 1.0
    assert r.voc == 1.0


def test_dec_insertion_does_not_cascade():
    # pred has a spurious leading consonant; every real consonant after it is
    # correctly vocalized. Positional pairing would mark them all wrong.
    gt = "בַגַ"  # bet+patach, gimel+patach
    pred = "אבַגַ"  # spurious leading alef, then the correct two clusters
    r = nakdimon_factoring(gt, pred)
    assert r.dec == 1.0
