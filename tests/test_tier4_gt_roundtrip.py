"""The benchmark's own tier-4 gold must survive the benchmark's own scorer.

This is the test whose absence let a total scorer/data divergence ship. Until
scorer 0.3.0 the CLI input enum was ``{pe, samekh, reversednun, puncta,
large_letter, small_letter, suspended_letter, inverted_nun}`` while every one
of the 516 tier-4 records in ``iaa_data/devarim_4folio/consensus_gold_
positional.json`` was typed ``circellus``, ``rafe`` or ``double_rafe``. The
intersection was empty: 516/516 records failed validation. Nothing caught it
because nothing had ever fed the shipped gold to the shipped CLI.

The tests below close that loop three ways:

1. the shipped gold validates against the CLI's input schema (``test_*_validates``);
2. it scores end-to-end through the real tier-4 scorer, self-against-self, and
   a perfect prediction earns F1 == 1.0 (``test_*_scores_end_to_end``);
3. an imperfect prediction is actually penalised, so (2) cannot pass by the
   scorer silently ignoring every record (``test_*_detects_a_miss``).

Test 3 matters more than it looks: an enum that accepted the records but a
scorer that dropped them would satisfy 1 and 2 while remaining just as broken.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from masoretic_eval.tier4_vocabulary import TIER4_TYPES
from masoretic_eval.tiers.tier4_metamarks import Tier4MetaMarks
from masoretic_eval.uxlc_loader import MetaMarkRecord

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CONSENSUS_GOLD = _REPO_ROOT / "iaa_data" / "devarim_4folio" / "consensus_gold_positional.json"
_SCORER_INPUT_SCHEMA = _REPO_ROOT / "masoretic_eval" / "schemas" / "scorer_input.schema.json"


def _load_consensus_gold() -> dict:
    return json.loads(_CONSENSUS_GOLD.read_text(encoding="utf-8"))


def _as_scorer_input(gold: dict) -> dict:
    """Project the positional gold into the CLI's documented input shape.

    The gold nests tier-4 records under each verse
    (``verses[].tier4_positional[]`` with the ``verse_ref`` on the verse); the
    scorer input carries a flat ``metamarks[]`` with ``verse_ref`` on each
    record. That reshaping is mechanical and is the only transformation
    applied here — in particular no type is renamed, because the point of the
    test is that no renaming should be necessary.
    """
    return {
        "text": " ".join(v["chunk"] for v in gold["verses"]),
        "metamarks": [
            {"type": rec["type"], "verse_ref": verse["verse_ref"], "ordinal": rec["ordinal"]}
            for verse in gold["verses"]
            for rec in verse.get("tier4_positional", [])
        ],
    }


def _as_records(scorer_input: dict) -> list[MetaMarkRecord]:
    return [
        MetaMarkRecord(type=m["type"], verse_ref=m["verse_ref"], ordinal=m["ordinal"])
        for m in scorer_input["metamarks"]
    ]


@pytest.fixture(scope="module")
def scorer_input() -> dict:
    return _as_scorer_input(_load_consensus_gold())


def test_consensus_gold_validates_against_the_cli_input_schema(scorer_input: dict) -> None:
    """Every shipped tier-4 record is a legal CLI input. Regression for 516/516."""
    schema = json.loads(_SCORER_INPUT_SCHEMA.read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema).iter_errors(scorer_input))

    assert not errors, "shipped consensus gold rejected by the scorer input schema:\n" + "\n".join(
        f"  {list(e.path)}: {e.message}" for e in errors[:10]
    )


def test_every_shipped_type_is_in_the_canonical_vocabulary(scorer_input: dict) -> None:
    shipped = {m["type"] for m in scorer_input["metamarks"]}

    assert shipped, "fixture produced no tier-4 records — the test is not exercising anything"
    assert shipped <= set(TIER4_TYPES), (
        f"shipped gold uses types outside the canonical vocabulary: "
        f"{sorted(shipped - set(TIER4_TYPES))}"
    )


def test_consensus_gold_scores_end_to_end_against_itself(scorer_input: dict) -> None:
    """Self-against-self must be a perfect score, not an empty one."""
    records = _as_records(scorer_input)
    result = Tier4MetaMarks().score(records, records)

    assert len(records) == 516, f"expected the frozen 516 gold records, got {len(records)}"
    assert result.f1 == pytest.approx(1.0)


def test_scorer_actually_penalises_a_missed_mark(scorer_input: dict) -> None:
    """Guard against a scorer that 'passes' by ignoring tier-4 entirely.

    Without this, a no-op scorer would satisfy the perfect-score test above.
    """
    records = _as_records(scorer_input)
    result = Tier4MetaMarks().score(records, records[:-1])

    assert result.f1 < 1.0, "dropping a gold record did not lower F1 — is tier 4 being scored?"
