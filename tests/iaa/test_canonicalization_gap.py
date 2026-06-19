"""raw α vs canon α gap.

Two modes:

* **Hermetic (always runs):** A synthetic 2-verse fixture where one side
  uses `double_rafe` and the other uses plain `rafe`. With raw codes those
  count as disagreement; with canon codes (`double_rafe` → `rafe`) the
  disagreement disappears. The test verifies the gap exists and has the
  expected sign — direct evidence that canonicalization is doing what the
  SPEC says.

* **Falsification-data (skipif `MASORETIC_IAA_DATA_DIR` unset):** Re-derives
  the gap from the upstream `falsify_4cell_RESULTS.json` and verifies it
  matches the published value to 1e-4. Skipped by default because the
  Devarim round-0 .txt files are NOT in this repo (separate upstream
  landing task).
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

import pytest

from masoretic_eval.iaa.alpha import (
    krippendorff_alpha_nominal,
    units_per_verse,
)
from masoretic_eval.iaa.compute import compute_iaa
from masoretic_eval.iaa.parse import Tier4Record


def test_canon_collapses_double_rafe_disagreement():
    """Synthetic: A uses ``double_rafe``, B uses ``rafe`` — raw disagrees, canon agrees."""
    a_records = [Tier4Record("double_rafe", "v", 3)]
    b_records = [Tier4Record("rafe", "v", 3)]

    # n_cons = 5: one marked ordinal + four `none`-on-both ordinals.
    units_raw = units_per_verse(a_records, b_records, 5, "v", canonicalize=False)
    units_canon = units_per_verse(a_records, b_records, 5, "v", canonicalize=True)

    # Raw: ord 3 is ("double_rafe", "rafe") — disagreement.
    assert ("double_rafe", "rafe") in units_raw
    # Canon: ord 3 is ("rafe", "rafe") — agreement.
    assert ("rafe", "rafe") in units_canon

    alpha_raw = krippendorff_alpha_nominal(units_raw)
    alpha_canon = krippendorff_alpha_nominal(units_canon)
    # Canon must score strictly higher (the disagreement was folded away).
    assert alpha_canon > alpha_raw


@pytest.mark.skipif(
    not os.environ.get("MASORETIC_IAA_DATA_DIR"),
    reason="MASORETIC_IAA_DATA_DIR unset (Devarim round-0 .txt files not in this repo)",
)
def test_devarim_canon_gap_matches_falsification():
    """Smoke: re-derive the canon-gap from the upstream falsification.

    Requires:
    * ``MASORETIC_IAA_DATA_DIR/a_side.txt``
    * ``MASORETIC_IAA_DATA_DIR/b_side.txt``
    * ``MASORETIC_IAA_DATA_DIR/verse_folio_map.json``
    * ``MASORETIC_IAA_DATA_DIR/falsify_4cell_RESULTS.json``

    Verifies that the gap ``α_*_canon - α_*_raw`` matches the published
    falsification numbers within 1e-4 (both A and B universes).
    """
    data_dir = Path(os.environ["MASORETIC_IAA_DATA_DIR"])
    falsify_path = data_dir / "falsify_4cell_RESULTS.json"
    if not falsify_path.exists():
        pytest.skip(f"falsify_4cell_RESULTS.json not at {falsify_path}")

    a_path = data_dir / "a_side.txt"
    b_path = data_dir / "b_side.txt"
    vfm_path = data_dir / "verse_folio_map.json"
    if not (a_path.exists() and b_path.exists() and vfm_path.exists()):
        pytest.skip("a_side/b_side/verse_folio_map files missing in data dir")

    vfm_raw = json.loads(vfm_path.read_text(encoding="utf-8"))
    if isinstance(vfm_raw, dict) and "folios" in vfm_raw:
        verse_folio_map = [
            (v, folio) for folio, verses in vfm_raw["folios"].items() for v in verses
        ]
    else:
        verse_folio_map = [(v, f) for v, f in vfm_raw]

    result = compute_iaa(
        a_path, b_path, verse_folio_map, bootstrap_b=0
    )  # bootstrap_b=0 skips CIs; we only need point estimates here.
    falsify = json.loads(falsify_path.read_text(encoding="utf-8"))
    cells = falsify["cells"]

    expected_a = cells["A_canon"]["alpha"] - cells["A_raw"]["alpha"]
    expected_b = cells["B_canon"]["alpha"] - cells["B_raw"]["alpha"]
    got_a = result.tier4.alpha_full_canon.point - result.tier4.alpha_full_raw.point
    got_b = result.tier4.alpha_positive_canon.point - result.tier4.alpha_positive_raw.point
    assert math.isclose(got_a, expected_a, abs_tol=1e-4), (got_a, expected_a)
    assert math.isclose(got_b, expected_b, abs_tol=1e-4), (got_b, expected_b)
