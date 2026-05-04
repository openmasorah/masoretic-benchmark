"""PAGE-XML 2019-07-15 parser. Authoritative implementation (Phase 03.1 A-04).

Verbatim move from openmesorah/gt-infra/gt_infra/export/page_xml_parser.py
in masoretic_eval v0.2.0. The gt-infra path becomes a 2-line shim.

Pitfall 2: bytes survive — no Unicode normalization anywhere. lxml does
not normalize on parse (verified in openmesorah 01-04 + Phase 1 byte-preservation tests).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lxml import etree

PAGE_NS = "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"
NS = {"p": PAGE_NS}


@dataclass(frozen=True)
class LineRecord:
    """One ``TextLine``'s content post-parse."""

    line_num: int
    verse_ref: str
    text: str
    conf: float | None


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
        verse_ref = ""
        for tok in custom.split(";"):
            tok = tok.strip()
            if tok.startswith("verse_ref:"):
                verse_ref = tok.removeprefix("verse_ref:").strip()
        te = tl.find("p:TextEquiv", NS)
        if te is None:
            continue
        conf_str = te.get("conf")
        conf = float(conf_str) if conf_str else None
        uni = te.find("p:Unicode", NS)
        # lxml returns str without normalization — bytes survive (Pitfall 2).
        text = (uni.text if uni is not None else "") or ""
        lines.append(LineRecord(line_num=line_num, verse_ref=verse_ref, text=text, conf=conf))
    lines.sort(key=lambda lr: lr.line_num)
    return lines
