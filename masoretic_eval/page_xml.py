"""PAGE-XML 2019-07-15 parser. Authoritative implementation (Phase 03.1 A-04).

Verbatim move from openmasorah/gt-infra/gt_infra/export/page_xml_parser.py
in masoretic_eval v0.2.0. The gt-infra path becomes a 2-line shim.

Pitfall 2: bytes survive — no Unicode normalization anywhere. lxml does
not normalize on parse (verified in openmasorah 01-04 + Phase 1 byte-preservation tests).
NFC normalization is applied at the scoring boundary (masoretic_eval/normalize.py),
never inside this parser.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from lxml import etree

PAGE_NS = "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"
NS = {"p": PAGE_NS}

# Comma-separated index values within a letter_size token, e.g. "large@5,large@12".
_LETTER_SIZE_ENTRY = re.compile(r"^(large|small)@(\d+)$")


@dataclass(frozen=True)
class LineRecord:
    """One ``TextLine``'s content post-parse."""

    line_num: int
    verse_ref: str
    text: str
    conf: float | None
    # Tier-4 @custom fields (meta-marks schema v0.1 §"Tracked v0.1 follow-ups" §2)
    parashah: Literal["petuhah", "setumah"] | None = None
    large_letters: tuple[int, ...] = field(default_factory=tuple)
    small_letters: tuple[int, ...] = field(default_factory=tuple)
    stichographic_column: int | None = None


def _parse_custom(custom_attr: str, line_id: str) -> dict:
    """Parse a ``TextLine @custom`` attribute into typed tier-4 fields.

    Splits on ``;``, strips whitespace, and routes each token:
      - ``verse_ref:<value>``           → ``verse_ref`` (str)
      - ``parashah:petuhah|setumah``    → ``parashah`` (Literal)
      - ``letter_size:large@<idx>[,large@<idx>…]``  → ``large_letters`` (tuple[int])
      - ``letter_size:small@<idx>[,small@<idx>…]``  → ``small_letters`` (tuple[int])
      - ``layout:stichographic_column@<n>``          → ``stichographic_column`` (int)

    Letter-size indices are the comma-separated zero-based code-unit indices
    into the TextLine's text content after NFC normalization (per schema §4).
    Multiple entries of the same size share the same semicolon-delimited token
    using comma-separated ``size@idx`` pairs, e.g. ``letter_size:large@5,large@12``.
    Indices are returned in parse order (not sorted or deduplicated); the schema
    does not specify ordering, so insertion order is preserved as a conservative
    default — raised as schema feedback if ordering must be canonical.

    Malformed tokens raise ``ValueError`` naming the offending token and
    ``TextLine`` id.
    """
    result: dict = {
        "verse_ref": "",
        "parashah": None,
        "large_letters": [],
        "small_letters": [],
        "stichographic_column": None,
    }
    for raw in custom_attr.split(";"):
        tok = raw.strip()
        if not tok:
            continue

        if tok.startswith("verse_ref:"):
            result["verse_ref"] = tok.removeprefix("verse_ref:").strip()

        elif tok.startswith("parashah:"):
            value = tok.removeprefix("parashah:").strip()
            if value not in ("petuhah", "setumah"):
                raise ValueError(
                    f"Malformed @custom token {tok!r} in TextLine {line_id!r}: "
                    f"parashah value must be 'petuhah' or 'setumah', got {value!r}"
                )
            result["parashah"] = value

        elif tok.startswith("letter_size:"):
            body = tok.removeprefix("letter_size:").strip()
            # body may be comma-separated: "large@5,large@12" or "small@3"
            for entry in body.split(","):
                entry = entry.strip()
                m = _LETTER_SIZE_ENTRY.match(entry)
                if not m:
                    raise ValueError(
                        f"Malformed @custom token {tok!r} in TextLine {line_id!r}: "
                        f"letter_size entry {entry!r} must match 'large@<int>' or 'small@<int>'"
                    )
                size, idx_str = m.group(1), m.group(2)
                if size == "large":
                    result["large_letters"].append(int(idx_str))
                else:
                    result["small_letters"].append(int(idx_str))

        elif tok.startswith("layout:stichographic_column@"):
            col_str = tok.removeprefix("layout:stichographic_column@").strip()
            if not col_str.isdigit() or int(col_str) not in (1, 2):
                raise ValueError(
                    f"Malformed @custom token {tok!r} in TextLine {line_id!r}: "
                    f"stichographic_column value must be '1' or '2', got {col_str!r}"
                )
            result["stichographic_column"] = int(col_str)

        elif tok.startswith("layout:"):
            raise ValueError(
                f"Malformed @custom token {tok!r} in TextLine {line_id!r}: "
                f"unrecognised layout subkey (expected 'stichographic_column@<n>')"
            )

        # Unknown tokens (e.g. future extensions or tool-generated metadata)
        # are silently skipped so the parser remains forward-compatible.

    return result


def parse_page_xml(xml_path: Path) -> list[LineRecord]:
    """Parse ``xml_path`` into a list of ``LineRecord`` sorted by ``line_num``.

    Robustness:
      - Missing ``TextEquiv`` → line skipped.
      - Missing ``@conf`` → ``conf=None``.
      - Missing ``Unicode`` text → empty string.
      - Unparseable ``@id`` → ``line_num=0`` (keeps ordering deterministic).
    """
    tree = etree.parse(str(xml_path))
    lines: list[LineRecord] = []
    for tl in tree.findall(".//p:TextLine", NS):
        tl_id = tl.get("id", "line_0")
        try:
            line_num = int(tl_id.split("_")[-1])
        except ValueError:
            line_num = 0
        custom = tl.get("custom", "")
        parsed = _parse_custom(custom, tl_id)
        te = tl.find("p:TextEquiv", NS)
        if te is None:
            continue
        conf_str = te.get("conf")
        conf = float(conf_str) if conf_str else None
        uni = te.find("p:Unicode", NS)
        # lxml returns str without normalization — bytes survive (Pitfall 2).
        text = (uni.text if uni is not None else "") or ""
        lines.append(
            LineRecord(
                line_num=line_num,
                verse_ref=parsed["verse_ref"],
                text=text,
                conf=conf,
                parashah=parsed["parashah"],
                large_letters=tuple(parsed["large_letters"]),
                small_letters=tuple(parsed["small_letters"]),
                stichographic_column=parsed["stichographic_column"],
            )
        )
    lines.sort(key=lambda lr: lr.line_num)
    return lines
