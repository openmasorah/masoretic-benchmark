#!/usr/bin/env python
"""Regenerate paper_iaa_results.json from the corrected pipeline.

Produces:

* ``headline`` block — UXLC-anchored tier-4 metrics + tier 1/2/3 CER.
  Removes the FINDING 3 (per-annotator-ordinal tier-1 propagation)
  contamination from the paper's §6.1 anchor-ambiguity statistic.
* ``sensitivity.per_annotator`` block — same metrics computed against
  the legacy per-annotator-ordinal anchoring. Lets the paper bound the
  FINDING 3 contamination empirically and lets a reader without UXLC
  reproduce the per-annotator numbers from the public positional JSONs
  alone.
* ``metadata.regeneration`` — provenance + commit-time fingerprints.

Inputs:

* ``iaa_data/devarim_4folio/{ginsberg,moster}_round0_positional.json``
  (committed; CC-BY-4.0).
* ``baselines/tests/fixtures/_uxlc_cache/Deuteronomy.xml`` (CC0; UXLC
  2.5 cache, used for the UXLC backbone tier-1 strings). The cache is
  gitignored — fetch the file from tanach.us (UXLC 2.5) into that path
  before running this script. The paper repo's published-numbers
  reproduction instructions handle this prerequisite.

Output: ``paper_iaa_results.json`` at the repo root (gitignored — a
regen artifact, not a committed source of truth; the contract for
"published numbers" is in the paper repo). Re-running this script with
the same inputs + same seed produces a byte-identical file.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from masoretic_eval.iaa.bootstrap import DEFAULT_B, DEFAULT_SEED  # noqa: E402
from masoretic_eval.iaa.projection import (  # noqa: E402
    compute_iaa_from_positional,
    compute_iaa_uxlc_anchored_from_positional,
)
from masoretic_eval.uxlc_loader import load_tier_strings  # noqa: E402

A_PROJ = _REPO_ROOT / "iaa_data" / "devarim_4folio" / "ginsberg_round0_positional.json"
B_PROJ = _REPO_ROOT / "iaa_data" / "devarim_4folio" / "moster_round0_positional.json"
UXLC_XML = _REPO_ROOT / "baselines" / "tests" / "fixtures" / "_uxlc_cache" / "Deuteronomy.xml"
OUTPUT = _REPO_ROOT / "paper_iaa_results.json"


def _to_dict(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {k: _to_dict(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {k: _to_dict(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_dict(v) for v in value]
    return value


def main() -> int:
    for p in (A_PROJ, B_PROJ, UXLC_XML):
        if not p.exists():
            sys.stderr.write(f"ERROR: required input missing: {p}\n")
            return 2

    uxlc_strings = load_tier_strings(UXLC_XML, tier=1)
    if not isinstance(uxlc_strings, dict):
        sys.stderr.write("ERROR: UXLC loader returned a non-dict tier-1 payload\n")
        return 2

    headline = compute_iaa_uxlc_anchored_from_positional(
        A_PROJ,
        B_PROJ,
        uxlc_strings,
        bootstrap_b=DEFAULT_B,
        bootstrap_seed=DEFAULT_SEED,
    )
    per_anno = compute_iaa_from_positional(
        A_PROJ,
        B_PROJ,
        bootstrap_b=DEFAULT_B,
        bootstrap_seed=DEFAULT_SEED,
    )

    out: dict[str, Any] = {
        "headline": _to_dict(headline),
        "sensitivity": {
            "per_annotator": _to_dict(per_anno),
        },
        "regeneration": {
            "script": "scripts/regenerate_paper_iaa_results.py",
            "bootstrap_b": DEFAULT_B,
            "bootstrap_seed_hex": f"0x{DEFAULT_SEED:X}",
            "inputs": {
                "a_projection": str(A_PROJ.relative_to(_REPO_ROOT)),
                "b_projection": str(B_PROJ.relative_to(_REPO_ROOT)),
                "uxlc_xml": str(UXLC_XML.relative_to(_REPO_ROOT)),
            },
            "notes": (
                "headline = UXLC-anchored tier-4 ordinals (FINDING 3 removed). "
                "sensitivity.per_annotator = legacy per-annotator-ordinal anchoring. "
                "Bootstrap CIs use the FINDING 1 multiplicity-safe aggregator "
                "(commit-or-later than the matcher-multiplicity-fix in this branch)."
            ),
        },
    }

    OUTPUT.write_text(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    sys.stdout.write(f"wrote {OUTPUT}\n")
    sys.stdout.write(
        f"headline F1 exact: {headline.tier4.f1_exact.point:.4f} "
        f"[{headline.tier4.f1_exact.ci_lower:.4f}, "
        f"{headline.tier4.f1_exact.ci_upper:.4f}]\n"
    )
    sys.stdout.write(
        f"sensitivity (per-annotator) F1 exact: {per_anno.tier4.f1_exact.point:.4f} "
        f"[{per_anno.tier4.f1_exact.ci_lower:.4f}, "
        f"{per_anno.tier4.f1_exact.ci_upper:.4f}]\n"
    )
    dropped = headline.metadata.get("dropped_record_counts", {})
    sys.stdout.write(
        f"UXLC reprojection drops: a_side={dropped.get('a_side')}, b_side={dropped.get('b_side')}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
