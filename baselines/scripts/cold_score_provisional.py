"""Provisional cold-score driver — EVALUATION_PROTOCOL.md steps 3-11, tier-1.

SINGLE-ANNOTATOR / PRE-ADJUDICATION / PROVISIONAL. Computes per-folio tier-1
(and diagnostic 2/3, tier-4 F1 when present) scores of a baseline prediction
against a gt_adapter golden, by building the {text, metamarks} scorer inputs the
shipped masoretic_eval.Scorer consumes.

This is the committed, reproducible form of the phase 03.1-05 `method1_whole_folio`
spike. `validate` mode reproduces the published F118B tier-1 CERs as a self-test.

Usage (run by path; not an importable package module):
  python baselines/scripts/cold_score_provisional.py validate
  python baselines/scripts/cold_score_provisional.py score \
      --folio-id leningrad_devarim_F119A_fixture \
      --golden <iaa_folio_..._gt_adapter_golden.json> \
      --baseline biblia_kraken \
      --pred results/biblia_kraken/leningrad_devarim_F119A_fixture.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from masoretic_eval.composite import Scorer

# RETRACTED 2026-07-10, kept only as a regression pin for the historical method.
#
# These were the F118B tier-1 CERs published in results/scores/ before that tree was
# withdrawn from v0.1. They are NOT the benchmark's numbers and must not be cited.
# They score Kraken's 109 segmented lines -- which include the masorah magna/parva
# apparatus -- against 26 physical lines of main-text GT, ordered by line_id because
# every bbox is [0,0,0,0]. The ranking they produce is inverted: biblia_kraken appears
# weakest here, while ROI-restricted main-text scoring puts it strongest on consonants.
#
# They remain here so that a change to the whole-folio code path still trips a diff.
F118B_EXPECTED_TIER1_CER = {
    "biblia_kraken": 0.9282,
    "llm_vision": 0.6613,
    "biblia_nakdimon": 0.6106,
    "biblia_char_menaked": 0.6106,
}


def _reading_order(lines: list[dict]) -> list[dict]:
    """Sort prediction lines into Hebrew reading order (EVALUATION_PROTOCOL step 3):
    (bbox.y_min asc, bbox.x_max desc). Fall back to line_id order when every bbox
    is the degenerate [0,0,0,0] (bboxes absent / degraded baseline)."""
    has_bbox = any(any(v != 0 for v in (ln.get("bbox") or [0, 0, 0, 0])) for ln in lines)
    if has_bbox:
        return sorted(lines, key=lambda ln: (ln["bbox"][1], -ln["bbox"][2]))
    return sorted(lines, key=lambda ln: ln.get("line_id", ""))


def _gt_input(folio_id: str, golden: dict) -> dict:
    """GT scorer input: space-join golden lines (step 4), no metamarks (tier-1)."""
    lines = golden.get("lines") or golden.get("text")
    return {"folio_id": folio_id, "text": " ".join(lines), "metamarks": []}


def _pred_input(folio_id: str, pred: dict) -> dict:
    """Prediction scorer input: space-join `tier1` over reading-ordered lines
    (step 5), no metamarks (tier-1)."""
    ordered = _reading_order(pred["lines"])
    return {
        "folio_id": folio_id,
        "text": " ".join(ln.get("tier1", "") for ln in ordered),
        "metamarks": [],
    }


def score_one(folio_id: str, golden: dict, pred: dict) -> dict:
    """Return {tier1_cer, tier2_cer, tier3_cer, tier4_f1, edits, denominator}."""
    gt = _gt_input(folio_id, golden)
    pr = _pred_input(folio_id, pred)
    result = Scorer.from_config("v0.1").score(pred=pr, ground_truth=gt)
    t1 = result.tiers["tier1"]
    t2 = result.tiers["tier2"]
    t3 = result.tiers["tier3"]
    t4 = result.tiers["tier4"]
    return {
        "tier1_cer": round(t1.cer, 4),
        "tier2_cer": round(t2.cer, 4),
        "tier3_cer": round(t3.cer, 4),
        "tier4_f1": getattr(t4, "f1", None),
        "tier1_edits": t1.edits,
        "tier1_denominator": t1.denominator,
    }


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def cmd_validate(_args) -> int:
    """Self-test: reproduce published F118B tier-1 CERs with Ben's-hand golden.

    Pinned to a FROZEN copy of the Ben's-hand golden (_selftest_f118b_ben_golden.json)
    so this driver-regression test survives the live F118B golden being switched to
    Moster's B-side (quick 260612-prz). It tests the driver's arithmetic, not the
    current golden."""
    fid = "leningrad_devarim_F118B_fixture"
    golden = _load(str(Path(__file__).resolve().parent / "_selftest_f118b_ben_golden.json"))
    repo = Path(__file__).resolve().parents[2]
    ok = True
    for bl, expected in F118B_EXPECTED_TIER1_CER.items():
        pred = _load(str(repo / f"results/{bl}/{fid}.json"))
        got = score_one(fid, golden, pred)["tier1_cer"]
        match = abs(got - expected) < 5e-4
        ok = ok and match
        print(f"{'OK ' if match else 'FAIL'} {bl}: got={got} expected={expected}")
    print("VALIDATION", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


def cmd_score(args) -> int:
    folio = args.folio_id
    golden = _load(args.golden)
    pred = _load(args.pred)
    out = score_one(folio, golden, pred)
    out["baseline_id"] = args.baseline
    out["folio_id"] = folio
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="cold_score_provisional")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate")
    sc = sub.add_parser("score")
    sc.add_argument("--folio-id", required=True)
    sc.add_argument("--golden", required=True)
    sc.add_argument("--baseline", required=True)
    sc.add_argument("--pred", required=True)
    args = p.parse_args(argv)
    return {"validate": cmd_validate, "score": cmd_score}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
