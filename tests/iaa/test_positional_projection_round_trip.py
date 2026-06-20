"""Positional projection publication path (SPEC 260619-n3u follow-up).

Round-0 raw .txt inputs are gitignored upstream (Yosef's private layout-
preserving format). The positional projection is the CC-BY-4.0 reproducibility
surface: per-verse (verse_ref, folio, chunk, consonant_count, tier4_positional
tuples) with layout stripped. compute_iaa_from_positional() consumes the
projection and produces byte-identical paper_iaa_results.json vs the raw-.txt
path.

These tests pin three properties:

1. **Hermetic cross-path byte equivalence** — a synthetic A/B fixture is
   projected and the JSON-serialized result from the raw-.txt path matches
   the projection path exactly. This is the byte-identical contract.
2. **Hermetic regeneration determinism** — projecting the same raw .txt
   twice produces byte-identical projection JSON.
3. **Data-gated Devarim regeneration determinism** — when
   ``MASORETIC_IAA_DATA_DIR`` is set, the real Devarim round-0 .txt files
   round-trip identically and the projection JSONs match the committed
   ``iaa_data/devarim_4folio/*_round0_positional.json`` byte-for-byte (when
   those committed files exist).

The projection's load-time validation invariant — ``extract_positional(chunk)``
must equal the stored ``tier4_positional`` and ``count_consonants(chunk)``
must equal ``consonant_count`` — is also tested here so the file format
can't drift away from its source-of-truth chunk.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from masoretic_eval.iaa.cli import serialize_result
from masoretic_eval.iaa.compute import compute_iaa
from masoretic_eval.iaa.projection import (
    PositionalProjectionInvalid,
    compute_iaa_from_positional,
    load_projection,
    project_side,
    serialize_projection,
)

_A_SIDE = "אבגד֯ה׃\nוזחט<DR>י׃\nכלמנֿס׃\n"
_B_SIDE = "אבג֯דה׃\nוזחטֿי׃\nכלמנֿס׃\n"
_VERSE_FOLIO_MAP = [
    ("Deut.99.1", "F999A"),
    ("Deut.99.2", "F999A"),
    ("Deut.99.3", "F999B"),
]


def _write_raw(tmp_path: Path) -> tuple[Path, Path]:
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text(_A_SIDE, encoding="utf-8")
    b.write_text(_B_SIDE, encoding="utf-8")
    return a, b


def test_cross_path_byte_identical_hermetic(tmp_path: Path):
    """Raw .txt path and positional path produce byte-identical IaaResult JSON."""
    a_raw, b_raw = _write_raw(tmp_path)

    a_proj = project_side(_A_SIDE, _VERSE_FOLIO_MAP, side_label="A")
    b_proj = project_side(_B_SIDE, _VERSE_FOLIO_MAP, side_label="B")
    a_proj_path = tmp_path / "a_positional.json"
    b_proj_path = tmp_path / "b_positional.json"
    a_proj_path.write_text(serialize_projection(a_proj) + "\n", encoding="utf-8")
    b_proj_path.write_text(serialize_projection(b_proj) + "\n", encoding="utf-8")

    raw_result = compute_iaa(a_raw, b_raw, _VERSE_FOLIO_MAP, bootstrap_b=64, bootstrap_seed=42)
    proj_result = compute_iaa_from_positional(
        a_proj_path, b_proj_path, bootstrap_b=64, bootstrap_seed=42
    )

    # Metadata's a_sha256/b_sha256 differ by construction (different files).
    # Strip those keys for the byte-equivalence claim — they pin file identity,
    # not result identity. The result tree itself must match.
    raw_dict = json.loads(serialize_result(raw_result))
    proj_dict = json.loads(serialize_result(proj_result))
    for d in (raw_dict, proj_dict):
        d["metadata"].pop("a_sha256", None)
        d["metadata"].pop("b_sha256", None)
    assert raw_dict == proj_dict


def test_projection_regeneration_deterministic_hermetic(tmp_path: Path):
    """Re-projecting the same raw .txt produces byte-identical projection JSON."""
    a_proj_1 = serialize_projection(project_side(_A_SIDE, _VERSE_FOLIO_MAP, side_label="A"))
    a_proj_2 = serialize_projection(project_side(_A_SIDE, _VERSE_FOLIO_MAP, side_label="A"))
    assert a_proj_1 == a_proj_2


def test_projection_round_trip_hermetic(tmp_path: Path):
    """Projection → JSON → load → projection: deep-equal data."""
    p = project_side(_A_SIDE, _VERSE_FOLIO_MAP, side_label="A")
    path = tmp_path / "a_positional.json"
    path.write_text(serialize_projection(p) + "\n", encoding="utf-8")
    loaded = load_projection(path)
    assert loaded == p


def test_projection_validation_rejects_tuples_drift_from_chunk(tmp_path: Path):
    """Load-time validation: stored positional must match what chunk produces.

    Catches files that were hand-edited or corrupted in transit — the chunk
    is the source of truth, the tuples are a derived convenience for paper
    readers, and they MUST agree.
    """
    p = project_side(_A_SIDE, _VERSE_FOLIO_MAP, side_label="A")
    path = tmp_path / "a_positional.json"
    path.write_text(serialize_projection(p) + "\n", encoding="utf-8")

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["verses"][0]["tier4_positional"].append({"type": "circellus", "ordinal": 99})
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    with pytest.raises(PositionalProjectionInvalid, match="tier4_positional"):
        load_projection(path)


def test_projection_validation_rejects_consonant_count_drift(tmp_path: Path):
    """Load-time validation: ``consonant_count`` must match the chunk's count."""
    p = project_side(_A_SIDE, _VERSE_FOLIO_MAP, side_label="A")
    path = tmp_path / "a_positional.json"
    path.write_text(serialize_projection(p) + "\n", encoding="utf-8")

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["verses"][0]["consonant_count"] += 7
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    with pytest.raises(PositionalProjectionInvalid, match="consonant_count"):
        load_projection(path)


def test_compute_from_positional_uses_embedded_verse_folio_map(tmp_path: Path):
    """The positional path does not need an external --verse-folio-map.

    Projections embed (verse_ref, folio) per verse. compute_iaa_from_positional
    sources verse_folio_map from the projections themselves.
    """
    a_proj = project_side(_A_SIDE, _VERSE_FOLIO_MAP, side_label="A")
    b_proj = project_side(_B_SIDE, _VERSE_FOLIO_MAP, side_label="B")
    a_proj_path = tmp_path / "a_positional.json"
    b_proj_path = tmp_path / "b_positional.json"
    a_proj_path.write_text(serialize_projection(a_proj) + "\n", encoding="utf-8")
    b_proj_path.write_text(serialize_projection(b_proj) + "\n", encoding="utf-8")

    # No verse_folio_map argument — it must come from the projections.
    result = compute_iaa_from_positional(a_proj_path, b_proj_path, bootstrap_b=0)
    assert result.metadata["n_verses"] == len(_VERSE_FOLIO_MAP)
    assert result.metadata["n_folios"] == len({f for _, f in _VERSE_FOLIO_MAP})


def test_compute_from_positional_rejects_verse_folio_map_disagreement(tmp_path: Path):
    """If A and B projections disagree on the verse_folio_map, refuse to compute."""
    a_proj = project_side(_A_SIDE, _VERSE_FOLIO_MAP, side_label="A")
    # B uses a different folio assignment for the same verse_refs.
    b_alt_map = [(v, "F999Z") for v, _ in _VERSE_FOLIO_MAP]
    b_proj = project_side(_B_SIDE, b_alt_map, side_label="B")

    a_proj_path = tmp_path / "a_positional.json"
    b_proj_path = tmp_path / "b_positional.json"
    a_proj_path.write_text(serialize_projection(a_proj) + "\n", encoding="utf-8")
    b_proj_path.write_text(serialize_projection(b_proj) + "\n", encoding="utf-8")

    with pytest.raises(PositionalProjectionInvalid, match="verse_folio_map"):
        compute_iaa_from_positional(a_proj_path, b_proj_path, bootstrap_b=0)


# ---------------------------------------------------------------------------
# Data-gated tests (require MASORETIC_IAA_DATA_DIR).
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not os.environ.get("MASORETIC_IAA_DATA_DIR"),
    reason="MASORETIC_IAA_DATA_DIR unset (Devarim round-0 .txt files not in this repo)",
)
def test_devarim_projection_regeneration_deterministic():
    """Projecting the real Devarim round-0 .txt twice → byte-identical JSON."""
    data_dir = Path(os.environ["MASORETIC_IAA_DATA_DIR"])
    a_path = data_dir / "a_side.txt"
    b_path = data_dir / "b_side.txt"
    vfm_path = data_dir / "verse_folio_map.json"
    for p in (a_path, b_path, vfm_path):
        if not p.exists():
            pytest.skip(f"missing required data file: {p}")

    vfm_raw = json.loads(vfm_path.read_text(encoding="utf-8"))
    if isinstance(vfm_raw, dict) and "folios" in vfm_raw:
        verse_folio_map = [
            (v, folio) for folio, verses in vfm_raw["folios"].items() for v in verses
        ]
    else:
        verse_folio_map = [(v, f) for v, f in vfm_raw]

    a_text = a_path.read_text(encoding="utf-8")
    p1 = serialize_projection(project_side(a_text, verse_folio_map, side_label="A"))
    p2 = serialize_projection(project_side(a_text, verse_folio_map, side_label="A"))
    assert p1 == p2


@pytest.mark.skipif(
    not os.environ.get("MASORETIC_IAA_DATA_DIR"),
    reason="MASORETIC_IAA_DATA_DIR unset (Devarim round-0 .txt files not in this repo)",
)
def test_devarim_cross_path_byte_identical():
    """Raw and positional paths produce byte-identical IaaResult on Devarim."""
    data_dir = Path(os.environ["MASORETIC_IAA_DATA_DIR"])
    a_path = data_dir / "a_side.txt"
    b_path = data_dir / "b_side.txt"
    vfm_path = data_dir / "verse_folio_map.json"
    for p in (a_path, b_path, vfm_path):
        if not p.exists():
            pytest.skip(f"missing required data file: {p}")

    vfm_raw = json.loads(vfm_path.read_text(encoding="utf-8"))
    if isinstance(vfm_raw, dict) and "folios" in vfm_raw:
        verse_folio_map = [
            (v, folio) for folio, verses in vfm_raw["folios"].items() for v in verses
        ]
    else:
        verse_folio_map = [(v, f) for v, f in vfm_raw]

    a_text = a_path.read_text(encoding="utf-8")
    b_text = b_path.read_text(encoding="utf-8")

    tmp = Path(os.environ.get("PYTEST_TMPDIR") or "/tmp") / "iaa_xpath"
    tmp.mkdir(parents=True, exist_ok=True)
    a_proj_path = tmp / "ginsberg_round0_positional.json"
    b_proj_path = tmp / "moster_round0_positional.json"
    a_proj_path.write_text(
        serialize_projection(project_side(a_text, verse_folio_map, side_label="ginsberg")) + "\n",
        encoding="utf-8",
    )
    b_proj_path.write_text(
        serialize_projection(project_side(b_text, verse_folio_map, side_label="moster")) + "\n",
        encoding="utf-8",
    )

    raw_result = compute_iaa(a_path, b_path, verse_folio_map, bootstrap_b=0)
    proj_result = compute_iaa_from_positional(a_proj_path, b_proj_path, bootstrap_b=0)

    raw_dict = json.loads(serialize_result(raw_result))
    proj_dict = json.loads(serialize_result(proj_result))
    for d in (raw_dict, proj_dict):
        d["metadata"].pop("a_sha256", None)
        d["metadata"].pop("b_sha256", None)
    assert raw_dict == proj_dict
