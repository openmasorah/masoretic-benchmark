from masoretic_eval.metrics.confusion import build_nikkud_confusion


def test_confusion_captures_qamatz_patach_swap():
    gt = "בָ"  # bet + qamatz (U+05B8)
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
    gt = "בְ"  # shva
    pred = "בֶ"  # segol
    m = build_nikkud_confusion(gt, pred)
    assert m["shva"]["segol"] == 1


def test_confusion_deletion_does_not_cascade():
    # gt has two clusters; pred dropped the FIRST consonant. Positional pairing
    # fabricates a qamatz->tsere substitution; cluster alignment must not.
    gt = "בָרֵ"  # bet+qamatz, resh+tsere
    pred = "רֵ"  # resh+tsere (first cluster deleted)
    m = build_nikkud_confusion(gt, pred)
    assert m["qamatz"]["__absent__"] == 1  # the deleted cluster's vowel
    assert m["tsere"]["tsere"] == 1  # the surviving cluster still matches
    assert m["qamatz"]["tsere"] == 0  # no fabricated substitution


def test_confusion_surplus_pred_mark_is_recorded_not_dropped():
    # pred hallucinates a dagesh the GT lacks. The old positional zip truncated
    # the surplus pred mark; it must be recorded as __absent__ -> dagesh.
    gt = "בַ"  # bet+patach
    pred = "בַּ"  # bet+patach+dagesh
    m = build_nikkud_confusion(gt, pred)
    assert m["patach"]["patach"] == 1
    assert m["__absent__"]["dagesh"] == 1


def test_confusion_within_cluster_marks_matched_as_multiset():
    # gt=dagesh+qamatz, pred=dagesh only. The dagesh matches; the qamatz is
    # omitted. Positional pairing mis-reports qamatz->dagesh + dagesh->absent.
    gt = "בָּ"  # bet+dagesh+qamatz
    pred = "בּ"  # bet+dagesh
    m = build_nikkud_confusion(gt, pred)
    assert m["dagesh"]["dagesh"] == 1
    assert m["qamatz"]["__absent__"] == 1
    assert m["qamatz"]["dagesh"] == 0
