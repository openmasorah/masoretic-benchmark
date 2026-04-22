from masoretic_eval.metrics.cer import cluster_aligned_cer


def test_identical_strings_have_zero_cer():
    gt = "בָרֵ"  # בָרֵ
    pred = "בָרֵ"
    r = cluster_aligned_cer(gt, pred)
    assert r.cer == 0.0
    assert r.edits == 0
    assert r.denominator == 4


def test_partial_cluster_substitution_counts_one_codepoint_edit():
    """Spec Section 4 invariant #4: bet+qamatz vs bet+patach = 1 codepoint edit over 2 cps."""
    gt = "בָ"   # bet + qamatz
    pred = "בַ"  # bet + patach
    r = cluster_aligned_cer(gt, pred)
    assert r.edits == 1
    assert r.denominator == 2
    assert r.cer == 0.5


def test_missing_cluster_contributes_all_codepoints_as_edits():
    # GT has one extra cluster of 2 codepoints that pred omits.
    gt = "בָרֵ"     # בָרֵ (2 clusters, 4 codepoints)
    pred = "בָ"                # בָ (1 cluster, 2 codepoints)
    r = cluster_aligned_cer(gt, pred)
    # The missing רֵ cluster contributes 2 codepoint edits (deletion).
    assert r.edits == 2
    assert r.denominator == 4
    assert r.cer == 0.5


def test_extra_cluster_in_prediction_contributes_codepoints_as_edits():
    gt = "בָ"
    pred = "בָרֵ"
    r = cluster_aligned_cer(gt, pred)
    # Prediction has an extra cluster — inserted, 2 codepoints edit.
    assert r.edits == 2
    # Denominator is GT codepoints only.
    assert r.denominator == 2
    assert r.cer == 1.0


def test_empty_gt_denominator_is_zero_and_cer_defined_as_zero_when_pred_also_empty():
    r = cluster_aligned_cer("", "")
    assert r.denominator == 0
    assert r.cer == 0.0


def test_empty_gt_nonempty_pred_raises_or_returns_defined_cer():
    # When GT is empty but prediction is not, CER is undefined by division.
    # Spec: we treat this as cer=1.0 when denominator=0 and edits>0.
    r = cluster_aligned_cer("", "בָ")
    assert r.denominator == 0
    assert r.edits == 2
    assert r.cer == 1.0


def test_three_way_substitution_counts_codepoints_within_clusters():
    # GT: בָ רֵ  (2 clusters, 4 codepoints)
    # Pred: בַ רַ (2 clusters, 4 codepoints). Both nikkud differ.
    gt = "בָרֵ"
    pred = "בַרַ"
    r = cluster_aligned_cer(gt, pred)
    assert r.edits == 2  # two nikkud substitutions within aligned clusters
    assert r.denominator == 4
    assert r.cer == 0.5
