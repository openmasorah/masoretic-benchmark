import json
import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def test_cli_score_writes_output(tmp_path):
    # Fixtures are created in Step 2 below.
    gt = FIXTURES / "cli_gt.json"
    pred = FIXTURES / "cli_pred.json"
    out = tmp_path / "result.json"
    rc = subprocess.run(
        [
            sys.executable,
            "-m",
            "masoretic_eval.cli",
            "score",
            "--gt",
            str(gt),
            "--pred",
            str(pred),
            "--folio-id",
            "leningrad_devarim_f237b",
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
    )
    assert rc.returncode == 0, rc.stderr
    data = json.loads(out.read_text())
    assert data["prediction_id"] == "leningrad_devarim_f237b"
    assert data["scorer_version"] == "0.2.0"
    assert "tier1" in data["tiers"]


def test_cli_help():
    rc = subprocess.run(
        [sys.executable, "-m", "masoretic_eval.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert rc.returncode == 0
    assert "score" in rc.stdout
