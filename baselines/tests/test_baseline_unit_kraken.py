"""BL-02 BibliaKrakenBaseline mocked unit tests.

Mirror of plan 03-02's test_atomic_run patterns: tests construct the
subclass via cls.__new__ + attribute assignment so we bypass real
Manifest.load (FakeManifest is enough). Kraken / PIL are mocked at the
sys.modules level via _kraken's lazy imports — no real model needed for
unit tier; live tier (test_baseline_live_kraken.py, gated by
RUN_LIVE_BASELINES=1) drives the real model.

Coverage:
- Test 1: happy path. run() succeeds; results/biblia_kraken/<folio>.json
  + run_meta.json exist; run_meta.pins.kraken_model_hash == KRAKEN_MODEL_HASH.
- Test 2: D-15 expected_total_reports off-by-one. Manifest declares 2
  but only 1 folio; BaselineError raised; results/biblia_kraken/ NOT
  created; .in_progress/biblia_kraken/ left for inspection.
- Test 3: D-13a script-start ScopeViolation. Out-of-scope folio_id ->
  ScopeViolation BEFORE _kraken._load_model is called (zero invocations).
- Test 4: D-04 KrakenInferenceFailure propagates; results/biblia_kraken/
  not created; .in_progress/ left for inspection.
- Test 5: Per-line LineRecord.kraken_confidence flows through to the
  prediction JSON's per-line records (load-bearing for paper's
  error-decomposition discussion per D-04).
"""

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path
from unittest.mock import patch

import pytest
from baselines._base import LineRecord

from tests._fake_manifest import FakeFolio, FakeManifest


def _ctor(tmp_path: Path, manifest: FakeManifest):
    """Construct BibliaKrakenBaseline bypassing Manifest.load."""
    from baselines.biblia_kraken import BibliaKrakenBaseline

    bl = BibliaKrakenBaseline.__new__(BibliaKrakenBaseline)
    bl.manifest = manifest
    bl.results_root = tmp_path
    bl.replay = False
    # Defaults the production __init__ would set:
    bl.model_path = tmp_path / "fake.mlmodel"
    bl.image_cache = tmp_path / "image-cache"
    from datetime import datetime

    bl._started_at = datetime.now(UTC).isoformat(timespec="seconds")
    bl._folio_meta = {}
    return bl


def _fake_lines(folio_id: str, n: int = 1) -> list[LineRecord]:
    return [
        LineRecord(
            line_id=f"{folio_id}_L{i + 1:03d}",
            bbox=(10, 10 + i * 50, 500, 60 + i * 50),
            tier1="שמע ישראל",
            tier2="שמע ישראל",
            tier3="שמע ישראל",
            tier4_records=tuple(),
            kraken_confidence=0.93,
        )
        for i in range(n)
    ]


# ----------------------------------------------------------------------
# Test 1: Happy path
# ----------------------------------------------------------------------


def test_kraken_run_writes_valid_prediction_and_run_meta(tmp_path, monkeypatch):
    fid = "leningrad_devarim_shema_fixture"
    manifest = FakeManifest(
        folios=[FakeFolio(id=fid)],
        expected_reports_per_baseline={"biblia_kraken": 1},
    )

    fake_lines = _fake_lines(fid, n=2)
    fake_image_path = tmp_path / "image-cache" / f"{fid}.jpg"

    with (
        patch("baselines.biblia_kraken.recognize_lines", return_value=fake_lines),
        patch("baselines.biblia_kraken.fetch_image", return_value=fake_image_path),
        patch("baselines.biblia_kraken.image_sha256", return_value="abc123"),
    ):
        bl = _ctor(tmp_path, manifest)
        rc = bl.run()

    assert rc == 0
    # Promoted to results/biblia_kraken/
    pred_path = tmp_path / "biblia_kraken" / f"{fid}.json"
    meta_path = tmp_path / "biblia_kraken" / "run_meta.json"
    assert pred_path.exists()
    assert meta_path.exists()

    pred = json.loads(pred_path.read_text())
    assert pred["baseline_id"] == "biblia_kraken"
    assert pred["folio_id"] == fid
    assert len(pred["lines"]) == 2
    assert all(0.0 <= ln["kraken_confidence"] <= 1.0 for ln in pred["lines"])

    meta = json.loads(meta_path.read_text())
    from baselines._kraken import KRAKEN_MODEL_HASH

    assert meta["pins"]["kraken_model_hash"] == KRAKEN_MODEL_HASH
    # D-19 required keys
    assert meta["baseline_id"] == "biblia_kraken"
    assert meta["replay_mode"] is False
    assert "hostname" in meta
    # Per-folio entry per D-19
    assert fid in meta["folios"]
    assert meta["folios"][fid]["line_count"] == 2


# ----------------------------------------------------------------------
# Test 2: D-15 expected_total_reports off-by-one
# ----------------------------------------------------------------------


def test_kraken_d15_off_by_one_prevents_promote(tmp_path):
    """Manifest declares 2 expected; only 1 folio in scope -> D-15 raises;
    results/biblia_kraken/ NOT created; .in_progress/ left for inspection."""
    from baselines._errors import BaselineError

    fid = "leningrad_devarim_shema_fixture"
    manifest = FakeManifest(
        folios=[FakeFolio(id=fid)],
        expected_reports_per_baseline={"biblia_kraken": 2},  # mismatch
    )

    fake_lines = _fake_lines(fid)
    fake_image_path = tmp_path / "image-cache" / f"{fid}.jpg"

    with (
        patch("baselines.biblia_kraken.recognize_lines", return_value=fake_lines),
        patch("baselines.biblia_kraken.fetch_image", return_value=fake_image_path),
        patch("baselines.biblia_kraken.image_sha256", return_value="abc"),
    ):
        bl = _ctor(tmp_path, manifest)
        with pytest.raises(BaselineError, match=r"D-15.*mismatch"):
            bl.run()

    assert not (tmp_path / "biblia_kraken").exists()
    sandbox = tmp_path / ".in_progress" / "biblia_kraken"
    assert sandbox.exists()
    pred_files = [p for p in sandbox.glob("*.json") if p.name != "run_meta.json"]
    assert len(pred_files) == 1


# ----------------------------------------------------------------------
# Test 3: D-13a ScopeViolation BEFORE model load
# ----------------------------------------------------------------------


def test_kraken_d13a_scope_violation_fires_before_model_load(tmp_path):
    """Out-of-scope folio_id -> ScopeViolation raised by _preflight before
    any kraken load attempt. Verified by asserting recognize_lines and
    _kraken._load_model are both never called."""
    from baselines._errors import ScopeViolation

    fid_in_scope = "leningrad_devarim_shema_fixture"
    manifest = FakeManifest(
        folios=[FakeFolio(id=fid_in_scope)],
        expected_reports_per_baseline={"biblia_kraken": 1},
    )

    with (
        patch("baselines.biblia_kraken.recognize_lines") as m_rec,
        patch("baselines.biblia_kraken.fetch_image") as m_fetch,
        patch("baselines._kraken._load_model") as m_load,
    ):
        bl = _ctor(tmp_path, manifest)
        with pytest.raises(ScopeViolation, match="BL-08"):
            bl.run(folio_ids=["non_existent_folio"])
        assert m_rec.call_count == 0, "recognize_lines must NOT be invoked on D-13a"
        assert m_fetch.call_count == 0, "fetch_image must NOT be invoked on D-13a"
        assert m_load.call_count == 0, "_load_model must NOT be invoked on D-13a"

    assert not (tmp_path / "biblia_kraken").exists()


# ----------------------------------------------------------------------
# Test 4: D-04 KrakenInferenceFailure propagates
# ----------------------------------------------------------------------


def test_kraken_d04_inference_failure_leaves_sandbox(tmp_path):
    """recognize_lines raises KrakenInferenceFailure; results/biblia_kraken/
    not created; .in_progress/biblia_kraken/ preserved for inspection."""
    from baselines._errors import KrakenInferenceFailure

    fid = "leningrad_devarim_shema_fixture"
    manifest = FakeManifest(
        folios=[FakeFolio(id=fid)],
        expected_reports_per_baseline={"biblia_kraken": 1},
    )

    def boom(*a, **kw):
        raise KrakenInferenceFailure(f"D-04: full-page failure on {fid}")

    fake_image_path = tmp_path / "image-cache" / f"{fid}.jpg"

    with (
        patch("baselines.biblia_kraken.recognize_lines", side_effect=boom),
        patch("baselines.biblia_kraken.fetch_image", return_value=fake_image_path),
        patch("baselines.biblia_kraken.image_sha256", return_value="abc"),
    ):
        bl = _ctor(tmp_path, manifest)
        with pytest.raises(KrakenInferenceFailure, match="D-04"):
            bl.run()

    assert not (tmp_path / "biblia_kraken").exists()
    assert (tmp_path / ".in_progress" / "biblia_kraken").exists()


# ----------------------------------------------------------------------
# Test 5: kraken_confidence flows into prediction JSON
# ----------------------------------------------------------------------


def test_kraken_confidence_flows_into_prediction_lines(tmp_path):
    """Per-line LineRecord.kraken_confidence is serialized into per-line
    records in the prediction JSON (D-04 + D-17)."""
    fid = "leningrad_devarim_shema_fixture"
    manifest = FakeManifest(
        folios=[FakeFolio(id=fid)],
        expected_reports_per_baseline={"biblia_kraken": 1},
    )

    fake_lines = [
        LineRecord(
            line_id=f"{fid}_L001",
            bbox=(0, 0, 100, 50),
            tier1="א",
            tier2="א",
            tier3="א",
            tier4_records=(),
            kraken_confidence=0.5,
        ),
        LineRecord(
            line_id=f"{fid}_L002",
            bbox=(0, 60, 100, 110),
            tier1="ב",
            tier2="ב",
            tier3="ב",
            tier4_records=(),
            kraken_confidence=0.99,
        ),
    ]
    fake_image_path = tmp_path / "image-cache" / f"{fid}.jpg"

    with (
        patch("baselines.biblia_kraken.recognize_lines", return_value=fake_lines),
        patch("baselines.biblia_kraken.fetch_image", return_value=fake_image_path),
        patch("baselines.biblia_kraken.image_sha256", return_value="abc"),
    ):
        bl = _ctor(tmp_path, manifest)
        bl.run()

    pred = json.loads((tmp_path / "biblia_kraken" / f"{fid}.json").read_text())
    confs = [ln["kraken_confidence"] for ln in pred["lines"]]
    assert confs == [0.5, 0.99]


# ----------------------------------------------------------------------
# AST invariant cross-check (defense-in-depth)
# ----------------------------------------------------------------------


def test_biblia_kraken_baseline_id_is_canonical():
    from baselines.biblia_kraken import BibliaKrakenBaseline

    assert BibliaKrakenBaseline.BASELINE_ID == "biblia_kraken"


def test_biblia_kraken_does_not_override_run():
    """D-12 structural lock — pinned by AST-walk in test_invariants.py too,
    but cheap to assert here so a regression surfaces in this file's failure
    output rather than only in test_invariants."""
    from baselines._base import BaselineBase
    from baselines.biblia_kraken import BibliaKrakenBaseline

    # The class object's own __dict__ MUST NOT contain `run` — only inherited.
    assert "run" not in BibliaKrakenBaseline.__dict__, (
        "D-12: BibliaKrakenBaseline must NOT override run()"
    )
    # Inheritance still resolves run from the base class.
    assert BibliaKrakenBaseline.run is BaselineBase.run
