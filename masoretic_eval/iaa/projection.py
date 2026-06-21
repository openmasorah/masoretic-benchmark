"""CC-BY-4.0 positional projection — the public reproducibility surface.

Round-0 raw .txt inputs are gitignored upstream (Yosef's private layout-
preserving format). SPEC 260619-n3u's SHA-pinning is theatre if there is no
publicly-licensed surface a third party can hash. The positional projection
is that surface:

* Per side, per verse: ``verse_ref``, ``folio``, ``chunk`` (post-``split_chunks``
  layout-free Hebrew text), ``consonant_count``, and the derived
  ``tier4_positional`` tuples (``type`` + 1-based ``ordinal``).
* The chunk is the source of truth; ``tier4_positional`` and
  ``consonant_count`` are derived convenience fields that ``load_projection``
  re-verifies (``PositionalProjectionInvalid`` on mismatch). This invariant
  prevents the file from drifting away from the chunk it was projected from.
* Determinism: ``serialize_projection`` writes UTF-8, ``sort_keys=True``,
  fixed indent — same source → byte-identical JSON.

The cross-path contract: ``compute_iaa_from_positional`` produces a
byte-identical ``paper_iaa_results.json`` vs the raw-.txt path
(``compute.compute_iaa``) given the same source data. The two paths share
the post-parse computation kernel (``_compute_from_verse_data``) so they
cannot drift.

JSON shape::

    {
      "format_version": 1,
      "side_label": "ginsberg",
      "license": "CC-BY-4.0",
      "source": "<short provenance string for the round-0 transcription>",
      "verses": [
        {
          "verse_ref": "Deut.32.1",
          "folio": "F118B",
          "chunk": "<Hebrew text with circellus / rafe / <DR>>",
          "consonant_count": 47,
          "tier4_positional": [
            {"type": "circellus", "ordinal": 5},
            {"type": "rafe", "ordinal": 12}
          ]
        }
      ]
    }
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from masoretic_eval.iaa.bootstrap import DEFAULT_B, DEFAULT_SEED
from masoretic_eval.iaa.parse import (
    Tier4Record,
    count_consonants,
    extract_positional,
    split_chunks,
)
from masoretic_eval.iaa.result import IaaResult

FORMAT_VERSION = 1
LICENSE = "CC-BY-4.0"


class PositionalProjectionInvalid(Exception):
    """The on-disk projection JSON failed a load-time invariant.

    Either the schema is malformed, the per-verse ``tier4_positional`` /
    ``consonant_count`` drifted from what the chunk produces, or A and B
    sides disagree on the verse_folio_map. The error message names the
    invariant.
    """


@dataclass(frozen=True)
class PositionalVerse:
    """One verse's positional projection record."""

    verse_ref: str
    folio: str
    chunk: str
    consonant_count: int
    tier4_positional: tuple[Tier4Record, ...]


@dataclass(frozen=True)
class PositionalProjection:
    """One annotator-side projection covering ``len(verses)`` verses."""

    format_version: int
    side_label: str
    license: str
    source: str
    verses: tuple[PositionalVerse, ...] = field(default_factory=tuple)


def project_side(
    side_text: str,
    verse_folio_map: Sequence[tuple[str, str]],
    *,
    side_label: str,
    source: str = "Round-0 raw transcription, layout-free projection",
) -> PositionalProjection:
    """Project a raw round-0 side .txt into a ``PositionalProjection``.

    Parsing runs the same ``split_chunks`` + ``extract_positional`` +
    ``count_consonants`` used by the raw-.txt compute path, so the
    projection's content is identical to what compute_iaa would derive
    internally. Verse count must match ``verse_folio_map`` exactly.
    """
    chunks = split_chunks(side_text)
    if len(chunks) != len(verse_folio_map):
        raise ValueError(
            f"verse-count mismatch projecting side {side_label!r}: "
            f"verse_folio_map={len(verse_folio_map)}, chunks={len(chunks)}"
        )
    verses: list[PositionalVerse] = []
    for (vref, folio), chunk in zip(verse_folio_map, chunks, strict=True):
        positional = tuple(extract_positional(chunk, vref))
        verses.append(
            PositionalVerse(
                verse_ref=vref,
                folio=folio,
                chunk=chunk,
                consonant_count=count_consonants(chunk),
                tier4_positional=positional,
            )
        )
    return PositionalProjection(
        format_version=FORMAT_VERSION,
        side_label=side_label,
        license=LICENSE,
        source=source,
        verses=tuple(verses),
    )


def _verse_to_dict(v: PositionalVerse) -> dict[str, Any]:
    return {
        "verse_ref": v.verse_ref,
        "folio": v.folio,
        "chunk": v.chunk,
        "consonant_count": v.consonant_count,
        "tier4_positional": [{"type": r.type, "ordinal": r.ordinal} for r in v.tier4_positional],
    }


def serialize_projection(projection: PositionalProjection) -> str:
    """Produce deterministic JSON (UTF-8, sort_keys, fixed indent).

    Floats are not used in the projection so float-rep stability is not a
    concern. Same source data → byte-identical output across runs.
    """
    doc = {
        "format_version": projection.format_version,
        "side_label": projection.side_label,
        "license": projection.license,
        "source": projection.source,
        "verses": [_verse_to_dict(v) for v in projection.verses],
    }
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False)


def _verse_from_dict(raw: dict[str, Any]) -> PositionalVerse:
    try:
        vref = raw["verse_ref"]
        folio = raw["folio"]
        chunk = raw["chunk"]
        consonant_count = int(raw["consonant_count"])
        positional_raw = raw["tier4_positional"]
    except KeyError as exc:
        raise PositionalProjectionInvalid(
            f"verse record missing required field: {exc.args[0]}"
        ) from exc
    if not isinstance(positional_raw, list):
        raise PositionalProjectionInvalid("tier4_positional must be a list")
    records = tuple(
        Tier4Record(type=item["type"], verse_ref=vref, ordinal=int(item["ordinal"]))
        for item in positional_raw
    )

    # Source-of-truth check: re-derive from chunk and assert the stored
    # convenience fields agree. This is the load-time invariant.
    expected_records = tuple(extract_positional(chunk, vref))
    if records != expected_records:
        raise PositionalProjectionInvalid(
            f"tier4_positional for verse {vref!r} drifts from chunk: "
            f"stored={records!r}, derived={expected_records!r}"
        )
    expected_n_cons = count_consonants(chunk)
    if consonant_count != expected_n_cons:
        raise PositionalProjectionInvalid(
            f"consonant_count for verse {vref!r} drifts from chunk: "
            f"stored={consonant_count}, derived={expected_n_cons}"
        )
    return PositionalVerse(
        verse_ref=vref,
        folio=folio,
        chunk=chunk,
        consonant_count=consonant_count,
        tier4_positional=records,
    )


def load_projection(path: Path) -> PositionalProjection:
    """Load + validate a projection JSON.

    Raises :class:`PositionalProjectionInvalid` if the file is malformed or
    a verse's derived fields drift from its chunk.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    try:
        format_version = int(raw["format_version"])
        side_label = raw["side_label"]
        license_str = raw["license"]
        source = raw.get("source", "")
        verses_raw = raw["verses"]
    except KeyError as exc:
        raise PositionalProjectionInvalid(
            f"projection missing required field: {exc.args[0]}"
        ) from exc
    if format_version != FORMAT_VERSION:
        raise PositionalProjectionInvalid(
            f"unsupported format_version {format_version}; expected {FORMAT_VERSION}"
        )
    if not isinstance(verses_raw, list):
        raise PositionalProjectionInvalid("verses must be a list")
    verses = tuple(_verse_from_dict(v) for v in verses_raw)
    return PositionalProjection(
        format_version=format_version,
        side_label=side_label,
        license=license_str,
        source=source,
        verses=verses,
    )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_iaa_from_positional(
    a_projection_path: Path,
    b_projection_path: Path,
    *,
    bootstrap_b: int = DEFAULT_B,
    bootstrap_seed: int = DEFAULT_SEED,
    expected_a_sha256: str | None = None,
    expected_b_sha256: str | None = None,
    gt_hash: str | None = None,
    force: bool = False,
) -> IaaResult:
    """Compute paper-grade IAA from two pre-projected positional JSONs.

    Byte-identical to :func:`masoretic_eval.iaa.compute.compute_iaa` when
    invoked with the same source round-0 .txt files. The verse_folio_map
    is sourced from the projections themselves; A and B must agree on it
    verse-by-verse or :class:`PositionalProjectionInvalid` is raised.

    SHA pinning works identically to the raw-.txt path — it now pins the
    projection JSON's hash, which IS the public reproducibility surface.
    """
    from masoretic_eval.iaa.compute import IaaInputMismatch, _compute_from_verse_data

    a_path = Path(a_projection_path)
    b_path = Path(b_projection_path)
    a_sha = _sha256(a_path)
    b_sha = _sha256(b_path)
    if not force:
        if expected_a_sha256 is not None and a_sha != expected_a_sha256:
            raise IaaInputMismatch(
                f"A-side projection SHA256 mismatch: expected {expected_a_sha256}, got {a_sha}"
            )
        if expected_b_sha256 is not None and b_sha != expected_b_sha256:
            raise IaaInputMismatch(
                f"B-side projection SHA256 mismatch: expected {expected_b_sha256}, got {b_sha}"
            )

    a_proj = load_projection(a_path)
    b_proj = load_projection(b_path)

    if len(a_proj.verses) != len(b_proj.verses):
        raise PositionalProjectionInvalid(
            f"verse-count mismatch: A has {len(a_proj.verses)} verses, B has {len(b_proj.verses)}"
        )
    verse_folio_map: list[tuple[str, str]] = []
    a_records_by_verse: dict[str, list[Tier4Record]] = {}
    b_records_by_verse: dict[str, list[Tier4Record]] = {}
    n_cons_by_verse: dict[str, int] = {}
    chunks_by_verse: dict[str, tuple[str, str, str]] = {}
    for a_v, b_v in zip(a_proj.verses, b_proj.verses, strict=True):
        if (a_v.verse_ref, a_v.folio) != (b_v.verse_ref, b_v.folio):
            raise PositionalProjectionInvalid(
                f"verse_folio_map disagreement between A and B sides: "
                f"A=({a_v.verse_ref!r}, {a_v.folio!r}) vs "
                f"B=({b_v.verse_ref!r}, {b_v.folio!r})"
            )
        verse_folio_map.append((a_v.verse_ref, a_v.folio))
        a_records_by_verse[a_v.verse_ref] = list(a_v.tier4_positional)
        b_records_by_verse[a_v.verse_ref] = list(b_v.tier4_positional)
        # n_cons mirrors the raw-.txt path: A-side defines the consonant axis.
        n_cons_by_verse[a_v.verse_ref] = a_v.consonant_count
        chunks_by_verse[a_v.verse_ref] = (a_v.folio, a_v.chunk, b_v.chunk)

    # Defensive: chunks_by_verse must cover every verse_ref in the order
    # verse_folio_map declares (preserves determinism with raw-.txt path).
    assert len(chunks_by_verse) == len(verse_folio_map), (
        "duplicate verse_ref in projection — would silently overwrite per-verse data"
    )

    return _compute_from_verse_data(
        verse_folio_map=verse_folio_map,
        a_records_by_verse=a_records_by_verse,
        b_records_by_verse=b_records_by_verse,
        n_cons_by_verse=n_cons_by_verse,
        chunks_by_verse=chunks_by_verse,
        bootstrap_b=bootstrap_b,
        bootstrap_seed=bootstrap_seed,
        metadata_extra={
            "a_sha256": a_sha,
            "b_sha256": b_sha,
            "gt_hash": gt_hash,
            "uxlc_anchored": False,
        },
    )


def compute_iaa_uxlc_anchored_from_positional(
    a_projection_path: Path,
    b_projection_path: Path,
    uxlc_text_by_verse: dict[str, str],
    *,
    bootstrap_b: int = DEFAULT_B,
    bootstrap_seed: int = DEFAULT_SEED,
    expected_a_sha256: str | None = None,
    expected_b_sha256: str | None = None,
    gt_hash: str | None = None,
    force: bool = False,
    gold_chunks_by_verse: dict[str, str] | None = None,
    uxlc_tier2_by_verse: dict[str, str] | None = None,
) -> IaaResult:
    """Headline IAA with FINDING 3 contamination removed.

    Identical to :func:`compute_iaa_from_positional` *except* each side's
    tier-4 records are reprojected from per-annotator ordinals to UXLC-frame
    ordinals before scoring (see :mod:`masoretic_eval.iaa.reproject` and
    ``masoretic_eval/iaa/ALIGNMENT.md`` for the alignment algorithm and the
    motivation).

    The per-annotator path (``compute_iaa_from_positional``) is the
    backwards-compatible sensitivity baseline; the paper reports the
    UXLC-anchored numbers as headline and the per-annotator numbers as a
    FINDING 3 sensitivity column.

    Schema impact: NONE. The published positional projection JSONs keep
    per-annotator ordinals (no v0.3 schema bump, no manifest fuse). UXLC is
    a separate runtime input — publicly available CC0 from UXLC 2.5 — that
    the scorer fetches alongside the projection JSONs. Without UXLC the
    scorer reproduces the per-annotator sensitivity number; with UXLC it
    reproduces the headline number.

    Records that anchor on a side-only consonant (a tier-1 insertion with
    no UXLC counterpart) are dropped from the reprojected set and the count
    surfaces in ``metadata["dropped_record_counts"]`` so the caller can
    audit the size of the dropped set.
    """
    from masoretic_eval.iaa.compute import IaaInputMismatch, _compute_from_verse_data
    from masoretic_eval.iaa.reproject import consonants_of, reproject_records

    a_path = Path(a_projection_path)
    b_path = Path(b_projection_path)
    a_sha = _sha256(a_path)
    b_sha = _sha256(b_path)
    if not force:
        if expected_a_sha256 is not None and a_sha != expected_a_sha256:
            raise IaaInputMismatch(
                f"A-side projection SHA256 mismatch: expected {expected_a_sha256}, got {a_sha}"
            )
        if expected_b_sha256 is not None and b_sha != expected_b_sha256:
            raise IaaInputMismatch(
                f"B-side projection SHA256 mismatch: expected {expected_b_sha256}, got {b_sha}"
            )

    a_proj = load_projection(a_path)
    b_proj = load_projection(b_path)

    if len(a_proj.verses) != len(b_proj.verses):
        raise PositionalProjectionInvalid(
            f"verse-count mismatch: A has {len(a_proj.verses)} verses, B has {len(b_proj.verses)}"
        )
    verse_folio_map: list[tuple[str, str]] = []
    a_records_by_verse: dict[str, list[Tier4Record]] = {}
    b_records_by_verse: dict[str, list[Tier4Record]] = {}
    n_cons_by_verse: dict[str, int] = {}
    chunks_by_verse: dict[str, tuple[str, str, str]] = {}
    dropped_a = 0
    dropped_b = 0
    missing_uxlc: list[str] = []
    for a_v, b_v in zip(a_proj.verses, b_proj.verses, strict=True):
        if (a_v.verse_ref, a_v.folio) != (b_v.verse_ref, b_v.folio):
            raise PositionalProjectionInvalid(
                f"verse_folio_map disagreement between A and B sides: "
                f"A=({a_v.verse_ref!r}, {a_v.folio!r}) vs "
                f"B=({b_v.verse_ref!r}, {b_v.folio!r})"
            )
        uxlc_text = uxlc_text_by_verse.get(a_v.verse_ref)
        if uxlc_text is None:
            missing_uxlc.append(a_v.verse_ref)
            continue
        verse_folio_map.append((a_v.verse_ref, a_v.folio))
        a_re = reproject_records(list(a_v.tier4_positional), a_v.chunk, uxlc_text)
        b_re = reproject_records(list(b_v.tier4_positional), b_v.chunk, uxlc_text)
        dropped_a += len(a_re.dropped)
        dropped_b += len(b_re.dropped)
        a_records_by_verse[a_v.verse_ref] = a_re.kept
        b_records_by_verse[a_v.verse_ref] = b_re.kept
        # n_cons becomes the UXLC consonant axis (the new ordinal domain).
        n_cons_by_verse[a_v.verse_ref] = len(consonants_of(uxlc_text))
        chunks_by_verse[a_v.verse_ref] = (a_v.folio, a_v.chunk, b_v.chunk)

    if missing_uxlc:
        raise PositionalProjectionInvalid(
            f"uxlc_text_by_verse missing {len(missing_uxlc)} verse_refs "
            f"(first: {missing_uxlc[0]!r}); cannot anchor tier-4 ordinals"
        )

    assert len(chunks_by_verse) == len(verse_folio_map)

    return _compute_from_verse_data(
        verse_folio_map=verse_folio_map,
        a_records_by_verse=a_records_by_verse,
        b_records_by_verse=b_records_by_verse,
        n_cons_by_verse=n_cons_by_verse,
        chunks_by_verse=chunks_by_verse,
        bootstrap_b=bootstrap_b,
        bootstrap_seed=bootstrap_seed,
        metadata_extra={
            "a_sha256": a_sha,
            "b_sha256": b_sha,
            "gt_hash": gt_hash,
            "uxlc_anchored": True,
            "dropped_record_counts": {"a_side": dropped_a, "b_side": dropped_b},
        },
        gold_chunks_by_verse=gold_chunks_by_verse,
        uxlc_tier2_by_verse=uxlc_tier2_by_verse,
    )
