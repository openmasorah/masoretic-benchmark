#!/usr/bin/env python3
"""Generate (and verify) the committed ``iaa_report.json`` release artifact (W3).

``iaa_report.json`` is what the release-tag gate
(``scripts/audit_release.py::check_iaa_report_real``) requires before a
``benchmark-v*`` tag may ship. It carries the paper's headline IAA numbers plus
an adjudication summary, in the shape ``schemas/iaa_report.schema.json`` fixes.

Two classes of number, pinned differently on purpose:

* **Headline CER / F1** (``tierN.cer_vs_consensus_b`` and ``tier4.f1_mean``) are
  the paper §5.1/§5.2 values. They come from the UXLC-anchored pipeline and are
  NOT recomputable without the gitignored UXLC 2.5 cache, so they are pinned
  here as constants and cross-checked against ``PAPER_5_2`` in
  ``tests/release/test_iaa_report_field_naming.py`` — the same source of truth
  the schema-rename (B3) test already guards.

* **adjudication_summary tier 1-3** are computed from the two committed CC-BY
  round-0 projections ALONE (no UXLC), so ``--check`` recomputes and verifies
  them on every push. tier 4 is pinned (it is UXLC-frame, matching ``f1_mean``).

The ``_note`` block is mandatory and load-bearing: the four adjudication
integers are a *descriptive workflow statistic the paper does not report*, and
without the note a reader would over-read them (sum the nested tiers, or take
them as an agreement measurement the paper deliberately declines to make).

Usage
-----
    python scripts/generate_iaa_report.py            # write iaa_report.json
    python scripts/generate_iaa_report.py --check    # verify committed report

Exit codes: 0 ok · 1 drift/mismatch (--check) · 2 integrity error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# The scorer path (masoretic_eval.iaa.cer -> metrics.cer -> segment) pulls
# rapidfuzz + grapheme. Imported lazily inside the recompute only, so the
# schema-only check (pre-commit) runs on jsonschema alone.

REPORT_PATH = REPO_ROOT / "iaa_report.json"
SCHEMA_PATH = REPO_ROOT / "schemas" / "iaa_report.schema.json"
A_PROJ = REPO_ROOT / "iaa_data" / "devarim_4folio" / "ginsberg_round0_positional.json"
B_PROJ = REPO_ROOT / "iaa_data" / "devarim_4folio" / "moster_round0_positional.json"

FOLIOS = [
    "leningrad_devarim_F118B_fixture",
    "leningrad_devarim_F119A_fixture",
    "leningrad_devarim_F119B_fixture",
    "leningrad_devarim_F120A_fixture",
]

# Paper §5.2 (B round-0 vs adjudicated consensus, tier 1-3) and §5.1 (tier-4 F1
# exact). Byte-identical to PAPER_5_2 in tests/release/test_iaa_report_field_naming.py
# and to the abstract. NOT recomputable without the gitignored UXLC cache.
CER_VS_CONSENSUS_B = {
    "tier1": (0.0029, [0.0006, 0.0059]),
    "tier2": (0.0172, [0.0105, 0.0248]),
    "tier3": (0.0234, [0.0166, 0.0309]),
}
TIER4_F1_EXACT = (0.9187, [0.8969, 0.9397])

# tier-4 adjudication count: FP+FN of the pair-level detection match under the
# §5.1 headline config (UXLC-anchored, canonicalised; tp=452, fp=39, fn=41).
# UXLC-frame — same frame as f1_mean, so the two are internally consistent.
# Recomputable only with the UXLC cache, hence pinned here; the reproduction
# command is in the note.
TIER4_DISAGREEMENTS = 80


class ReportError(RuntimeError):
    """Integrity problem; never swallowed."""


def _tier_disagreement_edits(tier: int) -> int:
    """Code-point edit ops between A and B round-0 tier-N projections, over all verses.

    The exact scoring path §5.2's CER uses: normalize -> tier strip ->
    cluster_aligned_cer. Reproducible from the two committed projections alone.
    """
    from masoretic_eval.iaa.cer import tier_view  # noqa: PLC0415
    from masoretic_eval.metrics.cer import cluster_aligned_cer  # noqa: PLC0415

    a = json.loads(A_PROJ.read_text(encoding="utf-8"))["verses"]
    b = json.loads(B_PROJ.read_text(encoding="utf-8"))["verses"]
    if len(a) != len(b):
        raise ReportError(f"projection length mismatch: A={len(a)} B={len(b)}")
    edits = 0
    for av, bv in zip(a, b, strict=True):
        edits += cluster_aligned_cer(
            tier_view(av["chunk"], tier=tier), tier_view(bv["chunk"], tier=tier)
        ).edits
    return edits


def build_report() -> dict:
    adjudication = {
        f"tier{t}_disagreements_reconciled": _tier_disagreement_edits(t) for t in (1, 2, 3)
    }
    adjudication["tier4_disagreements_reconciled"] = TIER4_DISAGREEMENTS

    report: dict = {
        "iaa_status": "real",
        "folios": FOLIOS,
    }
    for tier, (mean, ci) in CER_VS_CONSENSUS_B.items():
        report[tier] = {"cer_vs_consensus_b": mean, "ci95": ci}
    report["tier4"] = {"f1_mean": TIER4_F1_EXACT[0], "ci95": TIER4_F1_EXACT[1]}
    report["adjudication_summary"] = adjudication
    report["_note"] = {
        "cer_vs_consensus_b": (
            "Annotator B's (Moster) round-0 transcription vs the adjudicated "
            "consensus reference, tiers 1-3, code-point Levenshtein CER on "
            "NFC-normalised projection strings (DRAFT_v4 §5.2). The consensus is "
            "A's round-1 revision, byte-identical to B's round-2 endorsement -- "
            "NOT independent of either annotator, and NOT a bidirectional A-vs-B "
            "figure."
        ),
        "tier4_f1_mean": (
            "Pair-level tier-4 F1 EXACT point estimate (DRAFT_v4 §5.1 / App. A.3; "
            "tp=452, fp=39, fn=41). This is the exact-match figure, NOT the paper's "
            "F1 with +/-1-consonant tolerance (0.9472)."
        ),
        "adjudication_summary": (
            "DESCRIPTIVE WORKFLOW STATISTIC -- the paper reports no such counts, "
            "and these are NOT a post-adjudication agreement measurement. Each "
            "integer is the number of round-0 disagreements between annotator A "
            "(Ginsberg) and annotator B (Moster) that the two-round diff-and-revise "
            "protocol reconciled into the consensus (the protocol ended in a "
            "byte-identical SHA-256 endorsement, so every round-0 divergence was "
            "resolved). Units differ by tier and the tier 1-3 counts are NESTED, "
            "NOT disjoint -- DO NOT SUM. tier1/2/3 = cluster-aligned code-point "
            "edit operations between the two round-0 projections at that tier "
            "(tier2 includes tier1's consonantal edits; tier3 includes both); an "
            "edit op is not a discrete adjudication case. tier4 = unmatched tier-4 "
            "detections (FP+FN) under the §5.1 headline exact-match config "
            "(UXLC-anchored, canonicalised {rafe,double_rafe}->rafe; 4 records -- "
            "1 A-side, 3 B-side -- unalignable to the UXLC backbone are dropped per "
            "App. A.4), the frame that also produces f1_mean above."
        ),
        "reproduction": (
            "tier1/2/3 adjudication counts recompute from the two committed CC-BY "
            "projections alone via scripts/generate_iaa_report.py --check. The CER/F1 "
            "headline values and the tier-4 count are UXLC-frame and reproduce via "
            "scripts/regenerate_paper_iaa_results.py with the pinned UXLC 2.5 cache "
            "and seed 0xBEEF."
        ),
    }
    return report


def _validate(report: dict) -> list[str]:
    import jsonschema  # noqa: PLC0415

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        jsonschema.Draft202012Validator(schema).validate(report)
    except jsonschema.ValidationError as exc:
        return [f"iaa_report.json fails schema: {exc.message}"]
    return []


def check(recompute: bool) -> list[str]:
    """Verify the committed report.

    ``recompute=False`` (pre-commit): schema + iaa_status + pinned constants only,
    on jsonschema alone. ``recompute=True`` (CI / tests): additionally re-derives
    the tier 1-3 adjudication counts from the committed projections via the scorer
    path (rapidfuzz + grapheme), catching a tampered count.
    """
    if not REPORT_PATH.exists():
        return ["iaa_report.json is missing; run scripts/generate_iaa_report.py"]
    committed = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    errors = _validate(committed)

    if committed.get("iaa_status") != "real":
        errors.append(f"iaa_status={committed.get('iaa_status')!r} (expected 'real')")

    adj = committed.get("adjudication_summary", {})

    # Pinned values (UXLC-frame; not CI-recomputable) must match the committed report.
    for tier, (mean, ci) in CER_VS_CONSENSUS_B.items():
        block = committed.get(tier, {})
        if block.get("cer_vs_consensus_b") != mean or block.get("ci95") != ci:
            errors.append(f"{tier} drifted from the pinned paper §5.2 value {mean} {ci}")
    if committed.get("tier4", {}).get("f1_mean") != TIER4_F1_EXACT[0]:
        errors.append(f"tier4.f1_mean drifted from the pinned §5.1 value {TIER4_F1_EXACT[0]}")
    if adj.get("tier4_disagreements_reconciled") != TIER4_DISAGREEMENTS:
        errors.append(f"tier4 adjudication count drifted from the pinned {TIER4_DISAGREEMENTS}")

    if recompute:
        for t in (1, 2, 3):
            want = _tier_disagreement_edits(t)
            got = adj.get(f"tier{t}_disagreements_reconciled")
            if got != want:
                errors.append(
                    f"adjudication_summary.tier{t}_disagreements_reconciled={got} "
                    f"but recomputation from the committed projections gives {want}"
                )
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument(
        "--check", action="store_true", help="full verify incl. tier1-3 recompute (CI/tests)"
    )
    mode.add_argument(
        "--check-schema",
        action="store_true",
        help="light verify: schema + iaa_status + pinned constants, no scorer import (pre-commit)",
    )
    args = ap.parse_args()

    for p in (A_PROJ, B_PROJ, SCHEMA_PATH):
        if not p.exists():
            print(f"integrity: required input missing: {p}", file=sys.stderr)
            return 2

    if args.check or args.check_schema:
        errors = check(recompute=args.check)
        if errors:
            print(f"iaa_report verification FAILED ({len(errors)}):", file=sys.stderr)
            for e in errors:
                print(f"  {e}", file=sys.stderr)
            return 1
        depth = "adjudication tier1-3 recompute" if args.check else "pinned constants"
        print(f"ok: iaa_report.json validates, iaa_status=real, {depth}")
        return 0

    report = build_report()
    errors = _validate(report)
    if errors:
        for e in errors:
            print(f"integrity: {e}", file=sys.stderr)
        return 2
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    adj = report["adjudication_summary"]
    print(f"wrote {REPORT_PATH.relative_to(REPO_ROOT)}")
    print(f"  adjudication (nested, do not sum): {adj}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
