from masoretic_eval.composite import Scorer
from masoretic_eval.uxlc_loader import MetaMarkRecord


def test_composite_score_runs_all_4_tiers():
    s = Scorer.from_config("v0.1")
    gt = {
        "text": "בָרֵ֑",   # bet-qamatz + resh-tsere + etnachta
        "metamarks": [MetaMarkRecord("large_letter", "Deut.6.4", 1)],
    }
    pred = {
        "text": "בָרֵ֑",
        "metamarks": [MetaMarkRecord("large_letter", "Deut.6.4", 1)],
    }
    r = s.score(pred=pred, ground_truth=gt)
    assert r.tiers["tier1"].cer == 0.0
    assert r.tiers["tier2"].cer == 0.0
    assert r.tiers["tier3"].cer == 0.0
    assert r.tiers["tier4"].f1 == 1.0
    assert r.composite_cer3 == 0.0


def test_composite_cer3_weighted_average():
    """CER3 = 0.5·cer1 + 0.3·cer2 + 0.2·cer3. Inject known CER values."""
    from masoretic_eval.composite import compute_cer3
    assert abs(compute_cer3(cer1=0.1, cer2=0.2, cer3=0.3) - (0.05 + 0.06 + 0.06)) < 1e-9


def test_oracle_fields_pass_through():
    s = Scorer.from_config("v0.1")
    gt = {"text": "בָ", "metamarks": []}
    pred = {"text": "בָ", "metamarks": []}
    r = s.score(
        pred=pred,
        ground_truth=gt,
        nakdimon_disagreement_rate=0.112,
        dicta_disagreement_rate=0.092,
    )
    assert r.tiers["tier2"].diagnostics["nakdimon_disagreement_rate"] == 0.112
    assert r.tiers["tier2"].diagnostics["dicta_disagreement_rate"] == 0.092
