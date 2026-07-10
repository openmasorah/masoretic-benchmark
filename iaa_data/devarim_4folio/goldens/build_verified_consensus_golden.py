"""Project the verified-consensus gold into the cold-score driver's golden form.

OD-1 Option A: read iaa_data/devarim_4folio/consensus_gold_positional.json
(CC-BY-4.0 verified consensus gold; per-verse `chunk` form), group verses by
folio in document order, and emit one `*.gt_adapter_golden.json` per folio with
a `lines[]` array (each line = one verse chunk, full pointing retained).

The cold-score driver (baselines/scripts/cold_score_provisional.py) space-joins
`lines[]` for the GT scorer input; tier-1 CER is segmentation-invariant, so
chunk-per-line vs physical-line is lossless for tier-1, while the retained
nikkud/trop make tier-2/tier-3 meaningful (the prior Moster B-side fixtures are
consonant-only). `tier4_positional` is carried per verse for future tier-4 work
(the current driver scores tier-1/2/3 only).

CANONICAL. These goldens are the artifact `phase_0_manifest.json` computes each
folio's `gt_hash` over. They carry no `gt_hash` of their own -- the manifest is
the single source of truth for that digest (CLAUDE.md scope-freeze rule), and a
file cannot contain the hash of itself.

Output is byte-reproducible: re-running this script must leave the committed
goldens unchanged (tests/test_goldens_reproducible.py).

Run: .venv/bin/python iaa_data/devarim_4folio/goldens/build_verified_consensus_golden.py
"""

from __future__ import annotations

import json
from pathlib import Path

from masoretic_eval.iaa.parse import count_consonants

REPO = Path(__file__).resolve().parents[3]
SRC = REPO / "iaa_data" / "devarim_4folio" / "consensus_gold_positional.json"
OUT_DIR = Path(__file__).resolve().parent
FOLIO_ORDER = ["F118B", "F119A", "F119B", "F120A"]


def main() -> int:
    src = json.loads(SRC.read_text(encoding="utf-8"))
    verses = src["verses"]

    by_folio: dict[str, list[dict]] = {f: [] for f in FOLIO_ORDER}
    for v in verses:
        by_folio[v["folio"]].append(v)

    for folio in FOLIO_ORDER:
        rows = by_folio[folio]
        folio_id = f"leningrad_devarim_{folio}_fixture"
        lines = [r["chunk"] for r in rows]
        verse_refs = [r["verse_ref"] for r in rows]
        stored_cons = [r["consonant_count"] for r in rows]
        derived_cons = [count_consonants(r["chunk"]) for r in rows]

        # Sanity guard: stored consonant_count must equal the chunk's derived
        # count, verse by verse. Fail loud on drift.
        for ref, stored, derived in zip(verse_refs, stored_cons, derived_cons, strict=True):
            if stored != derived:
                raise SystemExit(
                    f"consonant_count drift {folio} {ref}: stored={stored} derived={derived}"
                )

        golden = {
            "folio_id": folio_id,
            "provisional": False,
            "single_annotator": False,
            "pre_adjudication": False,
            "side_label": "consensus_gold",
            "license": src.get("license", "CC-BY-4.0"),
            "_provenance": {
                "method": (
                    "OD-1 Option A: verified-consensus per-verse chunks grouped by "
                    "folio in document order, emitted as lines[] (one verse chunk per "
                    "line). GT scorer input space-joins lines[]; tier-1 CER is "
                    "segmentation-invariant so chunk-per-line is lossless for tier-1, "
                    "while retained nikkud/trop make tier-2/tier-3 meaningful."
                ),
                "annotators": "Ginsberg (A) + Moster (B), post-adjudication consensus",
                "source": (
                    "iaa_data/devarim_4folio/consensus_gold_positional.json "
                    "(CC-BY-4.0 verified consensus gold; Round-1 revised consensus, "
                    "FINAL 2026-06-19, byte-identical to Annotator B round-2 endorsement)"
                ),
                "verse_range_first": verse_refs[0],
                "verse_range_last": verse_refs[-1],
                "line_count": len(lines),
                "consonant_total": sum(stored_cons),
                "tier4_positional_total": sum(len(r.get("tier4_positional", [])) for r in rows),
                "provisional": False,
                "iaa_status": (
                    "post-adjudication consensus (Ginsberg A + Moster B); canonical "
                    "ground truth, hashed into phase_0_manifest.json as gt_hash"
                ),
            },
            "lines": lines,
            "verse_refs": verse_refs,
            "consonant_counts": stored_cons,
            # Carried for future tier-4 work; NOT consumed by the current
            # tier-1/2/3 cold-score driver (which sets metamarks=[]).
            "tier4_positional_by_verse": [
                {"verse_ref": r["verse_ref"], "tier4_positional": r.get("tier4_positional", [])}
                for r in rows
            ],
        }

        out_path = OUT_DIR / f"{folio_id}.gt_adapter_golden.json"
        out_path.write_text(
            json.dumps(golden, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            f"{folio}: lines={len(lines)} consonants={sum(stored_cons)} "
            f"tier4={golden['_provenance']['tier4_positional_total']} -> {out_path.name}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
