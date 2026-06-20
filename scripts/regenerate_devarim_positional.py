#!/usr/bin/env python
"""Regenerate the CC-BY-4.0 Devarim 4-folio positional projection JSONs.

Reads the private round-0 .txt files from ``MASORETIC_IAA_DATA_DIR``,
projects each side via :func:`masoretic_eval.iaa.project_side`, and writes
``iaa_data/devarim_4folio/{ginsberg,moster}_round0_positional.json``.
Re-loads both to verify the load-time invariants (chunk → tuples,
chunk → consonant_count) hold.

This script is hand-run by the operator when the raw .txt files change. The
deterministic guarantee — same input bytes → byte-identical projection JSON
— is what makes the resulting JSONs citation-stable.

Environment:

* ``MASORETIC_IAA_DATA_DIR`` (required): directory containing
  ``a_side.txt``, ``b_side.txt``, and ``verse_folio_map.json``.

The output directory ``iaa_data/devarim_4folio/`` is expected to exist
relative to the repo root.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Allow `python scripts/regenerate_devarim_positional.py` (where sys.path[0] is
# the script dir, not the repo root). When the package is installed via
# `pip install -e .` this insert is a no-op.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from masoretic_eval.iaa.projection import (  # noqa: E402
    load_projection,
    project_side,
    serialize_projection,
)


def _load_verse_folio_map(path: Path) -> list[tuple[str, str]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return [(v, f) for v, f in raw]
    if isinstance(raw, dict) and "folios" in raw:
        pairs: list[tuple[str, str]] = []
        for folio, verses in raw["folios"].items():
            for v in verses:
                pairs.append((v, folio))
        return pairs
    raise ValueError(f"unrecognised verse_folio_map shape in {path}")


def main() -> int:
    data_dir_env = os.environ.get("MASORETIC_IAA_DATA_DIR")
    if not data_dir_env:
        sys.stderr.write(
            "ERROR: MASORETIC_IAA_DATA_DIR is unset. Set it to the directory\n"
            "containing a_side.txt, b_side.txt, and verse_folio_map.json.\n"
        )
        return 2
    data_dir = Path(data_dir_env)
    a_path = data_dir / "a_side.txt"
    b_path = data_dir / "b_side.txt"
    vfm_path = data_dir / "verse_folio_map.json"
    for p in (a_path, b_path, vfm_path):
        if not p.exists():
            sys.stderr.write(f"ERROR: missing input file: {p}\n")
            return 2

    repo_root = Path(__file__).resolve().parent.parent
    out_dir = repo_root / "iaa_data" / "devarim_4folio"
    out_dir.mkdir(parents=True, exist_ok=True)

    verse_folio_map = _load_verse_folio_map(vfm_path)

    pairs = (
        ("ginsberg", a_path, out_dir / "ginsberg_round0_positional.json"),
        ("moster", b_path, out_dir / "moster_round0_positional.json"),
    )
    for label, src, dest in pairs:
        text = src.read_text(encoding="utf-8")
        projection = project_side(text, verse_folio_map, side_label=label)
        dest.write_text(serialize_projection(projection) + "\n", encoding="utf-8")
        # Round-trip: validate the file we just wrote loads + passes
        # source-of-truth invariants. Catches local FS/encoding surprises.
        load_projection(dest)
        sys.stdout.write(f"wrote {dest}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
