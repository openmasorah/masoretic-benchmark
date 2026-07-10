"""`manifest_hash` binding, and the v0.1 absence of a promoted results tree.

v0.1 ships under Option A: the IAA / adjudicated-GT benchmark and the scorer.
Automated baselines are deferred to v0.1.1, so `results/` and
`results_provisional/` are not part of the public tree.

This file used to pin an expected set of 11 promoted F118B artifacts. Those
artifacts were withdrawn: the F118B whole-folio scores were computed over Kraken
lines that include the masorah apparatus, ordered by `line_id` because every bbox
was `[0,0,0,0]` -- which inverts the ranking -- and the `biblia_char_menaked`
predictions were corrupt. Pinning them would have pinned that.

Two properties now, and neither is vacuous:

1. The tree really is absent. An empty glob must be asserted, not assumed --
   otherwise property 2 silently tests nothing.
2. *If* a promoted artifact exists (the v0.1.1 re-promotion), it binds to the
   current manifest. This keeps the rebind coupling guarded across the gap.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from masoretic_eval.manifest import Manifest

REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS = REPO_ROOT / "results"
RESULTS_PROVISIONAL = REPO_ROOT / "results_provisional"
MANIFEST_HASH_RE = re.compile(r"^[0-9a-f]{16}$")


def _current_manifest_hash() -> str:
    return Manifest.load(REPO_ROOT / "phase_0_manifest.json").manifest_hash


def _hash_bearing_artifacts() -> list[Path]:
    if not RESULTS.exists():
        return []
    found = []
    for path in RESULTS.rglob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and "manifest_hash" in payload:
            found.append(path)
    return sorted(found)


def test_the_manifest_hash_is_well_formed():
    assert MANIFEST_HASH_RE.fullmatch(_current_manifest_hash())


def _tracked_under(*paths: str) -> list[str]:
    """Git-tracked files under the given paths. A local run leaves gitignored
    crops behind, so 'published' means tracked, not 'present on this disk'."""
    out = subprocess.check_output(
        ["git", "-C", str(REPO_ROOT), "ls-files", "--", *paths], text=True
    )
    return [line for line in out.splitlines() if line]


def test_results_trees_publish_nothing_under_v01_option_a():
    """Baselines are deferred to v0.1.1. Their absence is intentional, so assert it.

    Checks tracked content, not directory existence: running a baseline locally
    creates `results/<bl>/<folio>/*.jpg` line crops, which are gitignored and were
    never part of the published tree.
    """
    tracked = _tracked_under("results", "results_provisional")
    assert not tracked, (
        "the withdrawn result trees are tracked again: "
        f"{tracked[:5]}{'...' if len(tracked) > 5 else ''}. "
        "If this is the v0.1.1 re-promotion, replace this test with a strict "
        "expected-set pin -- but only over re-emitted predictions (pinned "
        "transformers) and ROI/main-text scores."
    )


def test_any_promoted_artifact_binds_to_the_current_manifest_hash():
    """Guards the rebind coupling across the v0.1 -> v0.1.1 gap.

    Passes trivially while `results/` is absent -- which is exactly why the test
    above asserts that absence rather than letting it pass unnoticed.
    """
    expected = _current_manifest_hash()
    for path in _hash_bearing_artifacts():
        value = json.loads(path.read_text(encoding="utf-8"))["manifest_hash"]
        assert isinstance(value, str) and MANIFEST_HASH_RE.fullmatch(value), path
        assert value == expected, path
