"""Tests for v0.2 manifest schema bump (Phase 3 plan 03-01, A-1).

Covers:
- Schema $id is v0.2 and Draft202012Validator accepts it
- Schema validates v0.2 documents and rejects v0.1 documents (missing iaa_subset etc)
- Manifest.load reads BOTH v0.1 and v0.2 documents
- v0.1 reads coerce missing fields to legacy defaults
- v0.2 reads expose new typed fields
- expected_reports_for(baseline_id) precedence rule (Issue 5)
- frozen_leningrad_folios() helper

The legacy v0.1 schema is NOT supplied -- Manifest.load is the dual-read
substrate (per A-1, file is never rewritten on disk; coercion is in-memory).
"""

from __future__ import annotations

# NOTE: "0.1.0" / "v0.1.0" string literals throughout this file are arbitrary
# fixture data validating manifest field-shape roundtripping — they are NOT
# tied to the package masoretic_eval.__version__. Do NOT cascade these when
# bumping the package version. See schemas/run_meta.schema.json schema_version
# description for the package-version vs data-format-version distinction.
import json
from pathlib import Path

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "schemas" / "phase_0_manifest.schema.json"
CHANGELOG_PATH = REPO_ROOT / "schemas" / "phase_0_manifest.changelog.md"


# ---------------------------------------------------------------------------
# Schema-level tests
# ---------------------------------------------------------------------------


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_schema_id_is_v02():
    schema = _load_schema()
    assert schema["$id"] == "urn:masoretic:phase_0_manifest.schema:v0.2", schema["$id"]


def test_schema_passes_draft202012_metaschema():
    schema = _load_schema()
    jsonschema.Draft202012Validator.check_schema(schema)


def test_schema_required_includes_new_fields():
    schema = _load_schema()
    required = set(schema["required"])
    assert {
        "iaa_subset",
        "baselines_seeded",
        "expected_reports_per_baseline",
        "version",
        "frozen_at",
        "folios",
        "scorer_version",
        "expected_total_reports",
        "nakdimon_model_hash",
    } <= required


def test_nakdimon_model_hash_is_required_string_not_nullable():
    schema = _load_schema()
    assert schema["properties"]["nakdimon_model_hash"] == {"type": "string"}


def test_expected_total_reports_oneof_int_or_mapping():
    schema = _load_schema()
    spec = schema["properties"]["expected_total_reports"]
    assert "oneOf" in spec, spec
    shapes = spec["oneOf"]
    int_shape = next(s for s in shapes if s.get("type") == "integer")
    obj_shape = next(s for s in shapes if s.get("type") == "object")
    assert int_shape["minimum"] == 0
    assert obj_shape["additionalProperties"] == {"type": "integer", "minimum": 0}


def test_expected_reports_per_baseline_is_object_of_int():
    schema = _load_schema()
    spec = schema["properties"]["expected_reports_per_baseline"]
    assert spec["type"] == "object"
    assert spec["additionalProperties"] == {"type": "integer", "minimum": 0}


def test_iaa_subset_is_array_of_nonempty_strings():
    schema = _load_schema()
    spec = schema["properties"]["iaa_subset"]
    assert spec["type"] == "array"
    assert spec["items"]["type"] == "string"
    assert spec["items"]["minLength"] == 1


def test_baselines_seeded_enum_locked_to_four_baselines():
    schema = _load_schema()
    spec = schema["properties"]["baselines_seeded"]
    assert spec["type"] == "array"
    assert sorted(spec["items"]["enum"]) == sorted(
        ["llm_vision", "biblia_kraken", "biblia_nakdimon", "biblia_char_menaked"]
    )


def test_schema_validates_a_full_v02_document():
    schema = _load_schema()
    doc = {
        "version": "v0.2.0",
        "frozen_at": "2026-04-25T12:00:00Z",
        "scorer_version": "0.1.0",
        "nakdimon_model_hash": "",
        "expected_total_reports": 1,
        "iaa_subset": [],
        "baselines_seeded": [],
        "expected_reports_per_baseline": {
            "biblia_kraken": 1,
            "biblia_nakdimon": 1,
            "biblia_char_menaked": 1,
            "llm_vision": 1,
        },
        "folios": [
            {
                "id": "leningrad_devarim_F118B_fixture",
                "manuscript": "leningrad",
                "book": "devarim",
                "folio": "F118B",
                "image_url": "https://archive.org/download/leningrad-codex-color/BIB_LENCDX_F118B.jpg",
                "in_frozen_scope": True,
            }
        ],
    }
    jsonschema.validate(doc, schema)  # no raise


def test_schema_validates_actual_root_manifest():
    schema = _load_schema()
    manifest = json.loads((REPO_ROOT / "phase_0_manifest.json").read_text(encoding="utf-8"))
    jsonschema.validate(manifest, schema)  # no raise


def test_schema_rejects_unknown_top_level_fields_in_actual_manifest():
    schema = _load_schema()
    manifest = json.loads((REPO_ROOT / "phase_0_manifest.json").read_text(encoding="utf-8"))
    manifest["unexpected"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(manifest, schema)


def test_schema_rejects_v01_document_missing_iaa_subset():
    schema = _load_schema()
    legacy = {
        "version": "v0.1.0",
        "frozen_at": "2026-04-24T21:24:39Z",
        "scorer_version": "0.1.0",
        "nakdimon_model_hash": "",
        "expected_total_reports": 1,
        "folios": [],
        # missing iaa_subset, baselines_seeded, expected_reports_per_baseline
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(legacy, schema)


def test_schema_accepts_legacy_scalar_form_of_expected_total_reports():
    """oneOf branch: the legacy scalar must still validate."""
    schema = _load_schema()
    doc = {
        "version": "v0.2.0",
        "frozen_at": "2026-04-25T12:00:00Z",
        "scorer_version": "0.1.0",
        "nakdimon_model_hash": "",
        "expected_total_reports": 1,
        "iaa_subset": [],
        "baselines_seeded": [],
        "expected_reports_per_baseline": {},
        "folios": [],
    }
    jsonschema.validate(doc, schema)


def test_schema_accepts_per_baseline_mapping_form_of_expected_total_reports():
    schema = _load_schema()
    doc = {
        "version": "v0.2.0",
        "frozen_at": "2026-04-25T12:00:00Z",
        "scorer_version": "0.1.0",
        "nakdimon_model_hash": "",
        "expected_total_reports": {"biblia_kraken": 1, "llm_vision": 1},
        "iaa_subset": [],
        "baselines_seeded": [],
        "expected_reports_per_baseline": {},
        "folios": [],
    }
    jsonschema.validate(doc, schema)


# ---------------------------------------------------------------------------
# Changelog
# ---------------------------------------------------------------------------


def test_changelog_exists():
    assert CHANGELOG_PATH.exists(), f"missing: {CHANGELOG_PATH}"


def test_changelog_has_v01_to_v02_row():
    text = CHANGELOG_PATH.read_text(encoding="utf-8")
    assert "v0.1 | v0.2" in text, "changelog missing v0.1 -> v0.2 row"


# ---------------------------------------------------------------------------
# Manifest.load — dual-read
# ---------------------------------------------------------------------------

V01_DOC = {
    "version": "v0.1.0",
    "frozen_at": "2026-04-24T21:24:39Z",
    "scorer_version": "0.1.0",
    "nakdimon_model_hash": None,  # v0.1 allowed null
    "expected_total_reports": 1,
    "folios": [
        {
            "id": "leningrad_devarim_F118B_fixture",
            "manuscript": "leningrad",
            "book": "devarim",
            "folio": "F118B",
            "image_url": "https://archive.org/download/leningrad-codex-color/BIB_LENCDX_F118B.jpg",
            "iaa_folio": False,
            "gt_hash": None,
            "in_frozen_scope": True,
        }
    ],
    "baselines": {},
    "fuses_fired": [],
}


V02_DOC = {
    "version": "v0.2.0",
    "frozen_at": "2026-04-25T12:00:00Z",
    "scorer_version": "0.1.0",
    "nakdimon_model_hash": "",
    "expected_total_reports": 1,
    "iaa_subset": [],
    "baselines_seeded": [],
    "expected_reports_per_baseline": {
        "biblia_kraken": 1,
        "biblia_nakdimon": 1,
        "biblia_char_menaked": 1,
        "llm_vision": 1,
    },
    "folios": [
        {
            "id": "leningrad_devarim_F118B_fixture",
            "manuscript": "leningrad",
            "book": "devarim",
            "folio": "F118B",
            "image_url": "https://archive.org/download/leningrad-codex-color/BIB_LENCDX_F118B.jpg",
            "iaa_folio": False,
            "gt_hash": None,
            "in_frozen_scope": True,
        }
    ],
    "baselines": {},
    "fuses_fired": [],
}


def _write(tmp_path: Path, doc: dict, name: str = "manifest.json") -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def test_manifest_load_v01_with_legacy_defaults(tmp_path):
    from masoretic_eval.manifest import Manifest

    path = _write(tmp_path, V01_DOC)
    m = Manifest.load(path)
    assert m.version == "v0.1.0"
    assert m.iaa_subset == []
    assert m.baselines_seeded == []
    assert m.expected_reports_per_baseline == {}
    assert m.nakdimon_model_hash in (None, "")


def test_manifest_load_v02_exposes_new_fields(tmp_path):
    from masoretic_eval.manifest import Manifest

    path = _write(tmp_path, V02_DOC)
    m = Manifest.load(path)
    assert m.version == "v0.2.0"
    assert m.iaa_subset == []
    assert m.baselines_seeded == []
    assert m.expected_reports_per_baseline == {
        "biblia_kraken": 1,
        "biblia_nakdimon": 1,
        "biblia_char_menaked": 1,
        "llm_vision": 1,
    }
    assert m.nakdimon_model_hash == ""


def test_manifest_load_malformed_doc_raises(tmp_path):
    """A malformation NOT covered by v0.1 coercion must raise.

    Coercion only fills in missing iaa_subset/baselines_seeded/
    expected_reports_per_baseline and null nakdimon_model_hash.
    Other malformations (wrong types, missing version, malformed folios)
    must still surface as ManifestValidationError.
    """
    from masoretic_eval.manifest import Manifest, ManifestValidationError

    # Wrong type for version -- not coerceable.
    bad = dict(V02_DOC)
    bad["version"] = 123  # must be string per schema
    path = _write(tmp_path, bad)
    with pytest.raises((ManifestValidationError, jsonschema.ValidationError)):
        Manifest.load(path)

    # Folio missing required field 'image_url' -- not coerceable.
    bad2 = dict(V02_DOC)
    bad2["folios"] = [
        {
            "id": "x",
            "manuscript": "leningrad",
            "book": "devarim",
            "folio": "F118B",
            "in_frozen_scope": True,
            # missing image_url
        }
    ]
    path2 = _write(tmp_path, bad2, "bad2.json")
    with pytest.raises((ManifestValidationError, jsonschema.ValidationError)):
        Manifest.load(path2)


# ---------------------------------------------------------------------------
# expected_reports_for() precedence (Issue 5)
# ---------------------------------------------------------------------------


def test_expected_reports_for_precedence(tmp_path):
    """Per A-1 / Issue 5: per-baseline mapping is canonical when non-empty.

    On a manifest with BOTH expected_total_reports: 99 (legacy scalar) AND
    expected_reports_per_baseline: {"biblia_kraken": 1}, the mapping wins for
    biblia_kraken. A non-mapped baseline (biblia_nakdimon) raises KeyError —
    NEVER silently falls back to the legacy 99. Empty mapping + legacy scalar
    falls back to scalar (v0.1 compat).
    """
    from masoretic_eval.manifest import Manifest

    # Case 1: non-empty mapping wins; absent baseline raises KeyError
    doc = dict(V02_DOC)
    doc["expected_total_reports"] = 99
    doc["expected_reports_per_baseline"] = {"biblia_kraken": 1}
    path = _write(tmp_path, doc, "case1.json")
    m = Manifest.load(path)
    assert m.expected_reports_for("biblia_kraken") == 1
    with pytest.raises(KeyError):
        m.expected_reports_for("biblia_nakdimon")

    # Case 2: empty mapping + legacy scalar -> legacy fallback
    doc2 = dict(V02_DOC)
    doc2["expected_total_reports"] = 1
    doc2["expected_reports_per_baseline"] = {}
    path2 = _write(tmp_path, doc2, "case2.json")
    m2 = Manifest.load(path2)
    assert m2.expected_reports_for("biblia_kraken") == 1


# ---------------------------------------------------------------------------
# frozen_leningrad_folios()
# ---------------------------------------------------------------------------


def test_frozen_leningrad_folios_filters_to_in_scope_leningrad(tmp_path):
    from masoretic_eval.manifest import Manifest

    doc = dict(V02_DOC)
    doc["folios"] = [
        # in-scope leningrad
        {
            "id": "in_scope_len",
            "manuscript": "leningrad",
            "book": "devarim",
            "folio": "F118B",
            "image_url": "https://example.org/a.jpg",
            "iaa_folio": False,
            "gt_hash": None,
            "in_frozen_scope": True,
        },
        # out-of-scope leningrad
        {
            "id": "out_scope_len",
            "manuscript": "leningrad",
            "book": "devarim",
            "folio": "F196A",
            "image_url": "https://example.org/b.jpg",
            "iaa_folio": False,
            "gt_hash": None,
            "in_frozen_scope": False,
        },
        # in-scope cairo (filtered out by manuscript)
        {
            "id": "in_scope_cairo",
            "manuscript": "cairo_shmuel",
            "book": "shmuel",
            "folio": "F001A",
            "image_url": "https://example.org/c.jpg",
            "iaa_folio": False,
            "gt_hash": None,
            "in_frozen_scope": True,
        },
    ]
    path = _write(tmp_path, doc)
    m = Manifest.load(path)
    folios = m.frozen_leningrad_folios()
    assert [f.id for f in folios] == ["in_scope_len"]
