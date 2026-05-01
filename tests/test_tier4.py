from masoretic_eval.tiers.tier4_metamarks import Tier4MetaMarks
from masoretic_eval.uxlc_loader import MetaMarkRecord


def _rec(type_: str, verse: str, ord_: int) -> MetaMarkRecord:
    return MetaMarkRecord(type=type_, verse_ref=verse, ordinal=ord_)


def test_example1_large_letter_exact_match():
    """Shema's ע at Deut 6:4 — exact TP."""
    t = Tier4MetaMarks()
    gt = [_rec("large_letter", "Deut.6.4", 1)]
    pred = [_rec("large_letter", "Deut.6.4", 1)]
    r = t.score(gt, pred)
    assert r.precision == 1.0
    assert r.recall == 1.0
    assert r.f1 == 1.0


def test_example2_puncta_partial_coverage():
    """Two puncta in Num 3:39; pred emits only one → 1 TP + 1 FN."""
    t = Tier4MetaMarks()
    gt = [_rec("puncta", "Num.3.39", 1), _rec("puncta", "Num.3.39", 2)]
    pred = [_rec("puncta", "Num.3.39", 1)]
    r = t.score(gt, pred)
    assert r.diagnostics["tp_exact"] == 1
    assert r.diagnostics["fn"] == 1
    # precision = 1/1 = 1.0; recall = 1/2 = 0.5; f1 = 0.6667
    assert r.precision == 1.0
    assert r.recall == 0.5
    assert abs(r.f1 - (2 * 1.0 * 0.5 / 1.5)) < 1e-9


def test_example3_paragraph_pe_verse_ref_mismatch_full_miss():
    """Paragraph-pe at Deut 31:29; pred at Deut 31:30 — different verse_ref → 0 TP, 1 FN, 1 FP."""
    t = Tier4MetaMarks()
    gt = [_rec("pe", "Deut.31.29", 1)]
    pred = [_rec("pe", "Deut.31.30", 1)]
    r = t.score(gt, pred)
    assert r.diagnostics["tp_exact"] == 0
    assert r.diagnostics["tp_partial"] == 0
    assert r.diagnostics["fp"] == 1
    assert r.diagnostics["fn"] == 1
    assert r.precision == 0.0
    assert r.recall == 0.0
    assert r.f1 == 0.0


def test_example4_inverted_nun_ordinal_wrong_partial_credit():
    """Inverted nun at Num 10:35 with ordinal mismatch → ⅓ partial TP."""
    t = Tier4MetaMarks()
    gt = [_rec("inverted_nun", "Num.10.35", 1)]
    pred = [_rec("inverted_nun", "Num.10.35", 2)]
    r = t.score(gt, pred)
    assert r.diagnostics["tp_exact"] == 0
    assert r.diagnostics["tp_partial"] == 1
    # precision = (1/3) / 1 = 0.333...; recall = (1/3) / 1 = 0.333...
    assert abs(r.precision - 1.0 / 3.0) < 1e-9
    assert abs(r.recall - 1.0 / 3.0) < 1e-9
    assert abs(r.f1 - 1.0 / 3.0) < 1e-9


def test_example5_false_positive_pure():
    """Prediction invents small_letter at Deut 32:4; GT silent → 0 TP, 1 FP."""
    t = Tier4MetaMarks()
    gt: list[MetaMarkRecord] = []
    pred = [_rec("small_letter", "Deut.32.4", 1)]
    r = t.score(gt, pred)
    assert r.diagnostics["fp"] == 1
    # recall undefined when no GT records; convention: 1.0 when both TP=0 and FN=0,
    # else 0.0. Here TP=0, FN=0 → recall=1.0 (vacuously). But precision=0.
    # F1 with precision=0 → 0.
    assert r.precision == 0.0
    assert r.f1 == 0.0


def test_extra_prediction_at_exact_match_counts_as_false_positive():
    t = Tier4MetaMarks()
    gt = [_rec("inverted_nun", "Num.10.35", 1)]
    pred = [
        _rec("inverted_nun", "Num.10.35", 1),
        _rec("inverted_nun", "Num.10.35", 2),
    ]
    r = t.score(gt, pred)
    assert r.diagnostics["tp_exact"] == 1
    assert r.diagnostics["tp_partial"] == 0
    assert r.diagnostics["fp"] == 1
    assert r.diagnostics["fn"] == 0
    assert r.recall <= 1.0
    assert r.f1 <= 1.0


def test_tier4_metrics_are_bounded_for_representative_cases():
    cases = [
        ([], []),
        (
            [_rec("large_letter", "Deut.6.4", 1)],
            [_rec("large_letter", "Deut.6.4", 1)],
        ),
        (
            [_rec("inverted_nun", "Num.10.35", 1)],
            [_rec("inverted_nun", "Num.10.35", 2)],
        ),
        (
            [_rec("samekh", "Deut.1.1", 1)],
            [_rec("samekh", "Deut.1.1", 1), _rec("samekh", "Deut.1.1", 2)],
        ),
        (
            [_rec("puncta", "Num.3.39", 1), _rec("puncta", "Num.3.39", 2)],
            [_rec("puncta", "Num.3.39", 1)],
        ),
        ([], [_rec("small_letter", "Deut.32.4", 1)]),
    ]
    t = Tier4MetaMarks()
    for gt, pred in cases:
        r = t.score(gt, pred)
        assert 0.0 <= r.precision <= 1.0
        assert 0.0 <= r.recall <= 1.0
        assert 0.0 <= r.f1 <= 1.0


def test_empty_gt_and_empty_pred_is_perfect():
    t = Tier4MetaMarks()
    r = t.score([], [])
    assert r.f1 == 1.0
    assert r.precision == 1.0
    assert r.recall == 1.0
