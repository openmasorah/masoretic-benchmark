"""BL-04 BibliaCharMenakedBaseline mocked unit tests.

Mirror of plan 03-05's test_baseline_unit_nakdimon_chain.py: tests construct
the subclass via cls.__new__ + attribute assignment (bypassing real
Manifest.load), mock oracles.dictabert.diacritize + recognize_lines +
fetch_image, and assert both the realistic chain prediction AND the GT-fed
diagnostic prediction land on disk with the right shape.

Per D-26 + Phase 3 A-3: BL-04 imports oracles.dictabert.diacritize ONLY.
Per D-27: module docstring carries the verbatim off-label disclaimer
(verified by test_dictabert_disclaimer_invariant.py).

Coverage:
- Test 1: chain runs realistic + diagnostic; both files land on disk.
- Test 2: realistic uses Kraken text as tier-1; diagnostic uses GT consonants.
- Test 3: run_meta.pins.dictabert_model_revision is set to the Phase 2 lock;
  nakdimon_model_hash is None.
- Test 4: D-15 SandboxRun.count() counts realistic only (diagnostic NOT counted).
- Test 5: AST cross-check — class structure (BL-04 doesn't override run() or
  infer_folio()) — sanity guard for D-12.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from baselines._base import LineRecord
from tests._fake_manifest import FakeFolio, FakeManifest


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


@pytest.fixture
def gt_fixture(tmp_path):
    """Per-line GT fixture for the diagnostic chain. Provides {lines:[...]}
    with line_id, bbox, tier1 — the exact shape ChainBaseline._load_gt_consonants
    expects."""
    gt = tmp_path / "gt"
    gt.mkdir()
    fid = "leningrad_devarim_shema_fixture"
    (gt / f"{fid}.json").write_text(
        json.dumps(
            {
                "lines": [
                    {
                        "line_id": f"{fid}_L001",
                        "bbox": [10, 20, 500, 60],
                        "tier1": "שמע ישראל",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return gt


@pytest.fixture
def manifest_with_shema_fixture():
    fid = "leningrad_devarim_shema_fixture"
    return FakeManifest(
        folios=[FakeFolio(id=fid)],
        expected_reports_per_baseline={
            "biblia_kraken": 1,
            "biblia_nakdimon": 1,
            "biblia_char_menaked": 1,
            "llm_vision": 1,
        },
    )


def _ctor(tmp_path: Path, manifest: FakeManifest, gt_root: Path):
    """Construct BibliaCharMenakedBaseline bypassing real Manifest.load."""
    from baselines.biblia_char_menaked import BibliaCharMenakedBaseline

    bl = BibliaCharMenakedBaseline.__new__(BibliaCharMenakedBaseline)
    bl.manifest = manifest
    bl.results_root = tmp_path / "results"
    bl.replay = False
    bl.kraken_model_path = tmp_path / "fake.mlmodel"
    bl.image_cache = tmp_path / "image-cache"
    bl.gt_root = Path(gt_root)
    bl._started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    bl._folio_meta = {}
    return bl


def _kraken_lines(folio_id: str) -> list[LineRecord]:
    return [
        LineRecord(
            line_id=f"{folio_id}_L001",
            bbox=(10, 20, 500, 60),
            tier1="שמע ישראל",  # Kraken's "noisy" consonantal output
            tier2="שמע ישראל",
            tier3="שמע ישראל",
            tier4_records=tuple(),
            kraken_confidence=0.91,
        )
    ]


# ----------------------------------------------------------------------
# Test 1: chain produces realistic + diagnostic outputs
# ----------------------------------------------------------------------


def test_char_menaked_chain_runs_realistic_and_diagnostic(
    tmp_path, manifest_with_shema_fixture, gt_fixture
):
    fid = "leningrad_devarim_shema_fixture"
    fake_lines = _kraken_lines(fid)
    fake_image_path = tmp_path / "image-cache" / f"{fid}.jpg"

    with patch(
        "baselines._kraken.recognize_lines", return_value=fake_lines
    ), patch(
        "baselines._images.fetch_image", return_value=fake_image_path
    ), patch(
        "oracles.dictabert.diacritize", lambda s: f"DIAC({s})"
    ):
        bl = _ctor(tmp_path, manifest_with_shema_fixture, gt_fixture)
        rc = bl.run()

    assert rc == 0
    realistic_path = (
        tmp_path / "results" / "biblia_char_menaked" / f"{fid}.json"
    )
    diag_path = (
        tmp_path
        / "results"
        / "biblia_char_menaked"
        / "diagnostic"
        / f"{fid}.gt_fed.json"
    )
    assert realistic_path.exists(), "realistic prediction not promoted"
    assert diag_path.exists(), "GT-fed diagnostic not promoted"


# ----------------------------------------------------------------------
# Test 2: tier-1 differs between realistic (Kraken text) and diagnostic (GT)
# ----------------------------------------------------------------------


def test_char_menaked_tier1_kraken_vs_gt(
    tmp_path, manifest_with_shema_fixture, gt_fixture
):
    fid = "leningrad_devarim_shema_fixture"
    # Distinguishable strings so we can tell which path we're looking at.
    kraken_text = "ש0מע יש0ראל"  # Kraken's noisy output
    fake_lines = [
        LineRecord(
            line_id=f"{fid}_L001",
            bbox=(10, 20, 500, 60),
            tier1=kraken_text,
            tier2=kraken_text,
            tier3=kraken_text,
            tier4_records=tuple(),
            kraken_confidence=0.5,
        )
    ]
    fake_image_path = tmp_path / "image-cache" / f"{fid}.jpg"

    with patch(
        "baselines._kraken.recognize_lines", return_value=fake_lines
    ), patch(
        "baselines._images.fetch_image", return_value=fake_image_path
    ), patch(
        "oracles.dictabert.diacritize", lambda s: f"DIAC({s})"
    ):
        bl = _ctor(tmp_path, manifest_with_shema_fixture, gt_fixture)
        bl.run()

    realistic = json.loads(
        (tmp_path / "results" / "biblia_char_menaked" / f"{fid}.json").read_text(
            encoding="utf-8"
        )
    )
    diag = json.loads(
        (
            tmp_path
            / "results"
            / "biblia_char_menaked"
            / "diagnostic"
            / f"{fid}.gt_fed.json"
        ).read_text(encoding="utf-8")
    )

    # Realistic: tier-1 = Kraken text (noisy); tier-2/3 = diacritized Kraken text
    assert realistic["lines"][0]["tier1"] == kraken_text
    assert realistic["lines"][0]["tier2"].startswith("DIAC(")

    # Diagnostic: tier-1 = GT consonants; tier-2/3 = diacritized GT
    assert diag["lines"][0]["tier1"] == "שמע ישראל"  # the GT
    assert diag["lines"][0]["tier2"].startswith("DIAC(")
    assert diag["lines"][0]["tier1"] != kraken_text  # different from Kraken!


# ----------------------------------------------------------------------
# Test 3: run_meta pins (dictabert_model_revision set; nakdimon_model_hash None)
# ----------------------------------------------------------------------


def test_char_menaked_run_meta_pins(
    tmp_path, manifest_with_shema_fixture, gt_fixture
):
    fid = "leningrad_devarim_shema_fixture"
    fake_lines = _kraken_lines(fid)
    fake_image_path = tmp_path / "image-cache" / f"{fid}.jpg"

    with patch(
        "baselines._kraken.recognize_lines", return_value=fake_lines
    ), patch(
        "baselines._images.fetch_image", return_value=fake_image_path
    ), patch(
        "oracles.dictabert.diacritize", lambda s: f"DIAC({s})"
    ):
        bl = _ctor(tmp_path, manifest_with_shema_fixture, gt_fixture)
        bl.run()

    meta_path = tmp_path / "results" / "biblia_char_menaked" / "run_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    # Phase 2 02-04 lock — re-asserted here so a Phase 2 revision drift is
    # caught at the consumer layer too.
    assert (
        meta["pins"]["dictabert_model_revision"]
        == "d311fbf7c403e50b040440e4859ac78064d025d0"
    )
    assert meta["pins"]["nakdimon_model_hash"] is None
    # KRAKEN_MODEL_HASH is populated because the realistic chain uses Kraken.
    from baselines._kraken import KRAKEN_MODEL_HASH

    assert meta["pins"]["kraken_model_hash"] == KRAKEN_MODEL_HASH
    assert meta["pins"]["llm_pin_md_hash"] is None


# ----------------------------------------------------------------------
# Test 4: D-15 — SandboxRun.count() counts realistic only (diagnostic excluded)
# ----------------------------------------------------------------------


def test_char_menaked_diagnostic_not_counted_for_d15(
    tmp_path, manifest_with_shema_fixture, gt_fixture
):
    """If SandboxRun.count() counted the diagnostic file, D-15's
    expected_reports_per_baseline check would see 2 instead of 1 for a
    1-folio run and the run would falsely fail. This test pins the policy:
    diagnostic does NOT count."""
    fid = "leningrad_devarim_shema_fixture"
    fake_lines = _kraken_lines(fid)
    fake_image_path = tmp_path / "image-cache" / f"{fid}.jpg"

    # expected = 1 — must succeed if diagnostic is correctly excluded.
    with patch(
        "baselines._kraken.recognize_lines", return_value=fake_lines
    ), patch(
        "baselines._images.fetch_image", return_value=fake_image_path
    ), patch(
        "oracles.dictabert.diacritize", lambda s: f"DIAC({s})"
    ):
        bl = _ctor(tmp_path, manifest_with_shema_fixture, gt_fixture)
        rc = bl.run()

    assert rc == 0
    # Realistic AND diagnostic both exist — but D-15 was satisfied at count=1.
    final_dir = tmp_path / "results" / "biblia_char_menaked"
    assert (final_dir / f"{fid}.json").exists()
    assert (final_dir / "diagnostic" / f"{fid}.gt_fed.json").exists()


# ----------------------------------------------------------------------
# Test 5: AST cross-checks — D-12 structural guard (defense in depth)
# ----------------------------------------------------------------------


def test_char_menaked_baseline_id_canonical():
    from baselines.biblia_char_menaked import BibliaCharMenakedBaseline

    assert BibliaCharMenakedBaseline.BASELINE_ID == "biblia_char_menaked"


def test_char_menaked_pin_field_and_value():
    from baselines.biblia_char_menaked import BibliaCharMenakedBaseline

    assert (
        BibliaCharMenakedBaseline.DIACRITIZER_PIN_FIELD
        == "dictabert_model_revision"
    )
    assert (
        BibliaCharMenakedBaseline.DIACRITIZER_PIN_VALUE
        == "d311fbf7c403e50b040440e4859ac78064d025d0"
    )


def test_char_menaked_does_not_override_run_or_infer_folio():
    """D-12 structural lock + ChainBaseline contract: BL-04 only overrides
    BASELINE_ID, DIACRITIZER_PIN_FIELD, DIACRITIZER_PIN_VALUE, and diacritize().
    It MUST NOT override run() or infer_folio()."""
    from baselines.biblia_char_menaked import BibliaCharMenakedBaseline

    assert "run" not in BibliaCharMenakedBaseline.__dict__, (
        "D-12: BL-04 must NOT override run()"
    )
    assert "infer_folio" not in BibliaCharMenakedBaseline.__dict__, (
        "BL-04 must NOT override infer_folio() — that's ChainBaseline's "
        "shared two-output template"
    )
    # And it MUST override diacritize().
    assert "diacritize" in BibliaCharMenakedBaseline.__dict__, (
        "BL-04 must override diacritize() to wire the DictaBERT call"
    )
