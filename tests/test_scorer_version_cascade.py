"""`scorer_version` cascades manifest -> run_meta. Both ends must hold.

`baselines/src/baselines/_base.py` composes each run's `run_meta.json` with
``"scorer_version": getattr(self.manifest, "scorer_version", None)``. The field
is therefore a *cascade source*, not a label. When the manifest's copy went
stale against the package (at `0a58c1d`, 2026-04-26 -- before any promoted run),
all four promoted `run_meta.json` faithfully recorded a scorer version that had
not run: `0.1.0`, while each pins a `sibling_git_sha` at which
`masoretic_eval.__version__` was already `0.2.0`.

Nothing caught it. `audit_release.py` had zero `scorer_version` checks and the
release invariant that would have flagged the manifest was an unimplemented
`xfail(strict=True)` stub. These tests close both halves:

* manifest == package   (also asserted in tests/release/test_manifest_release_invariants.py)
* run_meta == manifest  (the half that was missing entirely)
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import masoretic_eval

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "phase_0_manifest.json"
RESULTS = REPO_ROOT / "results"

RUN_METAS = sorted(RESULTS.glob("*/run_meta.json"))


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_no_promoted_run_metas_under_v01_option_a():
    """Guard the parametrization: an empty glob makes every run_meta test below vacuous.

    Under v0.1 (Option A) baselines are deferred to v0.1.1, so no `run_meta.json` is
    published and there is nothing to cascade into. That is the expected state -- but
    it has to be *asserted*, or the parametrized tests would pass by finding nothing
    and we would have no signal when v0.1.1 re-promotes an artifact carrying a stale
    scorer_version.
    """
    tracked = subprocess.check_output(
        ["git", "-C", str(REPO_ROOT), "ls-files", "--", "results"], text=True
    ).splitlines()
    assert not tracked, (
        "results/ is published again. Good -- now delete this test; the parametrized "
        "cascade checks below will start doing real work."
    )


def test_manifest_scorer_version_matches_the_package():
    assert _manifest()["scorer_version"] == masoretic_eval.__version__


@pytest.mark.parametrize("run_meta", RUN_METAS, ids=lambda p: p.parent.name)
def test_run_meta_scorer_version_matches_the_manifest(run_meta: Path):
    """The cascade's downstream end. This is the half that had no gate."""
    assert _load(run_meta)["scorer_version"] == _manifest()["scorer_version"]


@pytest.mark.parametrize("run_meta", RUN_METAS, ids=lambda p: p.parent.name)
def test_run_meta_scorer_version_matches_the_scorer_it_actually_ran(run_meta: Path):
    """The evidence that made correcting the emitted records a fix, not a fabrication.

    Each run pins the scorer commit it executed. Read `__version__` out of that
    commit and require the recorded `scorer_version` to match it. This is what
    makes the field falsifiable: it can now only be right by being true.
    """
    meta = _load(run_meta)
    sha = meta["sibling_git_sha"]

    blob = subprocess.run(
        ["git", "show", f"{sha}:masoretic_eval/__init__.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if blob.returncode != 0:
        pytest.skip(f"pinned scorer commit {sha} not present in this clone")

    versions = [
        line.split("=", 1)[1].strip().strip('"').strip("'")
        for line in blob.stdout.splitlines()
        if line.startswith("__version__")
    ]
    assert len(versions) == 1, f"{sha}: expected one __version__ line, got {versions}"

    assert meta["scorer_version"] == versions[0], (
        f"{run_meta.parent.name}: run_meta records scorer_version="
        f"{meta['scorer_version']!r} but its pinned sibling_git_sha {sha} has "
        f"__version__={versions[0]!r}"
    )
