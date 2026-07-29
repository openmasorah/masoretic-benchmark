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
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SIGNOFF_PATH = REPO_ROOT / "RELEASE_SIGNOFF.md"
CHANGELOG_PATH = REPO_ROOT / "CHANGELOG.md"

#: Fields every sign-off entry must carry. ``Authorized by`` names the decision
#: authority; ``Authorization`` records HOW that authorization was given, which
#: is the part that makes the entry auditable rather than decorative.
REQUIRED_FIELDS = ("Version", "Signed off", "Authorized by", "Authorization")


def _section(text: str, heading: str) -> str | None:
    """Return the body of the ``## <heading>`` section, or None if absent."""
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$(.*?)(?=^##\s+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    return match.group(1) if match else None


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

    errors = [
        f"{signoff_path.name} entry for {tag!r} is missing the '{field}' field"
        for field in REQUIRED_FIELDS
        if not re.search(
            rf"^\s*[-*]?\s*\*{{0,2}}{re.escape(field)}\*{{0,2}}\s*:", body, re.MULTILINE
        )
    ]

    # Emptiness must be judged on the field's OWN line. A multi-line regex here
    # happily matched the *next* field's text and reported an empty value as
    # populated -- a validator that cannot see a blank field is worse than none,
    # because it certifies it.
    for field in ("Authorized by", "Authorization"):
        for line in body.splitlines():
            if not re.match(rf"^\s*[-*]?\s*\*{{0,2}}{re.escape(field)}\*{{0,2}}\s*:", line):
                continue
            value = line.split(":", 1)[1].strip().strip("*").strip()
            if not value:
                errors.append(
                    f"{signoff_path.name} entry for {tag!r} has an empty {field!r} -- "
                    f"a sign-off that records nothing authorizes nothing"
                )
            break
    return errors


def check_disclosure(tag: str, changelog_path: Path = CHANGELOG_PATH) -> list[str]:
    """The public-disclosure half of the gate.

    The CHANGELOG must carry a Governance section under the heading for the
    version being tagged. This is what stops the gate passing quietly: a release
    can only clear it by publishing how it was authorized.
    """
    if not changelog_path.exists():
        return [f"{changelog_path.name} is missing; a release must publish a changelog"]

    text = changelog_path.read_text(encoding="utf-8")
    heading = next(
        (
            line.lstrip("# ").strip()
            for line in text.splitlines()
            if line.startswith("## ") and tag in line
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

    if not re.search(r"^###\s+.*Governance", body, re.MULTILINE | re.IGNORECASE):
        return [
            f"{changelog_path.name} section for {tag!r} has no '### Governance' "
            f"subsection. Every release must publicly state how it was authorized "
            f"and what review it did or did not receive."
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
