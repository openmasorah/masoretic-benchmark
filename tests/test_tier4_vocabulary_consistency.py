"""The four tier-4 vocabulary sites must not drift apart again.

``masoretic_eval/tier4_vocabulary.py`` is the single definition. The JSON
Schemas duplicate it because JSON Schema has no way to import a Python tuple;
these tests are what makes that duplication safe. If someone edits an enum in
one schema and not the other — the exact failure mode that produced the
scorer/data divergence fixed in 0.3.0 — this file fails.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from masoretic_eval.tier4_vocabulary import (
    CATALOG_ONLY_MARKS,
    DEPRECATED_ALIASES,
    MANUSCRIPT_MARK_TYPES,
    TIER4_TYPES,
    canonicalize,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCORER_INPUT_SCHEMA = _REPO_ROOT / "masoretic_eval" / "schemas" / "scorer_input.schema.json"
_BASELINE_PREDICTION_SCHEMA = _REPO_ROOT / "schemas" / "baseline_prediction.schema.json"
_MANUSCRIPT_SCHEMA = _REPO_ROOT / "schemas" / "manuscript.schema.json"
_MANUSCRIPTS_YAML = _REPO_ROOT / "corpus" / "manuscripts.yaml"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_scorer_input_enum_matches_canonical_vocabulary() -> None:
    enum = _json(_SCORER_INPUT_SCHEMA)["properties"]["metamarks"]["items"]["properties"]["type"][
        "enum"
    ]

    assert enum == list(TIER4_TYPES)


def test_baseline_prediction_enum_matches_canonical_vocabulary() -> None:
    schema = _json(_BASELINE_PREDICTION_SCHEMA)
    enum = _find_tier4_type_enum(schema)

    assert enum == list(TIER4_TYPES)


def test_manuscript_mark_type_enum_is_the_canonical_superset() -> None:
    enum = _json(_MANUSCRIPT_SCHEMA)["$defs"]["mark_type_enum"]["enum"]

    assert enum == list(MANUSCRIPT_MARK_TYPES)
    assert set(TIER4_TYPES) <= set(enum), "catalog enum must admit every scorable record type"


def test_manuscripts_yaml_uses_only_canonical_terms() -> None:
    entries = yaml.safe_load(_MANUSCRIPTS_YAML.read_text(encoding="utf-8"))
    used: set[str] = set()
    _collect_mark_types(entries, used)

    assert used, "found no mark_types_* keys — this guard is not exercising anything"
    assert used <= set(MANUSCRIPT_MARK_TYPES), (
        f"corpus/manuscripts.yaml uses non-canonical mark types: "
        f"{sorted(used - set(MANUSCRIPT_MARK_TYPES))}"
    )


def test_no_deprecated_spelling_survives_in_any_enum() -> None:
    """'reversednun' and 'puncta' must be gone from every shipped enum."""
    retired = set(DEPRECATED_ALIASES)
    for path, enum in (
        (
            _SCORER_INPUT_SCHEMA,
            _json(_SCORER_INPUT_SCHEMA)["properties"]["metamarks"]["items"]["properties"]["type"][
                "enum"
            ],
        ),
        (_BASELINE_PREDICTION_SCHEMA, _find_tier4_type_enum(_json(_BASELINE_PREDICTION_SCHEMA))),
        (_MANUSCRIPT_SCHEMA, _json(_MANUSCRIPT_SCHEMA)["$defs"]["mark_type_enum"]["enum"]),
    ):
        assert not (retired & set(enum)), f"{path.name} still lists a retired spelling"


def test_vocabulary_has_no_duplicates() -> None:
    assert len(set(TIER4_TYPES)) == len(TIER4_TYPES)
    assert len(set(MANUSCRIPT_MARK_TYPES)) == len(MANUSCRIPT_MARK_TYPES)
    assert not (set(TIER4_TYPES) & set(CATALOG_ONLY_MARKS))


@pytest.mark.parametrize(("retired", "canonical"), sorted(DEPRECATED_ALIASES.items()))
def test_canonicalize_migrates_retired_spellings(retired: str, canonical: str) -> None:
    assert canonicalize(retired) == canonical
    assert canonical in TIER4_TYPES


def test_canonicalize_rejects_unknown_types() -> None:
    with pytest.raises(ValueError, match="unknown tier-4 mark type"):
        canonicalize("not_a_mark")


def test_uxlc_loader_emits_only_canonical_types() -> None:
    """The loader's tag and x-code maps are inside the vocabulary."""
    from masoretic_eval.uxlc_loader import _TAG_TO_TYPE, META_MARK_TAGS, _xcode_to_type

    emitted = {_TAG_TO_TYPE.get(tag, tag) for tag in META_MARK_TAGS}
    emitted |= {t for code in "45678" if (t := _xcode_to_type(code)) is not None}

    assert emitted <= set(TIER4_TYPES), (
        f"loader emits non-canonical types: {sorted(emitted - set(TIER4_TYPES))}"
    )


# --- helpers ---------------------------------------------------------------


def _find_tier4_type_enum(schema: dict) -> list[str]:
    """Locate the tier-4 record ``type`` enum inside a nested schema."""
    found: list[list[str]] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            props = node.get("properties")
            if (
                isinstance(props, dict)
                and {"type", "verse_ref", "ordinal"} <= set(props)
                and isinstance(props["type"], dict)
                and "enum" in props["type"]
            ):
                found.append(props["type"]["enum"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)
    assert len(found) == 1, f"expected exactly one tier-4 type enum, found {len(found)}"
    return found[0]


def _collect_mark_types(node: object, out: set[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("mark_types_covered", "mark_types_excluded") and isinstance(value, list):
                out.update(v for v in value if isinstance(v, str))
            else:
                _collect_mark_types(value, out)
    elif isinstance(node, list):
        for value in node:
            _collect_mark_types(value, out)
