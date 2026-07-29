"""The release gate's decision logic, executed — including its refusals.

The gate this replaces went permanently red because it required something the
project had decided not to require. The replacement is only worth having if its
refusals are real, so this file spends most of its effort on the negative cases:
a gate that cannot say no is a rubber stamp with extra steps.

Each refusal asserts the *reason*, not just the exit code. Asserting exit codes
alone let an earlier version of the D-16 harness pass a mutation that made the
gate refuse for entirely the wrong reason — the same failure as reading a test
summary line instead of the process exit status.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_release_signoff import (  # noqa: E402
    REQUIRED_FIELDS,
    check_disclosure,
    check_signoff,
)

TAG = "benchmark-v9.9.9"

GOOD_SIGNOFF = f"""# Release sign-off

## {TAG}

- **Version:** {TAG}
- **Signed off:** 2026-07-29
- **Authorized by:** A Maintainer
- **Authorization:** explicit decision recorded in the release coordination log
"""

GOOD_CHANGELOG = f"""# Changelog

## {TAG} (2026-07-29) — a release

### Something else

Text.

### Governance — how this release was authorized

Disclosure text.

## benchmark-v0.0.1 — an older release

### Governance

Older disclosure.
"""


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Passing case
# ---------------------------------------------------------------------------


def test_wellformed_signoff_and_disclosure_pass(tmp_path: Path) -> None:
    signoff = _write(tmp_path, "RELEASE_SIGNOFF.md", GOOD_SIGNOFF)
    changelog = _write(tmp_path, "CHANGELOG.md", GOOD_CHANGELOG)

    assert check_signoff(TAG, signoff) == []
    assert check_disclosure(TAG, changelog) == []


# ---------------------------------------------------------------------------
# Refusals — sign-off half
# ---------------------------------------------------------------------------


def test_missing_signoff_file_refuses(tmp_path: Path) -> None:
    errors = check_signoff(TAG, tmp_path / "RELEASE_SIGNOFF.md")

    assert errors
    assert "is missing" in errors[0]


def test_signoff_for_a_different_version_does_not_authorize_this_one(tmp_path: Path) -> None:
    """The entry is version-KEYED. This is the whole point of the mechanism.

    Without this, one sign-off would authorize every subsequent release --
    exactly the "assertion that can only be true" shape the pusher-identity
    design was rejected for.
    """
    other = GOOD_SIGNOFF.replace(TAG, "benchmark-v0.0.1")
    signoff = _write(tmp_path, "RELEASE_SIGNOFF.md", other)

    errors = check_signoff(TAG, signoff)

    assert errors
    assert "no sign-off entry for" in errors[0]
    assert "does not authorize this one" in errors[0]


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
def test_every_required_field_is_actually_required(field: str, tmp_path: Path) -> None:
    """Drop one field at a time; each omission must be caught on its own."""
    stripped = "\n".join(
        line for line in GOOD_SIGNOFF.splitlines() if not line.strip().startswith(f"- **{field}:")
    )
    signoff = _write(tmp_path, "RELEASE_SIGNOFF.md", stripped)

    errors = check_signoff(TAG, signoff)

    assert any(field in e for e in errors), f"omitting {field!r} was not caught: {errors}"


def test_an_entry_naming_nobody_authorizes_nothing(tmp_path: Path) -> None:
    empty = GOOD_SIGNOFF.replace("- **Authorized by:** A Maintainer", "- **Authorized by:**")
    signoff = _write(tmp_path, "RELEASE_SIGNOFF.md", empty)

    errors = check_signoff(TAG, signoff)

    assert errors
    assert any("authorizes nothing" in e or "Authorized by" in e for e in errors)


# ---------------------------------------------------------------------------
# Refusals — disclosure half
# ---------------------------------------------------------------------------


def test_missing_changelog_refuses(tmp_path: Path) -> None:
    errors = check_disclosure(TAG, tmp_path / "CHANGELOG.md")

    assert errors
    assert "missing" in errors[0]


def test_changelog_without_a_section_for_this_tag_refuses(tmp_path: Path) -> None:
    changelog = _write(
        tmp_path, "CHANGELOG.md", "# Changelog\n\n## benchmark-v0.0.1\n\n### Governance\n\nx\n"
    )

    errors = check_disclosure(TAG, changelog)

    assert errors
    assert "no '## ..." in errors[0]


def test_changelog_section_without_governance_refuses(tmp_path: Path) -> None:
    """A release may not pass the gate silently.

    The disclosure requirement is what distinguishes this policy from simply
    dropping the review requirement: clearing the gate requires publishing how
    the release was authorized.
    """
    no_gov = GOOD_CHANGELOG.replace("### Governance — how this release was authorized", "### Notes")
    changelog = _write(tmp_path, "CHANGELOG.md", no_gov)

    errors = check_disclosure(TAG, changelog)

    assert errors
    assert "Governance" in errors[0]


def test_governance_in_a_DIFFERENT_version_does_not_satisfy_this_one(tmp_path: Path) -> None:
    """Section scoping: the older release's Governance section must not count."""
    no_gov = GOOD_CHANGELOG.replace("### Governance — how this release was authorized", "### Notes")
    changelog = _write(tmp_path, "CHANGELOG.md", no_gov)

    errors = check_disclosure(TAG, changelog)

    assert errors, "a Governance heading under an older version satisfied the current one"


# ---------------------------------------------------------------------------
# The shipped tree
# ---------------------------------------------------------------------------


def test_shipped_signoff_file_documents_its_own_provenance_limit() -> None:
    """The file must not imply an authorship guarantee it cannot provide.

    Every commit here is made through the same local git identity, so an entry
    is a recorded claim of authorization, not proof of it. Saying so is the
    difference between a governance record and a decorative one.
    """
    text = (REPO_ROOT / "RELEASE_SIGNOFF.md").read_text(encoding="utf-8")

    assert "does not" in text and "git authorship" in text.replace("\n", " ")
    assert "Authorization" in text


def test_the_gate_would_refuse_the_current_tree_for_an_unsigned_version() -> None:
    """Sanity: the real files do not accidentally authorize an arbitrary tag."""
    errors = check_signoff("benchmark-v0.0.0-never-signed")

    assert errors, "the shipped sign-off file authorized a version nobody signed off"
