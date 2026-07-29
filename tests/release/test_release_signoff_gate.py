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


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
def test_every_required_field_is_also_checked_for_EMPTINESS(field: str, tmp_path: Path) -> None:
    """Present-but-blank must fail exactly like absent.

    Only `Authorized by` and `Authorization` were emptiness-checked, so an entry
    could carry a blank `Version` or `Signed off` and still authorize a release.
    """
    blanked = "\n".join(
        f"- **{field}:**" if line.strip().startswith(f"- **{field}:") else line
        for line in GOOD_SIGNOFF.splitlines()
    )
    signoff = _write(tmp_path, "RELEASE_SIGNOFF.md", blanked)

    errors = check_signoff(TAG, signoff)

    assert any(field in e and "authorizes nothing" in e for e in errors), (
        f"a blank {field!r} was certified as populated: {errors}"
    )


def test_the_version_field_must_name_the_same_release_as_the_heading(tmp_path: Path) -> None:
    """Two claims, one gate. Only the heading was ever read.

    A human auditing the file reads the `Version` field; the gate read the
    heading. An entry headed `## <tag>` declaring `Version: benchmark-v0.0.9`
    passed, so the two readers could disagree about what was authorized.
    """
    mismatched = GOOD_SIGNOFF.replace(f"- **Version:** {TAG}", "- **Version:** benchmark-v0.0.9")
    signoff = _write(tmp_path, "RELEASE_SIGNOFF.md", mismatched)

    errors = check_signoff(TAG, signoff)

    assert any("benchmark-v0.0.9" in e and "same release" in e for e in errors), errors


@pytest.mark.parametrize("bad", ["yes", "soon", "2026-13-45", "when it ships"])
def test_signed_off_must_parse_as_a_date(bad: str, tmp_path: Path) -> None:
    """Non-empty is not enough -- 'soon' records nothing auditable."""
    undated = GOOD_SIGNOFF.replace("- **Signed off:** 2026-07-29", f"- **Signed off:** {bad}")
    signoff = _write(tmp_path, "RELEASE_SIGNOFF.md", undated)

    errors = check_signoff(TAG, signoff)

    assert any("not an ISO date" in e for e in errors), errors


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


def test_a_longer_version_heading_does_not_satisfy_this_tag(tmp_path: Path) -> None:
    """Substring matching would let `benchmark-v9.9.99` disclose for `...v9.9.9`.

    Version numbers grow past a single digit, and first-match-wins meant the
    FIRST heading containing the tag as a substring won -- so a future patch's
    disclosure could satisfy a gate for a release that has none.
    """
    changelog = _write(
        tmp_path,
        "CHANGELOG.md",
        f"# Changelog\n\n## {TAG}9 — a later release\n\n### Governance\n\nIts own disclosure.\n",
    )

    errors = check_disclosure(TAG, changelog)

    assert errors, f"'{TAG}9' was accepted as the disclosure for '{TAG}'"
    assert "no '## ..." in errors[0]


def test_a_data_governance_heading_is_not_a_governance_disclosure(tmp_path: Path) -> None:
    """`### Data Governance of the corpus` is a provenance note, not a disclosure.

    The requirement is a statement about how THIS RELEASE was authorized. An
    unanchored search accepted any heading with the word anywhere in it.
    """
    decoy = GOOD_CHANGELOG.replace(
        "### Governance — how this release was authorized",
        "### Data Governance of the corpus",
    )
    changelog = _write(tmp_path, "CHANGELOG.md", decoy)

    errors = check_disclosure(TAG, changelog)

    assert errors, "a 'Data Governance' heading satisfied the authorization disclosure"
    assert "no '### Governance'" in errors[0]


def test_a_bare_governance_heading_is_not_a_statement(tmp_path: Path) -> None:
    """The heading is the container, not the disclosure."""
    hollow = GOOD_CHANGELOG.replace(
        "### Governance — how this release was authorized\n\nDisclosure text.\n",
        "### Governance — how this release was authorized\n\n",
    )
    changelog = _write(tmp_path, "CHANGELOG.md", hollow)

    errors = check_disclosure(TAG, changelog)

    assert errors, "an empty Governance subsection cleared the disclosure requirement"
    assert "EMPTY" in errors[0]


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


def test_the_shipped_changelog_satisfies_the_HARDENED_disclosure_rules() -> None:
    """The hardening must not have broken the release it was written for.

    Anchoring the Governance heading and requiring a non-empty body are exactly
    the kind of tightening that silently invalidates the real tree, so assert
    the shipped v0.1.1 disclosure still clears the rules it now has to meet.
    """
    assert check_disclosure("benchmark-v0.1.1") == []


def test_the_disclosure_states_THIS_release_s_own_review_status() -> None:
    """The disclosure must meet the standard it sets, on its own release.

    It declares that "a future release that ships without scholarly review must
    say so, here, in public." v0.1.1 IS such a release, and the section stated
    only v0.1.0's status -- the rule announced and not applied to its author's
    own release, which is the exact defect the whole section exists to correct.
    """
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    section = changelog.split("## benchmark-v0.1.0")[0]

    assert "without scholarly\nreview" in section or "without scholarly review" in section
    assert "benchmark-v0.1.1` ships" in section, (
        "the Governance section does not state v0.1.1's own review status"
    )


def test_no_surface_still_promises_the_review_folds_into_v0_1_1() -> None:
    """v0.1.1 is the release. It cannot be the future release that fixes itself.

    This is the F2 false-promise class appearing inside the disclosure that was
    written to correct it: a commitment whose deadline is the very release
    making the commitment.
    """
    surfaces = [
        REPO_ROOT / "CHANGELOG.md",
        REPO_ROOT / ".github" / "workflows" / "release-tag.yml",
        REPO_ROOT / "RELEASE_SIGNOFF.md",
    ]
    offenders = [
        p.relative_to(REPO_ROOT)
        for p in surfaces
        if "folds into v0.1.1" in p.read_text(encoding="utf-8")
    ]

    assert not offenders, f"self-referential review promise survives in {offenders}"


def test_the_gate_would_refuse_the_current_tree_for_an_unsigned_version() -> None:
    """Sanity: the real files do not accidentally authorize an arbitrary tag."""
    errors = check_signoff("benchmark-v0.0.0-never-signed")

    assert errors, "the shipped sign-off file authorized a version nobody signed off"
