"""T5: `gt_hash` is sha256[:16]. The schema must say so, not merely intend it.

The convention is 16 lowercase hex chars -- the same pin used by `manifest_hash`,
`kraken_model_hash` and `nakdimon_model_hash`. It is **not** a full SHA-256, and
the paper had to retract a claim that it was.

Until this landed, `gt_hash` was typed `["string", "null"]` with no `pattern`, and
`tests/fixtures/phase_0_manifest_sample.json` -- the fixture `docs/GETTING-STARTED.md`
tells readers to run the CLI against -- carried `"gt_hash": "sha256:abc"`. The exact
mislabel the paper retracted, shipped as the worked example, validating cleanly.

A convention that no gate enforces is a convention that drifts.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_SCHEMA = REPO_ROOT / "schemas" / "phase_0_manifest.schema.json"
PKG_SCHEMA = REPO_ROOT / "masoretic_eval" / "schemas" / "phase_0_manifest.schema.json"
SAMPLE = REPO_ROOT / "tests" / "fixtures" / "phase_0_manifest_sample.json"

GT_HASH_PATTERN = "^[0-9a-f]{16}$"


def _folio_gt_hash_schema(path: Path) -> dict:
    schema = json.loads(path.read_text(encoding="utf-8"))
    return schema["properties"]["folios"]["items"]["properties"]["gt_hash"]


@pytest.mark.parametrize("schema_path", [REPO_SCHEMA, PKG_SCHEMA], ids=["repo", "package"])
def test_gt_hash_is_pattern_constrained_in_both_schema_copies(schema_path: Path):
    gt_hash = _folio_gt_hash_schema(schema_path)
    assert gt_hash["pattern"] == GT_HASH_PATTERN
    assert gt_hash["type"] == ["string", "null"], "null must stay legal until the fuse"


def test_the_schema_copies_remain_byte_identical():
    """`Manifest.load` reads the package copy; audit_release + pre-commit read the repo copy."""
    assert REPO_SCHEMA.read_bytes() == PKG_SCHEMA.read_bytes()


@pytest.mark.parametrize(
    "bad",
    [
        "sha256:abc",  # the retracted mislabel, previously live in the sample fixture
        "sha256:" + "a" * 64,
        "a" * 64,  # a full SHA-256 -- the overclaim itself
        "4B7BC5BEA20BB201",  # uppercase
        "4b7bc5bea20bb20",  # 15 chars
        "4b7bc5bea20bb2011",  # 17 chars
        "",
        "deadbeef",
    ],
)
def test_non_conforming_gt_hash_is_rejected(bad: str):
    schema = _folio_gt_hash_schema(REPO_SCHEMA)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(bad)


@pytest.mark.parametrize("good", ["4b7bc5bea20bb201", "349c49877b364686", None])
def test_conforming_gt_hash_and_null_are_accepted(good):
    schema = _folio_gt_hash_schema(REPO_SCHEMA)
    jsonschema.Draft202012Validator(schema).validate(good)


def test_the_sample_fixture_no_longer_ships_the_retracted_label():
    """It is the worked example in docs/GETTING-STARTED.md. It must model the convention."""
    doc = json.loads(SAMPLE.read_text(encoding="utf-8"))
    for folio in doc["folios"]:
        gt_hash = folio.get("gt_hash")
        if gt_hash is None:
            continue
        assert not gt_hash.startswith("sha256:"), (
            f"{folio['id']}: the sample manifest teaches the mislabel the paper retracted"
        )
        assert len(gt_hash) == 16 and set(gt_hash) <= set("0123456789abcdef")
