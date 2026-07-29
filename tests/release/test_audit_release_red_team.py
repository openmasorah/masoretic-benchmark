"""REL-09: red-team fixture tests for scripts/audit_release.py."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
AUDIT = REPO_ROOT / "scripts" / "audit_release.py"
FIXTURES = REPO_ROOT / "tests" / "release" / "fixtures"


def _bootstrap_clean_tmp(tmp_path: Path) -> Path:
    """Materialize a minimal sibling-repo-like tree at tmp_path for audit testing."""
    subprocess.check_call(["git", "init", "-q"], cwd=tmp_path)
    subprocess.check_call(["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"])
    subprocess.check_call(["git", "-C", str(tmp_path), "config", "user.name", "test"])
    manifest = {
        "manifest_hash": "abc123",
        "scorer_version": "0.2.0",
        "nakdimon_model_hash": "8fd7722b8002a690",
        "folios": [
            {
                "folio_id": "leningrad_devarim_F118B",
                "manuscript": "leningrad",
                "book": "devarim",
                "gt_hash": "f1f1f1",
                "in_frozen_scope": True,
            }
        ],
        "manifest_changelog": [],
    }
    (tmp_path / "phase_0_manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "scripts").mkdir()
    shutil.copy(AUDIT, tmp_path / "scripts" / "audit_release.py")
    shutil.copy(
        REPO_ROOT / "scripts" / "reject_private_paths.py",
        tmp_path / "scripts" / "reject_private_paths.py",
    )
    subprocess.check_call(["git", "-C", str(tmp_path), "add", "."])
    subprocess.check_call(["git", "-C", str(tmp_path), "commit", "-q", "-m", "init"])
    return tmp_path


def _run_audit(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "scripts/audit_release.py",
            "--root",
            str(root),
            "--ignore-baalshem-strings",
            *args,
        ],
        cwd=root,
        capture_output=True,
        text=True,
    )


def _placeholder_cer_tier() -> dict:
    """An all-zero but schema-complete per-tier CER block.

    Kept in one place so adding a field to ``cer_tier`` in
    ``schemas/iaa_report.schema.json`` does not silently turn the placeholder
    red-team test into a schema-validation test.
    """
    return {
        "cer_vs_consensus_b": 0.0,
        "ci95": [0.0, 0.0],
        "cer_vs_consensus_a": 0.0,
        "ci95_vs_consensus_a": [0.0, 0.0],
        "cer_a_vs_b_round0": 0.0,
        "ci95_a_vs_b_round0": [0.0, 0.0],
        "denominator_codepoints_consensus": 1,
        "denominator_codepoints_a": 1,
        "edits_vs_consensus_b": 0,
        "edits_vs_consensus_a": 0,
        "edits_a_vs_b_round0": 0,
    }


def test_clean_repo_passes_audit(tmp_path):
    root = _bootstrap_clean_tmp(tmp_path)
    r = _run_audit(root, "--strict")
    assert r.returncode == 0, f"clean repo should pass; stderr: {r.stderr}"


def test_placeholder_iaa_report_fails_release_tier_audit(tmp_path):
    root = _bootstrap_clean_tmp(tmp_path)
    schemas = root / "schemas"
    schemas.mkdir()
    shutil.copy(
        REPO_ROOT / "schemas" / "iaa_report.schema.json",
        schemas / "iaa_report.schema.json",
    )
    report = {
        "iaa_status": "placeholder",
        "folios": [
            "leningrad_devarim_F118B_fixture",
            "leningrad_devarim_F119A_fixture",
            "leningrad_devarim_F120A_fixture",
        ],
        # Schema-valid but all-zero: the point of this fixture is that
        # `iaa_status: placeholder` must be caught by the RELEASE tier, not by
        # the schema. Carries the full v0.1.1 field set so the test still
        # exercises that distinction rather than tripping on a missing property.
        "tier1": _placeholder_cer_tier(),
        "tier2": _placeholder_cer_tier(),
        "tier3": _placeholder_cer_tier(),
        "tier4": {"f1_mean": 1.0, "ci95": [1.0, 1.0]},
        "adjudication_summary": {
            "tier1_disagreements_reconciled": 0,
            "tier2_disagreements_reconciled": 0,
            "tier3_disagreements_reconciled": 0,
            "tier4_disagreements_reconciled": 0,
        },
    }
    (root / "iaa_report.json").write_text(json.dumps(report))
    subprocess.check_call(["git", "-C", str(root), "add", "."])
    subprocess.check_call(["git", "-C", str(root), "commit", "-q", "-m", "placeholder"])
    staging = _run_audit(root, "--strict")
    assert staging.returncode == 0, staging.stderr
    release = _run_audit(root, "--strict", "--release-tier")
    assert release.returncode == 1
    assert "iaa_status='placeholder'" in release.stderr


def test_planted_cairo_shmuel_folio_fails_audit(tmp_path):
    root = _bootstrap_clean_tmp(tmp_path)
    planted = json.loads((FIXTURES / "planted_cairo_shmuel.json").read_text())
    (root / "phase_0_manifest.json").write_text(json.dumps(planted))
    subprocess.check_call(["git", "-C", str(root), "commit", "-aq", "-m", "plant"])
    r = _run_audit(root, "--strict")
    assert r.returncode == 1
    assert "manuscript=" in r.stderr or "cairo_shmuel" in r.stderr.lower()


def test_planted_baalshem_string_fails_audit(tmp_path):
    root = _bootstrap_clean_tmp(tmp_path)
    shutil.copy(FIXTURES / "planted_baalshem_string.txt", root / "leaked.txt")
    subprocess.check_call(["git", "-C", str(root), "add", "leaked.txt"])
    subprocess.check_call(["git", "-C", str(root), "commit", "-q", "-m", "plant"])
    r = subprocess.run(
        [sys.executable, "scripts/audit_release.py", "--root", str(root), "--strict"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 1
    assert "leaked.txt" in r.stderr


def test_planted_scans_dir_fails_audit(tmp_path):
    root = _bootstrap_clean_tmp(tmp_path)
    (root / "scans").mkdir()
    (root / "scans" / "private.jpg.placeholder").write_text("")
    subprocess.check_call(["git", "-C", str(root), "add", "scans/"])
    subprocess.check_call(["git", "-C", str(root), "commit", "-q", "-m", "plant"])
    r = _run_audit(root, "--strict")
    assert r.returncode == 1
    assert "scans/" in r.stderr


def test_manifest_hash_mismatch_fails_audit(tmp_path):
    root = _bootstrap_clean_tmp(tmp_path)
    (root / "results" / "biblia_kraken").mkdir(parents=True)
    mismatch = json.loads((FIXTURES / "manifest_hash_mismatch.json").read_text())
    (root / "results" / "biblia_kraken" / "F118B.json").write_text(json.dumps(mismatch))
    subprocess.check_call(["git", "-C", str(root), "add", "results/"])
    subprocess.check_call(["git", "-C", str(root), "commit", "-q", "-m", "plant"])
    r = _run_audit(root, "--strict")
    assert r.returncode == 1
    assert "manifest_hash" in r.stderr
