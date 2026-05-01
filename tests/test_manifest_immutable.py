from __future__ import annotations

import copy
import json
import subprocess

from scripts.manifest_immutable import main, validate_manifest_successor


def _manifest() -> dict:
    return {
        "frozen_at": "2026-05-01T06:36:29Z",
        "expected_total_reports": 0,
        "expected_reports_per_baseline": {"biblia_kraken": 1},
        "nakdimon_model_hash": "8fd7722b8002a690",
        "kraken_model_hash": "8514a0c7cc2b5b45",
        "dictabert_model_revision": "d311fbf7c403e50b040440e4859ac78064d025d0",
        "scorer_version": "0.1.0",
        "baselines_seeded": [],
        "baselines": {},
        "cost_caps_usd": {"per_folio": 5.0, "per_run": 30.0},
        "manifest_changelog": [
            {
                "prev_frozen_at": "2026-05-01T03:18:50Z",
                "new_frozen_at": "2026-05-01T06:36:29Z",
                "reason": "phase 3.1: biblia_nakdimon leningrad_devarim_F118B_fixture promoted",
            }
        ],
        "folios": [
            {
                "id": "leningrad_devarim_F118B_fixture",
                "manuscript": "leningrad",
                "book": "devarim",
                "folio": "F118B",
                "image_url": "https://example.org/f118b.jpg",
                "iaa_folio": True,
                "gt_hash": None,
                "in_frozen_scope": True,
            }
        ],
        "fuses_fired": [],
    }


def _append_row(doc: dict, *, reason: str = "phase 03.3: manifest gate test") -> None:
    previous = doc["frozen_at"]
    doc["frozen_at"] = "2026-05-01T07:00:00Z"
    doc["manifest_changelog"].append(
        {
            "prev_frozen_at": previous,
            "new_frozen_at": doc["frozen_at"],
            "reason": reason,
        }
    )


def test_edited_changelog_prefix_row_is_rejected():
    head = _manifest()
    staged = copy.deepcopy(head)
    staged["manifest_changelog"][0]["reason"] = "phase 03.3: edited changelog row"

    errors = validate_manifest_successor(head, staged)

    assert any("edited changelog" in error for error in errors)


def test_removed_changelog_row_is_rejected():
    head = _manifest()
    staged = copy.deepcopy(head)
    staged["manifest_changelog"] = []

    errors = validate_manifest_successor(head, staged)

    assert any("removed changelog" in error for error in errors)


def test_tracked_top_level_field_change_requires_new_changelog_row():
    head = _manifest()
    staged = copy.deepcopy(head)
    staged["kraken_model_hash"] = "newhash"

    errors = validate_manifest_successor(head, staged)

    assert any("tracked top-level field" in error for error in errors)


def test_tracked_top_level_field_change_accepts_coherent_append():
    head = _manifest()
    staged = copy.deepcopy(head)
    staged["expected_total_reports"] = 1
    _append_row(staged)

    errors = validate_manifest_successor(head, staged)

    assert errors == []


def test_prev_frozen_at_and_new_frozen_at_chain_is_validated():
    head = _manifest()
    staged = copy.deepcopy(head)
    staged["expected_total_reports"] = 1
    _append_row(staged)
    staged["manifest_changelog"][-1]["prev_frozen_at"] = "2026-05-01T00:00:00Z"

    errors = validate_manifest_successor(head, staged)

    assert any("prev_frozen_at" in error for error in errors)


def test_new_changelog_reason_must_match_phase_prefix_for_tracked_change():
    head = _manifest()
    staged = copy.deepcopy(head)
    staged["expected_total_reports"] = 1
    _append_row(staged, reason="manual update")

    errors = validate_manifest_successor(head, staged)

    assert any("tracked top-level field" in error and "reason" in error for error in errors)


def test_main_can_compare_against_explicit_base_ref(tmp_path, monkeypatch):
    head = _manifest()
    staged = copy.deepcopy(head)
    staged["kraken_model_hash"] = "newhash"
    manifest_path = tmp_path / "phase_0_manifest.json"
    manifest_path.write_text(json.dumps(staged), encoding="utf-8")

    calls = []

    def fake_check_output(args, **kwargs):
        calls.append(args)
        assert args == ["git", "show", f"origin/main:{manifest_path}"]
        return json.dumps(head)

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)

    assert main(str(manifest_path), "origin/main") == 1
    assert calls == [["git", "show", f"origin/main:{manifest_path}"]]
