"""Schema-level tests for schemas/baseline_prediction.schema.json (D-16/D-17).

Validates the schema itself parses as draft-2020-12, and that it accepts
canonical valid payloads while rejecting D-17 shape violations.

Pairs with test_run_meta_schema.py and test_schema_module.py.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PREDICTION_SCHEMA_PATH = REPO_ROOT / "schemas" / "baseline_prediction.schema.json"


@pytest.fixture(scope="module")
def prediction_schema() -> dict:
    with open(PREDICTION_SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def prediction_validator(prediction_schema) -> jsonschema.Draft202012Validator:
    jsonschema.Draft202012Validator.check_schema(prediction_schema)
    return jsonschema.Draft202012Validator(prediction_schema)


@pytest.fixture
def valid_prediction() -> dict:
    return {
        "schema_version": "0.1.0",
        "baseline_id": "biblia_kraken",
        "folio_id": "leningrad_devarim_F118B_fixture",
        "manifest_hash": "sha256:abc123",
        "run_meta_ref": "run_meta.json",
        "lines": [
            {
                "line_id": "leningrad_devarim_F118B_fixture_L001",
                "bbox": [10, 20, 500, 60],
                "tier1": "שמע ישראל",
                "tier2": "שְׁמַע יִשְׂרָאֵל",
                "tier3": "שְׁמַ֖ע יִשְׂרָאֵ֑ל",
                "tier4_records": [],
                "kraken_confidence": 0.93,
            }
        ],
    }


def test_schema_parses_as_draft202012(prediction_schema):
    jsonschema.Draft202012Validator.check_schema(prediction_schema)


def test_schema_id_is_v010(prediction_schema):
    assert prediction_schema["$id"] == "urn:masoretic:baseline_prediction.schema:v0.1.0"


def test_valid_payload_passes(prediction_validator, valid_prediction):
    prediction_validator.validate(valid_prediction)


def test_missing_lines_rejected(prediction_validator, valid_prediction):
    payload = deepcopy(valid_prediction)
    del payload["lines"]
    with pytest.raises(jsonschema.ValidationError, match=r"'lines' is a required"):
        prediction_validator.validate(payload)


def test_bbox_must_be_4_ints(prediction_validator, valid_prediction):
    payload = deepcopy(valid_prediction)
    payload["lines"][0]["bbox"] = [10, 20, 500]
    with pytest.raises(jsonschema.ValidationError) as exc:
        prediction_validator.validate(payload)
    assert "bbox" in str(exc.value) or exc.value.validator in ("minItems", "maxItems")


def test_kraken_confidence_capped_at_1(prediction_validator, valid_prediction):
    payload = deepcopy(valid_prediction)
    payload["lines"][0]["kraken_confidence"] = 1.5
    with pytest.raises(jsonschema.ValidationError) as exc:
        prediction_validator.validate(payload)
    assert exc.value.validator == "maximum" or "kraken_confidence" in str(exc.value)


def test_kraken_confidence_negative_rejected(prediction_validator, valid_prediction):
    payload = deepcopy(valid_prediction)
    payload["lines"][0]["kraken_confidence"] = -0.1
    with pytest.raises(jsonschema.ValidationError):
        prediction_validator.validate(payload)


def test_baseline_id_enum_enforced(prediction_validator, valid_prediction):
    payload = deepcopy(valid_prediction)
    payload["baseline_id"] = "abbyy_llm"  # dropped per A-2
    with pytest.raises(jsonschema.ValidationError):
        prediction_validator.validate(payload)


def test_schema_version_pinned_to_010(prediction_validator, valid_prediction):
    payload = deepcopy(valid_prediction)
    payload["schema_version"] = "0.2.0"
    with pytest.raises(jsonschema.ValidationError):
        prediction_validator.validate(payload)


def test_run_meta_ref_pinned(prediction_validator, valid_prediction):
    payload = deepcopy(valid_prediction)
    payload["run_meta_ref"] = "other.json"
    with pytest.raises(jsonschema.ValidationError):
        prediction_validator.validate(payload)


def test_additional_top_level_property_rejected(prediction_validator, valid_prediction):
    payload = deepcopy(valid_prediction)
    payload["bonus_field"] = "nope"
    with pytest.raises(jsonschema.ValidationError):
        prediction_validator.validate(payload)


def test_llm_winner_enum_claude_or_gemini(prediction_validator, valid_prediction):
    payload = deepcopy(valid_prediction)
    payload["baseline_id"] = "llm_vision"
    del payload["lines"][0]["kraken_confidence"]
    payload["lines"][0]["llm_winner"] = "abbyy"  # dropped per A-2
    payload["lines"][0]["llm_tie_breaks"] = 1
    with pytest.raises(jsonschema.ValidationError):
        prediction_validator.validate(payload)


def test_llm_winner_claude_accepted(prediction_validator, valid_prediction):
    payload = deepcopy(valid_prediction)
    payload["baseline_id"] = "llm_vision"
    del payload["lines"][0]["kraken_confidence"]
    payload["lines"][0]["llm_winner"] = "claude"
    payload["lines"][0]["llm_tie_breaks"] = 0
    prediction_validator.validate(payload)


def test_tier4_record_shape_enforced(prediction_validator, valid_prediction):
    payload = deepcopy(valid_prediction)
    payload["lines"][0]["tier4_records"] = [
        {"type": "large_letter", "verse_ref": "Deut.6.4", "ordinal": 1}
    ]
    prediction_validator.validate(payload)


@pytest.mark.parametrize(
    "legacy_type",
    ["PE", "SAMEKH", "LARGE", "SMALL", "INV_NUN", "PUNCTA", "SUSPENDED"],
)
def test_tier4_record_legacy_uppercase_types_rejected(
    prediction_validator, valid_prediction, legacy_type
):
    payload = deepcopy(valid_prediction)
    payload["lines"][0]["tier4_records"] = [
        {"type": legacy_type, "verse_ref": "Deut.6.4", "ordinal": 1}
    ]
    with pytest.raises(jsonschema.ValidationError):
        prediction_validator.validate(payload)


def test_tier4_record_unknown_type_rejected(prediction_validator, valid_prediction):
    payload = deepcopy(valid_prediction)
    payload["lines"][0]["tier4_records"] = [
        {"type": "MYSTERY", "verse_ref": "Deut.6.4", "ordinal": 1}
    ]
    with pytest.raises(jsonschema.ValidationError):
        prediction_validator.validate(payload)


def test_tier4_record_ordinal_must_be_positive(prediction_validator, valid_prediction):
    payload = deepcopy(valid_prediction)
    payload["lines"][0]["tier4_records"] = [
        {"type": "large_letter", "verse_ref": "Deut.6.4", "ordinal": 0}
    ]
    with pytest.raises(jsonschema.ValidationError):
        prediction_validator.validate(payload)


def test_manifest_hash_nullable(prediction_validator, valid_prediction):
    payload = deepcopy(valid_prediction)
    payload["manifest_hash"] = None
    prediction_validator.validate(payload)


def test_empty_lines_array_allowed(prediction_validator, valid_prediction):
    payload = deepcopy(valid_prediction)
    payload["lines"] = []
    prediction_validator.validate(payload)
