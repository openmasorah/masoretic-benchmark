#!/usr/bin/env python3
"""Generate (and verify) the committed ``iaa_report.json`` release artifact (W3).

``iaa_report.json`` is what the release-tag gate
(``scripts/audit_release.py::check_iaa_report_real``) requires before a
``benchmark-v*`` tag may ship. It carries the paper's headline IAA numbers plus
an adjudication summary, in the shape ``schemas/iaa_report.schema.json`` fixes.

Two classes of number, pinned differently on purpose:

* **Headline CER / F1** (``tierN.cer_vs_consensus_b`` and ``tier4.f1_mean``) are
  the paper §5.1/§5.2 values, pinned here as constants and cross-checked against
  ``PAPER_5_2`` in ``tests/release/test_iaa_report_field_naming.py`` — the same
  source of truth the schema-rename (B3) test already guards. The tier-1/2/3 CER
  values ARE recomputable from the three committed projection JSONs alone; only
  ``tier4.f1_mean`` needs the gitignored UXLC 2.5 cache. (This docstring
  previously said none of them were recomputable. That was false, and it misled
  two independent external reviewers who repeated it rather than testing it.)

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
GOLD_PROJ = REPO_ROOT / "iaa_data" / "devarim_4folio" / "consensus_gold_positional.json"

FOLIOS = [
    "leningrad_devarim_F118B_fixture",
    "leningrad_devarim_F119A_fixture",
    "leningrad_devarim_F119B_fixture",
    "leningrad_devarim_F120A_fixture",
]

# Paper §5.2 (B round-0 vs adjudicated consensus, tier 1-3) and §5.1 (tier-4 F1
# exact). Byte-identical to PAPER_5_2 in tests/release/test_iaa_report_field_naming.py
# and to the abstract.
#
# CORRECTED 2026-07-29 (v0.1.1). The tier-2/tier-3 values shipped in
# benchmark-v0.1.0 (0.0172, 0.0234) were WRONG: the `<DR>` double-rafe editor
# token was scored as four literal ASCII characters in the tier-2/3 CER path,
# and the sides carry unequal token counts (A=25, B=56, consensus=27). Fixed in
# masoretic_eval/iaa/cer.py; see CHANGELOG v0.1.1. Tier 1 is unaffected (the
# consonant filter drops ASCII) and so is every tier-4 figure.
#
# These ARE recomputable from the three committed projection JSONs alone -- no
# UXLC cache required. The comment here previously claimed otherwise; that was
# false, and two external reviewers repeated the claim from this comment rather
# than testing it. Only the tier-4 UXLC-frame figures need the UXLC 2.5 cache.
CER_VS_CONSENSUS_B = {
    "tier1": (0.0029, [0.0006, 0.0059]),
    "tier2": (0.0031, [0.0006, 0.0062]),
    "tier3": (0.0119, [0.0085, 0.0156]),
}
TIER4_F1_EXACT = (0.9187, [0.8969, 0.9397])

# A round-0 vs the adjudicated consensus. Publishes the adjudication anchor's
# other half: near-zero by construction, because the consensus IS A's own
# round-1 revision. Kept as a pinned expectation like the block above; the
# generator recomputes it and refuses to write on a mismatch.
CER_VS_CONSENSUS_A = {
    "tier1": (0.0, [0.0, 0.0]),
    "tier2": (0.0, [0.0, 0.0001]),
    "tier3": (0.0015, [0.0008, 0.0023]),
}

# A round-0 vs B round-0 -- the only PRE-adjudication, mutually independent
# figure in this report, and the one to cite as "inter-annotator agreement".
# Direction: A is the reference (denominator). See ``CER_A_VS_B_REF_B`` for the
# other direction, reported in the note so nobody rediscovers the asymmetry and
# reads it as a discrepancy.
CER_A_VS_B_ROUND0 = {
    "tier1": (0.0029, [0.0006, 0.0059]),
    "tier2": (0.0031, [0.0007, 0.0063]),
    "tier3": (0.013, [0.0096, 0.0167]),
}
CER_A_VS_B_REF_B = {
    "tier1": (0.0028, [0.0006, 0.0057]),
    "tier2": (0.003, [0.0006, 0.0059]),
    "tier3": (0.013, [0.0096, 0.0166]),
}

# Reference-side code-point denominators, per tier, over all 96 verses. These
# are REFERENCE-DEPENDENT: the consensus and A sides differ slightly (a tier-2
# codepoint, twelve at tier 3), so a single "the denominator" would be wrong for
# two of the three blocks. Recomputed and asserted, never hand-copied.
#
# The v0.1.1 fix plan quoted 5597 / 9329 / 11176. Tiers 2 and 3 there are each
# 108 too high -- exactly 27 `<DR>` tokens x 4 ASCII characters, i.e. the same
# contamination the CER values had. Tier 1 was right because its consonant
# filter drops ASCII.
DENOMINATORS_CONSENSUS = {"tier1": 5597, "tier2": 9221, "tier3": 11068}
DENOMINATORS_A = {"tier1": 5597, "tier2": 9222, "tier3": 11056}

N_VERSES = 96

# tier-4 adjudication count: FP+FN of the pair-level detection match under the
# §5.1 headline config (UXLC-anchored, canonicalised; tp=452, fp=39, fn=41).
# UXLC-frame — same frame as f1_mean, so the two are internally consistent.
# Recomputable only with the UXLC cache, hence pinned here; the reproduction
# command is in the note.
TIER4_DISAGREEMENTS = 80


class ReportError(RuntimeError):
    """Integrity problem; never swallowed."""


def _load_verses(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["verses"]


def _macro(per_verse: list[float]) -> float:
    return sum(per_verse) / len(per_verse) if per_verse else float("nan")


def _cer_block(ref_path: Path, hyp_path: Path, tier: int) -> tuple[float, list[float]]:
    """Macro-averaged per-verse CER + verse-bootstrap 95% CI, ``ref`` as denominator.

    Identical path to ``masoretic_eval.iaa.compute._tier_cer_result``: per-verse
    CER through ``iaa.cer.per_verse_cer``, then ``bootstrap_metric`` with
    :func:`_macro` -- this module's copy of that function's ``_macro_cer``,
    same arithmetic -- at the package defaults (B, seed 0xBEEF, percentile). Verified
    to reproduce the published ``cer_vs_consensus_b`` point estimates AND their
    CIs exactly, which is what licenses using it for the new blocks.
    """
    from masoretic_eval.iaa.bootstrap import (  # noqa: PLC0415
        DEFAULT_B,
        DEFAULT_SEED,
        bootstrap_metric,
    )
    from masoretic_eval.iaa.cer import per_verse_cer  # noqa: PLC0415

    ref, hyp = _load_verses(ref_path), _load_verses(hyp_path)
    if len(ref) != len(hyp):
        raise ReportError(f"projection length mismatch: {len(ref)} vs {len(hyp)}")
    payloads = [
        per_verse_cer(r["chunk"], h["chunk"], tier=tier) for r, h in zip(ref, hyp, strict=True)
    ]
    m = bootstrap_metric(payloads, _macro, b=DEFAULT_B, seed=DEFAULT_SEED)
    return round(m.point, 4), [round(m.ci_lower, 4), round(m.ci_upper, 4)]


def _denominator(path: Path, tier: int) -> int:
    """Total code points on one side's tier view, over all verses."""
    from masoretic_eval.iaa.cer import tier_view  # noqa: PLC0415

    return sum(len(tier_view(v["chunk"], tier=tier)) for v in _load_verses(path))


def _edits(ref_path: Path, hyp_path: Path, tier: int) -> int:
    """Cluster-aligned code-point edit ops between two sides at one tier."""
    from masoretic_eval.iaa.cer import tier_view  # noqa: PLC0415
    from masoretic_eval.metrics.cer import cluster_aligned_cer  # noqa: PLC0415

    ref, hyp = _load_verses(ref_path), _load_verses(hyp_path)
    return sum(
        cluster_aligned_cer(
            tier_view(r["chunk"], tier=tier), tier_view(h["chunk"], tier=tier)
        ).edits
        for r, h in zip(ref, hyp, strict=True)
    )


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
        "n_verses": N_VERSES,
    }

    # Every CER below is COMPUTED here from the committed projections, then
    # checked against its pinned expectation. The pin is the paper cross-check,
    # not the source: if computation and pin ever disagree the generator
    # refuses to write rather than silently publishing either one.
    drift: list[str] = []
    for tier in ("tier1", "tier2", "tier3"):
        t = int(tier[-1])
        vs_b = _cer_block(GOLD_PROJ, B_PROJ, t)
        vs_a = _cer_block(GOLD_PROJ, A_PROJ, t)
        a_vs_b = _cer_block(A_PROJ, B_PROJ, t)
        b_vs_a = _cer_block(B_PROJ, A_PROJ, t)
        for label, got, want in (
            ("cer_vs_consensus_b", vs_b, CER_VS_CONSENSUS_B[tier]),
            ("cer_vs_consensus_a", vs_a, CER_VS_CONSENSUS_A[tier]),
            ("cer_a_vs_b_round0", a_vs_b, CER_A_VS_B_ROUND0[tier]),
            ("cer_a_vs_b_round0 (ref=B)", b_vs_a, CER_A_VS_B_REF_B[tier]),
        ):
            if [got[0], got[1]] != [want[0], list(want[1])]:
                drift.append(f"{tier}.{label}: computed {got} != pinned {want}")

        den_gold, den_a = _denominator(GOLD_PROJ, t), _denominator(A_PROJ, t)
        if den_gold != DENOMINATORS_CONSENSUS[tier] or den_a != DENOMINATORS_A[tier]:
            drift.append(
                f"{tier} denominators: computed consensus={den_gold} A={den_a} != pinned "
                f"{DENOMINATORS_CONSENSUS[tier]} / {DENOMINATORS_A[tier]}"
            )

        report[tier] = {
            "cer_vs_consensus_b": vs_b[0],
            "ci95": vs_b[1],
            "cer_vs_consensus_a": vs_a[0],
            "ci95_vs_consensus_a": vs_a[1],
            "cer_a_vs_b_round0": a_vs_b[0],
            "ci95_a_vs_b_round0": a_vs_b[1],
            "reference_side": (
                "consensus for the vs_consensus_* figures; annotator A for a_vs_b_round0"
            ),
            "denominator_codepoints_consensus": den_gold,
            "denominator_codepoints_a": den_a,
            "edits_vs_consensus_b": _edits(GOLD_PROJ, B_PROJ, t),
            "edits_vs_consensus_a": _edits(GOLD_PROJ, A_PROJ, t),
            "edits_a_vs_b_round0": _edits(A_PROJ, B_PROJ, t),
        }
    if drift:
        raise ReportError(
            "computed IAA figures disagree with their pinned expectations; refusing to "
            "write a report whose numbers nobody has reconciled:\n  " + "\n  ".join(drift)
        )

    report["tier4"] = {"f1_mean": TIER4_F1_EXACT[0], "ci95": TIER4_F1_EXACT[1]}
    report["adjudication_summary"] = adjudication
    report["_note"] = {
        "which_number_to_cite": (
            "CITE `cer_a_vs_b_round0` AS INTER-ANNOTATOR AGREEMENT: 0.0029 / 0.0031 "
            "/ 0.0130 at tiers 1/2/3. It is the only figure here computed between "
            "two mutually independent, PRE-adjudication transcriptions. The two "
            "`cer_vs_consensus_*` blocks are adjudication diagnostics, not "
            "agreement measurements -- see their notes. Reporting either of them "
            "as 'inter-annotator agreement' overstates the result, and reporting "
            "`cer_vs_consensus_a` as one would be circular; it is near zero by "
            "construction."
        ),
        "metric": (
            "All CER figures: CLUSTER-ALIGNED code-point CER on NFD-normalised "
            "projection strings (CGJ stripped first), macro-averaged over the 96 "
            "verses, reference side as denominator; annotator-tool editor tokens "
            "are stripped before scoring. Verse-bootstrap percentile 95% CIs, "
            "seed 0xBEEF. All three blocks and every count in them recompute from "
            "the three committed projection JSONs ALONE -- no UXLC cache -- via "
            "scripts/generate_iaa_report.py --check. Only the tier-4 figures are "
            "UXLC-frame. Per-tier reference-side code-point denominators are "
            "published per block because they are reference-dependent; a single "
            "'the denominator' would be wrong for two of the three."
        ),
        "cer_a_vs_b_round0": (
            "Annotator A (Ginsberg) round-0 vs annotator B (Moster) round-0, "
            "tiers 1-3. THE HEADLINE AGREEMENT FIGURE: both sides are blind, "
            "pre-adjudication, and independent of each other. DIRECTIONAL -- A is "
            "the reference/denominator. The other direction (B as reference) is "
            "0.0028 / 0.0030 / 0.0130; the small tier-1/2 gap is denominator "
            "asymmetry, not a discrepancy, and is stated here so nobody "
            "rediscovers it and reads it as one. NOTE the edit counts "
            "(18 / 33 / 148) are IDENTICAL to adjudication_summary tiers 1-3: "
            "that summary always WAS this comparison, expressed as edit "
            "operations instead of CER. These are two views of one measurement, "
            "not two independent statistics -- do not present them as "
            "corroborating each other."
        ),
        "cer_vs_consensus_b": (
            "Annotator B's (Moster) round-0 transcription vs the adjudicated "
            "consensus reference, tiers 1-3. An ADJUDICATION DIAGNOSTIC, not an "
            "agreement figure: the consensus is A's round-1 revision, "
            "byte-identical to B's round-2 endorsement, so it is NOT independent "
            "of either annotator. CORRECTED 2026-07-29 -- the tier-2/tier-3 "
            "values in v0.1.0 counted the `<DR>` token as literal text; see "
            "CHANGELOG v0.1.1."
        ),
        "cer_vs_consensus_a": (
            "Annotator A's (Ginsberg) round-0 transcription vs the adjudicated "
            "consensus -- 0 edits at tier 1, 1 at tier 2, 18 at tier 3. THIS IS "
            "THE CIRCULARITY, QUANTIFIED, and it is published precisely so the "
            "reader can see it rather than infer it: the consensus IS A's own "
            "round-1 revision, so this measures how little A changed its mind "
            "during adjudication, NOT how well A agrees with an independent "
            "reference. The near-zero values are a property of the protocol, not "
            "a quality result. Raw edit counts are published alongside so the "
            "tier-1 zero is legible as a measurement rather than a stub."
        ),
        "tier4_f1_mean": (
            "Pair-level tier-4 F1 EXACT point estimate, UXLC-frame (tp=452, fp=39, "
            "fn=41). This is the exact-match figure, NOT the F1 with +/-1-consonant "
            "tolerance (0.9472). The canonicalisation, matching, dropped-record and "
            "frame rules behind it are specified IN THIS REPOSITORY at "
            "iaa_data/devarim_4folio/README.md ('Tier-4 scoring specification'); they "
            "were previously cited only to an unpublished paper draft, which left the "
            "published figure undefined from the tag alone. The committed-data-only "
            "counterpart is F1 exact 0.8988, and Krippendorff alpha 0.7470 here is the "
            "positive-universe canon figure -- see that spec for the full alpha table, "
            "since full-universe alpha is ~0.20 higher and an unlabelled 'alpha' is "
            "ambiguous between them."
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

        # Every CER in the report recomputes from the committed projections.
        # This is what makes "generator-produced" verifiable rather than
        # asserted: a hand-edited iaa_report.json fails here.
        for tier in ("tier1", "tier2", "tier3"):
            t = int(tier[-1])
            block = committed.get(tier, {})
            for field, ci_field, (ref, hyp) in (
                ("cer_vs_consensus_b", "ci95", (GOLD_PROJ, B_PROJ)),
                ("cer_vs_consensus_a", "ci95_vs_consensus_a", (GOLD_PROJ, A_PROJ)),
                ("cer_a_vs_b_round0", "ci95_a_vs_b_round0", (A_PROJ, B_PROJ)),
            ):
                point, ci = _cer_block(ref, hyp, t)
                if block.get(field) != point or block.get(ci_field) != ci:
                    errors.append(
                        f"{tier}.{field}={block.get(field)} {block.get(ci_field)} but "
                        f"recomputation gives {point} {ci}"
                    )
            for field, path in (
                ("denominator_codepoints_consensus", GOLD_PROJ),
                ("denominator_codepoints_a", A_PROJ),
            ):
                want_den = _denominator(path, t)
                if block.get(field) != want_den:
                    errors.append(
                        f"{tier}.{field}={block.get(field)} but recomputation gives {want_den}"
                    )
            for field, (ref, hyp) in (
                ("edits_vs_consensus_b", (GOLD_PROJ, B_PROJ)),
                ("edits_vs_consensus_a", (GOLD_PROJ, A_PROJ)),
                ("edits_a_vs_b_round0", (A_PROJ, B_PROJ)),
            ):
                want_edits = _edits(ref, hyp, t)
                if block.get(field) != want_edits:
                    errors.append(
                        f"{tier}.{field}={block.get(field)} but recomputation gives {want_edits}"
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
