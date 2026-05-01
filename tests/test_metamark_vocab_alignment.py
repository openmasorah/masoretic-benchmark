from __future__ import annotations

import json
from pathlib import Path

from masoretic_eval.uxlc_loader import META_MARK_TAGS, _xcode_to_type

REPO_ROOT = Path(__file__).resolve().parents[1]
PREDICTION_SCHEMA_PATH = REPO_ROOT / "schemas" / "baseline_prediction.schema.json"


def test_baseline_schema_tier4_enum_matches_uxlc_loader_vocabulary():
    schema = json.loads(PREDICTION_SCHEMA_PATH.read_text(encoding="utf-8"))
    schema_enum = set(
        schema["properties"]["lines"]["items"]["properties"]["tier4_records"][
            "items"
        ]["properties"]["type"]["enum"]
    )
    loader_vocab = set(META_MARK_TAGS) | {
        mark_type
        for mark_type in (_xcode_to_type(code) for code in ("4", "5", "6", "7", "8"))
        if mark_type is not None
    }

    assert schema_enum == loader_vocab
