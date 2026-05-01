import hashlib
import json
from pathlib import Path

import pytest

from masoretic_eval.manifest import Manifest, ManifestValidationError

FIXTURE = Path(__file__).parent / "fixtures" / "phase_0_manifest_sample.json"


def test_load_manifest():
    m = Manifest.load(FIXTURE)
    assert m.version == "v0.2.0"
    assert len(m.folios) == 2


def test_in_frozen_scope_filter():
    m = Manifest.load(FIXTURE)
    frozen = list(m.frozen_folios())
    assert len(frozen) == 2
    assert all(f.in_frozen_scope for f in frozen)


def test_iaa_folios():
    m = Manifest.load(FIXTURE)
    iaa = list(m.iaa_folios())
    assert [f.id for f in iaa] == ["leningrad_devarim_f237b"]


def test_validate_prediction_coverage_passes_when_all_folios_covered():
    m = Manifest.load(FIXTURE)
    pred_folios = {"leningrad_devarim_f237b", "leningrad_devarim_f238a"}
    m.validate_prediction_coverage(pred_folios)  # no raise


def test_validate_prediction_coverage_fails_on_missing():
    m = Manifest.load(FIXTURE)
    pred_folios = {"leningrad_devarim_f237b"}
    with pytest.raises(ManifestValidationError, match="missing predictions"):
        m.validate_prediction_coverage(pred_folios)


def test_validate_prediction_coverage_fails_on_extra():
    m = Manifest.load(FIXTURE)
    pred_folios = {"leningrad_devarim_f237b", "leningrad_devarim_f238a", "ghost_folio"}
    with pytest.raises(ManifestValidationError, match="unknown folios"):
        m.validate_prediction_coverage(pred_folios)


def test_get_folio_by_id():
    m = Manifest.load(FIXTURE)
    f = m.get_folio("leningrad_devarim_f237b")
    assert f.book == "devarim"
    assert f.iaa_folio is True


def test_manifest_hash_is_stable_16_hex_from_canonical_raw_json(tmp_path):
    raw_doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(raw_doc, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    manifest = Manifest.load(manifest_path)
    expected = hashlib.sha256(
        json.dumps(
            raw_doc,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]

    assert manifest.manifest_hash == expected
    assert len(manifest.manifest_hash) == 16
    assert manifest.manifest_hash == manifest.manifest_hash.lower()
    assert all(c in "0123456789abcdef" for c in manifest.manifest_hash)


def test_manifest_hash_ignores_whitespace_and_top_level_key_order(tmp_path):
    raw_doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    reordered_doc = dict(reversed(list(raw_doc.items())))
    compact_path = tmp_path / "compact.json"
    reordered_path = tmp_path / "reordered.json"
    compact_path.write_text(
        json.dumps(raw_doc, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    reordered_path.write_text(
        json.dumps(reordered_doc, ensure_ascii=False, indent=4),
        encoding="utf-8",
    )

    assert Manifest.load(compact_path).manifest_hash == Manifest.load(
        reordered_path
    ).manifest_hash
