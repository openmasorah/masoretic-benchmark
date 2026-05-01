"""Schema-level tests for schemas/run_meta.schema.json (D-16/D-19).

Validates the schema itself parses as draft-2020-12, and that it accepts
canonical valid payloads while rejecting D-19 required-field violations.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_META_SCHEMA_PATH = REPO_ROOT / "schemas" / "run_meta.schema.json"


@pytest.fixture(scope="module")
def run_meta_schema() -> dict:
    with open(RUN_META_SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def run_meta_validator(run_meta_schema) -> jsonschema.Draft202012Validator:
    jsonschema.Draft202012Validator.check_schema(run_meta_schema)
    return jsonschema.Draft202012Validator(run_meta_schema)


@pytest.fixture
def valid_run_meta() -> dict:
    return {
        "schema_version": "0.1.0",
        "baseline_id": "biblia_kraken",
        "manifest_hash": "sha256:abc123",
        "scorer_version": "0.1.0",
        "started_at_iso": "2026-04-25T14:00:00Z",
        "completed_at_iso": "2026-04-25T14:05:23Z",
        "hostname": "macbook.local",
        "sibling_git_sha": "abc1234",
        "replay_mode": False,
        "pins": {
            "kraken_model_hash": "deadbeef",
            "nakdimon_model_hash": "8fd7722b8002a690",
            "dictabert_model_revision": None,
            "llm_pin_md_hash": None,
        },
        "budget": {
            "cap_per_folio": None,
            "cap_run": None,
            "used_total": None,
            "rate_table_snapshot": None,
        },
        "combine": {
            "tie_break_total": None,
            "tie_break_winners": None,
        },
        "folios": {
            "leningrad_devarim_F118B_fixture": {
                "budget_used": None,
                "replay_used": None,
                "line_count": 5,
                "scope_check_passed_at_iso": "2026-04-25T14:00:01Z",
            }
        },
    }


def test_schema_parses_as_draft202012(run_meta_schema):
    jsonschema.Draft202012Validator.check_schema(run_meta_schema)


def test_schema_id_is_v010(run_meta_schema):
    assert run_meta_schema["$id"] == "urn:masoretic:run_meta.schema:v0.1.0"


def test_valid_payload_passes(run_meta_validator, valid_run_meta):
    run_meta_validator.validate(valid_run_meta)


def test_missing_pins_kraken_key_rejected(run_meta_validator, valid_run_meta):
    """D-19: pins.kraken_model_hash is REQUIRED key (null is allowed
    as VALUE; missing key is not)."""
    payload = deepcopy(valid_run_meta)
    del payload["pins"]["kraken_model_hash"]
    with pytest.raises(jsonschema.ValidationError) as exc:
        run_meta_validator.validate(payload)
    assert "kraken_model_hash" in str(exc.value)


def test_pins_kraken_null_value_accepted(run_meta_validator, valid_run_meta):
    payload = deepcopy(valid_run_meta)
    payload["pins"]["kraken_model_hash"] = None
    run_meta_validator.validate(payload)


def test_missing_top_level_required_rejected(run_meta_validator, valid_run_meta):
    for required in [
        "schema_version",
        "baseline_id",
        "scorer_version",
        "started_at_iso",
        "completed_at_iso",
        "hostname",
        "sibling_git_sha",
        "replay_mode",
        "pins",
        "budget",
        "combine",
        "folios",
    ]:
        payload = deepcopy(valid_run_meta)
        del payload[required]
        with pytest.raises(jsonschema.ValidationError):
            run_meta_validator.validate(payload)


def test_baseline_id_enum_enforced(run_meta_validator, valid_run_meta):
    payload = deepcopy(valid_run_meta)
    payload["baseline_id"] = "not_a_real_baseline"
    with pytest.raises(jsonschema.ValidationError):
        run_meta_validator.validate(payload)


def test_replay_mode_must_be_bool(run_meta_validator, valid_run_meta):
    payload = deepcopy(valid_run_meta)
    payload["replay_mode"] = "false"
    with pytest.raises(jsonschema.ValidationError):
        run_meta_validator.validate(payload)


def test_combine_tie_break_winners_null_accepted(run_meta_validator, valid_run_meta):
    payload = deepcopy(valid_run_meta)
    payload["combine"]["tie_break_winners"] = None
    run_meta_validator.validate(payload)


def test_combine_tie_break_winners_object_accepted(run_meta_validator, valid_run_meta):
    payload = deepcopy(valid_run_meta)
    payload["combine"]["tie_break_total"] = 5
    payload["combine"]["tie_break_winners"] = {"claude": 3, "gemini": 2}
    run_meta_validator.validate(payload)


def test_combine_tie_break_winners_partial_object_rejected(run_meta_validator, valid_run_meta):
    """If tie_break_winners is an object, it MUST have both claude AND gemini."""
    payload = deepcopy(valid_run_meta)
    payload["combine"]["tie_break_winners"] = {"claude": 3}
    with pytest.raises(jsonschema.ValidationError):
        run_meta_validator.validate(payload)


def test_combine_tie_break_winners_extra_key_rejected(run_meta_validator, valid_run_meta):
    payload = deepcopy(valid_run_meta)
    payload["combine"]["tie_break_winners"] = {
        "claude": 3,
        "gemini": 2,
        "abbyy": 1,  # dropped per A-2
    }
    with pytest.raises(jsonschema.ValidationError):
        run_meta_validator.validate(payload)


def test_budget_inner_keys_required(run_meta_validator, valid_run_meta):
    """budget is REQUIRED at top level; each inner key is also required
    even though values may be null."""
    for key in ["cap_per_folio", "cap_run", "used_total", "rate_table_snapshot"]:
        payload = deepcopy(valid_run_meta)
        del payload["budget"][key]
        with pytest.raises(jsonschema.ValidationError):
            run_meta_validator.validate(payload)


def test_pins_inner_keys_required(run_meta_validator, valid_run_meta):
    for key in [
        "kraken_model_hash",
        "nakdimon_model_hash",
        "dictabert_model_revision",
        "llm_pin_md_hash",
    ]:
        payload = deepcopy(valid_run_meta)
        del payload["pins"][key]
        with pytest.raises(jsonschema.ValidationError):
            run_meta_validator.validate(payload)


def test_folio_inner_required(run_meta_validator, valid_run_meta):
    for key in ["budget_used", "replay_used", "line_count", "scope_check_passed_at_iso"]:
        payload = deepcopy(valid_run_meta)
        del payload["folios"]["leningrad_devarim_F118B_fixture"][key]
        with pytest.raises(jsonschema.ValidationError):
            run_meta_validator.validate(payload)


def test_folio_line_count_must_be_nonnegative(run_meta_validator, valid_run_meta):
    payload = deepcopy(valid_run_meta)
    payload["folios"]["leningrad_devarim_F118B_fixture"]["line_count"] = -1
    with pytest.raises(jsonschema.ValidationError):
        run_meta_validator.validate(payload)


def test_schema_version_pinned_to_010(run_meta_validator, valid_run_meta):
    payload = deepcopy(valid_run_meta)
    payload["schema_version"] = "0.2.0"
    with pytest.raises(jsonschema.ValidationError):
        run_meta_validator.validate(payload)


def test_additional_top_level_property_rejected(run_meta_validator, valid_run_meta):
    payload = deepcopy(valid_run_meta)
    payload["bonus_field"] = "nope"
    with pytest.raises(jsonschema.ValidationError):
        run_meta_validator.validate(payload)


def test_manifest_hash_null_rejected(run_meta_validator, valid_run_meta):
    payload = deepcopy(valid_run_meta)
    payload["manifest_hash"] = None
    with pytest.raises(jsonschema.ValidationError):
        run_meta_validator.validate(payload)


def test_zero_folios_allowed(run_meta_validator, valid_run_meta):
    payload = deepcopy(valid_run_meta)
    payload["folios"] = {}
    run_meta_validator.validate(payload)
