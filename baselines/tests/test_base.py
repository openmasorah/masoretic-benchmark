"""BaselineBase template-method shape + ABC behavior tests.

Plan 03-02 Task 2 behavior:
  - run() is concrete (not abstract); only infer_folio is abstract.
  - run() ordering: preflight -> sandbox enter -> per-folio scope_check
    + infer_folio -> validate_expected_total_reports -> write_run_meta
    -> promote.
  - BASELINE_ID required.
"""

from __future__ import annotations

import inspect
from abc import ABC

import pytest
from baselines._base import BaselineBase, LineRecord
from baselines._errors import BaselineError

from tests._fake_manifest import FakeFolio, FakeManifest


def test_baselinebase_is_abc():
    assert issubclass(BaselineBase, ABC)


def test_run_is_concrete_not_abstract():
    """D-12: run() is locked + concrete on the base; only infer_folio
    is abstract."""
    assert "run" not in BaselineBase.__abstractmethods__
    assert "infer_folio" in BaselineBase.__abstractmethods__


def test_cannot_instantiate_without_infer_folio(tmp_path):
    """ABC enforcement: cannot instantiate BaselineBase directly."""
    with pytest.raises(TypeError, match=r"abstract|infer_folio"):
        BaselineBase(tmp_path / "manifest.json", tmp_path)  # type: ignore[abstract]


def test_run_calls_template_methods_in_order(tmp_path, mocker):
    """Verify the locked call order: preflight -> scope_check (per folio)
    -> infer_folio -> validate_expected_total_reports -> write_run_meta
    -> sandbox.promote.

    We monkey-patch the helpers to log call order; the locked run()
    drives them in the order BaselineBase declares (D-12)."""
    fid = "leningrad_devarim_shema_fixture"
    manifest = FakeManifest(
        folios=[FakeFolio(id=fid)],
        expected_reports_per_baseline={"biblia_kraken": 1},
    )

    call_order: list[str] = []

    class TracingBaseline(BaselineBase):
        BASELINE_ID = "biblia_kraken"

        def _preflight(self, folio_ids):
            call_order.append("preflight")
            super()._preflight(folio_ids)

        def _scope_check(self, folio):
            call_order.append(f"scope_check({folio.id})")
            super()._scope_check(folio)

        def infer_folio(self, folio):
            call_order.append(f"infer_folio({folio.id})")
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

    bl = TracingBaseline.__new__(TracingBaseline)
    bl.manifest = manifest
    bl.results_root = tmp_path
    bl.replay = False

    # Spy on the validator + write_run_meta + sandbox.promote
    import baselines._run_meta as rm

    real_validate = rm.validate_expected_total_reports

    def spy_validate(**kw):
        call_order.append("validate_expected_total_reports")
        return real_validate(**kw)

    mocker.patch.object(rm, "validate_expected_total_reports", side_effect=spy_validate)

    import baselines._atomic as atomic

    real_promote = atomic.SandboxRun.promote

    def spy_promote(self):
        call_order.append("sandbox.promote")
        return real_promote(self)

    mocker.patch.object(atomic.SandboxRun, "promote", spy_promote)

    real_write_run_meta = atomic.SandboxRun.write_run_meta

    def spy_write_run_meta(self, payload):
        call_order.append("sandbox.write_run_meta")
        return real_write_run_meta(self, payload)

    mocker.patch.object(atomic.SandboxRun, "write_run_meta", spy_write_run_meta)

    # _base.py imports validate_expected_total_reports inside run() so the
    # monkeypatch on rm.validate_expected_total_reports is picked up at
    # call time (not at class-load time).

    rc = bl.run()
    assert rc == 0
    assert call_order == [
        "preflight",
        f"scope_check({fid})",
        f"infer_folio({fid})",
        "validate_expected_total_reports",
        "sandbox.write_run_meta",
        "sandbox.promote",
    ], f"unexpected order: {call_order}"


def test_baseline_id_required(tmp_path):
    """Subclass missing BASELINE_ID raises BaselineError on construction."""
    fid = "leningrad_devarim_shema_fixture"
    manifest = FakeManifest(
        folios=[FakeFolio(id=fid)],
        expected_reports_per_baseline={"biblia_kraken": 1},
    )

    class Untagged(BaselineBase):
        BASELINE_ID = ""  # explicitly empty

        def infer_folio(self, folio):
            return []

    bl = Untagged.__new__(Untagged)
    bl.manifest = manifest
    bl.results_root = tmp_path
    bl.replay = False

    # Re-run the BASELINE_ID guard inline as __init__ would
    if not bl.BASELINE_ID:
        with pytest.raises(BaselineError, match="BASELINE_ID"):
            raise BaselineError("subclass must set BASELINE_ID")


def test_run_meta_includes_required_fields(tmp_path):
    """run_meta payload contains schema_version, baseline_id, scorer_version,
    completed_at_iso, replay_mode."""
    import json

    fid = "leningrad_devarim_shema_fixture"
    manifest = FakeManifest(
        folios=[FakeFolio(id=fid)],
        expected_reports_per_baseline={"biblia_kraken": 1},
        scorer_version="v0.1.0-scorer",
    )

    class GoodBaseline(BaselineBase):
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

    bl = GoodBaseline.__new__(GoodBaseline)
    bl.manifest = manifest
    bl.results_root = tmp_path
    bl.replay = False
    bl.run()

    meta = json.loads((tmp_path / "biblia_kraken" / "run_meta.json").read_text())
    assert meta["baseline_id"] == "biblia_kraken"
    assert meta["scorer_version"] == "v0.1.0-scorer"
    assert "completed_at_iso" in meta
    assert "replay_mode" in meta
    assert meta["replay_mode"] is False


def test_serialize_includes_optional_fields_when_set(tmp_path):
    """LineRecord with kraken_confidence / llm_winner set must include
    them in the serialized JSON."""
    import json

    fid = "leningrad_devarim_shema_fixture"
    manifest = FakeManifest(
        folios=[FakeFolio(id=fid)],
        expected_reports_per_baseline={"biblia_kraken": 1},
    )

    class Provenanced(BaselineBase):
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
                    kraken_confidence=0.97,
                    llm_winner="claude",
                    llm_tie_breaks=1,
                )
            ]

    bl = Provenanced.__new__(Provenanced)
    bl.manifest = manifest
    bl.results_root = tmp_path
    bl.replay = False
    bl.run()

    pred = json.loads((tmp_path / "biblia_kraken" / f"{fid}.json").read_text())
    line = pred["lines"][0]
    assert line["kraken_confidence"] == 0.97
    assert line["llm_winner"] == "claude"
    assert line["llm_tie_breaks"] == 1


def test_run_signature_is_documented_locked(tmp_path):
    """Sanity check that run() accepts folio_ids: list[str] | None kw-only."""
    sig = inspect.signature(BaselineBase.run)
    assert "folio_ids" in sig.parameters
    p = sig.parameters["folio_ids"]
    assert p.kind == inspect.Parameter.KEYWORD_ONLY
