"""Golden fixture end-to-end: scorer output must be byte-identical to expected_result.json.

This is the Week-1 day 1-2 non-negotiable gate: if this test drifts, the
scorer contract has changed and every downstream consumer must be notified.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

GOLDEN = Path(__file__).parent / "fixtures" / "golden"


def test_golden_fixture_roundtrip(tmp_path):
    out = tmp_path / "actual.json"
    rc = subprocess.run(
        [sys.executable, "-m", "masoretic_eval.cli", "score",
         "--gt", str(GOLDEN / "gt.json"),
         "--pred", str(GOLDEN / "prediction.json"),
         "--folio-id", "golden_deut_6_4_5",
         "--gt-version", "v0.1.0-golden",
         "--out", str(out)],
        capture_output=True, text=True,
    )
    assert rc.returncode == 0, rc.stderr
    actual = json.loads(out.read_text())
    expected = json.loads((GOLDEN / "expected_result.json").read_text())

    # Structural invariants that must never drift.
    assert actual["scorer_version"] == expected["scorer_version"]
    assert actual["normalization"] == expected["normalization"]
    assert actual["denominator_policy"] == expected["denominator_policy"]

    # Tier-level numeric invariants.
    for tier in ("tier1", "tier2", "tier3", "tier4"):
        assert actual["tiers"][tier] == expected["tiers"][tier], f"drift in {tier}"
    assert actual["composite"] == expected["composite"]
    assert actual["tiers"]["tier4"]["fn"] == 1  # the large ע that prediction dropped
