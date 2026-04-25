"""Shared Kraken wrapper used by BL-02 (and re-used by BL-03/BL-04 in wave 3).

Public surface (load-bearing — wave 3 plans 03-05/03-06/03-07 import these
symbols by name; rename = breakage):

    recognize_lines(image_path, model_path, *, folio_id) -> list[LineRecord]
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
            f"KRAKEN_PIN.md latest row sha256 malformed: {sha!r} "
            "(placeholder not replaced?)"
        )
    return sha


def _derive_model_hash() -> str:
    """Mirror oracles._hashing.compute_nakdimon_model_hash."""
    sha = _read_pin_sha256()
    seed = f"kraken=={KRAKEN_VERSION}:{sha}".encode("utf-8")
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
    from PIL import Image  # noqa: WPS433
    from kraken import blla, rpred  # noqa: WPS433

    try:
        image = Image.open(image_path).convert("RGB")
        baseline = blla.segment(image)
        network = _load_model(model_path)
        records = list(rpred.rpred(network, image, baseline))
    except KrakenInferenceFailure:
        raise
    except Exception as e:
        raise KrakenInferenceFailure(
            f"D-04: Kraken full-page failure on folio {folio_id} "
            f"(image={image_path}): {e!r}"
        ) from e

    if not records:
        raise KrakenInferenceFailure(
            f"D-04: Kraken yielded zero line records on folio {folio_id} "
            f"(image={image_path})"
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
        bbox_raw = (
            getattr(rec, "line_bbox", None)
            or getattr(rec, "bbox", None)
            or (0, 0, 0, 0)
        )
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
