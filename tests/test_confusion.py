from masoretic_eval.metrics.confusion import build_nikkud_confusion


def test_confusion_captures_qamatz_patach_swap():
    gt = "בָ"    # bet + qamatz (U+05B8)
    pred = "בַ"  # bet + patach (U+05B7)
    m = build_nikkud_confusion(gt, pred)
    # GT qamatz observed as pred patach
    assert m["qamatz"]["patach"] == 1
    assert m["qamatz"]["qamatz"] == 0


def test_confusion_captures_correct_match():
    gt = "בָ"
    pred = "בָ"
    m = build_nikkud_confusion(gt, pred)
    assert m["qamatz"]["qamatz"] == 1


def test_confusion_captures_shva_segol_confusion():
    gt = "בְ"     # shva
    pred = "בֶ"   # segol
    m = build_nikkud_confusion(gt, pred)
    assert m["shva"]["segol"] == 1
