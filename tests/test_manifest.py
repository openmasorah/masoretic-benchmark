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
