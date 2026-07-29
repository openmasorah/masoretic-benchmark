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
import re
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

    Under v0.1 (Option A) baselines are deferred to a future release, so no `run_meta.json` is
    published and there is nothing to cascade into. That is the expected state -- but
    it has to be *asserted*, or the parametrized tests would pass by finding nothing
    and we would have no signal when a release re-promotes an artifact carrying a stale
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


def test_package_version_matches_the_distribution_metadata():
    """`__version__` must equal what `pip`/`importlib.metadata` reports.

    THE HALF THAT WAS MISSING, and it let the same incident recur. The test
    above compares the manifest to ``__version__`` -- but when BOTH are stale
    it passes while saying nothing, because nothing tied either end to
    ``pyproject.toml``. That is exactly what happened at v0.1.1: the scorer
    took a BREAKING tier-4 vocabulary bump to ``0.3.0`` in ``pyproject.toml``
    while ``__version__`` and ``scorer_version`` both sat at ``0.2.0``, so the
    installed package reported a version its own metadata contradicted -- and
    the guard above was green throughout.

    Anchoring to the distribution metadata is what makes the chain
    non-vacuous: ``pyproject.toml`` is the only end a human edits when
    releasing, so it is the only end that can be trusted to move.
    """
    from importlib.metadata import PackageNotFoundError, version  # noqa: PLC0415

    try:
        installed = version("masoretic-eval")
    except PackageNotFoundError:  # pragma: no cover - editable/dev checkouts
        pytest.skip("masoretic-eval is not installed; nothing to compare against")

    assert installed == masoretic_eval.__version__, (
        f"installed distribution reports {installed} but masoretic_eval.__version__ is "
        f"{masoretic_eval.__version__} -- bump masoretic_eval/__init__.py to match "
        f"pyproject.toml"
    )


def test_the_whole_version_chain_is_one_value():
    """pyproject -> __version__ -> manifest, asserted end to end in one place.

    The three are separate files edited by separate motions, and every prior
    break in this repo has been two of them agreeing while the third drifted.
    Comparing them pairwise in separate tests is how that stayed invisible; this
    asserts the whole chain at once so a partial bump cannot be green.
    """
    from importlib.metadata import PackageNotFoundError, version  # noqa: PLC0415

    try:
        installed = version("masoretic-eval")
    except PackageNotFoundError:  # pragma: no cover
        pytest.skip("masoretic-eval is not installed; nothing to compare against")

    chain = {
        "pyproject (via importlib.metadata)": installed,
        "masoretic_eval.__version__": masoretic_eval.__version__,
        "phase_0_manifest.json::scorer_version": _manifest()["scorer_version"],
    }

    assert len(set(chain.values())) == 1, "scorer version chain has drifted: " + ", ".join(
        f"{k}={v}" for k, v in chain.items()
    )


# ---------------------------------------------------------------------------
# Documentation surfaces.
#
# The version chain above was made airtight and the docs still shipped `0.2.0`
# in six places, because no gate had ever looked at prose. A reader following
# GETTING-STARTED sees a `scorer_version` the scorer cannot emit, which is the
# same defect as a stale field -- it just fails at a human instead of a test.
#
# `CHANGELOG.md` is excluded on purpose: it is a historical record, and quoting
# the version a past release shipped is precisely its job.
# ---------------------------------------------------------------------------

_SCORER_VERSION_CLAIM = re.compile(r'"scorer_version":\s*"([0-9][^"]*)"')
_DUNDER_VERSION_CLAIM = re.compile(r"__version__`?\s*=\s*`?([0-9][0-9.]*)")
_EVAL_PIN_CLAIM = re.compile(r"(masoretic-eval(?:\[[a-z-]+\])?>=[0-9][0-9.]*,<[0-9][0-9.]*)")


def _tracked_docs() -> list[Path]:
    out = subprocess.check_output(
        ["git", "-C", str(REPO_ROOT), "ls-files", "--", "*.md"], text=True
    ).splitlines()
    return [REPO_ROOT / p for p in out if Path(p).name != "CHANGELOG.md"]


def test_docs_do_not_advertise_a_scorer_version_the_package_cannot_emit():
    stale = [
        f"{p.relative_to(REPO_ROOT)}:{n}: scorer_version {m.group(1)!r}"
        for p in _tracked_docs()
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        for m in _SCORER_VERSION_CLAIM.finditer(line)
        if m.group(1) != masoretic_eval.__version__
    ] + [
        f"{p.relative_to(REPO_ROOT)}:{n}: __version__ {m.group(1)!r}"
        for p in _tracked_docs()
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        for m in _DUNDER_VERSION_CLAIM.finditer(line)
        if m.group(1) != masoretic_eval.__version__
    ]

    assert not stale, f"docs claim a version other than {masoretic_eval.__version__}: " + "; ".join(
        stale
    )


def test_docs_quote_dependency_pins_that_the_pyprojects_actually_declare():
    """A documented pin nobody satisfies is worse than none -- it is followed."""
    real = "\n".join(
        (REPO_ROOT / f).read_text(encoding="utf-8")
        for f in ("oracles/pyproject.toml", "baselines/pyproject.toml")
    )
    wrong = [
        f"{p.relative_to(REPO_ROOT)}:{n}: {m.group(1)!r}"
        for p in _tracked_docs()
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        for m in _EVAL_PIN_CLAIM.finditer(line.replace(" ", ""))
        if m.group(1) not in real.replace(" ", "")
    ]

    assert not wrong, "docs quote masoretic-eval pins no pyproject declares: " + "; ".join(wrong)


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
