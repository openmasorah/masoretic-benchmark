"""Tests for baselines._schema validators + SandboxRun write-time wiring.

Two layers covered:

1. validate_prediction / validate_run_meta — pure JSON Schema wrappers.
2. SandboxRun.write_prediction / write_diagnostic / write_run_meta —
   wired to call the validators BEFORE the atomic write, so an off-shape
   payload raises ValidationError and never reaches results/<bl>/.

Mirrors test_prediction_schema.py / test_run_meta_schema.py fixtures.
"""

from __future__ import annotations

from copy import deepcopy

import jsonschema
import pytest
from baselines._atomic import SandboxRun
from baselines._run_meta import write_run_meta as run_meta_writer
from baselines._schema import validate_prediction, validate_run_meta


@pytest.fixture
def valid_prediction() -> dict:
    return {
        "schema_version": "0.1.0",
        "baseline_id": "biblia_kraken",
        "folio_id": "leningrad_devarim_shema_fixture",
        "manifest_hash": "sha256:abc",
        "run_meta_ref": "run_meta.json",
        "lines": [
            {
                "line_id": "leningrad_devarim_shema_fixture_L001",
                "bbox": [10, 20, 500, 60],
                "tier1": "שמע ישראל",
                "tier2": "שְׁמַע יִשְׂרָאֵל",
                "tier3": "שְׁמַע יִשְׂרָאֵל",
                "tier4_records": [],
                "kraken_confidence": 0.93,
            }
        ],
    }


@pytest.fixture
def valid_run_meta() -> dict:
    return {
        "schema_version": "0.1.0",
        "baseline_id": "biblia_kraken",
        "manifest_hash": "sha256:abc",
        "scorer_version": "0.1.0",
        "started_at_iso": "2026-04-25T14:00:00Z",
        "completed_at_iso": "2026-04-25T14:05:23Z",
        "hostname": "macbook.local",
        "sibling_git_sha": "abc1234",
        "replay_mode": False,
        "pins": {
            "kraken_model_hash": "deadbeef",
            "nakdimon_model_hash": None,
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
            "leningrad_devarim_shema_fixture": {
                "budget_used": None,
                "replay_used": None,
                "line_count": 5,
                "scope_check_passed_at_iso": "2026-04-25T14:00:01Z",
            }
        },
    }


# -- pure validator behavior ------------------------------------------------


def test_validate_prediction_accepts_valid(valid_prediction):
    assert validate_prediction(valid_prediction) is None


def test_validate_prediction_rejects_missing_lines(valid_prediction):
    payload = deepcopy(valid_prediction)
    del payload["lines"]
    with pytest.raises(jsonschema.ValidationError, match=r"'lines' is a required"):
        validate_prediction(payload)


def test_validate_prediction_rejects_short_bbox(valid_prediction):
    payload = deepcopy(valid_prediction)
    payload["lines"][0]["bbox"] = [1, 2, 3]
    with pytest.raises(jsonschema.ValidationError):
        validate_prediction(payload)


def test_validate_run_meta_accepts_valid(valid_run_meta):
    assert validate_run_meta(valid_run_meta) is None


def test_validate_run_meta_rejects_missing_pins_kraken_key(valid_run_meta):
    payload = deepcopy(valid_run_meta)
    del payload["pins"]["kraken_model_hash"]
    with pytest.raises(jsonschema.ValidationError) as exc:
        validate_run_meta(payload)
    assert "kraken_model_hash" in str(exc.value)


def test_validate_run_meta_accepts_null_pin_value(valid_run_meta):
    """null is a valid VALUE; missing KEY is not."""
    payload = deepcopy(valid_run_meta)
    payload["pins"]["kraken_model_hash"] = None
    assert validate_run_meta(payload) is None


# -- SandboxRun wiring (D-14 + D-16 defense-in-depth) ------------------------


def test_sandbox_write_prediction_validates_before_write(tmp_path, valid_prediction):
    """Off-shape payload raises ValidationError BEFORE atomic write.
    Sandbox is preserved (D-14 leave-for-inspection), but no .json file
    is written for that folio."""
    bad = deepcopy(valid_prediction)
    bad["lines"][0]["bbox"] = [1, 2, 3]  # too short

    with SandboxRun(tmp_path, "biblia_kraken") as sb:
        with pytest.raises(jsonschema.ValidationError):
            sb.write_prediction("leningrad_devarim_shema_fixture", bad)
        # Sandbox dir exists (entered) but no folio file landed.
        sandbox_files = sorted(p.name for p in sb.sandbox_dir.glob("*.json"))
        assert sandbox_files == []
        # And no .json.tmp leftover either (atomic-write idiom).
        tmps = sorted(p.name for p in sb.sandbox_dir.glob("*.json.tmp"))
        assert tmps == []

    # Final dir was never touched.
    final_dir = tmp_path / "biblia_kraken"
    assert not final_dir.exists() or not any(final_dir.iterdir())


def test_sandbox_write_prediction_succeeds_for_valid(tmp_path, valid_prediction):
    with SandboxRun(tmp_path, "biblia_kraken") as sb:
        path = sb.write_prediction("leningrad_devarim_shema_fixture", valid_prediction)
        assert path.exists()
        assert path.parent == sb.sandbox_dir


def test_sandbox_write_diagnostic_validates_before_write(tmp_path, valid_prediction):
    """write_diagnostic uses the same prediction shape (D-01)."""
    bad = deepcopy(valid_prediction)
    del bad["lines"]

    with SandboxRun(tmp_path, "biblia_nakdimon") as sb:
        with pytest.raises(jsonschema.ValidationError):
            sb.write_diagnostic("leningrad_devarim_shema_fixture", bad)
        diag_dir = sb.sandbox_dir / "diagnostic"
        # diag_dir may or may not exist (mkdir runs before validation),
        # but no .json file should be inside it.
        if diag_dir.exists():
            written = sorted(p.name for p in diag_dir.glob("*.json"))
            assert written == []


def test_sandbox_write_run_meta_validates_before_write(tmp_path, valid_run_meta):
    bad = deepcopy(valid_run_meta)
    del bad["pins"]["kraken_model_hash"]

    with SandboxRun(tmp_path, "biblia_kraken") as sb:
        with pytest.raises(jsonschema.ValidationError):
            sb.write_run_meta(bad)
        # No run_meta.json landed in the sandbox.
        assert not (sb.sandbox_dir / "run_meta.json").exists()
        assert not (sb.sandbox_dir / "run_meta.json.tmp").exists()


def test_sandbox_write_run_meta_succeeds_for_valid(tmp_path, valid_run_meta):
    with SandboxRun(tmp_path, "biblia_kraken") as sb:
        path = sb.write_run_meta(valid_run_meta)
        assert path.exists()
        assert path.name == "run_meta.json"


# -- run_meta_writer helper (defense in depth) ------------------------------


def test_run_meta_writer_validates_before_write(tmp_path, valid_run_meta):
    """baselines._run_meta.write_run_meta is the second call site
    (separate from SandboxRun); validators run there too."""
    bad = deepcopy(valid_run_meta)
    del bad["folios"]["leningrad_devarim_shema_fixture"]["line_count"]

    target = tmp_path / "run_meta.json"
    with pytest.raises(jsonschema.ValidationError):
        run_meta_writer(target, bad)
    assert not target.exists()


def test_run_meta_writer_succeeds_for_valid(tmp_path, valid_run_meta):
    target = tmp_path / "run_meta.json"
    run_meta_writer(target, valid_run_meta)
    assert target.exists()
