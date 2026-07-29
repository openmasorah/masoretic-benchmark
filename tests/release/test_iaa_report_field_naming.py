"""The IAA report must not name a quantity it does not measure (blocker B3).

`iaa_report.schema.json` required `bidirectional_cer_mean` per tier -- the CER
between annotator A and annotator B. The released paper reports no such number:
the string "bidirectional" appears **zero times** in `DRAFT_v4.md`.

What §5.2 actually reports is annotator B's round-0 transcription versus the
**adjudicated consensus reference** -- and the paper is explicit that the
consensus is *not independent of either annotator* (it is A's round-1 revision,
byte-identical to B's round-2 endorsement). So it is neither a bidirectional
agreement figure nor an independent human-vs-reference baseline.

Publishing §5.2's value under the old field name would have been exactly the
class of mislabel the paper retracted five of. The field is now
`cer_vs_consensus_b`.

These tests exist so the old name cannot come back, and so the report can never
publish a tier-1/2/3 figure the paper has not defended.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = REPO_ROOT / "schemas" / "iaa_report.schema.json"

# DRAFT_v4 §5.2, overall column. Lives in the private planning repo, so these
# are pinned here as constants -- CI in this public repo cannot read that file
# (Pitfall 8), and regenerating needs the gitignored UXLC cache.
PAPER_5_2 = {
    "tier1": (0.0029, [0.0006, 0.0059]),
    "tier2": (0.0031, [0.0006, 0.0062]),
    "tier3": (0.0119, [0.0085, 0.0156]),
}

# v0.1.1 additions, recomputed from the three committed projections (no UXLC).
# A-as-reference; see scripts/generate_iaa_report.py.
A_VS_B_ROUND0 = {
    "tier1": (0.0029, [0.0006, 0.0059], 18),
    "tier2": (0.0031, [0.0007, 0.0063], 33),
    "tier3": (0.013, [0.0096, 0.0167], 148),
}
VS_CONSENSUS_A = {
    "tier1": (0.0, [0.0, 0.0], 0),
    "tier2": (0.0, [0.0, 0.0001], 1),
    "tier3": (0.0015, [0.0008, 0.0023], 18),
}
DENOMINATORS = {"tier1": (5597, 5597), "tier2": (9221, 9222), "tier3": (11068, 11056)}


def _schema() -> dict:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def test_cer_tier_requires_the_honestly_named_field():
    tier = _schema()["$defs"]["cer_tier"]
    assert "cer_vs_consensus_b" in tier["required"]
    assert "cer_vs_consensus_b" in tier["properties"]


def test_cer_tier_requires_the_independent_agreement_figure():
    """v0.1.1: publishing only vs-consensus figures is itself a mislabel risk.

    Both `cer_vs_consensus_*` blocks are adjudication diagnostics measured
    against a reference that is not independent of either annotator. A report
    that omitted the one genuinely independent pre-adjudication number would
    leave a reader with nothing to cite but a diagnostic -- the same class of
    error as the old `bidirectional_cer_mean` name. So it is REQUIRED, not
    optional.
    """
    tier = _schema()["$defs"]["cer_tier"]
    for field in (
        "cer_a_vs_b_round0",
        "ci95_a_vs_b_round0",
        "cer_vs_consensus_a",
        "ci95_vs_consensus_a",
    ):
        assert field in tier["required"], f"{field} must be required, not optional"
        assert field in tier["properties"]


def test_the_agreement_field_declares_its_direction_and_its_double():
    """A directional metric with a symmetric-sounding name is a trap.

    `cer_a_vs_b_round0` reads as symmetric but is denominator-dependent, and its
    edit counts are the same measurement as `adjudication_summary`. Both facts
    must be on the field itself, not only in the report's note.
    """
    desc = _schema()["$defs"]["cer_tier"]["properties"]["cer_a_vs_b_round0"]["description"]
    assert "DIRECTIONAL" in desc
    assert "adjudication_summary" in desc


def test_the_circular_field_says_it_is_circular():
    """`cer_vs_consensus_a` is ~0 by construction; the schema must say why."""
    desc = _schema()["$defs"]["cer_tier"]["properties"]["cer_vs_consensus_a"]["description"]
    assert "BY CONSTRUCTION" in desc
    assert "Never cite as inter-annotator agreement" in desc


def test_raw_edit_counts_ship_with_every_cer():
    """A 0.0000 CER must be legible as a measurement, not an empty field."""
    tier = _schema()["$defs"]["cer_tier"]
    for field in ("edits_vs_consensus_b", "edits_vs_consensus_a", "edits_a_vs_b_round0"):
        assert field in tier["required"]


def test_both_reference_side_denominators_are_published():
    """The denominator is reference-dependent; one number would be wrong twice."""
    tier = _schema()["$defs"]["cer_tier"]
    assert "denominator_codepoints_consensus" in tier["required"]
    assert "denominator_codepoints_a" in tier["required"]


def test_the_misleading_field_name_is_gone():
    """No *field* may be called bidirectional; the paper publishes no such number.

    The word survives in the description, where it appears only to say what the
    field is NOT. That negation is the point, so this bans the identifier rather
    than the string.
    """
    schema = _schema()
    tier = schema["$defs"]["cer_tier"]
    assert "bidirectional_cer_mean" not in tier["properties"]
    assert "bidirectional_cer_mean" not in tier["required"]

    def _field_names(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "properties" and isinstance(value, dict):
                    yield from value
                yield from _field_names(value)
        elif isinstance(node, list):
            for item in node:
                yield from _field_names(item)

    offenders = [n for n in _field_names(schema) if "bidirectional" in n.lower()]
    assert not offenders, f"schema declares un-measured quantities: {offenders}"


def test_the_field_description_states_what_it_is_not():
    """A reader of the public schema must not infer independence or symmetry."""
    desc = _schema()["$defs"]["cer_tier"]["properties"]["cer_vs_consensus_b"]["description"]
    assert "NOT a bidirectional" in desc
    assert "not independent of either annotator" in desc


def test_paper_5_2_values_validate_against_the_renamed_schema():
    """The exact numbers W3 will publish must satisfy the schema as written."""
    import jsonschema

    schema = _schema()
    report = {
        "folios": [
            "leningrad_devarim_F118B_fixture",
            "leningrad_devarim_F119A_fixture",
            "leningrad_devarim_F119B_fixture",
            "leningrad_devarim_F120A_fixture",
        ],
        "adjudication_summary": {
            "tier1_disagreements_reconciled": 0,
            "tier2_disagreements_reconciled": 0,
            "tier3_disagreements_reconciled": 0,
            "tier4_disagreements_reconciled": 0,
        },
        "tier4": {"f1_mean": 0.9187, "ci95": [0.8969, 0.9397]},
    }
    for tier, (mean, ci) in PAPER_5_2.items():
        a_mean, a_ci, a_edits = VS_CONSENSUS_A[tier]
        ab_mean, ab_ci, ab_edits = A_VS_B_ROUND0[tier]
        den_gold, den_a = DENOMINATORS[tier]
        report[tier] = {
            "cer_vs_consensus_b": mean,
            "ci95": ci,
            "cer_vs_consensus_a": a_mean,
            "ci95_vs_consensus_a": a_ci,
            "cer_a_vs_b_round0": ab_mean,
            "ci95_a_vs_b_round0": ab_ci,
            "denominator_codepoints_consensus": den_gold,
            "denominator_codepoints_a": den_a,
            "edits_vs_consensus_b": 0,
            "edits_vs_consensus_a": a_edits,
            "edits_a_vs_b_round0": ab_edits,
        }

    jsonschema.Draft202012Validator(schema).validate(report)


def test_committed_report_matches_these_pinned_values():
    """The shipped report must carry exactly the numbers pinned above.

    Guards the README/CHANGELOG/iaa_report.json identity property from the
    schema side: if the generator's output and this pin ever diverge, one of
    them is publishing a number nobody reconciled.
    """
    report = json.loads((REPO_ROOT / "iaa_report.json").read_text(encoding="utf-8"))
    for tier in PAPER_5_2:
        block = report[tier]
        assert (block["cer_vs_consensus_b"], block["ci95"]) == PAPER_5_2[tier]
        ab_mean, ab_ci, ab_edits = A_VS_B_ROUND0[tier]
        assert (block["cer_a_vs_b_round0"], block["ci95_a_vs_b_round0"]) == (ab_mean, ab_ci)
        assert block["edits_a_vs_b_round0"] == ab_edits
        a_mean, a_ci, a_edits = VS_CONSENSUS_A[tier]
        assert (block["cer_vs_consensus_a"], block["ci95_vs_consensus_a"]) == (a_mean, a_ci)
        assert block["edits_vs_consensus_a"] == a_edits
        assert (
            block["denominator_codepoints_consensus"],
            block["denominator_codepoints_a"],
        ) == DENOMINATORS[tier]


def test_a_vs_b_edits_equal_the_adjudication_summary():
    """They are one measurement in two units -- if they drift, one is wrong."""
    report = json.loads((REPO_ROOT / "iaa_report.json").read_text(encoding="utf-8"))
    for tier in PAPER_5_2:
        t = tier[-1]
        assert (
            report[tier]["edits_a_vs_b_round0"]
            == report["adjudication_summary"][f"tier{t}_disagreements_reconciled"]
        )


def test_a_report_using_the_old_field_name_is_rejected():
    import jsonschema
    import pytest

    schema = _schema()
    report = {
        "folios": ["leningrad_devarim_F118B_fixture"],
        "adjudication_summary": {
            "tier1_disagreements_reconciled": 0,
            "tier2_disagreements_reconciled": 0,
            "tier3_disagreements_reconciled": 0,
            "tier4_disagreements_reconciled": 0,
        },
        "tier1": {"bidirectional_cer_mean": 0.0029, "ci95": [0.0006, 0.0059]},
        "tier2": {"cer_vs_consensus_b": 0.0031, "ci95": [0.0006, 0.0062]},
        "tier3": {"cer_vs_consensus_b": 0.0119, "ci95": [0.0085, 0.0156]},
        "tier4": {"f1_mean": 0.9187, "ci95": [0.8969, 0.9397]},
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)
