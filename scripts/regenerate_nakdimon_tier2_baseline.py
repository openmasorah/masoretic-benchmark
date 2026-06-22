#!/usr/bin/env python
"""Nakdimon tier-2 baseline for the v0.2.0 Devarim 4-folio benchmark.

This script measures Nakdimon's tier-2 (consonants + nikkud) Character Error
Rate against the UXLC tier-2 reference on the frozen 96-verse Devarim subset.
Nakdimon (elazarg/nakdimon, MIT, PyPI 0.1.2, MODEL_HASH 8fd7722b8002a690) is a
diacritization model; tier 2 is the diacritization task it was trained for.

Pipeline per verse:
1. Read UXLC tier-1 (consonants only) — the publicly-available standardized
   consonantal text for the verse. This is the input to Nakdimon.
2. Read UXLC tier-2 (consonants + nikkud) — the gold reference for the
   diacritized output.
3. Run ``nakdimon.diacritize`` on the tier-1 string.
4. Compute tier-2 CER between Nakdimon's output and the UXLC tier-2 gold,
   using the same scorer the IAA pipeline uses (cluster-aligned CER on the
   tier-2 view).
5. Macro-average per folio + overall; verse-bootstrap CIs (seed=0xBEEF,
   B=10000) for the overall number.

Output:
    nakdimon_tier2_baseline.json  (gitignored — regen artifact)

Comparable surface (in paper_iaa_results.json from the sibling regen): the
human-vs-UXLC tier-2 CER (``headline.tier2.cer_vs_uxlc``) is scored against
the SAME UXLC tier-2 reference and is the quantity directly comparable to this
Nakdimon number. Annotator-vs-annotator (human-pair) CER is a different,
non-comparable quantity and is deliberately not used here. Nakdimon is a
diacritization system, not OCR/HTR; this script makes no OCR-gap or
human-ceiling claim.

Environment: this script MUST run in a Python 3.11 venv with
``tensorflow==2.15.0`` and ``nakdimon==0.1.2`` installed — Nakdimon's
TF pin is incompatible with macOS-arm64 Python 3.12+. Build:

    python3.11 -m venv /tmp/venv-nakdimon311
    /tmp/venv-nakdimon311/bin/pip install -e ".[page-xml]" -e "./oracles[nakdimon]"

Then run:

    /tmp/venv-nakdimon311/bin/python scripts/regenerate_nakdimon_tier2_baseline.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from masoretic_eval.iaa.bootstrap import DEFAULT_B, DEFAULT_SEED, bootstrap_metric  # noqa: E402
from masoretic_eval.iaa.projection import load_projection  # noqa: E402
from masoretic_eval.metrics.cer import cluster_aligned_cer  # noqa: E402
from masoretic_eval.normalize import normalize_for_scoring  # noqa: E402
from masoretic_eval.strip import strip_for_tier2  # noqa: E402
from masoretic_eval.uxlc_loader import load_tier_strings  # noqa: E402

UXLC_XML = _REPO_ROOT / "baselines" / "tests" / "fixtures" / "_uxlc_cache" / "Deuteronomy.xml"
A_PROJ = _REPO_ROOT / "iaa_data" / "devarim_4folio" / "ginsberg_round0_positional.json"
OUTPUT = _REPO_ROOT / "nakdimon_tier2_baseline.json"


def _tier2_view(text: str) -> str:
    return strip_for_tier2(normalize_for_scoring(text))


def _macro_cer(per_verse: list[float]) -> float:
    if not per_verse:
        return float("nan")
    return sum(per_verse) / len(per_verse)


def main() -> int:
    try:
        from oracles.nakdimon_oss import MODEL_HASH, diacritize  # type: ignore[import-not-found]
    except ImportError as exc:
        sys.stderr.write(
            f"ERROR: Nakdimon is not importable from this Python ({sys.executable}).\n"
            f"  {exc}\n"
            "Build the py3.11 venv per the script docstring and re-run.\n"
        )
        return 2

    for p in (A_PROJ, UXLC_XML):
        if not p.exists():
            sys.stderr.write(f"ERROR: required input missing: {p}\n")
            return 2

    # Source the verse list from the published projection (canonical 96-verse
    # frozen scope; folio map is the manifest's). A-side is sufficient — both
    # sides agree on the verse_folio_map by construction.
    a_proj = load_projection(A_PROJ)
    verse_refs: list[str] = [v.verse_ref for v in a_proj.verses]
    verse_folio: dict[str, str] = {v.verse_ref: v.folio for v in a_proj.verses}

    uxlc_tier1 = load_tier_strings(UXLC_XML, tier=1)
    uxlc_tier2 = load_tier_strings(UXLC_XML, tier=2)
    assert isinstance(uxlc_tier1, dict) and isinstance(uxlc_tier2, dict)

    missing = [v for v in verse_refs if v not in uxlc_tier1 or v not in uxlc_tier2]
    if missing:
        sys.stderr.write(f"ERROR: UXLC missing {len(missing)} verses (first: {missing[0]!r})\n")
        return 2

    sys.stdout.write(f"Nakdimon MODEL_HASH: {MODEL_HASH}\n")
    sys.stdout.write(f"Diacritizing {len(verse_refs)} verses (first call pays TF compile)...\n")

    per_verse_cer: dict[str, float] = {}
    for i, vref in enumerate(verse_refs, start=1):
        cons = uxlc_tier1[vref]
        gold = uxlc_tier2[vref]
        prediction = diacritize(cons)
        # Score on the tier-2 strip view used elsewhere in the scorer.
        gold_view = _tier2_view(gold)
        pred_view = _tier2_view(prediction)
        per_verse_cer[vref] = cluster_aligned_cer(gold_view, pred_view).cer
        if i in (1, len(verse_refs)) or i % 20 == 0:
            sys.stdout.write(f"  [{i}/{len(verse_refs)}] {vref} CER={per_verse_cer[vref]:.4f}\n")

    # Per-folio macro CER + verse-bootstrap CI (verses within that folio).
    folios = sorted(set(verse_folio.values()))
    per_folio: dict[str, object] = {}
    for folio in folios:
        folio_payloads = [per_verse_cer[v] for v in verse_refs if verse_folio[v] == folio]
        ci = bootstrap_metric(folio_payloads, _macro_cer, b=DEFAULT_B, seed=DEFAULT_SEED)
        per_folio[folio] = {
            "point": ci.point,
            "ci_lower": ci.ci_lower,
            "ci_upper": ci.ci_upper,
            "ci_method": ci.ci_method,
            "n_verses": len(folio_payloads),
        }

    overall_payloads = [per_verse_cer[v] for v in verse_refs]
    overall_ci = bootstrap_metric(overall_payloads, _macro_cer, b=DEFAULT_B, seed=DEFAULT_SEED)
    overall = {
        "point": overall_ci.point,
        "ci_lower": overall_ci.ci_lower,
        "ci_upper": overall_ci.ci_upper,
        "ci_method": overall_ci.ci_method,
        "n_verses": len(overall_payloads),
    }

    # Comparable human-vs-UXLC numbers live in paper_iaa_results.json
    # (headline.tier2.cer_vs_uxlc) — scored against the same UXLC reference.
    out = {
        "baseline": "nakdimon_oss",
        "model_hash": MODEL_HASH,
        "tier": 2,
        "task": "diacritization",
        "input_source": "UXLC tier-1 consonants",
        "gold_source": "UXLC tier-2 consonants+nikkud",
        "scorer": "masoretic_eval.metrics.cer.cluster_aligned_cer on tier-2 strip view",
        "bootstrap_b": DEFAULT_B,
        "bootstrap_seed_hex": f"0x{DEFAULT_SEED:X}",
        "overall_cer": overall,
        "per_folio_cer": per_folio,
        "per_verse_cer": per_verse_cer,
        "comparison_note": (
            "Comparable surface: the human-vs-UXLC tier-2 CER "
            "(paper_iaa_results.json headline.tier2.cer_vs_uxlc) is scored "
            "against the same UXLC tier-2 reference. Annotator-vs-annotator "
            "(human-pair) CER is a different, non-comparable quantity. "
            "Nakdimon is a diacritization model, not OCR/HTR."
        ),
    }
    OUTPUT.write_text(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

    sys.stdout.write(f"\nwrote {OUTPUT}\n")
    sys.stdout.write(
        f"Nakdimon overall tier-2 CER vs UXLC: "
        f"{overall['point']:.4f} [{overall['ci_lower']:.4f}, {overall['ci_upper']:.4f}]\n"
    )
    sys.stdout.write(
        "Comparable human-vs-UXLC tier-2 CER: see "
        "paper_iaa_results.json headline.tier2.cer_vs_uxlc.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
