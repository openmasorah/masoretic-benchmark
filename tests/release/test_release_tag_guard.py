"""Tests for the release-tag guard (blocker B5).

Two independent failures were papered over by the claim "CI enforces D-16":

1. `ci.yml` had no `tags:` trigger, so `audit_release.py --release-tier` --
    and therefore `check_iaa_report_real` -- had never executed in CI.
2. `check_iaa_report_real` returned [] when `iaa_report.json` was ABSENT, so
   even had it run, a release with no IAA report at all would have passed.

The workflow itself can't be unit-tested here, so we pin its contract: the
triggers it must carry, the jobs publication depends on, and the refusal to
default a missing reviewer identity.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release-tag.yml"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from audit_release import check_iaa_report_real  # noqa: E402

# --------------------------------------------------------------------------
# The audit-level hole: absence must fail at release tier.
# --------------------------------------------------------------------------


def test_missing_iaa_report_fails_release_tier(tmp_path):
    """A release tag must not ship without the IAA report REL-01 requires."""
    errors = check_iaa_report_real(tmp_path)
    assert errors, "absent iaa_report.json passed the release-tier check"
    assert "missing" in errors[0]


def test_placeholder_iaa_report_still_fails(tmp_path):
    (tmp_path / "iaa_report.json").write_text('{"iaa_status": "placeholder"}', encoding="utf-8")
    errors = check_iaa_report_real(tmp_path)
    assert errors
    assert "placeholder" in errors[0]


def test_real_iaa_report_passes(tmp_path):
    (tmp_path / "iaa_report.json").write_text('{"iaa_status": "real"}', encoding="utf-8")
    assert check_iaa_report_real(tmp_path) == []


# --------------------------------------------------------------------------
# The workflow contract.
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def workflow() -> dict:
    assert WORKFLOW.exists(), "release-tag.yml is the only thing enforcing D-16"
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_workflow_triggers_on_release_tags(workflow):
    # PyYAML parses a bare `on:` key as the boolean True. Accept either.
    triggers = workflow.get("on", workflow.get(True))
    assert triggers is not None, "workflow has no triggers"
    assert "benchmark-v*" in triggers["push"]["tags"]


def test_workflow_is_dry_runnable_without_cutting_a_tag(workflow):
    """A gate nobody can rehearse is a gate nobody trusts."""
    triggers = workflow.get("on", workflow.get(True))
    assert "workflow_dispatch" in triggers


def test_release_audit_runs_the_release_tier_audit(workflow):
    steps = workflow["jobs"]["release-audit"]["steps"]
    runs = " ".join(s.get("run", "") for s in steps)
    assert "--release-tier" in runs, "release-tier checks would never execute"
    assert "rebind_manifest_hash.py --check" in runs


def test_publication_depends_on_both_gates(workflow):
    """The tag existing is not the release. Publication needs audit AND sign-off.

    Updated 2026-07-29 with the policy change: the blocking gate is `signoff`
    (maintainer sign-off + published governance disclosure), not `approval`.
    """
    needs = workflow["jobs"]["publish"]["needs"]
    assert set(needs) == {"release-audit", "signoff"}


def test_publication_does_not_depend_on_the_advisory_review_job(workflow):
    """Advisory means advisory.

    If `publish` ever regained a dependency on `approval`, the scholarly review
    would silently become blocking again while the CHANGELOG still told readers
    it was advisory — a gate whose documented behaviour and real behaviour
    disagree, which is the defect this whole release has been correcting.
    """
    assert "approval" not in workflow["jobs"]["publish"]["needs"]
    assert workflow["jobs"]["approval"].get("continue-on-error") is True


def test_the_blocking_gate_checks_signoff_and_disclosure(workflow):
    """The `signoff` job must actually run the checker, not just exist."""
    runs = " ".join(s.get("run", "") for s in workflow["jobs"]["signoff"]["steps"])

    assert "check_release_signoff.py" in runs
    assert "--tag" in runs


def test_approval_gate_refuses_to_default_the_reviewer(workflow):
    """An unset YOSEF_GH_USERNAME must FAIL its step, never silently approve.

    Still asserted even though the job is advisory: a misconfigured reviewer
    variable should surface loudly in the release log rather than be reported as
    "no review found".
    """
    steps = workflow["jobs"]["approval"]["steps"]
    guard = steps[0]
    body = guard.get("run", "")
    assert "YOSEF_GH_USERNAME is not set" in body
    assert "exit 1" in body


def test_approval_gate_reads_reviews_not_reactions(workflow):
    """D-16: a thumbs-up reaction does not count; only a written APPROVED review."""
    steps = workflow["jobs"]["approval"]["steps"]
    runs = " ".join(s.get("run", "") for s in steps)
    assert "/reviews" in runs
    assert "APPROVED" in runs
    assert "reactions" not in runs


def test_approval_gate_uses_latest_review_state_per_user(workflow):
    """A later REQUEST_CHANGES or dismissal must override an earlier APPROVED."""
    steps = workflow["jobs"]["approval"]["steps"]
    runs = " ".join(s.get("run", "") for s in steps)
    assert "group_by(.user.login)" in runs
    assert "max_by(.submitted_at)" in runs


def test_ci_yml_does_not_claim_to_be_d16():
    """The A-03 title gate must not masquerade as the release gate."""
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "THIS IS NOT D-16" in ci
    assert "NOT D-16" in ci  # also in the job's display name


def test_ci_yml_points_at_the_CURRENT_release_gate():
    """Disclaiming the wrong gate is only half the job; it must name the right one.

    This comment survived the policy change at 721077b still describing the
    release gate as "approval from the reviewer of record, or a lapsed review
    window with a logged waiver" -- a stale governance claim sitting in the
    tree that gets tagged, which is the class the whole X-series closed. It has
    zero executable effect, and that is exactly why nothing caught it.
    """
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "RELEASE_SIGNOFF.md" in ci, (
        "ci.yml describes the release gate without naming the sign-off file it actually requires"
    )
    assert "ADVISORY" in ci or "advisory" in ci, (
        "ci.yml must say scholarly review is advisory; the superseded policy made "
        "it blocking, and a reader following this comment would expect a gate that "
        "no longer exists"
    )
