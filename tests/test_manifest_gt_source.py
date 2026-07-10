"""Tests for the per-folio `gt_source` field (blocker B4) and schema-copy sync.

`gt_hash` is a digest with no stated provenance. D-28 named
`adjudicated_gt_<folio>.json` as canonical GT and it was never produced, so
`gt_hash` is computed over a *derived projection* of
`iaa_data/devarim_4folio/consensus_gold_positional.json`. `gt_source` records
which artifact, at which rev, so the digest is interpretable.

Two properties are load-bearing and easy to regress:

1. `gt_source` must live **per-folio**. The manifest root is
   `additionalProperties: false`, so a top-level `gt_source` hard-fails
   `Manifest.load` -- which breaks the scorer CLI, not just a test.
2. The schema exists in **two copies**. `Manifest.load` validates against the
   package copy (`masoretic_eval/schemas/`), while `audit_release.py` and the
   pre-commit hooks read the repo copy (`schemas/`). Nothing asserted they
   stay in sync. A divergence would mean the loader and the release gate
   enforce different contracts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from masoretic_eval.manifest import Manifest, ManifestValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_SCHEMA = REPO_ROOT / "schemas" / "phase_0_manifest.schema.json"
PKG_SCHEMA = REPO_ROOT / "masoretic_eval" / "schemas" / "phase_0_manifest.schema.json"
MANIFEST = REPO_ROOT / "phase_0_manifest.json"

GT_SOURCE = "iaa_data/devarim_4folio/consensus_gold_positional.json@a9e6ba9"


def _manifest_doc() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _write(tmp_path: Path, doc: dict) -> Path:
    path = tmp_path / "phase_0_manifest.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# The two schema copies must not drift.
# --------------------------------------------------------------------------


def test_schema_copies_are_byte_identical():
    """The loader and the release gate must enforce the same contract."""
    assert REPO_SCHEMA.read_bytes() == PKG_SCHEMA.read_bytes(), (
        "schemas/phase_0_manifest.schema.json and masoretic_eval/schemas/... have "
        "diverged; Manifest.load validates against the package copy while "
        "audit_release.py and pre-commit read the repo copy"
    )


def test_gt_source_is_declared_in_the_schema():
    schema = json.loads(REPO_SCHEMA.read_text(encoding="utf-8"))
    folio_props = schema["properties"]["folios"]["items"]["properties"]
    assert "gt_source" in folio_props, "gt_source must be typed, not merely tolerated"
    assert folio_props["gt_source"]["type"] == ["string", "null"]


# --------------------------------------------------------------------------
# Per-folio accepted; top-level rejected. (B4)
# --------------------------------------------------------------------------


def test_per_folio_gt_source_validates_and_surfaces_on_the_loaded_folio(tmp_path):
    doc = _manifest_doc()
    doc["folios"][0]["gt_source"] = GT_SOURCE

    manifest = Manifest.load(_write(tmp_path, doc))

    assert manifest.folios[0].gt_source == GT_SOURCE
    assert manifest.folios[1].gt_source is None, "must default to None, not crash"


def test_top_level_gt_source_is_rejected(tmp_path):
    """The root is additionalProperties:false. This is why B4 said per-folio."""
    doc = _manifest_doc()
    doc["gt_source"] = GT_SOURCE

    with pytest.raises(ManifestValidationError):
        Manifest.load(_write(tmp_path, doc))


def test_gt_source_absent_is_still_valid(tmp_path):
    """Additive change: today's manifest, with no gt_source anywhere, must load."""
    manifest = Manifest.load(_write(tmp_path, _manifest_doc()))
    assert all(f.gt_source is None for f in manifest.folios)


def test_gt_source_null_is_valid(tmp_path):
    doc = _manifest_doc()
    for folio in doc["folios"]:
        folio["gt_source"] = None
    manifest = Manifest.load(_write(tmp_path, doc))
    assert all(f.gt_source is None for f in manifest.folios)


def test_gt_source_rejects_a_non_string(tmp_path):
    doc = _manifest_doc()
    doc["folios"][0]["gt_source"] = 42
    with pytest.raises(ManifestValidationError):
        Manifest.load(_write(tmp_path, doc))


# --------------------------------------------------------------------------
# The changelog discipline (D-09) is documentation, so pin it.
# --------------------------------------------------------------------------


def test_changelog_records_the_gt_source_addition():
    changelog = (REPO_ROOT / "schemas" / "phase_0_manifest.changelog.md").read_text(
        encoding="utf-8"
    )
    assert "gt_source" in changelog, "schema changes must be documented at bump (D-09)"


# --------------------------------------------------------------------------
# gt_source is immutable once set (append-only invariant).
# --------------------------------------------------------------------------


def test_gt_source_is_in_the_immutable_field_list():
    """A rewritable provenance pointer is not provenance."""
    import sys

    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import manifest_immutable  # noqa: PLC0415

    assert "gt_source" in manifest_immutable.IMMUTABLE_FIELDS
    # gt_hash's own semantics must be unchanged by this addition.
    assert "gt_hash" in manifest_immutable.IMMUTABLE_FIELDS
