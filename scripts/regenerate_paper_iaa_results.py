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
    load_projection,
)
from masoretic_eval.iaa.reproject import consonants_of, reproject_records  # noqa: E402
from masoretic_eval.iaa.stratify import stratify_tier4  # noqa: E402
from masoretic_eval.uxlc_loader import load_tier_strings  # noqa: E402

A_PROJ = _REPO_ROOT / "iaa_data" / "devarim_4folio" / "ginsberg_round0_positional.json"
B_PROJ = _REPO_ROOT / "iaa_data" / "devarim_4folio" / "moster_round0_positional.json"
GOLD_PROJ = _REPO_ROOT / "iaa_data" / "devarim_4folio" / "consensus_gold_positional.json"
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
    for p in (A_PROJ, B_PROJ, GOLD_PROJ, UXLC_XML):
        if not p.exists():
            sys.stderr.write(f"ERROR: required input missing: {p}\n")
            return 2

    uxlc_strings = load_tier_strings(UXLC_XML, tier=1)
    if not isinstance(uxlc_strings, dict):
        sys.stderr.write("ERROR: UXLC loader returned a non-dict tier-1 payload\n")
        return 2

    # A2a — consensus-gold chunks for the human-vs-reference CER decomposition.
    # The gold projection's per-verse chunk IS the reference text; tier 1/2/3
    # CER of each annotator's round-0 chunk against it (gold as reference) lands
    # in headline.tier{1,2,3}.cer_vs_gold.{a,b}.
    gold_proj = load_projection(GOLD_PROJ)
    gold_chunks_by_verse = {v.verse_ref: v.chunk for v in gold_proj.verses}

    headline = compute_iaa_uxlc_anchored_from_positional(
        A_PROJ,
        B_PROJ,
        uxlc_strings,
        bootstrap_b=DEFAULT_B,
        bootstrap_seed=DEFAULT_SEED,
        gold_chunks_by_verse=gold_chunks_by_verse,
    )
    per_anno = compute_iaa_from_positional(
        A_PROJ,
        B_PROJ,
        bootstrap_b=DEFAULT_B,
        bootstrap_seed=DEFAULT_SEED,
    )

    # Per-folio + Ha'azinu-vs-prose stratification (SF-1 from the v3 paper plan).
    # Computed on both anchoring frames so the paper can pick which to quote.
    a_proj = load_projection(A_PROJ)
    b_proj = load_projection(B_PROJ)
    verse_folio_map = [(v.verse_ref, v.folio) for v in a_proj.verses]
    a_recs_per_anno = {v.verse_ref: list(v.tier4_positional) for v in a_proj.verses}
    b_recs_per_anno = {v.verse_ref: list(v.tier4_positional) for v in b_proj.verses}
    n_cons_per_anno = {v.verse_ref: v.consonant_count for v in a_proj.verses}
    per_anno_strat = stratify_tier4(
        verse_folio_map, a_recs_per_anno, b_recs_per_anno, n_cons_per_anno
    )

    a_recs_uxlc: dict[str, list] = {}
    b_recs_uxlc: dict[str, list] = {}
    n_cons_uxlc: dict[str, int] = {}
    for a_v, b_v in zip(a_proj.verses, b_proj.verses, strict=True):
        uxlc_text = uxlc_strings[a_v.verse_ref]
        a_recs_uxlc[a_v.verse_ref] = reproject_records(
            list(a_v.tier4_positional), a_v.chunk, uxlc_text
        ).kept
        b_recs_uxlc[a_v.verse_ref] = reproject_records(
            list(b_v.tier4_positional), b_v.chunk, uxlc_text
        ).kept
        n_cons_uxlc[a_v.verse_ref] = len(consonants_of(uxlc_text))
    headline_strat = stratify_tier4(verse_folio_map, a_recs_uxlc, b_recs_uxlc, n_cons_uxlc)

    out: dict[str, Any] = {
        "headline": {
            **_to_dict(headline),
            "stratification": _to_dict(headline_strat),
        },
        "sensitivity": {
            "per_annotator": {
                **_to_dict(per_anno),
                "stratification": _to_dict(per_anno_strat),
            },
        },
        "regeneration": {
            "script": "scripts/regenerate_paper_iaa_results.py",
            "bootstrap_b": DEFAULT_B,
            "bootstrap_seed_hex": f"0x{DEFAULT_SEED:X}",
            "inputs": {
                "a_projection": str(A_PROJ.relative_to(_REPO_ROOT)),
                "b_projection": str(B_PROJ.relative_to(_REPO_ROOT)),
                "gold_projection": str(GOLD_PROJ.relative_to(_REPO_ROOT)),
                "uxlc_xml": str(UXLC_XML.relative_to(_REPO_ROOT)),
            },
            "notes": (
                "headline = UXLC-anchored tier-4 ordinals (FINDING 3 removed). "
                "sensitivity.per_annotator = legacy per-annotator-ordinal anchoring. "
                "Bootstrap CIs use the FINDING 1 multiplicity-safe aggregator "
                "(commit-or-later than the matcher-multiplicity-fix in this branch). "
                "headline.tier{1,2,3}.cer_vs_gold.{a,b} (A2a) = each annotator's "
                "round-0 CER against the consensus gold (gold as CER reference), "
                "structurally comparable to the Nakdimon-vs-UXLC tier-2 baseline."
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
    # A2a — human-vs-gold tier-2 CER (the new Nakdimon comparison baseline).
    for tier in (1, 2, 3):
        tcr = getattr(headline, f"tier{tier}")
        if tcr.cer_vs_gold is None:
            continue
        a = tcr.cer_vs_gold["a"].cer_overall
        b = tcr.cer_vs_gold["b"].cer_overall
        sys.stdout.write(
            f"A2a tier{tier} cer_vs_gold: "
            f"A={a.point:.4f} [{a.ci_lower:.4f}, {a.ci_upper:.4f}]  "
            f"B={b.point:.4f} [{b.ci_lower:.4f}, {b.ci_upper:.4f}]\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
