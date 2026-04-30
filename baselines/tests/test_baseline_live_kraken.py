"""Live BL-02 test — gated by RUN_LIVE_BASELINES=1.

GT-07 compatibility: the dry-run Shema folio produces a schema-valid
prediction file when run end-to-end against the cached BiblIA_01.mlmodel
+ a fetched archive.org image.

Skipped by default (model is ~16 MB, image fetch hits archive.org). The
default `pytest baselines/tests/` run does not exercise this — only:

    RUN_LIVE_BASELINES=1 pytest baselines/tests/test_baseline_live_kraken.py

The mocked-unit tier (test_baseline_unit_kraken.py) is the PR-blocking
substrate; this file is the integration smoke test for the cached model.

Marker: `live_kraken` (a sub-marker of `live_baselines` so future
RUN_LIVE_BASELINES=1 expansions can opt-in/out per baseline).
"""

from __future__ import annotations

import json
import os
from datetime import UTC
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = REPO_ROOT / "baselines" / ".cache" / "kraken" / "BiblIA_01.mlmodel"


# Top-level skipif: this test runs ONLY when both env gate is set AND
# the model is locally cached (the fetch script is the operator's job).
pytestmark = [
    pytest.mark.live_baselines,
    pytest.mark.live_kraken,
    pytest.mark.skipif(
        os.environ.get("RUN_LIVE_BASELINES") != "1",
        reason="live tier; set RUN_LIVE_BASELINES=1 to enable",
    ),
    pytest.mark.skipif(
        not MODEL_PATH.exists(),
        reason=(
            "cached BiblIA_01.mlmodel missing; run "
            "baselines/scripts/fetch_biblia_kraken_model.py first"
        ),
    ),
]


def test_live_kraken_shema_fixture_emits_schema_valid_prediction(tmp_path):
    """End-to-end on the dry-run Shema folio: real cached Kraken model +
    real archive.org image fetch. The emitted prediction is validated by
    SandboxRun.write_prediction at write time (jsonschema), so the test
    only needs to assert success + spot-check the on-disk artifact."""
    from baselines._kraken import KRAKEN_MODEL_HASH
    from baselines.biblia_kraken import BibliaKrakenBaseline

    from tests._fake_manifest import FakeManifest

    fid = "leningrad_devarim_F118B_fixture"
    image_url = "https://archive.org/download/leningrad-codex-color/BIB_LENCDX_F118B.jpg"
    # FakeFolio doesn't carry an image_url field; FakeFolio is frozen=True so
    # setattr won't work — use a small concrete subclass below instead.
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class _F:
        id: str
        manuscript: str = "leningrad"
        in_frozen_scope: bool = True
        image_url: str = image_url

    manifest = FakeManifest(
        folios=[_F(id=fid)],
        expected_reports_per_baseline={"biblia_kraken": 1},
    )

    bl = BibliaKrakenBaseline.__new__(BibliaKrakenBaseline)
    bl.manifest = manifest
    bl.results_root = tmp_path
    bl.replay = False
    bl.model_path = MODEL_PATH
    bl.image_cache = REPO_ROOT / "baselines" / ".cache" / "images"
    from datetime import datetime

    bl._started_at = datetime.now(UTC).isoformat(timespec="seconds")
    bl._folio_meta = {}

    rc = bl.run()
    assert rc == 0

    pred_path = tmp_path / "biblia_kraken" / f"{fid}.json"
    meta_path = tmp_path / "biblia_kraken" / "run_meta.json"
    assert pred_path.exists()
    assert meta_path.exists()

    pred = json.loads(pred_path.read_text())
    assert pred["baseline_id"] == "biblia_kraken"
    assert pred["folio_id"] == fid
    assert len(pred["lines"]) >= 1
    # Schema (validated at write time) requires bbox of 4 ints, tier1/2/3
    # strings, etc. We re-assert one shape-spot-check here.
    assert all(len(ln["bbox"]) == 4 for ln in pred["lines"])
    assert all(0.0 <= ln.get("kraken_confidence", 0.0) <= 1.0 for ln in pred["lines"])

    meta = json.loads(meta_path.read_text())
    assert meta["pins"]["kraken_model_hash"] == KRAKEN_MODEL_HASH
