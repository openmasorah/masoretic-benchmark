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
    "tier2": (0.0172, [0.0105, 0.0248]),
    "tier3": (0.0234, [0.0166, 0.0309]),
}


def _schema() -> dict:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def test_cer_tier_requires_the_honestly_named_field():
    tier = _schema()["$defs"]["cer_tier"]
    assert tier["required"] == ["cer_vs_consensus_b", "ci95"]
    assert "cer_vs_consensus_b" in tier["properties"]


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
        report[tier] = {"cer_vs_consensus_b": mean, "ci95": ci}

    jsonschema.Draft202012Validator(schema).validate(report)


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
        "tier2": {"cer_vs_consensus_b": 0.0172, "ci95": [0.0105, 0.0248]},
        "tier3": {"cer_vs_consensus_b": 0.0234, "ci95": [0.0166, 0.0309]},
        "tier4": {"f1_mean": 0.9187, "ci95": [0.8969, 0.9397]},
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(report)
