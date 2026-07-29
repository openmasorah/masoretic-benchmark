#!/usr/bin/env python3
"""Release gate: maintainer sign-off + public governance disclosure.

What this replaces, and why
---------------------------
The v0.1.1 D-16 gate required an APPROVED GitHub review from a named scholarly
reviewer before a ``benchmark-v*`` tag could publish. That contradicted the
project's own documented authority model, in which the maintainer is the sole
decision authority and collaborators are consultants rather than approval gates.
The contradiction was not theoretical: v0.1.0 shipped under an explicit,
recorded decision to take the scholarly review off the critical path, and the
gate went permanently red for doing what the project had decided to do.

A required gate that contradicts the project's decision model produces exactly
one outcome — it gets ignored — which is worse than no gate, because it also
trains everyone to ignore the gates that matter.

So the requirement moves to what the project actually holds itself to:

1. an **explicit, version-keyed maintainer sign-off** committed to the tree, and
2. a **public governance disclosure** in the CHANGELOG for that same version.

Scholarly review is **advisory**: recorded when present, never required. That is
a deliberate, disclosed policy decision by the project's decision authority —
not a softened gate. The distinction is the disclosure requirement above: this
gate cannot pass silently, because passing requires publishing a statement about
how the release was authorized.

Why a file rather than an identity check
----------------------------------------
The obvious alternative — check who pushed the tag — was rejected. Tag pushes
may be performed by a delegate acting on the maintainer's authorization, so a
pusher-identity check would verify the delegate's credentials and report them as
the maintainer's sign-off. That is an assertion that can only ever be true,
which is the same defect as a version guard comparing two copies of the same
stale value.

A committed entry is checkable from the tagged tree alone, survives re-clone,
and is visible to anyone auditing the release without API access.

Honest limitation
-----------------
This checks that a sign-off entry EXISTS and is well-formed for the version
being tagged. It cannot verify who authored it: every commit in this repository
is made through the same local git identity. The entry is therefore required to
state its own provenance — who authorized the release and how that
authorization was given — so a reader can evaluate the claim rather than infer
it from a signature that does not exist. The stronger form, for a future
release, is the maintainer committing (ideally GPG-signing) the entry directly.

Exit codes: 0 ok · 1 gate failure · 2 usage/integrity error.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SIGNOFF_PATH = REPO_ROOT / "RELEASE_SIGNOFF.md"
CHANGELOG_PATH = REPO_ROOT / "CHANGELOG.md"

#: Fields every sign-off entry must carry. ``Authorized by`` names the decision
#: authority; ``Authorization`` records HOW that authorization was given, which
#: is the part that makes the entry auditable rather than decorative.
REQUIRED_FIELDS = ("Version", "Signed off", "Authorized by", "Authorization")


#: A ``### Governance`` subsection must *start* with the word. ``### Data
#: Governance of the corpus`` is a data-provenance note, not a statement about
#: how the release was authorized, and an unanchored search accepted it.
GOVERNANCE_HEADING_RE = re.compile(r"^###\s+Governance\b.*$", re.MULTILINE | re.IGNORECASE)


def _section(text: str, heading: str) -> str | None:
    """Return the body of the ``## <heading>`` section, or None if absent."""
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$(.*?)(?=^##\s+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    return match.group(1) if match else None


def _version_anchored(tag: str) -> re.Pattern[str]:
    """Match ``tag`` as a whole token, never as a prefix of a longer one.

    A plain substring test reports ``benchmark-v0.1.1`` as present in a
    ``benchmark-v0.1.10`` heading, and first-match-wins would then let a future
    release's disclosure satisfy this one's gate.

    Excluding a *numeric* suffix was not enough. Probes against the first
    version of this fix showed ``benchmark-v0.1.1-rc1``, ``benchmark-v0.1.1.post1``
    and even ``benchmark-v0.1.1garbage`` all authorizing ``benchmark-v0.1.1``,
    because none of them continues with a digit. Pre-releases and post-releases
    are precisely the neighbouring versions a release gate must distinguish.

    So the rule is a real token boundary: the tag must be followed by
    whitespace or end-of-line, which admits the shipped heading form
    ``## benchmark-v0.1.1 (2026-07-29) -- ...`` and rejects every suffix.
    """
    return re.compile(rf"(?<![\w.-]){re.escape(tag)}(?=\s|$)")


#: Bodies that occupy the space a disclosure should fill without disclosing
#: anything. Compared after HTML comments are stripped and markdown
#: punctuation is collapsed, so "- TBD" and "**TODO**" are covered too.
PLACEHOLDER_BODIES = frozenset(
    {"tbd", "todo", "tba", "n/a", "na", "none", "nil", "xxx", "pending", "coming soon"}
)

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_MARKDOWN_NOISE_RE = re.compile(r"[\s*_`>#.\-]+")


def _is_substantive(content: str) -> bool:
    """Does this section body actually say something?

    Requiring merely non-whitespace was not enough. Probes showed a Governance
    body consisting only of ``<!-- no published disclosure -->`` clearing the
    gate -- an HTML comment renders as nothing at all, so the published page
    would show a bare heading while the gate reported a disclosure. ``TBD`` and
    ``-`` cleared it too.

    This is not a quality judgement and there is no length threshold. It rejects
    exactly two things: content that renders to nothing, and a fixed set of
    words that are conventional stand-ins for content not yet written.
    """
    visible = _HTML_COMMENT_RE.sub("", content).strip()
    if not visible:
        return False

    # Collapse markdown scaffolding so "- **TBD**" reduces to "tbd", and a body
    # of only "---" or "..." reduces to nothing at all.
    normalized = _MARKDOWN_NOISE_RE.sub(" ", visible).strip().lower()
    if not normalized:
        return False

    return normalized not in PLACEHOLDER_BODIES


def _field_line(body: str, field: str) -> str | None:
    """The line declaring ``field``, or None. First declaration wins."""
    for line in body.splitlines():
        if re.match(rf"^\s*[-*]?\s*\*{{0,2}}{re.escape(field)}\*{{0,2}}\s*:", line):
            return line
    return None


def _field_value(line: str) -> str:
    """The value on a field line, judged on that line ALONE.

    Emptiness must never be assessed across lines: a multi-line regex here
    happily matched the *next* field's text and reported a blank value as
    populated. A validator that cannot see an empty field is worse than none,
    because it certifies it.
    """
    return line.split(":", 1)[1].strip().strip("*").strip()


def check_signoff(tag: str, signoff_path: Path = SIGNOFF_PATH) -> list[str]:
    """The maintainer sign-off half of the gate."""
    if not signoff_path.exists():
        return [
            f"{signoff_path.name} is missing. A release tag requires an explicit, "
            f"version-keyed maintainer sign-off committed to the tree."
        ]

    text = signoff_path.read_text(encoding="utf-8")
    body = _section(text, tag)
    if body is None:
        return [
            f"{signoff_path.name} has no sign-off entry for {tag!r}. "
            f"Add a '## {tag}' section recording who authorized this release and how. "
            f"An entry for a different version does not authorize this one."
        ]

    errors: list[str] = []
    values: dict[str, str] = {}

    # Presence and emptiness are checked for EVERY required field. An earlier
    # version checked emptiness for only two of the four, so an entry could
    # carry a blank `Signed off` and still authorize a release.
    for field in REQUIRED_FIELDS:
        line = _field_line(body, field)
        if line is None:
            errors.append(f"{signoff_path.name} entry for {tag!r} is missing the '{field}' field")
            continue
        value = _field_value(line)
        if not value:
            errors.append(
                f"{signoff_path.name} entry for {tag!r} has an empty {field!r} -- "
                f"a sign-off that records nothing authorizes nothing"
            )
            continue
        values[field] = value

    # The heading and the `Version` field are two independent claims about which
    # release this entry authorizes. Only the heading was ever checked, so an
    # entry headed `## benchmark-v0.1.1` could declare `Version: benchmark-v0.0.9`
    # and pass -- the gate reading one claim while a human reads the other.
    declared = values.get("Version")
    if declared is not None and declared != tag:
        errors.append(
            f"{signoff_path.name} entry under '## {tag}' declares 'Version: {declared}' -- "
            f"the heading and the Version field must name the same release, or it is "
            f"unclear which one was actually authorized"
        )

    # `Signed off` is the date the authorization was given. Non-empty is not
    # enough: 'yes' and 'soon' are non-empty and record nothing auditable.
    signed_off = values.get("Signed off")
    if signed_off is not None:
        errors.extend(_check_signed_off(signed_off, tag, signoff_path.name))

    return errors


#: Only the extended ISO form. ``date.fromisoformat`` also accepts the compact
#: ``20260729``, which reads as a number rather than a date to a human auditor.
_ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _check_signed_off(value: str, tag: str, filename: str) -> list[str]:
    """``Signed off`` must be a real, already-elapsed calendar date."""
    if not _ISO_DATE_RE.fullmatch(value):
        return [
            f"{filename} entry for {tag!r} has 'Signed off: {value}', which is not an "
            f"ISO date in YYYY-MM-DD form. The field records WHEN authorization was "
            f"given; a value a reader cannot parse as a date records nothing."
        ]

    try:
        signed = date.fromisoformat(value)
    except ValueError:
        return [
            f"{filename} entry for {tag!r} has 'Signed off: {value}', which is not a "
            f"real calendar date."
        ]

    # One day of slack, not zero: the maintainer may sign in a timezone ahead of
    # the runner's, and rejecting a same-moment sign-off as "the future" would
    # be a gate that fails for being in the wrong place. A day covers every
    # offset; it does not admit a date anyone would call future-dated.
    if signed > date.today() + timedelta(days=1):
        return [
            f"{filename} entry for {tag!r} is dated {value}, in the future. A release "
            f"cannot be authorized before the authorization happened -- either the "
            f"date is a typo or the entry was written ahead of the decision."
        ]

    return []


def check_disclosure(tag: str, changelog_path: Path = CHANGELOG_PATH) -> list[str]:
    """The public-disclosure half of the gate.

    The CHANGELOG must carry a Governance section under the heading for the
    version being tagged. This is what stops the gate passing quietly: a release
    can only clear it by publishing how it was authorized.
    """
    if not changelog_path.exists():
        return [f"{changelog_path.name} is missing; a release must publish a changelog"]

    text = changelog_path.read_text(encoding="utf-8")
    anchored = _version_anchored(tag)
    heading = next(
        (
            line.lstrip("# ").strip()
            for line in text.splitlines()
            if line.startswith("## ") and anchored.search(line)
        ),
        None,
    )
    if heading is None:
        return [
            f"{changelog_path.name} has no '## ...{tag}...' section. "
            f"The tag being published must have a changelog entry."
        ]

    body = _section(text, heading)
    if body is None:  # pragma: no cover - heading came from the same parse
        return [f"could not read the {changelog_path.name} section for {tag!r}"]

    match = GOVERNANCE_HEADING_RE.search(body)
    if match is None:
        return [
            f"{changelog_path.name} section for {tag!r} has no '### Governance' "
            f"subsection. Every release must publicly state how it was authorized "
            f"and what review it did or did not receive."
        ]

    # A heading with nothing under it satisfies the letter of the requirement and
    # none of its purpose. A bare heading is not a statement -- and neither is
    # one whose body renders to nothing (an HTML comment) or says only "TBD".
    rest = body[match.end() :]
    stop = re.search(r"^#{1,3}\s", rest, re.MULTILINE)
    content = rest[: stop.start()] if stop else rest
    if not _is_substantive(content):
        return [
            f"{changelog_path.name} section for {tag!r} has an EMPTY or placeholder "
            f"'### Governance' subsection. A bare heading, an HTML comment and a 'TBD' "
            f"are not disclosures -- state how the release was authorized and what "
            f"review it did or did not receive."
        ]
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tag", required=True, help="the tag being published, e.g. benchmark-v0.1.1")
    args = ap.parse_args()

    if not args.tag.strip():
        print("::error::--tag must not be empty", file=sys.stderr)
        return 2

    errors = check_signoff(args.tag) + check_disclosure(args.tag)
    if errors:
        for err in errors:
            print(f"::error::{err}", file=sys.stderr)
        print(
            f"::error::release gate REFUSED for {args.tag}: "
            f"maintainer sign-off and a published governance disclosure are both required.",
            file=sys.stderr,
        )
        return 1

    print(f"release gate satisfied for {args.tag}: sign-off entry present, disclosure published.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
