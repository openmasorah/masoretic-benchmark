from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from masoretic_eval.manifest import Manifest

REPO_ROOT = Path(__file__).resolve().parents[1]
FOLIO_ID = "leningrad_devarim_F118B_fixture"
MANIFEST_HASH_RE = re.compile(r"^[0-9a-f]{16}$")
PROMOTED_BASELINES = (
    "biblia_char_menaked",
    "biblia_kraken",
    "biblia_nakdimon",
    "llm_vision",
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _f118b_artifact_paths() -> list[Path]:
    results_dir = REPO_ROOT / "results"
    expected_paths: set[Path] = set()
    for baseline_id in PROMOTED_BASELINES:
        baseline_dir = results_dir / baseline_id
        expected_paths.add(baseline_dir / f"{FOLIO_ID}.json")
        expected_paths.add(baseline_dir / "run_meta.json")
        expected_paths.update((baseline_dir / "diagnostic").glob(f"{FOLIO_ID}*.json"))
    expected_paths.add(results_dir / "scores" / f"{FOLIO_ID}.json")

    discovered_paths = {
        path
        for path in results_dir.rglob("*.json")
        if path in expected_paths
        or (path.name == "run_meta.json" and path.parent.name in PROMOTED_BASELINES)
        or FOLIO_ID in path.name
    }
    assert discovered_paths == expected_paths
    return sorted(discovered_paths)


def test_promoted_f118b_artifacts_bind_to_current_manifest_hash():
    expected_hash = Manifest.load(REPO_ROOT / "phase_0_manifest.json").manifest_hash
    assert MANIFEST_HASH_RE.fullmatch(expected_hash)

    for path in _f118b_artifact_paths():
        assert path.exists(), f"missing promoted F118B artifact: {path}"
        payload = _load_json(path)
        assert "manifest_hash" in payload, f"missing manifest_hash in {path}"
        assert payload["manifest_hash"] == expected_hash, path


def test_promoted_f118b_artifacts_do_not_carry_empty_manifest_hashes():
    for path in _f118b_artifact_paths():
        payload = _load_json(path)
        value = payload.get("manifest_hash")
        assert value is not None, f"null manifest_hash in {path}"
        assert value != "", f"empty manifest_hash in {path}"
        assert isinstance(value, str), f"non-string manifest_hash in {path}"
        assert MANIFEST_HASH_RE.fullmatch(value), f"malformed manifest_hash in {path}"
