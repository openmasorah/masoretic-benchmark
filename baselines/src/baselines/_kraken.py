"""Shared Kraken wrapper used by BL-02 (and re-used by BL-03/BL-04 in wave 3).

Public surface (load-bearing — wave 3 plans 03-05/03-06/03-07 import these
symbols by name; rename = breakage):

    recognize_lines(image_path, model_path, *, folio_id) -> list[LineRecord]
    serialize_pagexml(lines, *, folio_id) -> str   # A-04/D-21 LOCKED 2026-04-27
    KRAKEN_MODEL_HASH: str         # 16-char digest derived from KRAKEN_PIN.md
    KRAKEN_VERSION:    str         # "7.0.1"

Per D-04: per-line LineRecord.kraken_confidence is populated as the mean of
per-character confidences from rpred.rpred. Full-page Kraken failure (zero
records or all-empty transcription) raises KrakenInferenceFailure; the caller
(BaselineBase.run via SandboxRun.__exit__ on exception) leaves
results/.in_progress/<bl>/ for inspection per the atomic-run policy (D-14).

KRAKEN_MODEL_HASH is canonical-from-the-pin: recomputed on import from the
latest dated row of baselines/KRAKEN_PIN.md. Bumping the pin moves the
constant; tests assert the linkage holds. Mirrors the shape of
oracles._hashing.compute_nakdimon_model_hash so the digest formula is
uniform across Phase 2 (Nakdimon) and Phase 3 (Kraken).
"""

from __future__ import annotations

import hashlib
import re
from functools import lru_cache
from pathlib import Path

from baselines._base import LineRecord
from baselines._errors import KrakenInferenceFailure

# Path resolution: this file is at
#   <repo>/baselines/src/baselines/_kraken.py
# parents[0]=baselines, parents[1]=src, parents[2]=baselines, parents[3]=<repo>.
REPO_ROOT = Path(__file__).resolve().parents[3]
KRAKEN_PIN_MD = REPO_ROOT / "baselines" / "KRAKEN_PIN.md"
KRAKEN_VERSION = "7.0.1"


def _read_pin_sha256() -> str:
    """Parse KRAKEN_PIN.md, return the latest dated row's sha256 column.

    Append-only newest-first convention. Row format:

        | <YYYY-MM-DD> | <DOI> | <kraken-version> | <64-hex sha256> | <reason> |
    """
    text = KRAKEN_PIN_MD.read_text(encoding="utf-8")
    rows = [r for r in text.splitlines() if r.startswith("| 2026-")]
    if not rows:
        raise RuntimeError(
            "no dated row in KRAKEN_PIN.md; pin not initialized "
            "(see baselines/scripts/fetch_biblia_kraken_model.py)"
        )
    cols = [c.strip() for c in rows[0].strip("|").split("|")]
    sha = cols[3]
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise RuntimeError(
            f"KRAKEN_PIN.md latest row sha256 malformed: {sha!r} (placeholder not replaced?)"
        )
    return sha


def _derive_model_hash() -> str:
    """Mirror oracles._hashing.compute_nakdimon_model_hash."""
    sha = _read_pin_sha256()
    seed = f"kraken=={KRAKEN_VERSION}:{sha}".encode()
    return hashlib.sha256(seed).hexdigest()[:16]


# Module-level constant — load-bearing for wave-3 imports.
KRAKEN_MODEL_HASH: str = _derive_model_hash()


@lru_cache(maxsize=1)
def _load_model(model_path: Path):
    """Lazy-load the kraken model. Cache size 1: kraken models are heavy
    (~tens of MB) and inference is pure; no per-folio reload needed.

    The lazy import keeps the kraken package off the test path (mocked unit
    tests don't need kraken installed) and matches the pattern from oracles.
    """
    from kraken.lib import models

    return models.load_any(str(model_path))


def recognize_lines(
    image_path: Path,
    model_path: Path,
    *,
    folio_id: str,
) -> list[LineRecord]:
    """Run Kraken segmentation + recognition on `image_path`.

    Returns one LineRecord per recognized line. tier1=tier2=tier3 are all
    set to the raw kraken-emitted string: the scorer (D-22 untouched) re-derives
    consonantal / nikkud / trop tier views at score time. Tier-4 metamarks
    are NOT emitted by Kraken — `tier4_records` is always an empty tuple.

    Per-line `kraken_confidence` is populated from the mean of `rec.confidences`
    when rpred.rpred yields per-character confidences; falls back to 0.0 when
    the record exposes no confidences.

    Raises KrakenInferenceFailure on full-page failure:
      - any exception during PIL.Image.open / blla.segment / rpred.rpred
      - rpred.rpred yields zero records
      - every record has empty text
    The caller's SandboxRun __exit__ leaves the sandbox for inspection.
    """
    # Lazy-imported so unit tests (which patch via the package qualified path)
    # don't require kraken / PIL on the import path.
    from kraken import blla, rpred  # noqa: WPS433
    from PIL import Image  # noqa: WPS433

    try:
        image = Image.open(image_path).convert("RGB")
        baseline = blla.segment(image)
        network = _load_model(model_path)
        records = list(rpred.rpred(network, image, baseline))
    except KrakenInferenceFailure:
        raise
    except Exception as e:
        raise KrakenInferenceFailure(
            f"D-04: Kraken full-page failure on folio {folio_id} (image={image_path}): {e!r}"
        ) from e

    if not records:
        raise KrakenInferenceFailure(
            f"D-04: Kraken yielded zero line records on folio {folio_id} (image={image_path})"
        )

    out: list[LineRecord] = []
    for i, rec in enumerate(records):
        text = str(rec)
        if not text:
            continue
        confs = list(getattr(rec, "confidences", []) or [])
        mean_conf = (sum(confs) / len(confs)) if confs else 0.0
        # Kraken's record exposes line geometry under one of a few attribute
        # names depending on version; tolerate the common shapes.
        bbox_raw = getattr(rec, "line_bbox", None) or getattr(rec, "bbox", None) or (0, 0, 0, 0)
        x0, y0, x1, y1 = (
            int(bbox_raw[0]),
            int(bbox_raw[1]),
            int(bbox_raw[2]),
            int(bbox_raw[3]),
        )
        out.append(
            LineRecord(
                line_id=f"{folio_id}_L{i + 1:03d}",
                bbox=(x0, y0, x1, y1),
                tier1=text,
                tier2=text,
                tier3=text,
                tier4_records=tuple(),
                kraken_confidence=round(float(mean_conf), 4),
            )
        )

    if not out:
        raise KrakenInferenceFailure(
            f"D-04: Kraken records produced zero non-empty lines on "
            f"folio {folio_id} (image={image_path})"
        )

    return out


# A-04/D-21 LOCKED 2026-04-27: deterministic PAGE-XML serializer for the
# BL-02 cache (Phase 03.1). The output round-trips through
# masoretic_eval.page_xml.parse_page_xml without raising. Used by BL-02's
# .cache/kraken/<folio_id>/<KRAKEN_MODEL_HASH>.page.xml side-effect cache,
# which is the chain consumption path BL-03/BL-04 read in plan 03.1-06.
#
# Determinism contract:
#   - No timestamps in output (PAGE-XML schema permits Created/LastChange
#     under <Metadata>; we OMIT them so byte-equality holds across re-runs).
#   - Element/attribute order is fixed by construction order.
#   - lxml's pretty_print=False with explicit declaration produces a
#     deterministic byte-string given identical inputs.
def serialize_pagexml(
    lines: list[LineRecord],
    *,
    folio_id: str,
    image_filename: str | None = None,
) -> str:
    """Serialize ``lines`` to a deterministic PAGE-XML 2019-07-15 string.

    Each ``LineRecord`` becomes a ``TextLine`` element with:
      - ``id``: ``line_<line_num>`` where ``line_num`` is parsed from
        ``line_id`` suffix (``..._L001`` -> ``1``); falls back to enumeration
        order when the suffix is absent.
      - ``Coords``: a ``points`` attribute encoding the bbox as four corner
        points (``x0,y0 x1,y0 x1,y1 x0,y1``); satisfies PAGE schema's
        required Coords child without forcing a polygon shape we don't have.
      - ``TextEquiv``: with ``conf`` attribute carrying ``kraken_confidence``
        (rounded to 4 decimal places) and a ``Unicode`` child carrying the
        tier-1 string (== tier-2 == tier-3 == raw kraken transcription per
        ``recognize_lines``).

    Pitfall 2 byte-preservation: NO Unicode normalization is applied. lxml's
    serializer preserves the raw UTF-8 string verbatim. CGJ U+034F survives.

    Caller's responsibility: write the returned str via
    ``Path.write_text(..., encoding="utf-8")``. The returned string starts
    with ``<?xml version='1.0' encoding='UTF-8'?>``.
    """
    from lxml import etree as _etree  # noqa: WPS433 — lazy to keep test path light

    PAGE_NS = "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"
    nsmap = {None: PAGE_NS}

    pcgts = _etree.Element(f"{{{PAGE_NS}}}PcGts", nsmap=nsmap)
    # <Metadata>: minimal; OMIT Created/LastChange for byte-determinism.
    metadata = _etree.SubElement(pcgts, f"{{{PAGE_NS}}}Metadata")
    creator = _etree.SubElement(metadata, f"{{{PAGE_NS}}}Creator")
    creator.text = f"masoretic-benchmark BL-02 (kraken {KRAKEN_VERSION})"
    page = _etree.SubElement(
        pcgts,
        f"{{{PAGE_NS}}}Page",
        attrib={
            "imageFilename": image_filename or f"{folio_id}.jpg",
            # imageWidth/imageHeight are required by the schema as integers
            # but we don't track full-page dims here; emit 0 sentinels (the
            # parser doesn't validate against schema and ignores these).
            "imageWidth": "0",
            "imageHeight": "0",
        },
    )
    text_region = _etree.SubElement(
        page,
        f"{{{PAGE_NS}}}TextRegion",
        attrib={"id": f"region_{folio_id}"},
    )
    # TextRegion schema requires a Coords; emit a degenerate one mirroring
    # full-page (0,0,0,0) so downstream parsers don't trip on missing geom.
    _etree.SubElement(
        text_region,
        f"{{{PAGE_NS}}}Coords",
        attrib={"points": "0,0 0,0 0,0 0,0"},
    )

    for idx, lr in enumerate(lines, start=1):
        # Recover line_num from line_id suffix when possible: "<folio>_L001" -> 1.
        line_num = idx
        suffix = lr.line_id.rsplit("_", 1)[-1] if "_" in lr.line_id else ""
        if suffix.startswith("L") and suffix[1:].isdigit():
            line_num = int(suffix[1:])

        tl = _etree.SubElement(
            text_region,
            f"{{{PAGE_NS}}}TextLine",
            attrib={"id": f"line_{line_num}"},
        )
        x0, y0, x1, y1 = lr.bbox
        _etree.SubElement(
            tl,
            f"{{{PAGE_NS}}}Coords",
            attrib={"points": f"{x0},{y0} {x1},{y0} {x1},{y1} {x0},{y1}"},
        )
        te_attrib = {}
        if lr.kraken_confidence is not None:
            te_attrib["conf"] = f"{round(float(lr.kraken_confidence), 4):.4f}"
        te = _etree.SubElement(
            tl,
            f"{{{PAGE_NS}}}TextEquiv",
            attrib=te_attrib,
        )
        uni = _etree.SubElement(te, f"{{{PAGE_NS}}}Unicode")
        # Pitfall 2: no normalization. lxml stores the str verbatim.
        uni.text = lr.tier1

    # Deterministic serialization: pretty_print=False, fixed declaration.
    return _etree.tostring(
        pcgts,
        xml_declaration=True,
        encoding="UTF-8",
        pretty_print=False,
        standalone=None,
    ).decode("utf-8")
