"""D-14 sandbox-then-promote semantics tests.

Plan 03-02 Task 2 behavior tests 3 + 4:
  - Test 3 (success): clean run -> results/<bl>/ has folio JSONs +
    run_meta.json; .in_progress/<bl>/ is gone (or empty).
  - Test 4 (abort): infer_folio raises -> .in_progress/<bl>/ is left
    populated; results/<bl>/ is untouched.

Phase 03.1 A-01 amendment: per-folio promotion replaces whole-batch
sandbox.promote(). Tests that call bl.run() now route the manifest bump
through a tmp_path manifest via PHASE_0_MANIFEST_PATH env var.
"""

from __future__ import annotations

import json

import pytest
from baselines._atomic import SandboxRun
from baselines._base import BaselineBase, LineRecord

from tests._fake_manifest import FakeFolio, FakeManifest


def _ctor(tmp_path, manifest, cls):
    bl = cls.__new__(cls)
    bl.manifest = manifest
    bl.results_root = tmp_path
    bl.replay = False
    return bl


def _seed_manifest_for_run(tmp_path, monkeypatch, baseline_id: str = "biblia_kraken"):
    """A-01: BaselineBase.run reads PHASE_0_MANIFEST_PATH per folio.
    Seed an empty-but-valid manifest in tmp_path and point the env there.
    Returns the path to the seeded manifest."""
    p = tmp_path / "phase_0_manifest.json"
    p.write_text(
        json.dumps(
            {
                "version": "v0.2.0",
                "frozen_at": "2026-04-25T16:30:44Z",
                "expected_reports_per_baseline": {baseline_id: 0},
                "manifest_changelog": [],
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    )
    monkeypatch.setenv("PHASE_0_MANIFEST_PATH", str(p))
    return p


# -- D-14 success path -------------------------------------------------------


class _GoodBaseline(BaselineBase):
    BASELINE_ID = "biblia_kraken"

    def infer_folio(self, folio):
        return [
            LineRecord(
                line_id=f"{folio.id}_L001",
                bbox=(0, 0, 1, 1),
                tier1="א",
                tier2="א",
                tier3="א",
                tier4_records=(),
            )
        ]


def test_d14_success_promotes_to_results_dir(tmp_path, monkeypatch):
    fid = "leningrad_devarim_shema_fixture"
    manifest = FakeManifest(
        folios=[FakeFolio(id=fid)],
        expected_reports_per_baseline={"biblia_kraken": 1},
    )
    _seed_manifest_for_run(tmp_path, monkeypatch, "biblia_kraken")
    bl = _ctor(tmp_path, manifest, _GoodBaseline)
    rc = bl.run()
    assert rc == 0

    # Final dir contains the folio prediction + run_meta
    final_pred = tmp_path / "biblia_kraken" / f"{fid}.json"
    final_meta = tmp_path / "biblia_kraken" / "run_meta.json"
    assert final_pred.exists(), "prediction must be promoted"
    assert final_meta.exists(), "run_meta must be in final dir (A-01)"

    # Sandbox dir is gone (or empty) -- per-folio promote drained it; run_meta
    # writes directly to final dir per A-01 amendment.
    sandbox = tmp_path / ".in_progress" / "biblia_kraken"
    if sandbox.exists():
        assert not any(sandbox.iterdir()), f"sandbox should be empty, has {list(sandbox.iterdir())}"

    # Prediction shape sanity
    payload = json.loads(final_pred.read_text())
    assert payload["baseline_id"] == "biblia_kraken"
    assert payload["folio_id"] == fid
    assert payload["schema_version"]
    assert len(payload["lines"]) == 1
    assert payload["lines"][0]["line_id"] == f"{fid}_L001"


# -- D-14 abort path ---------------------------------------------------------


class _BoomBaseline(BaselineBase):
    BASELINE_ID = "biblia_kraken"

    def infer_folio(self, folio):
        raise RuntimeError("boom")


def test_d14_abort_leaves_sandbox_for_inspection(tmp_path, monkeypatch):
    fid = "leningrad_devarim_shema_fixture"
    manifest = FakeManifest(
        folios=[FakeFolio(id=fid)],
        expected_reports_per_baseline={"biblia_kraken": 1},
    )
    _seed_manifest_for_run(tmp_path, monkeypatch, "biblia_kraken")
    bl = _ctor(tmp_path, manifest, _BoomBaseline)

    with pytest.raises(RuntimeError, match="boom"):
        bl.run()

    # results/<bl>/ must NOT exist (no successful run)
    assert not (tmp_path / "biblia_kraken").exists(), "results/<bl>/ must not be created on abort"
    # .in_progress/<bl>/ must exist (sandbox left for inspection per D-14)
    assert (tmp_path / ".in_progress" / "biblia_kraken").exists(), (
        "sandbox must be left populated for inspection"
    )


# -- D-15 off-by-one ---------------------------------------------------------


class _UnderCounterBaseline(BaselineBase):
    """Writes one folio prediction; manifest declares two expected -> D-15 trips."""

    BASELINE_ID = "biblia_kraken"

    def infer_folio(self, folio):
        return [
            LineRecord(
                line_id=f"{folio.id}_L001",
                bbox=(0, 0, 1, 1),
                tier1="א",
                tier2="א",
                tier3="א",
                tier4_records=(),
            )
        ]


def test_d15_off_by_one_raises_after_per_folio_promote(tmp_path, monkeypatch):
    """A-01 amendment: per-folio promote means D-15 check happens at the
    end-of-run, AFTER all folios already promoted. The folio that did
    promote is in results/<bl>/; the validate raises BaselineError because
    1 != 2. Off-by-one D-15 is now detected post-promote rather than
    pre-promote (the per-folio invariant subsumed the pre-promote check).
    The CI-side `test_results_dir_count_equals_manifest_expected_reports`
    is the cross-run gate that flags the persistent inconsistency.
    """
    from baselines._errors import BaselineError

    fid = "leningrad_devarim_shema_fixture"
    manifest = FakeManifest(
        folios=[FakeFolio(id=fid)],
        expected_reports_per_baseline={"biblia_kraken": 2},  # declares 2, only 1 folio in scope
    )
    _seed_manifest_for_run(tmp_path, monkeypatch, "biblia_kraken")
    bl = _ctor(tmp_path, manifest, _UnderCounterBaseline)

    with pytest.raises(BaselineError, match=r"D-15.*mismatch"):
        bl.run()

    # A-01 amendment: per-folio promote landed the single folio in results/<bl>/
    # before the end-of-run D-15 mismatch raised. The cross-run CI gate
    # surfaces the persistent inconsistency; this in-run check is a
    # defensive double-check.
    assert (tmp_path / "biblia_kraken" / f"{fid}.json").exists()


def test_d15_unknown_baseline_raises_baselineerror(tmp_path, monkeypatch):
    """Manifest declares mapping for some baselines but not this one ->
    KeyError -> wrapped as BaselineError with D-15 context."""
    from baselines._errors import BaselineError

    fid = "leningrad_devarim_shema_fixture"
    manifest = FakeManifest(
        folios=[FakeFolio(id=fid)],
        expected_reports_per_baseline={"other_baseline": 1},
    )
    _seed_manifest_for_run(tmp_path, monkeypatch, "biblia_kraken")
    bl = _ctor(tmp_path, manifest, _GoodBaseline)

    with pytest.raises(BaselineError, match=r"D-15.*does not declare expected reports"):
        bl.run()


# -- SandboxRun unit tests ---------------------------------------------------
#
# Note: as of plan 03-03 the SandboxRun.write_* methods validate their
# payloads against the new JSON Schemas BEFORE the atomic write. The unit
# tests below feed schema-conformant fixtures so they exercise the
# write/promote path rather than the validator's reject path. Reject-path
# coverage lives in test_schema_module.py.


def _valid_pred(folio_id: str, baseline_id: str = "biblia_kraken") -> dict:
    return {
        "schema_version": "0.1.0",
        "baseline_id": baseline_id,
        "folio_id": folio_id,
        "manifest_hash": "fake-manifest-hash",
        "run_meta_ref": "run_meta.json",
        "lines": [
            {
                "line_id": f"{folio_id}_L001",
                "bbox": [0, 0, 1, 1],
                "tier1": "א",
                "tier2": "א",
                "tier3": "א",
                "tier4_records": [],
            }
        ],
    }


def _valid_meta(baseline_id: str = "biblia_kraken") -> dict:
    return {
        "schema_version": "0.1.0",
        "baseline_id": baseline_id,
        "manifest_hash": "fake-manifest-hash",
        "scorer_version": "v0.1.0-scorer",
        "started_at_iso": "2026-04-25T16:00:00Z",
        "completed_at_iso": "2026-04-25T16:01:00Z",
        "hostname": "test-host",
        "sibling_git_sha": "abc1234",
        "replay_mode": False,
        "pins": {
            "kraken_model_hash": None,
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
        "folios": {},
    }


def test_sandbox_run_atomic_write_uses_temp_then_replace(tmp_path):
    """SandboxRun._atomic_write_json writes via .tmp + os.replace."""
    sr = SandboxRun(tmp_path, "biblia_kraken")
    with sr as sb:
        sb.write_prediction("folio_x", _valid_pred("folio_x"))
        out = sb.sandbox_dir / "folio_x.json"
        assert out.exists()
        # No leftover .tmp files
        assert not list(sb.sandbox_dir.glob("*.tmp"))


def test_sandbox_run_count_excludes_run_meta(tmp_path):
    sr = SandboxRun(tmp_path, "biblia_kraken")
    with sr as sb:
        sb.write_prediction("a", _valid_pred("a"))
        sb.write_prediction("b", _valid_pred("b"))
        sb.write_run_meta(_valid_meta())
        assert sb.count() == 2


def test_sandbox_run_promote_atomic_rename_per_file(tmp_path):
    sr = SandboxRun(tmp_path, "biblia_kraken")
    with sr as sb:
        sb.write_prediction("a", _valid_pred("a"))
        sb.write_run_meta(_valid_meta())
        sb.promote()
    assert (tmp_path / "biblia_kraken" / "a.json").exists()
    assert (tmp_path / "biblia_kraken" / "run_meta.json").exists()


def test_sandbox_run_diagnostic_subdir(tmp_path):
    """BL-03/BL-04 GT-fed diagnostic chain (D-01) goes into a subdir."""
    sr = SandboxRun(tmp_path, "biblia_nakdimon")
    with sr as sb:
        sb.write_prediction("a", _valid_pred("a", baseline_id="biblia_nakdimon"))
        sb.write_diagnostic("a", _valid_pred("a", baseline_id="biblia_nakdimon"))
        sb.write_run_meta(_valid_meta(baseline_id="biblia_nakdimon"))
        assert (sb.sandbox_dir / "diagnostic" / "a.gt_fed.json").exists()
        # count() counts only top-level (realistic chain), not diagnostics
        assert sb.count() == 1
        sb.promote()
    assert (tmp_path / "biblia_nakdimon" / "diagnostic" / "a.gt_fed.json").exists()


def test_sandbox_run_promote_idempotent_replace_subdir(tmp_path):
    """If results/<bl>/diagnostic/ already exists from a prior run, promote
    must atomically replace it, not error out."""
    # Pre-existing final dir with a stale diagnostic subdir
    final = tmp_path / "biblia_nakdimon"
    final.mkdir()
    (final / "diagnostic").mkdir()
    (final / "diagnostic" / "stale.json").write_text("stale")

    sr = SandboxRun(tmp_path, "biblia_nakdimon")
    with sr as sb:
        sb.write_prediction("a", _valid_pred("a", baseline_id="biblia_nakdimon"))
        sb.write_diagnostic("a", _valid_pred("a", baseline_id="biblia_nakdimon"))
        sb.write_run_meta(_valid_meta(baseline_id="biblia_nakdimon"))
        sb.promote()
    # Stale file should be gone (subdir replaced)
    assert not (final / "diagnostic" / "stale.json").exists()
    assert (final / "diagnostic" / "a.gt_fed.json").exists()
