"""JSON Schema validators for prediction + run_meta files (D-16).

Schemas live in the sibling repo's top-level ``schemas/`` directory:

    schemas/baseline_prediction.schema.json
    schemas/run_meta.schema.json

Both at draft-2020-12. Validators are ``jsonschema.Draft202012Validator``
instances, lazy-loaded on first use and cached.

Validation runs at TWO layers per Plan 03-03 design:

1. ``SandboxRun.write_prediction`` / ``write_diagnostic`` / ``write_run_meta``
   call the relevant validator BEFORE the atomic POSIX rename. An off-shape
   payload raises ``jsonschema.ValidationError`` and the corresponding file
   never reaches the sandbox (no ``.tmp`` leftover either) — and therefore
   never reaches ``results/<bl>/``.
2. The ``masoretic_eval`` CLI also validates predictions against the
   prediction schema at score time (Plan 03-08 wires this end).

This module is intentionally tiny: just two pure validators + a small
loader. ``_load_validator`` is ``lru_cache``-d so the second-and-later
calls are O(1).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import jsonschema

# _schema.py lives at .../baselines/src/baselines/_schema.py
#   parents[0] = .../baselines/src/baselines
#   parents[1] = .../baselines/src
#   parents[2] = .../baselines
#   parents[3] = sibling repo root (masoretic-benchmark)
SCHEMAS_DIR = Path(__file__).resolve().parents[3] / "schemas"
PREDICTION_SCHEMA_PATH = SCHEMAS_DIR / "baseline_prediction.schema.json"
RUN_META_SCHEMA_PATH = SCHEMAS_DIR / "run_meta.schema.json"


@lru_cache(maxsize=2)
def _load_validator(schema_path_str: str) -> jsonschema.Draft202012Validator:
    """Load a Draft202012Validator from disk, cache it.

    Takes a string (not a Path) so lru_cache's hash key is stable.
    """
    schema_path = Path(schema_path_str)
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)
    # Defensive: catch broken schemas at first use rather than at every
    # validate() call.
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def validate_prediction(payload: dict) -> None:
    """Validate ``payload`` against ``schemas/baseline_prediction.schema.json``.

    Raises ``jsonschema.ValidationError`` on a shape mismatch. Returns
    ``None`` on success.
    """
    _load_validator(str(PREDICTION_SCHEMA_PATH)).validate(payload)


def validate_run_meta(payload: dict) -> None:
    """Validate ``payload`` against ``schemas/run_meta.schema.json``.

    Raises ``jsonschema.ValidationError`` on a shape mismatch. Returns
    ``None`` on success.
    """
    _load_validator(str(RUN_META_SCHEMA_PATH)).validate(payload)
