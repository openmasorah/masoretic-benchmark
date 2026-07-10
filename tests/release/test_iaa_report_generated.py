"""The committed iaa_report.json is the artifact the release-tag gate requires (W3).

It carries two classes of number:

* Headline CER / F1 (§5.2 / §5.1) -- pinned; must match ``PAPER_5_2`` (the same
  source of truth the B3 rename test guards) and the paper.
* adjudication_summary -- a descriptive workflow statistic the paper does not
  report. tier 1-3 are recomputed here from the two committed projections; tier 4
  is the UXLC-frame FP+FN pinned alongside f1_mean.

The mandatory ``_note`` block is asserted too: without it the four integers
over-read (nested tiers summed; taken as an agreement measurement). These tests
exist so the report cannot ship the numbers without the disclaimers.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from tests.release.test_iaa_report_field_naming import PAPER_5_2

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT = REPO_ROOT / "iaa_report.json"
SCHEMA = REPO_ROOT / "schemas" / "iaa_report.schema.json"


def _report() -> dict:
    return json.loads(REPORT.read_text(encoding="utf-8"))


def test_report_exists_and_validates():
    assert REPORT.exists(), "iaa_report.json is missing; the release-tag gate requires it"
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(_report())


def test_iaa_status_is_real():
    """The release-tier gate (check_iaa_report_real) requires exactly this."""
    assert _report()["iaa_status"] == "real"


def test_headline_cer_matches_the_pinned_paper_values():
    report = _report()
    for tier, (mean, ci) in PAPER_5_2.items():
        assert report[tier]["cer_vs_consensus_b"] == mean, tier
        assert report[tier]["ci95"] == ci, tier


def test_tier4_is_the_exact_f1_not_the_tolerance_headline():
    """f1_mean is F1-exact (0.9187), not the +/-1-tol 0.9472; the note must say so."""
    report = _report()
    assert report["tier4"]["f1_mean"] == 0.9187
    assert report["tier4"]["ci95"] == [0.8969, 0.9397]
    assert "EXACT" in report["_note"]["tier4_f1_mean"]
    assert "0.9472" in report["_note"]["tier4_f1_mean"]


def test_adjudication_tier1_3_recompute_from_the_committed_projections():
    """The projections-only counts must be exactly reproducible, or they are not provenance."""
    from masoretic_eval.iaa.cer import _STRIPPERS
    from masoretic_eval.metrics.cer import cluster_aligned_cer
    from masoretic_eval.normalize import normalize_for_scoring

    a = json.loads(
        (REPO_ROOT / "iaa_data/devarim_4folio/ginsberg_round0_positional.json").read_text()
    )["verses"]
    b = json.loads(
        (REPO_ROOT / "iaa_data/devarim_4folio/moster_round0_positional.json").read_text()
    )["verses"]
    adj = _report()["adjudication_summary"]
    for tier in (1, 2, 3):
        strip = _STRIPPERS[tier]
        edits = sum(
            cluster_aligned_cer(
                strip(normalize_for_scoring(av["chunk"])), strip(normalize_for_scoring(bv["chunk"]))
            ).edits
            for av, bv in zip(a, b, strict=True)
        )
        assert adj[f"tier{tier}_disagreements_reconciled"] == edits, tier


def test_adjudication_counts_are_the_expected_values():
    """Regression pin on all four (tier4 is UXLC-frame, not recomputed here)."""
    adj = _report()["adjudication_summary"]
    assert adj == {
        "tier1_disagreements_reconciled": 18,
        "tier2_disagreements_reconciled": 165,
        "tier3_disagreements_reconciled": 280,
        "tier4_disagreements_reconciled": 80,
    }


def test_the_note_block_carries_the_load_bearing_disclaimers():
    note = _report()["_note"]
    adj_note = note["adjudication_summary"]
    # not a paper number, not an agreement measurement
    assert "the paper reports no such counts" in adj_note
    assert "NOT a post-adjudication agreement measurement" in adj_note
    # the nesting trap
    assert "DO NOT SUM" in adj_note
    # the axis
    assert "Ginsberg" in adj_note and "Moster" in adj_note
    # tier-4 frame disclosure
    assert "UXLC-anchored" in adj_note and "dropped" in adj_note
    # cer note names the non-independence
    assert "NOT independent of either annotator" in note["cer_vs_consensus_b"]
