import json
import subprocess
import sys
from pathlib import Path

from masoretic_eval.manifest import Manifest

FIXTURES = Path(__file__).parent / "fixtures"
MANIFEST_FIXTURE = FIXTURES / "phase_0_manifest_sample.json"


def _run_score(
    gt: Path,
    pred: Path,
    out: Path,
    *,
    manifest: Path | None = MANIFEST_FIXTURE,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    cmd = [
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
    ]
    if manifest is not None:
        cmd.extend(["--manifest", str(manifest)])
    return subprocess.run(
        cmd,
        capture_output=True,
        cwd=cwd,
        text=True,
    )


def test_cli_score_writes_output(tmp_path):
    # Fixtures are created in Step 2 below.
    gt = FIXTURES / "cli_gt.json"
    pred = FIXTURES / "cli_pred.json"
    out = tmp_path / "result.json"
    rc = _run_score(gt, pred, out)
    assert rc.returncode == 0, rc.stderr
    data = json.loads(out.read_text())
    assert data["prediction_id"] == "leningrad_devarim_f237b"
    assert data["manifest_hash"] == Manifest.load(MANIFEST_FIXTURE).manifest_hash
    assert data["scorer_version"] == "0.2.0"
    assert "tier1" in data["tiers"]


def test_cli_requires_manifest_when_default_missing(tmp_path):
    gt = FIXTURES / "cli_gt.json"
    pred = FIXTURES / "cli_pred.json"
    out = tmp_path / "result.json"

    rc = _run_score(gt, pred, out, manifest=None, cwd=tmp_path)

    assert rc.returncode != 0
    assert "manifest required" in rc.stderr
    assert not out.exists()


def test_cli_rejects_gt_missing_text_without_writing_output(tmp_path):
    gt = tmp_path / "missing_text_gt.json"
    pred = FIXTURES / "cli_pred.json"
    out = tmp_path / "result.json"
    gt.write_text(json.dumps({"metamarks": []}), encoding="utf-8")

    rc = _run_score(gt, pred, out)

    assert rc.returncode != 0
    assert "schema validation" in rc.stderr
    assert "--gt" in rc.stderr
    assert not out.exists()


def test_cli_accepts_optional_input_metadata(tmp_path):
    gt = tmp_path / "gt_with_metadata.json"
    pred = tmp_path / "pred_with_metadata.json"
    out = tmp_path / "result.json"
    gt.write_text(
        json.dumps(
            {
                "folio_id": "leningrad_devarim_f237b",
                "gt_version": "v0.1.0-test",
                "text": "שמע ישראל",
                "metamarks": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    pred.write_text(
        json.dumps(
            {
                "folio_id": "leningrad_devarim_f237b",
                "text": "שמע ישראל",
                "metamarks": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rc = _run_score(gt, pred, out)

    assert rc.returncode == 0, rc.stderr
    assert out.exists()


def test_cli_rejects_pred_unknown_metamark_without_writing_output(tmp_path):
    gt = FIXTURES / "cli_gt.json"
    pred = tmp_path / "unknown_metamark_pred.json"
    out = tmp_path / "result.json"
    pred.write_text(
        json.dumps(
            {
                "text": "שמע ישראל",
                "metamarks": [{"type": "unknown", "verse_ref": "Deut.6.4", "ordinal": 1}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rc = _run_score(gt, pred, out)

    assert rc.returncode != 0
    assert "schema validation" in rc.stderr
    assert "--pred" in rc.stderr
    assert "unknown" in rc.stderr
    assert not out.exists()


def test_cli_help():
    rc = subprocess.run(
        [sys.executable, "-m", "masoretic_eval.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert rc.returncode == 0
    assert "score" in rc.stdout
