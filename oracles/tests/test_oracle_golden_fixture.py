"""ORA-06 contract test: oracle pipeline output roundtrips through the
unmodified scorer CLI without changing any tier score (D-25, Pitfall 5).

Two legs, both run via subprocess against the unmodified masoretic_eval CLI:
  Leg A: rates absent (None)              -- matches existing tests/test_golden_fixture.py baseline
  Leg B: rates populated from cached file -- proves the populated path is also bit-identical

Every byte of tier1/tier3/tier4 + composite + confusion_matrices MUST be
identical between A and B. tier2 differs ONLY in the two disagreement-rate
fields. CGJ U+034F preservation is verified end-to-end.

This test NEVER hits live DICTA -- it reads pre-cached oracle outputs from
oracles/tests/fixtures/oracle_cache/golden_fixture_oracles.json. Regenerate
that fixture via oracles/scripts/regenerate_golden_oracle_cache.py when
oracles drift.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]  # masoretic-benchmark/
GOLDEN_DIR = REPO_ROOT / "tests" / "fixtures" / "golden"
GT = GOLDEN_DIR / "gt.json"
PRED = GOLDEN_DIR / "prediction.json"
EXPECTED_NULL_RATES = GOLDEN_DIR / "expected_result.json"
ORACLE_CACHE = Path(__file__).parent / "fixtures" / "oracle_cache" / "golden_fixture_oracles.json"

CGJ = "͏"


def _run_scorer(out_path: Path, *, nakdimon_rate=None, dicta_rate=None) -> dict:
    cmd = [
        sys.executable,
        "-m",
        "masoretic_eval.cli",
        "score",
        "--gt",
        str(GT),
        "--pred",
        str(PRED),
        "--folio-id",
        "golden_deut_6_4_5",
        "--gt-version",
        "v0.1.0-golden",
        "--out",
        str(out_path),
    ]
    if nakdimon_rate is not None:
        cmd += ["--nakdimon-disagreement-rate", str(nakdimon_rate)]
    if dicta_rate is not None:
        cmd += ["--dicta-disagreement-rate", str(dicta_rate)]
    rc = subprocess.run(cmd, capture_output=True, text=True)
    assert rc.returncode == 0, f"scorer CLI failed: {rc.stderr}"
    return json.loads(out_path.read_text(encoding="utf-8"))


def test_oracle_roundtrip_preserves_scorer_output(tmp_path):
    # --- Leg A: rates absent ---
    a = _run_scorer(tmp_path / "a.json")
    # --- Leg B: rates populated from cached fixture ---
    cached = json.loads(ORACLE_CACHE.read_text(encoding="utf-8"))
    b = _run_scorer(
        tmp_path / "b.json",
        nakdimon_rate=cached["nakdimon_disagreement_rate"],
        dicta_rate=cached["dicta_disagreement_rate"],
    )
    # Tiers 1, 3, 4 must be byte-identical
    for tier in ("tier1", "tier3", "tier4"):
        assert a["tiers"][tier] == b["tiers"][tier], (
            f"drift in {tier}: A={a['tiers'][tier]} B={b['tiers'][tier]}"
        )
    # Composite + confusion matrices must be byte-identical
    assert a["composite"] == b["composite"], "composite drift between leg A and leg B"
    assert a["confusion_matrices"] == b["confusion_matrices"], "confusion drift"
    # Tier 2 keys identical EXCEPT the two rate fields
    a2, b2 = a["tiers"]["tier2"], b["tiers"]["tier2"]
    rate_keys = {"nakdimon_disagreement_rate", "dicta_disagreement_rate"}
    for key in set(a2) | set(b2):
        if key in rate_keys:
            continue
        assert a2[key] == b2[key], f"tier2 drift in non-rate key '{key}': A={a2[key]} B={b2[key]}"
    # Cached rates equal Leg B's emitted rates
    assert b2["nakdimon_disagreement_rate"] == cached["nakdimon_disagreement_rate"]
    assert b2["dicta_disagreement_rate"] == cached["dicta_disagreement_rate"]


def test_leg_a_matches_existing_expected_result():
    """Pitfall 5 anchor: the existing tests/fixtures/golden/expected_result.json
    must remain Leg A's exact output -- proves Phase 2 did NOT perturb the
    Phase 1-committed baseline."""
    if not EXPECTED_NULL_RATES.exists():
        import pytest

        pytest.skip("expected_result.json not found -- Phase 1 baseline missing")
    expected = json.loads(EXPECTED_NULL_RATES.read_text(encoding="utf-8"))
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        actual = _run_scorer(Path(td) / "a.json")
    assert actual.get("tiers") == expected.get("tiers"), (
        "Phase 2 perturbed Leg A -- tier results drifted vs. expected_result.json"
    )
    assert actual.get("composite") == expected.get("composite"), "composite drift"
    assert actual.get("confusion_matrices") == expected.get("confusion_matrices"), "confusion drift"


def test_cgj_preserved_through_both_legs(tmp_path):
    """Phase 1 D-30/D-31 carry-forward: U+034F (CGJ) survives end-to-end."""
    gt_text = GT.read_text(encoding="utf-8")
    pred_text = PRED.read_text(encoding="utf-8")
    if CGJ not in gt_text and CGJ not in pred_text:
        import pytest

        pytest.skip("CGJ U+034F not present in golden fixture -- nothing to preserve here")
    _run_scorer(tmp_path / "a.json")
    cached = json.loads(ORACLE_CACHE.read_text(encoding="utf-8"))
    _run_scorer(
        tmp_path / "b.json",
        nakdimon_rate=cached["nakdimon_disagreement_rate"],
        dicta_rate=cached["dicta_disagreement_rate"],
    )
    for path in (tmp_path / "a.json", tmp_path / "b.json"):
        blob = path.read_text(encoding="utf-8")
        assert CGJ in blob, f"CGJ U+034F stripped from scorer output at {path}"
