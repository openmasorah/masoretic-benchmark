"""A-01 paired-success-or-paired-rollback tests for SandboxRun.promote_folio.

Mirrors test_atomic_run.py pattern (lines 30-149 success + abort + D-15
off-by-one). Adds the per-folio promotion rollback semantics that the
Phase 3 D-14 amendment requires (Phase 03.1 A-01).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from baselines._atomic import SandboxRun
from baselines._manifest_bump import (
    ManifestChangelogOverflow,
    build_bump,
)


def _make_manifest(
    tmp_path: Path,
    baseline_id: str = "biblia_kraken",
    expected: int = 0,
) -> Path:
    m = {
        "version": "v0.2.0",
        "frozen_at": "2026-04-25T16:30:44Z",
        "expected_reports_per_baseline": {
            baseline_id: expected,
            "biblia_nakdimon": 0,
            "biblia_char_menaked": 0,
            "llm_vision": 0,
        },
        "manifest_changelog": [],
    }
    path = tmp_path / "phase_0_manifest.json"
    path.write_text(json.dumps(m, ensure_ascii=False, sort_keys=True, indent=2))
    return path


# ---------------------------------------------------------------------------
# Test 1: success path
# ---------------------------------------------------------------------------


def test_promote_folio_success(tmp_path):
    sr = SandboxRun(tmp_path, "biblia_kraken")
    sr.sandbox_dir.mkdir(parents=True, exist_ok=True)
    (sr.sandbox_dir / "F1.json").write_text('{"folio_id":"F1"}')
    manifest = _make_manifest(tmp_path)

    sr.promote_folio(
        "F1",
        manifest_path=manifest,
        bump_manifest=build_bump("biblia_kraken", "F1"),
    )

    assert (sr.final_dir / "F1.json").exists()
    assert not (sr.sandbox_dir / "F1.json").exists()
    m = json.loads(manifest.read_text())
    assert m["expected_reports_per_baseline"]["biblia_kraken"] == 1
    assert len(m["manifest_changelog"]) == 1
    assert m["manifest_changelog"][0]["reason"] == "phase 3.1: biblia_kraken F1 promoted"


# ---------------------------------------------------------------------------
# Test 2: manifest write failure -> rename rollback
# ---------------------------------------------------------------------------


def test_promote_folio_manifest_failure_rolls_back_rename(tmp_path):
    sr = SandboxRun(tmp_path, "biblia_kraken")
    sr.sandbox_dir.mkdir(parents=True, exist_ok=True)
    (sr.sandbox_dir / "F1.json").write_text('{"folio_id":"F1"}')
    manifest = _make_manifest(tmp_path)

    def _bad_bump(prev):
        raise RuntimeError("manifest write failed")

    with pytest.raises(RuntimeError, match="manifest write failed"):
        sr.promote_folio("F1", manifest_path=manifest, bump_manifest=_bad_bump)

    # A-01 rollback: prediction file MUST be back in sandbox, NOT in results/.
    assert not (sr.final_dir / "F1.json").exists()
    assert (sr.sandbox_dir / "F1.json").exists()
    # Manifest unchanged.
    m = json.loads(manifest.read_text())
    assert m["expected_reports_per_baseline"]["biblia_kraken"] == 0


# ---------------------------------------------------------------------------
# Test 3: rename failure -> manifest unchanged
# ---------------------------------------------------------------------------


def test_promote_folio_rename_failure_does_not_bump_manifest(tmp_path):
    sr = SandboxRun(tmp_path, "biblia_kraken")
    sr.sandbox_dir.mkdir(parents=True, exist_ok=True)
    (sr.sandbox_dir / "F1.json").write_text('{"folio_id":"F1"}')
    manifest = _make_manifest(tmp_path)

    with patch("baselines._atomic.os.replace", side_effect=OSError("disk full")):
        with pytest.raises(OSError, match="disk full"):
            sr.promote_folio(
                "F1",
                manifest_path=manifest,
                bump_manifest=build_bump("biblia_kraken", "F1"),
            )

    m = json.loads(manifest.read_text())
    assert m["expected_reports_per_baseline"]["biblia_kraken"] == 0
    assert m["manifest_changelog"] == []


# ---------------------------------------------------------------------------
# Test 4: BL-01 paired dir rename
# ---------------------------------------------------------------------------


def test_promote_folio_bl01_paired_dir_rename(tmp_path):
    sr = SandboxRun(tmp_path, "llm_vision")
    sr.sandbox_dir.mkdir(parents=True, exist_ok=True)
    (sr.sandbox_dir / "F1.json").write_text('{"folio_id":"F1"}')
    # BL-01 paired dir with replay log + crop.
    (sr.sandbox_dir / "F1").mkdir()
    (sr.sandbox_dir / "F1" / "llm_calls.jsonl").write_text("{}\n")
    (sr.sandbox_dir / "F1" / "line_1.jpg").write_bytes(b"\xff\xd8")  # JPEG magic
    manifest = _make_manifest(tmp_path, baseline_id="llm_vision", expected=0)

    sr.promote_folio(
        "F1",
        manifest_path=manifest,
        bump_manifest=build_bump("llm_vision", "F1"),
    )
    assert (sr.final_dir / "F1.json").exists()
    assert (sr.final_dir / "F1" / "llm_calls.jsonl").exists()
    assert (sr.final_dir / "F1" / "line_1.jpg").exists()


# ---------------------------------------------------------------------------
# Test 5: parent-dir fsync called (Pitfall 3)
# ---------------------------------------------------------------------------


def test_promote_folio_calls_fsync_parent_at_least_three_times(tmp_path):
    sr = SandboxRun(tmp_path, "llm_vision")
    sr.sandbox_dir.mkdir(parents=True, exist_ok=True)
    (sr.sandbox_dir / "F1.json").write_text('{"folio_id":"F1"}')
    (sr.sandbox_dir / "F1").mkdir()
    (sr.sandbox_dir / "F1" / "llm_calls.jsonl").write_text("{}\n")
    manifest = _make_manifest(tmp_path, baseline_id="llm_vision", expected=0)

    with patch("baselines._atomic.os.fsync") as mock_fsync:
        sr.promote_folio(
            "F1",
            manifest_path=manifest,
            bump_manifest=build_bump("llm_vision", "F1"),
        )
    # Pitfall 3: fsync(parent) called for prediction, dir, manifest.
    assert mock_fsync.call_count >= 3


# ---------------------------------------------------------------------------
# Pitfall 7: manifest_changelog row-count gate
# ---------------------------------------------------------------------------


def _prev_with_changelog_rows(n: int, baseline_id: str = "biblia_kraken") -> dict:
    """Construct a `prev` manifest with `n` synthetic manifest_changelog rows.
    Used by the Pitfall 7 row-count gate test (Test 10)."""
    return {
        "version": "v0.2.0",
        "frozen_at": "2026-04-25T16:30:44Z",
        "expected_reports_per_baseline": {baseline_id: 0},
        "manifest_changelog": [
            {
                "prev_frozen_at": "2026-04-25T00:00:00Z",
                "new_frozen_at": "2026-04-25T00:00:00Z",
                "reason": f"synthetic seed row {i}",
            }
            for i in range(n)
        ],
        "cost_caps_usd": {"per_folio": 5.00, "per_run": 30.00},
        "nakdimon_model_hash": "8fd7722b8002a690",
        "dictabert_model_revision": "d311fbf7c403e50b040440e4859ac78064d025d0",
        "kraken_model_hash": "8514a0c7cc2b5b45",
    }


def test_build_bump_changelog_growth_gate_below_warn(tmp_path):
    """Pitfall 7: post-append row count of 39 (below WARN_AT=40) -> silent."""
    import warnings

    prev = _prev_with_changelog_rows(38)
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any UserWarning would fail this
        new = build_bump("biblia_kraken", "F1")(prev)
    assert len(new["manifest_changelog"]) == 39


def test_build_bump_changelog_growth_gate_at_warn(tmp_path):
    """Pitfall 7: post-append row count of 40 (== WARN_AT) -> warns, no raise."""
    prev = _prev_with_changelog_rows(39)
    with pytest.warns(UserWarning, match="manifest_changelog at 40 rows"):
        new = build_bump("biblia_kraken", "F1")(prev)
    assert len(new["manifest_changelog"]) == 40


def test_build_bump_changelog_growth_gate_between_thresholds(tmp_path):
    """Pitfall 7: post-append row count of 49 (between thresholds) -> warns, no raise."""
    prev = _prev_with_changelog_rows(48)
    with pytest.warns(UserWarning, match="manifest_changelog at 49 rows"):
        new = build_bump("biblia_kraken", "F1")(prev)
    assert len(new["manifest_changelog"]) == 49


def test_build_bump_changelog_growth_gate_at_fail(tmp_path):
    """Pitfall 7: post-append row count of 50 (== FAIL_AT) -> raises."""
    prev = _prev_with_changelog_rows(49)
    with pytest.raises(ManifestChangelogOverflow, match="50 rows"):
        build_bump("biblia_kraken", "F1")(prev)


# ---------------------------------------------------------------------------
# D-06 idempotent first-promotion seeding
# ---------------------------------------------------------------------------


def test_build_bump_idempotent_d06_seeding(tmp_path):
    """D-06 first-promotion seeding is idempotent on subsequent calls."""
    prev = {
        "version": "v0.2.0",
        "frozen_at": "2026-04-25T16:30:44Z",
        "expected_reports_per_baseline": {"biblia_kraken": 0},
        "manifest_changelog": [],
    }
    bump = build_bump("biblia_kraken", "F1")
    new1 = bump(prev)
    # First call seeds D-06 fields.
    assert new1["cost_caps_usd"] == {"per_folio": 5.00, "per_run": 30.00}
    assert new1["nakdimon_model_hash"] == "8fd7722b8002a690"
    assert new1["dictabert_model_revision"] == "d311fbf7c403e50b040440e4859ac78064d025d0"
    assert new1["kraken_model_hash"] == "8514a0c7cc2b5b45"
    assert new1["expected_reports_per_baseline"]["biblia_kraken"] == 1
    assert len(new1["manifest_changelog"]) == 1
    # Second call: idempotent -- no overwrite, no duplicate seeding.
    new2 = bump(new1)
    assert new2["cost_caps_usd"] == {"per_folio": 5.00, "per_run": 30.00}
    assert new2["expected_reports_per_baseline"]["biblia_kraken"] == 2
    assert len(new2["manifest_changelog"]) == 2
