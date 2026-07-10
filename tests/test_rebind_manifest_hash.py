"""Regression tests for the manifest_hash rebind path (blocker B1).

Any manifest edit re-fingerprints the manifest and strands every promoted
artifact carrying the old `manifest_hash`. `scripts/rebind_manifest_hash.py`
makes that a command instead of a hand-edit (cf. the by-hand `daf2c86`).

These tests used to poison the *committed* `results/` artifacts and restore them
in a `finally`. Those artifacts were withdrawn in the v0.1 Option A scope narrow
(baselines deferred to v0.1.1), so the tests now build a synthetic results tree
per test. That is strictly better: the properties below are properties of the
script, not of whatever happens to be committed, and they keep guarding the tool
through the gap in which no promoted artifact exists.

Pinned properties:

1. Discovery finds every `manifest_hash`-bearing JSON under results/, **including
   inside a `diagnostic/` subdirectory** -- the case
   `audit_release.check_results_manifest_hash` missed for its whole life because
   it globbed only one level deep.
2. `--check` fails on drift, wherever the drift is.
3. Rewriting touches exactly one line per file and is idempotent.
4. An empty tree is "nothing to do", not a false pass on a stale binding.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "rebind_manifest_hash.py"

GOOD = "0123456789abcdef"
STALE = "deadbeefdeadbeef"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("rebind_manifest_hash", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rebind = _load_script_module()


def _artifact(path: Path, manifest_hash: str) -> Path:
    """A promoted-artifact-shaped file: top-level, 2-space-indented manifest_hash."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"folio_id": "f", "manifest_hash": manifest_hash}, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _tree(root: Path, manifest_hash: str = GOOD) -> dict[str, Path]:
    """A results/ tree covering the shapes the real one had, incl. diagnostic/."""
    return {
        "prediction": _artifact(root / "biblia_kraken" / "folio.json", manifest_hash),
        "run_meta": _artifact(root / "biblia_kraken" / "run_meta.json", manifest_hash),
        "diagnostic": _artifact(
            root / "biblia_nakdimon" / "diagnostic" / "folio.gt_fed.json", manifest_hash
        ),
        "scores": _artifact(root / "scores" / "folio.json", manifest_hash),
    }


@pytest.fixture
def results(tmp_path, monkeypatch):
    root = tmp_path / "results"
    files = _tree(root)
    monkeypatch.setattr(rebind, "RESULTS_DIR", root)
    return files


def test_discovery_finds_every_hash_bearing_file_including_diagnostic_subdirs(results):
    """A one-level glob would miss `diagnostic/`. That bug shipped once already."""
    assert sorted(rebind.discover_artifacts()) == sorted(results.values())


def test_discovery_is_empty_when_the_tree_is_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(rebind, "RESULTS_DIR", tmp_path / "does_not_exist")
    assert rebind.discover_artifacts() == []


def test_check_passes_on_the_real_repo():
    """v0.1 has no promoted artifacts, so this must exit 0 -- 'nothing to do', not a lie."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr


def _hash_of(path: Path) -> str:
    return json.loads(path.read_text(encoding="utf-8"))["manifest_hash"]


@pytest.mark.parametrize("victim", ["prediction", "run_meta", "diagnostic", "scores"])
def test_check_detects_drift_anywhere_in_the_tree(results, victim):
    _artifact(results[victim], STALE)

    drifted = [p for p in rebind.discover_artifacts() if _hash_of(p) != GOOD]
    assert drifted == [results[victim]], "drift went undetected"

    # and the rewrite path repairs exactly that file
    assert rebind.rewrite(results[victim], GOOD) is True
    assert not [p for p in rebind.discover_artifacts() if _hash_of(p) != GOOD]


def test_rewrite_is_single_line_and_idempotent(tmp_path):
    path = _artifact(tmp_path / "run_meta.json", GOOD)
    original = path.read_text(encoding="utf-8")

    _artifact(path, STALE)
    assert rebind.rewrite(path, GOOD) is True

    # byte-identical to the original: only the one field ever moved
    assert path.read_text(encoding="utf-8") == original
    # idempotent: a second pass is a no-op
    assert rebind.rewrite(path, GOOD) is False
    assert json.loads(path.read_text(encoding="utf-8"))["manifest_hash"] == GOOD


def test_rewrite_refuses_a_file_with_no_manifest_hash(tmp_path):
    orphan = tmp_path / "no_hash.json"
    orphan.write_text('{"folio_id": "x"}\n', encoding="utf-8")
    with pytest.raises(rebind.RebindError, match="no manifest_hash line"):
        rebind.rewrite(orphan, GOOD)


def test_audit_release_catches_drift_in_a_diagnostic_subdir(tmp_path):
    """REL-09 gate must not be blind to results/<baseline>/diagnostic/*.json."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import audit_release  # noqa: PLC0415

    manifest = {"manifest_hash": GOOD, "folios": []}
    (tmp_path / "phase_0_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    _tree(tmp_path / "results")
    _artifact(tmp_path / "results" / "biblia_nakdimon" / "diagnostic" / "folio.gt_fed.json", STALE)

    errors = audit_release.check_results_manifest_hash(tmp_path)
    assert errors, "audit_release missed stale manifest_hash in a diagnostic/ file"
    assert "diagnostic" in errors[0]
