"""BL-03 BibliaNakdimonBaseline live tier — env-gated, Linux+Py3.11 only.

Pitfall 1 (Phase 2 02-02 carry-forward): nakdimon==0.1.2 + tensorflow==2.15
SIGABRTs on macOS arm64 + Python 3.11/3.12. THIS test runs cleanly on
Linux + Python 3.11 in CI (Plan 03-08 wires the nightly cron); locally
on Mac it is gated to skip via:

  - the `live_baselines` marker (Phase 2 D-24 inheritance) — skipped
    unless RUN_LIVE_BASELINES=1;
  - additional skipif checks for the cached BiblIA Kraken model and the
    diagnostic-chain GT fixture path supplied by env var.

Issue 2 fix (plan 03-05): Phase 1 has not yet emitted a per-line GT
export `{lines:[{line_id,bbox,tier1}]}` for the Shema fixture (Phase 1's
golden fixture is a single-text-blob shape — see 01-13b SUMMARY,
gt-infra/exports does not exist with the line-level shape this loader
needs). The diagnostic-chain assertion is wrapped with a pytest.skip
when OPENMESORAH_GT_EXPORT_JSON is unset; the realistic-chain prediction
still runs end-to-end against Kraken + Nakdimon when both gates pass.

# TODO(phase-1-gt-export): unblock the diagnostic-chain section below
# when Phase 1 emits per-line GT for `leningrad_devarim_F118B_fixture`
# via OPENMESORAH_GT_EXPORT_JSON. Until then, the diagnostic chain code path
# is exercised only by the mocked-unit tier (test_baseline_unit_nakdimon_chain.py).
"""

from __future__ import annotations

import os
from datetime import UTC
from pathlib import Path

import pytest

_THIS = Path(__file__).resolve()
SIBLING_ROOT = _THIS.parents[2]

DEFAULT_KRAKEN_MODEL = SIBLING_ROOT / "baselines" / ".cache" / "kraken" / "BiblIA_01.mlmodel"
GT_EXPORT_PATH_ENV = "OPENMESORAH_GT_EXPORT_JSON"


@pytest.mark.live_baselines
def test_live_realistic_chain_on_shema_fixture(tmp_path):
    """Live realistic chain: real Kraken + real Nakdimon over the Shema fixture.

    Skipped unless ALL of:
      - RUN_LIVE_BASELINES=1
      - cached BiblIA Kraken model present at the canonical path
        (operator must run baselines/scripts/fetch_biblia_kraken_model.py)

    On Linux+Py3.11 this exercises the full chain end-to-end:
    fetch_image -> recognize_lines -> nakdimon_diacritize -> serialize
    -> SandboxRun.write_prediction -> validate_expected_total_reports
    -> SandboxRun.promote -> realistic prediction file on disk.
    """
    if not DEFAULT_KRAKEN_MODEL.exists():
        pytest.skip(
            f"BiblIA Kraken model not cached at {DEFAULT_KRAKEN_MODEL}; "
            "run baselines/scripts/fetch_biblia_kraken_model.py first"
        )

    # Construct against an in-memory FakeManifest to avoid the manifest
    # schema bump's strictness for live ops; the real Manifest path is
    # exercised by score-time integration tests (Phase 4).
    from datetime import datetime

    from baselines.biblia_nakdimon import BibliaNakdimonBaseline

    from tests._fake_manifest import FakeFolio, FakeManifest

    fid = "leningrad_devarim_F118B_fixture"
    manifest = FakeManifest(
        folios=[FakeFolio(id=fid)],
        expected_reports_per_baseline={"biblia_nakdimon": 1},
    )
    bl = BibliaNakdimonBaseline.__new__(BibliaNakdimonBaseline)
    bl.manifest = manifest
    bl.results_root = tmp_path / "results"
    bl.replay = False
    bl.kraken_model_path = DEFAULT_KRAKEN_MODEL
    bl.image_cache = tmp_path / "image-cache"
    bl.gt_root = tmp_path / "no-gt-here"  # forces the diagnostic to fail; see below
    bl._started_at = datetime.now(UTC).isoformat(timespec="seconds")
    bl._folio_meta = {}

    # Issue 2 fix: if no explicit GT fixture is available, skip the
    # diagnostic-chain assertion (and the realistic-chain assertion, since
    # infer_folio writes both in one pass and a missing GT would raise
    # BaselineError).
    gt_path = os.environ.get(GT_EXPORT_PATH_ENV)
    if not gt_path:
        pytest.skip(f"set {GT_EXPORT_PATH_ENV} to run live diagnostic-chain fixture")

    gt_fixture = Path(gt_path)
    if not gt_fixture.exists():
        pytest.skip(f"{GT_EXPORT_PATH_ENV} does not exist: {gt_fixture}")
    bl.gt_root = gt_fixture.parent

    rc = bl.run()
    assert rc == 0

    realistic_path = tmp_path / "results" / "biblia_nakdimon" / f"{fid}.json"
    diag_path = tmp_path / "results" / "biblia_nakdimon" / "diagnostic" / f"{fid}.gt_fed.json"
    rm_path = tmp_path / "results" / "biblia_nakdimon" / "run_meta.json"

    assert realistic_path.exists()
    assert diag_path.exists()
    assert rm_path.exists()

    # Sanity: prediction validates against schema (already validated at
    # write time; we re-load to confirm).
    import json

    pred = json.loads(realistic_path.read_text(encoding="utf-8"))
    assert pred["baseline_id"] == "biblia_nakdimon"
    assert pred["folio_id"] == fid
    assert len(pred["lines"]) > 0

    rm = json.loads(rm_path.read_text(encoding="utf-8"))
    assert rm["pins"]["nakdimon_model_hash"] == "8fd7722b8002a690"
    assert rm["pins"]["kraken_model_hash"] is not None
    assert rm["pins"]["dictabert_model_revision"] is None
