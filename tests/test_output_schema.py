import json

from masoretic_eval import __version__
from masoretic_eval.composite import Scorer
from masoretic_eval.output_schema import serialize


def test_output_schema_contains_required_fields():
    s = Scorer.from_config("v0.1")
    gt = {"text": "בָ", "metamarks": []}
    pred = {"text": "בָ", "metamarks": []}
    r = s.score(pred=pred, ground_truth=gt)
    obj = serialize(
        result=r,
        prediction_id="test-0001",
        gt_version="v0.1.0",
    )
    assert obj["scorer_version"] == __version__
    assert obj["gt_version"] == "v0.1.0"
    assert obj["normalization"] == "NFD (scoring) / LC-order (raw GT)"
    assert obj["denominator_policy"] == {
        "tier1": "consonants_only",
        "tier2": "consonants+nikkud",
        "tier3": "full",
    }
    assert obj["qere_ketiv_policy"] == "score_against_qere"
    assert "tier1" in obj["tiers"]
    assert "tier4" in obj["tiers"]
    assert obj["composite"]["cer3"] == 0.0


def test_output_serializes_to_valid_json():
    s = Scorer.from_config("v0.1")
    gt = {"text": "בָ", "metamarks": []}
    pred = {"text": "בָ", "metamarks": []}
    r = s.score(pred=pred, ground_truth=gt)
    obj = serialize(result=r, prediction_id="x", gt_version="v0.1.0")
    # Round-trip through JSON.
    dumped = json.dumps(obj)
    restored = json.loads(dumped)
    assert restored["prediction_id"] == "x"


def test_caveats_include_reproducibility_note():
    s = Scorer.from_config("v0.1")
    gt = {"text": "בָ", "metamarks": []}
    pred = {"text": "בָ", "metamarks": []}
    r = s.score(
        pred=pred,
        ground_truth=gt,
        nakdimon_disagreement_rate=0.1,
        dicta_disagreement_rate=0.1,
    )
    obj = serialize(result=r, prediction_id="x", gt_version="v0.1.0")
    caveats = obj["caveats"]
    assert any("nakdimon" in c.lower() for c in caveats)
    assert any("dicta" in c.lower() for c in caveats)
