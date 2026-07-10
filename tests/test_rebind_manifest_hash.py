"""Regression tests for the manifest_hash rebind path (blocker B1).

Any manifest edit re-fingerprints the manifest and strands every promoted
artifact carrying the old `manifest_hash`. `scripts/rebind_manifest_hash.py`
makes that a command instead of a hand-edit (cf. the by-hand `daf2c86`).

These tests pin three properties:

1. The script's discovery walk finds exactly the artifact set the strict bind
   test pins. If they diverge, the script would silently skip a file.
2. `--check` actually fails on drift, including drift in a `diagnostic/`
   subdirectory -- the case `audit_release.check_results_manifest_hash` missed
   for its whole life because it globbed only one level deep.
3. Rewriting touches exactly one line per file and is idempotent.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "rebind_manifest_hash.py"

sys.path.insert(0, str(REPO_ROOT))
from tests.test_manifest_hash_artifacts import (  # noqa: E402
    _f118b_artifact_paths,
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location("rebind_manifest_hash", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rebind = _load_script_module()


def test_discovery_matches_the_strict_bind_test_expectations():
    """The walk and the pinned list must agree, or the script skips files silently."""
    assert sorted(rebind.discover_artifacts()) == sorted(_f118b_artifact_paths())


def test_check_passes_on_a_clean_tree():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize(
    "victim",
    [
        "results/biblia_kraken/run_meta.json",
        # The case audit_release.py missed: two levels deep.
        "results/biblia_nakdimon/diagnostic/leningrad_devarim_F118B_fixture.gt_fed.json",
    ],
)
def test_check_detects_drift_including_in_diagnostic_subdirs(victim, tmp_path, monkeypatch):
    path = REPO_ROOT / victim
    original = path.read_text(encoding="utf-8")
    poisoned = re.sub(r'("manifest_hash": ")[0-9a-f]{16}', r"\1deadbeefdeadbeef", original, count=1)
    assert poisoned != original, "poison did not apply; has the field shape changed?"

    path.write_text(poisoned, encoding="utf-8")
    try:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--check"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert proc.returncode == 1, "drift went undetected"
        assert victim in proc.stderr
    finally:
        path.write_text(original, encoding="utf-8")


def test_audit_release_also_catches_diagnostic_drift():
    """REL-09 gate must not be blind to results/<baseline>/diagnostic/*.json."""
    victim = (
        REPO_ROOT / "results/biblia_nakdimon/diagnostic/leningrad_devarim_F118B_fixture.gt_fed.json"
    )
    original = victim.read_text(encoding="utf-8")
    victim.write_text(
        re.sub(r'("manifest_hash": ")[0-9a-f]{16}', r"\1deadbeefdeadbeef", original, count=1),
        encoding="utf-8",
    )
    try:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        import audit_release  # noqa: PLC0415

        importlib.reload(audit_release)
        errors = audit_release.check_results_manifest_hash(REPO_ROOT)
        assert errors, "audit_release missed stale manifest_hash in a diagnostic/ file"
        assert "diagnostic" in errors[0]
    finally:
        victim.write_text(original, encoding="utf-8")


def test_rewrite_is_single_line_and_idempotent():
    path = REPO_ROOT / "results/biblia_kraken/run_meta.json"
    original = path.read_text(encoding="utf-8")
    expected = rebind.current_manifest_hash()

    poisoned = re.sub(r'("manifest_hash": ")[0-9a-f]{16}', r"\1deadbeefdeadbeef", original, count=1)
    path.write_text(poisoned, encoding="utf-8")
    try:
        assert rebind.rewrite(path, expected) is True
        after = path.read_text(encoding="utf-8")

        # byte-identical to the original: only the one field ever moved
        assert after == original

        # idempotent: a second pass is a no-op
        assert rebind.rewrite(path, expected) is False

        # and the payload still parses with the right value
        assert json.loads(after)["manifest_hash"] == expected
    finally:
        path.write_text(original, encoding="utf-8")


def test_rewrite_refuses_a_file_with_no_manifest_hash(tmp_path):
    orphan = tmp_path / "no_hash.json"
    orphan.write_text('{"folio_id": "x"}\n', encoding="utf-8")
    with pytest.raises(rebind.RebindError, match="no manifest_hash line"):
        rebind.rewrite(orphan, "0123456789abcdef")
