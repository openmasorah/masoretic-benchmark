"""The D-16 approval gate's SHELL LOGIC, executed — not merely inspected.

Why this exists
---------------
``tests/release/test_release_tag_guard.py`` pins the workflow's *contract*: the
triggers it carries, the jobs publication depends on, the refusal to default a
missing reviewer identity. It cannot pin the gate's *behaviour*, because that
lives in a shell script inside a ``run:`` block.

That was the whole exposure. The gate runs only when a ``benchmark-v*`` tag is
pushed — by which point the tag object already exists and it is too late to
discover the logic is wrong. And at v0.1.1 the gate was rewritten to carry a
**waiver path that can let a release proceed without an approving review**. A
gate that can waive its own requirement is precisely the code that needs a
regression test before it governs a real tag; until this file, its only test was
an ad-hoc harness in a temp directory.

That is the same defect class as the v0.1.1 "recomputed on every push" claim:
verification asserted but not executed by anything automated.

What this does
--------------
Extracts the approval step's script **verbatim** from the workflow YAML — so the
text under test is the text that ships, not a paraphrase that can drift — and
runs it against a stubbed ``gh`` for each scenario the policy distinguishes.

Fixtures are generated per-run with timestamps relative to *now*, so "requested
20 days ago" keeps meaning that. Committed fixtures with frozen dates would
quietly stop testing the window as the repository ages.

The reviewer login is parameterised. Hard-coding a real collaborator's GitHub
handle into fixtures would put a person's identity in test data for no reason.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release-tag.yml"

#: Placeholder handle. The gate reads the real one from the repository variable
#: ``YOSEF_GH_USERNAME`` at run time; nothing here depends on its value.
REVIEWER = "reviewer-of-record"
OTHER = "someone-else"
WINDOW_DAYS = 14


# ---------------------------------------------------------------------------
# Extract the shipped script
# ---------------------------------------------------------------------------


def _approval_gate_script() -> str:
    """The approval step's ``run:`` block, verbatim from the workflow."""
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["approval"]["steps"]
    matches = [s for s in steps if "run" in s and "REVIEW_WINDOW_DAYS" in s.get("run", "")]

    assert len(matches) == 1, (
        f"expected exactly one approval step reading REVIEW_WINDOW_DAYS, found {len(matches)}. "
        "If the gate was restructured, update this extractor rather than deleting the test."
    )
    return matches[0]["run"]


def _iso(days_ago: float) -> str:
    return (datetime.now(UTC) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Scenario fixtures: (reviews, timeline, pr)
# ---------------------------------------------------------------------------


def _requested(days_ago: float, who: str = REVIEWER) -> list[dict]:
    return [
        {
            "event": "review_requested",
            "created_at": _iso(days_ago),
            "requested_reviewer": {"login": who},
        }
    ]


def _review(state: str, days_ago: float, who: str = REVIEWER) -> dict:
    return {"user": {"login": who}, "state": state, "submitted_at": _iso(days_ago)}


SCENARIOS: dict[str, dict] = {
    # --- passes ---
    "approved": {
        "reviews": [_review("APPROVED", 1)],
        "timeline": _requested(20),
        "pr": {"created_at": _iso(20), "requested_reviewers": []},
        "expect_exit": 0,
        "expect_waiver": False,
        "expect_reason": "D-16 satisfied",
        "why": "a standing APPROVED review is the original, unchanged pass condition",
    },
    "waiver_window_lapsed": {
        "reviews": [],
        "timeline": _requested(20),
        "pr": {"created_at": _iso(20), "requested_reviewers": [{"login": REVIEWER}]},
        "expect_exit": 0,
        "expect_waiver": True,
        "expect_reason": "D-16 waiver",
        "why": "requested 20d ago, window is 14d, no review of any kind",
    },
    "waiver_created_at_fallback": {
        "reviews": [],
        "timeline": [],  # no review_requested event recorded
        "pr": {"created_at": _iso(20), "requested_reviewers": [{"login": REVIEWER}]},
        "expect_exit": 0,
        "expect_waiver": True,
        "expect_reason": "falling back to PR created_at",
        "why": "request still pending, timeline has no event; falls back to created_at",
    },
    # --- refusals ---
    "never_requested": {
        "reviews": [],
        "timeline": [],
        "pr": {"created_at": _iso(20), "requested_reviewers": []},
        "expect_exit": 1,
        "expect_waiver": False,
        "expect_reason": "was never requested as a reviewer",
        "why": (
            "a review you never asked for cannot lapse. NOT hypothetical: this is the "
            "actual state of release PR #45 for benchmark-v0.1.0 -- no review_requested "
            "event exists on it, so the tag's gate fails here rather than on the window."
        ),
    },
    "window_not_lapsed": {
        "reviews": [],
        "timeline": _requested(3),
        "pr": {"created_at": _iso(3), "requested_reviewers": [{"login": REVIEWER}]},
        "expect_exit": 1,
        "expect_waiver": False,
        "expect_reason": "has not lapsed",
        "why": "3 days elapsed against a 14-day window",
    },
    "engaged_without_approving": {
        "reviews": [_review("COMMENTED", 1)],
        "timeline": _requested(20),
        "pr": {"created_at": _iso(20), "requested_reviewers": []},
        "expect_exit": 1,
        "expect_waiver": False,
        "expect_reason": "The window waiver covers NO response",
        "why": "the waiver covers NO response, not a withheld one -- silence after speaking",
    },
    "approval_superseded": {
        "reviews": [_review("APPROVED", 20), _review("REQUEST_CHANGES", 1)],
        "timeline": _requested(25),
        "pr": {"created_at": _iso(25), "requested_reviewers": []},
        "expect_exit": 1,
        "expect_waiver": False,
        "expect_reason": "The window waiver covers NO response",
        "why": "an APPROVED later changed to REQUEST_CHANGES must not count",
    },
    "approval_by_someone_else": {
        "reviews": [_review("APPROVED", 1, who=OTHER)],
        "timeline": _requested(20),
        "pr": {"created_at": _iso(20), "requested_reviewers": [{"login": REVIEWER}]},
        "expect_exit": 0,
        "expect_waiver": True,
        "expect_reason": "D-16 waiver",
        "why": (
            "another person's approval is not the reviewer of record's. This still PASSES, "
            "but via the waiver -- the window has lapsed and the reviewer of record has not "
            "responded. Pinned so that route is a deliberate outcome rather than a surprise."
        ),
    },
}


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


def _gnu_date() -> str | None:
    """Path to a ``date`` supporting ``-d`` (GNU). BSD ``date`` on macOS does not."""
    for candidate in ("date", "gdate"):
        exe = shutil.which(candidate)
        if exe is None:
            continue
        probe = subprocess.run(
            [exe, "-u", "-d", "2020-01-01T00:00:00Z", "+%s"],
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode == 0:
            return exe
    return None


def _write_harness(tmp_path: Path, scenario: dict) -> tuple[Path, dict[str, str]]:
    import json

    fx = tmp_path / "fx"
    fx.mkdir()
    (fx / "reviews.json").write_text(json.dumps(scenario["reviews"]), encoding="utf-8")
    (fx / "timeline.json").write_text(json.dumps(scenario["timeline"]), encoding="utf-8")
    (fx / "pr.json").write_text(json.dumps(scenario["pr"]), encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/bin/bash\n"
        "# Stub for `gh api <endpoint>`; dispatches on the endpoint path.\n"
        'case "$2" in\n'
        '  *"/reviews?"*)  cat "$FX/reviews.json" ;;\n'
        '  *"/timeline?"*) cat "$FX/timeline.json" ;;\n'
        '  *)              cat "$FX/pr.json" ;;\n'
        "esac\n",
        encoding="utf-8",
    )
    gh.chmod(0o755)

    gnu_date = _gnu_date()
    assert gnu_date is not None  # guarded by the fixture below
    if Path(gnu_date).name != "date":
        shim = bin_dir / "date"
        shim.write_text(f'#!/bin/bash\nexec {gnu_date} "$@"\n', encoding="utf-8")
        shim.chmod(0o755)

    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "FX": str(fx),
        "REVIEW_WINDOW_DAYS": str(WINDOW_DAYS),
        "YOSEF": REVIEWER,
        "NUMBERS": "1",
        "REPO": "example/repo",
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"),
    }
    return tmp_path / "summary.md", env


@pytest.fixture(scope="module")
def gate_script() -> str:
    if shutil.which("jq") is None:
        _fail_if_ci("jq is not installed")
        pytest.skip("jq is not installed")
    if _gnu_date() is None:
        _fail_if_ci("no GNU-compatible `date -d` found (install coreutils for gdate)")
        pytest.skip("no GNU-compatible `date -d` found")
    return _approval_gate_script()


def _fail_if_ci(reason: str) -> None:
    """Never let this test silently skip in CI.

    A test that exists but does not execute is the exact defect this file was
    written to close. Locally a missing ``jq``/``gdate`` is a dev-box gap worth
    skipping over; in CI it means the gate is unverified and the run must fail.
    """
    if os.environ.get("CI"):
        pytest.fail(f"D-16 gate logic went untested in CI: {reason}")


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_gate_decides_correctly(name: str, gate_script: str, tmp_path: Path) -> None:
    scenario = SCENARIOS[name]
    summary_path, env = _write_harness(tmp_path, scenario)

    result = subprocess.run(
        ["bash", "-c", gate_script], capture_output=True, text=True, env=env, check=False
    )
    combined = result.stdout + result.stderr

    assert result.returncode == scenario["expect_exit"], (
        f"scenario {name!r} ({scenario['why']}) expected exit "
        f"{scenario['expect_exit']}, got {result.returncode}\n{combined}"
    )

    waived = "::notice::D-16 waiver" in combined
    assert waived == scenario["expect_waiver"], (
        f"scenario {name!r} ({scenario['why']}) expected waiver={scenario['expect_waiver']}, "
        f"got {waived}\n{combined}"
    )

    # The exit code alone is not enough. Neutering the "responded without
    # approving" refusal leaves the gate still exiting 1 -- but via the
    # window-not-lapsed message, i.e. refusing for the wrong reason. An
    # exit-code-only assertion passes that mutation, which is exactly the
    # "a non-zero exit is not automatically a caught regression" trap. Pin the
    # reason, not just the verdict.
    assert scenario["expect_reason"] in combined, (
        f"scenario {name!r} reached exit {result.returncode} but not for the expected reason "
        f"{scenario['expect_reason']!r} ({scenario['why']})\n{combined}"
    )

    if scenario["expect_waiver"]:
        summary = summary_path.read_text(encoding="utf-8") if summary_path.exists() else ""
        assert "D-16 WAIVER" in summary, (
            "a waiver must be written to the run summary, not only to the log -- "
            "the disclosure obligation depends on it being visible"
        )


def test_every_policy_branch_is_covered(gate_script: str) -> None:
    """Each refusal/pass path in the shipped script must have a scenario.

    Without this, adding a branch to the gate and forgetting a fixture would
    leave it silently untested — how the gate came to be untested in the first
    place.
    """
    branches = {
        "approved": "D-16 satisfied",
        "engaged_without_approving": "reviewed PR(s)",
        "waiver": "D-16 waiver",
        "never_requested": "was never requested",
        "window_not_lapsed": "has not lapsed",
    }
    missing = [name for name, needle in branches.items() if needle not in gate_script]

    assert not missing, f"gate script no longer contains branches: {missing}"


def test_unset_reviewer_variable_is_not_defaulted(gate_script: str) -> None:
    """The identity check is a separate step; assert it still hard-fails.

    Pinned here because a waiver path makes "pass on missing config" a much more
    attractive shortcut than it was when the gate was approval-only.
    """
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["approval"]["steps"]
    guard = [s for s in steps if "YOSEF_GH_USERNAME is not set" in s.get("run", "")]

    assert guard, "the unset-YOSEF_GH_USERNAME hard-fail step is gone"
    assert "exit 1" in guard[0]["run"]
