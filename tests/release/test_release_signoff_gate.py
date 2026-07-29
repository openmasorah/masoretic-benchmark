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
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_release_signoff import (  # noqa: E402
    REQUIRED_FIELDS,
    _is_substantive,
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


@pytest.mark.parametrize(
    ("bad", "reason"),
    [
        ("yes", "not an ISO date"),
        ("soon", "not an ISO date"),
        ("when it ships", "not an ISO date"),
        # `date.fromisoformat` accepts the compact form, which reads as a number
        # rather than a date to the human auditor the field exists for.
        ("20260729", "not an ISO date"),
        # Well-formed but impossible. This refuses at the calendar, not at the
        # shape, and the two are pinned separately -- a shape check that happened
        # to swallow this would look identical from the exit code alone.
        ("2026-13-45", "not a real calendar date"),
    ],
)
def test_signed_off_must_parse_as_a_date(bad: str, reason: str, tmp_path: Path) -> None:
    """Non-empty is not enough -- 'soon' records nothing auditable."""
    undated = GOOD_SIGNOFF.replace("- **Signed off:** 2026-07-29", f"- **Signed off:** {bad}")
    signoff = _write(tmp_path, "RELEASE_SIGNOFF.md", undated)

    errors = check_signoff(TAG, signoff)

    assert any(reason in e for e in errors), f"{bad!r} refused, but not for {reason!r}: {errors}"


def test_signed_off_may_not_be_dated_in_the_future(tmp_path: Path) -> None:
    """A release cannot be authorized before the authorization happened.

    A well-formed date passed unconditionally, so an entry could be written
    ahead of the decision it records and the gate would call it authorized.
    """
    ahead = GOOD_SIGNOFF.replace("- **Signed off:** 2026-07-29", "- **Signed off:** 2099-01-01")
    signoff = _write(tmp_path, "RELEASE_SIGNOFF.md", ahead)

    errors = check_signoff(TAG, signoff)

    assert any("in the future" in e for e in errors), errors


def test_a_signoff_dated_today_is_accepted(tmp_path: Path) -> None:
    """The positive control for the future-date check.

    Guards the obvious over-correction: rejecting the future must not reject
    the present, which is when a real sign-off is actually written. One day of
    slack is deliberate -- the maintainer may sign in a timezone ahead of the
    runner's, and a gate that fails for being in the wrong place is not a gate.
    """
    today = date.today().isoformat()
    entry = GOOD_SIGNOFF.replace("- **Signed off:** 2026-07-29", f"- **Signed off:** {today}")
    signoff = _write(tmp_path, "RELEASE_SIGNOFF.md", entry)

    assert check_signoff(TAG, signoff) == []


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


@pytest.mark.parametrize("suffix", ["-rc1", ".post1", "garbage", "9", "-final"])
def test_no_suffixed_version_heading_can_authorize_this_tag(suffix: str, tmp_path: Path) -> None:
    """Excluding a NUMERIC suffix was not enough, and probes proved it.

    `benchmark-v0.1.1-rc1`, `benchmark-v0.1.1.post1` and even
    `benchmark-v0.1.1garbage` all cleared the first version of this fix,
    because none of them continues with a digit. Pre-releases and post-releases
    are exactly the neighbouring versions a release gate has to tell apart, so
    the rule is now a real token boundary rather than a list of bad next
    characters.
    """
    changelog = _write(
        tmp_path,
        "CHANGELOG.md",
        f"# Changelog\n\n## {TAG}{suffix} — a different release\n\n"
        f"### Governance\n\nIts own disclosure.\n",
    )

    errors = check_disclosure(TAG, changelog)

    assert errors, f"'{TAG}{suffix}' was accepted as the disclosure for '{TAG}'"
    assert "no '## ..." in errors[0]


def test_the_shipped_heading_form_still_matches() -> None:
    """Positive control for the boundary rule.

    Tightening the anchor to "whitespace or end of line" is exactly the kind of
    change that rejects the real heading -- `## benchmark-v0.1.1 (2026-07-29)
    — corrections to v0.1.0` -- along with the fakes.
    """
    assert check_disclosure("benchmark-v0.1.1") == []


@pytest.mark.parametrize(
    "hollow",
    [
        # Renders as literally nothing on the published page while the gate
        # reports a disclosure. This one was found by probe, not by reading.
        "<!-- no published disclosure -->",
        "TBD",
        "TODO",
        "N/A",
        "-",
        "...",
        "- **TBD**",
    ],
)
def test_a_placeholder_governance_body_is_not_a_disclosure(hollow: str, tmp_path: Path) -> None:
    """Non-whitespace was the wrong bar; it admits everything above."""
    changelog = _write(
        tmp_path,
        "CHANGELOG.md",
        f"# Changelog\n\n## {TAG} (2026-07-29) — a release\n\n### Governance\n\n{hollow}\n",
    )

    errors = check_disclosure(TAG, changelog)

    assert errors, f"a Governance body of {hollow!r} cleared the disclosure requirement"
    assert "placeholder" in errors[0]


# ---------------------------------------------------------------------------
# The empty-disclosure check, by CATEGORY.
#
# Three review rounds each broke the previous version of this check, and each
# time the fix addressed the literal strings the reviewer sent. Enumerating
# categories instead is what makes the next instance of a known category fail
# here rather than in review: a new entity or a new zero-width codepoint is
# covered by the mechanism these cases exercise, not by having been listed.
# ---------------------------------------------------------------------------

INVISIBLE_BODIES: dict[str, list[str]] = {
    # Terminated or not. CommonMark runs an unterminated comment to end of
    # document, so the section renders blank either way.
    "html-comment": ["<!-- no published disclosure -->", "<!-- unclosed", "<!-- a --> <!-- b"],
    # Markup with no statement in it.
    "tag-only": ["<span></span>", "<div><span></span></div>", "<br/>", "<p>   </p>"],
    # Contents are not prose. These survived plain tag-stripping as CSS/JS text.
    "discarded-element": [
        "<style>body{color:red}</style>",
        "<script>var x=1</script>",
        "<template><p>x</p></template>",
        "<style>body{color:red}",
    ],
    # Decode to something invisible. Named, decimal and zero-width alike.
    "html-entity": ["&nbsp;", "&#160;", "&#8203;", "&zwnj;", "&nbsp;&#8203;"],
    # Literal codepoints. U+200B/U+2060/U+FEFF are NOT Python whitespace, so
    # `.strip()` preserved them and one zero-width space read as content.
    "invisible-codepoint": ["​", "⁠", "﻿", "\xa0", "​⁠"],
    # Declares a label for use elsewhere; renders nothing at spec level. The
    # title is optional and may sit on the definition line or on an indented
    # continuation line -- matching single lines only left `  "title"` behind
    # as substance, which made the docstring's own enumeration false.
    "link-reference-definition": [
        "[ref]: https://example.org",
        "[a]: https://x.org\n[b]: https://y.org",
        '[policy]: https://example.org\n    "title"',
        '[policy]: https://example.org "title"',
        "[policy]: https://example.org\n    (title)",
        # Angle-bracketed destination: the tag stripper used to eat it,
        # stranding "[ref]:" as substance. Order-dependent regression.
        "[ref]: <foo bar>",
        '[ref]: <foo bar> "t"',
    ],
    # Markup that shows the reader no text at all.
    # Includes links whose TEXT is only invisible characters: those are not
    # literally empty, so the pattern missed them and the leftover `[]()`
    # punctuation counted as content. Removing invisible characters FIRST
    # closes the class rather than one codepoint.
    "empty-link-or-image": [
        "[]()",
        "[](/policy)",
        "![](x)",
        "[][policy]",
        "[\u200b]()",
        "[\u200b](/policy)",
        "[\u2060]()",
        "[\u05b0]()",
        "[\xa0]()",
        "![\u200b](x)",
    ],
    # Zero visible output, and not Python whitespace.
    "control-character": ["\x01", "\x01\x02\x1f"],
    # Combining marks have zero advance width with no base character to sit on.
    "combining-mark-only": ["ְָ", "́"],
    # The original class: words that hold the space without filling it.
    "placeholder-word": ["TBD", "TODO", "N/A", "-", "...", "- **TBD**"],
}


@pytest.mark.parametrize(
    ("category", "body"),
    [(cat, body) for cat, bodies in INVISIBLE_BODIES.items() for body in bodies],
    ids=[f"{cat}-{i}" for cat, bodies in INVISIBLE_BODIES.items() for i, _ in enumerate(bodies)],
)
def test_a_governance_body_that_renders_to_nothing_is_refused(
    category: str, body: str, tmp_path: Path
) -> None:
    """Every category must refuse, whatever spelling it arrives in.

    The failure they share is the worst shape this gate can take: reporting a
    published governance disclosure while the published page shows a bare
    heading.
    """
    changelog = _write(
        tmp_path,
        "CHANGELOG.md",
        f"# Changelog\n\n## {TAG} (2026-07-29) — a release\n\n### Governance\n\n{body}\n",
    )

    errors = check_disclosure(TAG, changelog)

    assert errors, f"[{category}] body {body!r} normalizes to nothing but cleared the gate"
    assert "placeholder" in errors[0]


@pytest.mark.parametrize(
    ("label", "visible"),
    [
        ("plain", "Real disclosure text."),
        # Text FIRST is visible even though the comment eats the rest of the
        # document. Rejecting this would be the over-correction.
        ("text-then-unclosed-comment", "Real text, then a comment. <!-- unclosed"),
        ("text-with-inline-tags", "Real text <span>emphasis</span> here."),
        # An autolink is content, not a tag. The tag pattern requires a letter
        # after `<` precisely so this survives.
        ("autolink", "See <https://example.org/policy> for detail."),
        ("comment-then-text", "<!-- note --> Authorized by the maintainer."),
        # Entity decoding must not eat an ampersand that is just an ampersand.
        ("raw-ampersand", "R&D review completed."),
        ("escaped-ampersand", "R&amp;D review completed."),
        # Zs collapses to a space rather than being deleted, so the words on
        # either side of an NBSP survive with their boundary intact.
        ("internal-nbsp", "Authorized\xa0by the maintainer."),
        ("text-plus-link-ref", "Authorized by the maintainer.\n\n[policy]: https://example.org"),
        (
            "text-plus-multiline-link-ref",
            'Authorized.\n\n[policy]: https://example.org\n    "title"',
        ),
        # A link WITH text is content. Only the empty-text form is markup.
        ("link-with-text", "[policy](https://example.org)"),
        # Hebrew link text: the base letter survives Mn deletion, so this is
        # a link with text and must NOT be swept up with the invisible ones.
        ("link-with-hebrew-text", "[\u05d5\u05b0](https://example.org)"),
        # Confirmed in review as CORRECT passes, pinned so they are not
        # re-litigated as holes: visible punctuation is content, and `[]: x`
        # is not a link-reference definition (CommonMark needs a label).
        ("visible-punctuation-only", "[]{}()"),
        ("empty-label-is-not-a-ref-def", "[]: x"),
        # THE CONTROL THAT MATTERS MOST IN THIS REPOSITORY. Nikkud are Mn and
        # are stripped by the visibility measure; the base consonants are not,
        # so a pointed Hebrew disclosure must survive. Only a body of BARE
        # marks reduces to nothing.
        ("hebrew-with-nikkud", "וְאָהַבְתָּ — authorized by the maintainer."),
        ("hebrew-with-nikkud-alone", "וְאָהַבְתָּ"),
        ("hebrew-unpointed", "ואהבת"),
        # Cc is stripped apart from these three, which are real layout.
        ("tab-and-newline", "Authorized\tby\nthe maintainer."),
    ],
)
def test_real_content_survives_the_invisibility_check(
    label: str, visible: str, tmp_path: Path
) -> None:
    """Positive controls. Normalization must not remove the statement.

    Every tightening in this sequence has been one step away from rejecting the
    real disclosure, so these carry as much weight as the refusals.
    """
    changelog = _write(
        tmp_path,
        "CHANGELOG.md",
        f"# Changelog\n\n## {TAG} (2026-07-29) — a release\n\n### Governance\n\n{visible}\n",
    )

    assert check_disclosure(TAG, changelog) == [], f"[{label}] {visible!r} is content and refused"


def test_KNOWN_BOUND_quoted_gt_in_an_attribute_defeats_the_tag_pattern(tmp_path: Path) -> None:
    """Pins a documented limitation as current behaviour, not as correctness.

    `<span title="a>b"></span>` leaves `b"` behind, so it passes. HTML
    attributes are not parsed; closing this needs a real HTML parser, which is
    a dependency this CI gate should not take on in order to defend against its
    own maintainer.

    The threat this check exists for is a disclosure forgotten, deferred, or
    left as a stub -- not one deliberately hidden by the person required to
    write it. `_is_substantive.__doc__` states this bound, and this test fails
    if that statement is ever removed, so the code cannot quietly start
    claiming more than it does. Same precedent as the withdrawn-request waiver.
    """
    changelog = _write(
        tmp_path,
        "CHANGELOG.md",
        f"# Changelog\n\n## {TAG} (2026-07-29) — a release\n\n"
        f'### Governance\n\n<span title="a>b"></span>\n',
    )

    assert check_disclosure(TAG, changelog) == [], (
        "the quoted-attribute case now refuses -- good, but the documented bound "
        "in _is_substantive is stale and must be updated"
    )

    doc = _is_substantive.__doc__ or ""
    assert "KNOWN BOUNDS" in doc
    assert "attributes are not parsed" in doc.replace("\n", " ")


def test_KNOWN_BOUND_nested_parens_in_a_link_destination_are_not_counted(tmp_path: Path) -> None:
    """The second documented limitation, pinned the same way as the first.

    CommonMark permits balanced parentheses in a link destination, and a regex
    cannot match balanced delimiters. `[](foo(and)bar)` therefore leaves `bar)`
    and passes. Rather than pretend otherwise with a deeper pattern that would
    fail one nesting level further down, the enumerated clause is scoped to
    simple destinations and this case is documented as a bound.

    Closing it needs a real CommonMark parser -- a dependency this gate should
    not take on to defend against its own maintainer.
    """
    changelog = _write(
        tmp_path,
        "CHANGELOG.md",
        f"# Changelog\n\n## {TAG} (2026-07-29) — a release\n\n### Governance\n\n[](foo(and)bar)\n",
    )

    assert check_disclosure(TAG, changelog) == [], (
        "the nested-paren case now refuses -- good, but the documented bound in "
        "_is_substantive is stale and must be updated"
    )

    doc = (_is_substantive.__doc__ or "").replace("\n", " ")
    assert "KNOWN BOUNDS" in doc
    assert "Nested parentheses" in doc
    assert "no nested parentheses" in doc, "the enumerated clause must be scoped, not absolute"


def test_the_docstring_describes_the_normalization_it_actually_performs() -> None:
    """A wrong self-description is this project's documented failure mode.

    The `<DR>` incident began with a docstring claiming behaviour the code did
    not have, and two external reviewers later quoted that claim back verbatim.
    So the property statement is asserted here: it must enumerate the
    normalization rather than promise that the body "renders visibly", which is
    a stronger claim than removal-based normalization can support.
    """
    doc = (_is_substantive.__doc__ or "").replace("\n", " ")

    assert "approximation" in doc, "the docstring must not claim a rendering guarantee"
    for enumerated in (
        "comments",
        "entities",
        "link-reference",
        "tags",
        "empty-text links",
        "Mn",
        "Cc",
        "Cf",
    ):
        assert enumerated in doc, f"the docstring does not mention {enumerated!r}"


def test_the_enumeration_is_not_merely_present_but_TRUE() -> None:
    """Each enumerated removal is executed against a body that needs it.

    The enumeration went false once already: it claimed link-reference
    definitions were dropped while the rule matched single lines only, so a
    multiline definition left its title behind. A list of claims that nothing
    exercises is the `<DR>` docstring again in a new place, so every clause
    above is tied here to a body it alone accounts for.
    """
    accounted_for = {
        "comments": "<!-- x -->",
        "discarded element contents": "<style>body{color:red}</style>",
        "tags": "<span></span>",
        "entities": "&#8203;",
        # SCOPED: simple destinations only. Nested parentheses are a KNOWN
        # BOUND, pinned separately -- the clause claims only what it does.
        "empty-text links (simple destination)": "[](/policy)",
        "empty-alt images (simple destination)": "![](x)",
        "link-reference definitions": '[policy]: https://example.org\n    "title"',
        # The angle-bracketed destination is why ref-def removal must run
        # BEFORE tag stripping; this fixture fails if that order regresses.
        "link-reference definitions (angle-bracketed destination)": "[ref]: <foo bar>",
        "Cf": "​",
        "Cc": "\x01",
        "Mn": "ְָ",
        "Zs": "\xa0",
        "placeholder words": "TBD",
    }

    survivors = {clause: body for clause, body in accounted_for.items() if _is_substantive(body)}

    assert not survivors, (
        "the docstring enumerates removals the code does not perform: "
        + ", ".join(f"{c} ({b!r})" for c, b in survivors.items())
    )


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

    Widened from the exact string "folds into v0.1.1" after the first fix left
    the same promise alive four times in the workflow as "folds into the next
    patch release" -- the identical commitment, phrased so an exact-match guard
    could not see it. The class is the deferral idiom, not one spelling of it.
    """
    surfaces = [
        REPO_ROOT / "CHANGELOG.md",
        REPO_ROOT / ".github" / "workflows" / "release-tag.yml",
        REPO_ROOT / "RELEASE_SIGNOFF.md",
        REPO_ROOT / "README.md",
    ]
    offenders = [
        f"{p.relative_to(REPO_ROOT)}:{n}"
        for p in surfaces
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if "folds into" in line or "fold into" in line or "folds forward" in line
    ]

    assert not offenders, (
        "the review-deferral promise survives in " + ", ".join(offenders) + " -- say "
        "'remains outstanding for a future release'; a named next release is a "
        "commitment nobody is holding"
    )


def test_the_gate_would_refuse_the_current_tree_for_an_unsigned_version() -> None:
    """Sanity: the real files do not accidentally authorize an arbitrary tag."""
    errors = check_signoff("benchmark-v0.0.0-never-signed")

    assert errors, "the shipped sign-off file authorized a version nobody signed off"
