"""End-to-end smoke test: re-derive the published Devarim α cells.

Skipped by default because the Devarim round-0 .txt files are NOT in this
repo — they are CC-BY-4.0-eligible but live in a separate upstream landing
task. When the data lands, set ``MASORETIC_IAA_DATA_DIR=/path/to/dir`` and
this test verifies that ``compute_iaa()`` reproduces the falsification's α
values within 1e-4.

Expected files inside ``MASORETIC_IAA_DATA_DIR``:

* ``a_side.txt`` — A-side raw round-0 transcription.
* ``b_side.txt`` — B-side raw round-0 transcription.
* ``verse_folio_map.json`` — ``{"folios": {"F118B": ["Deut.32.1", ...], ...}}``.
* ``falsify_4cell_RESULTS.json`` — upstream pre-decision falsification
  result. Source of truth for the 4 published α values.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

import pytest

from masoretic_eval.iaa.compute import compute_iaa

DATA_DIR_ENV = "MASORETIC_IAA_DATA_DIR"


@pytest.mark.skipif(
    not os.environ.get(DATA_DIR_ENV),
    reason=f"{DATA_DIR_ENV} unset (Devarim round-0 .txt files not in this repo)",
)
def test_smoke_devarim_4folio_reproduces_published_alpha():
    data_dir = Path(os.environ[DATA_DIR_ENV])
    a_path = data_dir / "a_side.txt"
    b_path = data_dir / "b_side.txt"
    vfm_path = data_dir / "verse_folio_map.json"
    falsify_path = data_dir / "falsify_4cell_RESULTS.json"

    for p in (a_path, b_path, vfm_path, falsify_path):
        if not p.exists():
            pytest.skip(f"missing required data file: {p}")

    vfm_raw = json.loads(vfm_path.read_text(encoding="utf-8"))
    if isinstance(vfm_raw, dict) and "folios" in vfm_raw:
        verse_folio_map = [
            (v, folio) for folio, verses in vfm_raw["folios"].items() for v in verses
        ]
    else:
        verse_folio_map = [(v, f) for v, f in vfm_raw]

    # bootstrap_b=0 — point estimates only. Smoke test verifies the headline
    # numbers, not CI widths (which depend on the bootstrap sample size).
    result = compute_iaa(a_path, b_path, verse_folio_map, bootstrap_b=0)

    falsify = json.loads(falsify_path.read_text(encoding="utf-8"))
    cells = falsify["cells"]

    # 4-cell verification against published numbers (1e-4 per SPEC).
    assert math.isclose(
        result.tier4.alpha_full_canon.point, cells["A_canon"]["alpha"], abs_tol=1e-4
    )
    assert math.isclose(
        result.tier4.alpha_positive_canon.point,
        cells["B_canon"]["alpha"],
        abs_tol=1e-4,
    )
    assert math.isclose(result.tier4.alpha_full_raw.point, cells["A_raw"]["alpha"], abs_tol=1e-4)
    assert math.isclose(
        result.tier4.alpha_positive_raw.point,
        cells["B_raw"]["alpha"],
        abs_tol=1e-4,
    )
