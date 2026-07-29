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
import html
import re
import sys
import unicodedata
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

#: ``<!--`` through ``-->`` **or end of input**. CommonMark treats an
#: unterminated HTML comment as running to the end of the document, so
#: ``<!-- unclosed`` renders as nothing at all; matching only closed pairs left
#: that body looking like content to the gate and blank to every reader.
_HTML_COMMENT_RE = re.compile(r"<!--.*?(?:-->|\Z)", re.DOTALL)

#: Elements whose CONTENTS are not prose. ``<style>body{color:red}</style>``
#: survives tag-stripping as ``body{color:red}`` -- markup counted as a
#: statement. Closing tag or end of input, for the same reason as comments.
_DISCARDED_ELEMENT_RE = re.compile(
    r"<(script|style|template)\b[^>]*>.*?(?:</\1\s*>|\Z)", re.DOTALL | re.IGNORECASE
)

#: Tag shapes only -- ``<span>``, ``</div>``, ``<br/>``. Deliberately requires a
#: letter after ``<`` so a markdown autolink such as ``<https://example.org>``
#: is left intact: that IS visible content. Tags are stripped rather than
#: rejected, so ``real <em>text</em>`` still reads as the text it renders to.
_HTML_TAG_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9-]*(?:\s[^<>]*)?/?>")

#: A CommonMark link-reference definition renders nothing at all -- it declares
#: a label for use elsewhere. A body consisting only of these is blank.
#:
#: The title is optional and may sit on the definition line OR on an indented
#: continuation line. The first version of this matched single lines only, so
#: ``[policy]: https://example.org`` + ``    "title"`` left the title line
#: behind as substance -- which made the docstring's own enumeration false, the
#: precise defect the enumeration was written to prevent.
_TITLE = r"(?:\"[^\"]*\"|'[^']*'|\([^)]*\))"
#: CommonMark allows a destination in angle brackets, which may contain spaces:
#: ``[ref]: <foo bar>``. Without this alternative the definition did not match,
#: and the tag stripper then ate ``<foo bar>`` as if it were an HTML tag,
#: leaving ``[ref]:`` behind as substance.
_DESTINATION = r"(?:<[^<>\n]*>|\S+)"
_LINK_REF_DEF_RE = re.compile(
    rf"^[ ]{{0,3}}\[[^\]]+\]:[ \t]*{_DESTINATION}[ \t]*{_TITLE}?[ \t]*"
    rf"(?:\n[ \t]+{_TITLE}[ \t]*)?$",
    re.MULTILINE,
)

#: Inline links with empty TEXT and images with empty ALT render no visible
#: text. ``[](/policy)`` and ``![](x)`` are markup that shows the reader
#: nothing. The reference forms ``[][ref]`` / ``![][ref]`` are the same class.
#: A link WITH text -- ``[policy](https://example.org)`` -- is content and is
#: deliberately not matched.
_EMPTY_LINK_RE = re.compile(r"!?\[[ \t]*\](?:\([^)]*\)|\[[^\]]*\])")

_MARKDOWN_NOISE_RE = re.compile(r"[\s*_`>#.\-]+")


def _visible_text(content: str) -> str:
    """Approximate what a reader would see, by removal only. No parser.

    Order matters and is not arbitrary.

    * Comments and discarded elements come off the RAW text, before entity
      decoding, so an escaped ``&lt;!--`` stays the literal text it renders as
      instead of being promoted into a comment and deleted.
    * Link-reference definitions are removed BEFORE HTML tags. A destination
      may be angle-bracketed -- ``[ref]: <foo bar>`` -- and the tag stripper
      would otherwise consume it as if it were a tag, leaving ``[ref]:``
      stranded as substance. Definition matching is line-anchored on the raw
      text, so running it earlier is safe.
    * Entity decoding precedes the invisible-codepoint pass, because
      ``&nbsp;`` has to become U+00A0 for that pass to see it.
    * Empty-link removal runs LAST, after invisible characters are gone. A link
      whose text is a zero-width space is not literally empty, so the pattern
      missed it and the leftover ``[]()`` punctuation then counted as content.
      Deleting invisible characters first turns every invisible-text link into
      an empty-text link, which closes the class rather than one codepoint:
      ZWSP, word joiner and a combining-mark-only link text all reduce the same
      way.
    """
    text = _HTML_COMMENT_RE.sub("", content)
    text = _DISCARDED_ELEMENT_RE.sub("", text)
    text = _LINK_REF_DEF_RE.sub("", text)
    text = _HTML_TAG_RE.sub("", text)
    text = html.unescape(text)
    text = "".join(_visible_char(ch) for ch in text)

    return _EMPTY_LINK_RE.sub("", text)


def _visible_char(ch: str) -> str:
    """One character's contribution to the visible text. May be empty.

    * ``Cf`` (format) is deleted: U+200B, U+2060 and U+FEFF are not Python
      whitespace, so ``.strip()`` preserved them and a body of one zero-width
      space read as content.
    * ``Cc`` (control) is deleted apart from tab/newline/carriage return, which
      are real layout. A body of a lone ``\\x01`` shows a reader nothing.
    * ``Mn`` (non-spacing mark) is deleted because it has zero advance width on
      its own. Hebrew nikkud are ``Mn`` and the base consonants are not, so a
      pointed Hebrew word survives intact -- only a body of *bare* marks is
      reduced to nothing. That distinction is load-bearing in this repository.
    * ``Zs`` becomes an ordinary space rather than being deleted, so
      NBSP-joined words keep their boundary.
    """
    category = unicodedata.category(ch)
    if category == "Zs":
        return " "
    if category in {"Cf", "Mn"}:
        return ""
    if category == "Cc" and ch not in "\t\n\r":
        return ""
    return ch


def _is_substantive(content: str) -> bool:
    """Is anything left of this section body after normalization?

    THE TRUE PROPERTY, stated precisely because a wrong self-description is
    this project's documented failure mode. This does **not** verify that the
    body "visibly renders"; it verifies that the body is non-empty after a
    specific, listed normalization:

    * HTML comments removed, terminated or not
    * ``<script>``/``<style>``/``<template>`` contents removed
    * remaining HTML tags removed
    * HTML entities decoded
    * empty-text links and empty-alt images with a SIMPLE destination -- one
      containing no nested parentheses -- removed (``[](/x)``, ``![](x)``),
      including links whose text is only invisible characters, since those are
      removed first
    * CommonMark link-reference definitions dropped, including an angle-
      bracketed destination and an indented title continuation line
    * Unicode ``Cf`` deleted; ``Cc`` deleted apart from tab/newline/return;
      ``Mn`` (zero-width combining marks) deleted; ``Zs`` collapsed to a space
    * a fixed set of placeholder words rejected

    That is an approximation of "renders visibly", not a guarantee of it. Four
    rounds of review each broke the previous blocklist, so the list above is
    the honest description of what is enforced rather than a claim about what
    a browser would show. It is also load-bearing: at round four the
    link-reference rule matched single lines only, so this enumeration was
    *false* -- exactly the defect enumerating was meant to prevent.

    ``Mn`` deletion is deliberately narrow. Hebrew nikkud are ``Mn`` and the
    base consonants are not, so a pointed Hebrew disclosure survives and only a
    body of bare combining marks is reduced to nothing. This repository will
    plausibly carry Hebrew in a disclosure; breaking that would be a worse
    failure than the hole being closed.

    KNOWN BOUNDS, deliberately not closed. Both are cases where a regex would
    have to parse a recursive or context-sensitive grammar, and both are pinned
    by test so the code cannot quietly start claiming more than it does:

    * **HTML attributes are not parsed**, so a quoted ``>`` inside one defeats
      the tag pattern: ``<span title="a>b"></span>`` leaves ``b"`` and passes.
    * **Nested parentheses in a link destination are not counted.** CommonMark
      permits them, and a regex cannot match balanced delimiters, so
      ``[](foo(and)bar)`` leaves ``bar)`` and passes. The enumeration above is
      scoped to simple destinations rather than overstating this.

    Closing either needs a real parser -- an HTML parser, or a CommonMark one.
    That is a dependency this CI gate should not take on in order to defend
    against its own maintainer. A maintainer determined to hide his own
    disclosure from his own gate can; that is not the threat this check exists
    for, which is the disclosure being forgotten, deferred, or left as a stub.
    Same precedent as the withdrawn-request waiver.

    There is no length threshold. Visible punctuation is content, and a
    threshold would be one more arbitrary surface to argue about.

    CORRECT PASSES, recorded so they are not mistaken for holes on a later
    read. Each was raised in review and confirmed to render visibly:

    * ``[]{}()`` -- punctuation with no markup meaning. Visible, so content;
      this is the no-threshold position doing its job, not a gap.
    * ``[]: x`` -- not a link-reference definition. CommonMark requires a
      non-empty label, so this renders as literal text.
    * A lone ``Mc`` (spacing combining mark) -- unlike ``Mn`` it has advance
      width, so it is visible and only ``Mn`` is deleted.
    """
    visible = _visible_text(content).strip()
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
