#!/usr/bin/env python
"""Rafe text-rule tier-4 baseline (BL-05) for the v0.2.0 Devarim 4-folio benchmark.

Measures how far a parameter-free linguistic rule reproduces the Leningrad
scribe's actual rafe placement. The rule (``masoretic_eval.metrics.rafe_rule``):
predict a rafe on every begadkefat consonant that lacks a dagesh. Features
(consonants + dagesh) are read from the adjudicated consensus transcription, so
this is an *oracle-text* baseline — it consumes perfect tier-1/tier-2 and asks
only how discriminative the tier-4 rafe axis is under a deterministic rule. It
is NOT an end-to-end image->tier-4 system; end-to-end tier-4 remains open.

Pipeline per verse (all inputs public, CC-BY-4.0):
1. Read the consensus ``chunk`` (vocalized+accented text) and its
   ``tier4_positional`` records from ``iaa_data/devarim_4folio/
   consensus_gold_positional.json``.
2. Predict rafe ordinals from the chunk via the begadkefat / no-dagesh rule.
3. Score predictions against the consensus rafe records (double_rafe
   canonicalized to rafe) with the SAME matcher the IAA tier-4 panel uses
   (``masoretic_eval.iaa.f1``), exact (tolerance=0) and ±1.
4. Pool confusion counts (micro-average) overall, per folio, and on the
   Ha'azinu-vs-prose split; verse-bootstrap CI (seed=0xBEEF, B=10000) for the
   overall F1.

Two hard validation gates (fail loudly, never soften):
* every verse's rule-walk consonant count equals the shipped ``consonant_count``
  (ordinal-contract alignment);
* every gold rafe ordinal lands on a real consonant, and none carries a dagesh
  (the rule's dagesh assumption is consistent with the gold).

Output:
    rafe_tier4_baseline.json  (gitignored — regen artifact)

Note on the private spike: spike 003 (private, not in this public repo) reported
the same rule against Moster's pre-adjudication round-0 rafe set. This public
regeneration scores against the *adjudicated consensus* — the paper's reference
— and is the number of record. A learned-letter-set LOFO variant exists in that
spike and underperforms the a-priori rule (tiny-n learning generalizes worse
than the linguistic rule); the a-priori rule is reported here precisely because
it is parameter-free — no folio-selection, no forking path.

    python scripts/regenerate_rafe_tier4_baseline.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from masoretic_eval.iaa.bootstrap import DEFAULT_B, DEFAULT_SEED, bootstrap_metric  # noqa: E402
from masoretic_eval.iaa.f1 import Detection, detections_from_records  # noqa: E402
from masoretic_eval.iaa.parse import Tier4Record  # noqa: E402
from masoretic_eval.iaa.stratify import _haazinu_subset  # noqa: E402
from masoretic_eval.metrics.rafe_rule import (  # noqa: E402
    BEGADKEFAT,
    parse_consonants,
    pooled_rafe_f1,
    predict_rafe,
)

CONSENSUS = _REPO_ROOT / "iaa_data" / "devarim_4folio" / "consensus_gold_positional.json"
OUTPUT = _REPO_ROOT / "rafe_tier4_baseline.json"

Payload = tuple[list[Detection], list[Detection]]


def _validate_and_build(
    verses: list[dict],
) -> tuple[dict[str, Payload], dict[str, str]]:
    """Return ``{verse_ref: (gold_dets, pred_dets)}`` + verse->folio, gates enforced."""
    payloads: dict[str, Payload] = {}
    verse_folio: dict[str, str] = {}
    rafe_gold = rafe_off_consonant = rafe_with_dagesh = 0
    for v in verses:
        vref = v["verse_ref"]
        chunk = v["chunk"]
        verse_folio[vref] = v["folio"]
        cons = parse_consonants(chunk)  # asserts count vs count_consonants
        # GATE 1: ordinal-contract alignment against the shipped count.
        if len(cons) != v["consonant_count"]:
            raise AssertionError(
                f"{vref}: rule-walk counted {len(cons)} consonants, "
                f"shipped consonant_count={v['consonant_count']}"
            )
        letter_at = {c.ordinal: c.letter for c in cons}
        dagesh_at = {c.ordinal: c.dagesh for c in cons}
        # GATE 2: gold rafe lands on a consonant and never carries a dagesh.
        for m in v["tier4_positional"]:
            if m["type"] in ("rafe", "double_rafe"):
                rafe_gold += 1
                if m["ordinal"] not in letter_at:
                    rafe_off_consonant += 1
                if dagesh_at.get(m["ordinal"]):
                    rafe_with_dagesh += 1
        gold_records = [Tier4Record(m["type"], vref, m["ordinal"]) for m in v["tier4_positional"]]
        gold_dets = detections_from_records(gold_records)
        pred_dets = detections_from_records(predict_rafe(chunk, vref))
        payloads[vref] = (gold_dets, pred_dets)
    if rafe_off_consonant:
        raise AssertionError(f"GATE 2: {rafe_off_consonant} gold rafe ordinals off any consonant")
    if rafe_with_dagesh:
        raise AssertionError(
            f"GATE 2: {rafe_with_dagesh} gold rafe consonants carry a dagesh "
            "(contradicts the no-dagesh rule assumption)"
        )
    sys.stdout.write(
        f"gates PASS: {len(verses)} verses; {rafe_gold} gold rafe(+DR), "
        "all on a consonant, none with dagesh\n"
    )
    return payloads, verse_folio


def _panel(payloads: list[Payload]) -> dict[str, object]:
    exact = pooled_rafe_f1(payloads, tolerance=0)
    tol1 = pooled_rafe_f1(payloads, tolerance=1)
    return {
        "n_verses": len(payloads),
        "f1_exact": exact.f1,
        "f1_tolerance_1": tol1.f1,
        "precision_exact": exact.precision,
        "recall_exact": exact.recall,
        "tp": exact.tp,
        "fp": exact.fp,
        "fn": exact.fn,
    }


def main() -> int:
    if not CONSENSUS.exists():
        sys.stderr.write(f"ERROR: required input missing: {CONSENSUS}\n")
        return 2
    data = json.loads(CONSENSUS.read_text())
    verses = data["verses"]

    payloads_by_verse, verse_folio = _validate_and_build(verses)
    verse_refs = [v["verse_ref"] for v in verses]

    def payloads_for(subset: list[str]) -> list[Payload]:
        return [payloads_by_verse[v] for v in subset]

    overall = payloads_for(verse_refs)
    overall_panel = _panel(overall)
    ci = bootstrap_metric(
        overall, lambda ps: pooled_rafe_f1(ps, tolerance=0).f1, b=DEFAULT_B, seed=DEFAULT_SEED
    )
    overall_panel["f1_exact_ci_lower"] = ci.ci_lower
    overall_panel["f1_exact_ci_upper"] = ci.ci_upper
    overall_panel["f1_exact_ci_method"] = ci.ci_method

    folios = sorted(set(verse_folio.values()))
    per_folio = {
        folio: _panel(payloads_for([v for v in verse_refs if verse_folio[v] == folio]))
        for folio in folios
    }

    haazinu = set(_haazinu_subset(verse_refs))
    by_section = {
        "haazinu": _panel(payloads_for([v for v in verse_refs if v in haazinu])),
        "prose": _panel(payloads_for([v for v in verse_refs if v not in haazinu])),
    }

    out = {
        "baseline": "rafe_text_rule",
        "baseline_id": "BL-05",
        "tier": 4,
        "mark_type": "rafe",
        "task": "rafe detection (oracle-text rule)",
        "rule": "predict rafe iff letter in begadkefat and no dagesh",
        "begadkefat": "".join(sorted(BEGADKEFAT)),
        "input_source": "consensus_gold_positional.json chunk (consonants + dagesh)",
        "gold_source": "consensus_gold_positional.json tier4_positional rafe/double_rafe records",
        "scorer": "masoretic_eval.iaa.f1.f1_with_tolerance (exact + tol-1); double_rafe->rafe",
        "bootstrap_b": DEFAULT_B,
        "bootstrap_seed_hex": f"0x{DEFAULT_SEED:X}",
        "overall": overall_panel,
        "per_folio": per_folio,
        "by_section": by_section,
        "note": (
            "Oracle-text baseline: consonants+dagesh read from the adjudicated "
            "consensus transcription. Demonstrates the tier-4 rafe axis is "
            "scoreable and discriminative; NOT an end-to-end image->tier-4 "
            "system. Recall is high (the scribe's rafe is mostly begadkefat) "
            "and precision moderate (rafe is placed selectively, not on every "
            "eligible consonant) — the gap is the headroom a context-aware "
            "system would have to close."
        ),
    }
    OUTPUT.write_text(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

    sys.stdout.write(f"\nwrote {OUTPUT}\n")
    sys.stdout.write(
        f"rafe text-rule tier-4 F1 (exact) vs consensus: "
        f"{overall_panel['f1_exact']:.4f} "
        f"[{overall_panel['f1_exact_ci_lower']:.4f}, {overall_panel['f1_exact_ci_upper']:.4f}]  "
        f"(P={overall_panel['precision_exact']:.4f} R={overall_panel['recall_exact']:.4f})\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
