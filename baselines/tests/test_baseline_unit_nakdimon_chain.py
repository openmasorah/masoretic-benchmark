"""BL-03 BibliaNakdimonBaseline + ChainBaseline mocked unit tests.

Plan 03-05 (Wave 3a). The chain has TWO outputs per folio:

  - Realistic chain (counted toward expected_total_reports):
        results/biblia_nakdimon/<folio>.json
        Kraken consonants -> nakdimon_oss.diacritize -> tier-2/3
  - GT-fed diagnostic (NOT counted; paper-only):
        results/biblia_nakdimon/diagnostic/<folio>.gt_fed.json
        GT consonants -> nakdimon_oss.diacritize -> diagnostic prediction
        (isolates diacritizer error from OCR error per D-01)

Per A-3 (locked): BL-03 imports oracles.nakdimon_oss.diacritize DIRECTLY.
Phase 4 score-time work uses oracles.compute_oracles.compute_oracle_rates;
zero references to that symbol from baselines/ — enforced by Plan 03-08
grep test, asserted here too as a unit-tier defense-in-depth check.

Pitfall 1 (Phase 2 carry-forward): nakdimon==0.1.2 + tensorflow==2.15
SIGABRTs on macOS arm64 + Python 3.11/3.12. THIS test file does NOT
import oracles.nakdimon_oss at module import time — every diacritize
call site is monkeypatched at sys.modules level so the real TF import
is never triggered.
"""

from __future__ import annotations

import ast
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest
from baselines._base import LineRecord

from tests._fake_manifest import FakeFolio, FakeManifest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stub_nakdimon_oss(monkeypatch, fn=lambda s: f"DIAC({s})"):
    """Inject a fake `oracles.nakdimon_oss` into sys.modules BEFORE
    `baselines.biblia_nakdimon` is imported by the test, so the real
    Nakdimon TF stack never loads (Pitfall 1).

    Also returns the fake module so tests can swap fn mid-run.
    """
    fake = ModuleType("oracles.nakdimon_oss")
    fake.diacritize = fn  # type: ignore[attr-defined]
    fake.MODEL_HASH = "8fd7722b8002a690"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "oracles.nakdimon_oss", fake)
    # If oracles itself isn't importable in the test env, give it a stub
    # parent so `from oracles.nakdimon_oss import …` resolves.
    if "oracles" not in sys.modules:
        oracles_pkg = ModuleType("oracles")
        oracles_pkg.__path__ = []  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "oracles", oracles_pkg)
    return fake


def _ctor_chain(cls, tmp_path: Path, manifest: FakeManifest, *, gt_root: Path):
    """Construct a ChainBaseline subclass bypassing real Manifest.load."""
    bl = cls.__new__(cls)
    bl.manifest = manifest
    bl.results_root = tmp_path / "results"
    bl.replay = False
    bl.kraken_model_path = tmp_path / "fake.mlmodel"
    bl.image_cache = tmp_path / "image-cache"
    bl.gt_root = gt_root
    bl._started_at = datetime.now(UTC).isoformat(timespec="seconds")
    bl._folio_meta = {}
    return bl


def _gt_fixture(tmp_path: Path, folio_id: str) -> Path:
    """Write a per-line GT export {lines:[{line_id,bbox,tier1}, …]} for the
    diagnostic chain. Real Phase 1 has only a single-text-blob fixture
    (per Issue 2 fix in plan); the unit tests still exercise the chain
    code path with this synthetic line-level shape.
    """
    gt_dir = tmp_path / "gt"
    gt_dir.mkdir(parents=True, exist_ok=True)
    (gt_dir / f"{folio_id}.json").write_text(
        json.dumps(
            {
                "lines": [
                    {
                        "line_id": f"{folio_id}_L001",
                        "bbox": [10, 20, 500, 60],
                        "tier1": "שמע ישראל",
                    },
                    {
                        "line_id": f"{folio_id}_L002",
                        "bbox": [10, 80, 500, 120],
                        "tier1": "יהוה אלהינו",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return gt_dir


def _kraken_lines(folio_id: str, n: int = 1) -> list[LineRecord]:
    """Synthetic Kraken output for the realistic chain."""
    return [
        LineRecord(
            line_id=f"{folio_id}_L{i + 1:03d}",
            bbox=(10, 20 + i * 60, 500, 60 + i * 60),
            tier1=f"KRAKEN_TEXT_{i + 1}",
            tier2=f"KRAKEN_TEXT_{i + 1}",
            tier3=f"KRAKEN_TEXT_{i + 1}",
            tier4_records=tuple(),
            kraken_confidence=0.85 + 0.01 * i,
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# ChainBaseline contract
# ---------------------------------------------------------------------------


def test_chain_is_abstract_cannot_instantiate(monkeypatch):
    """Test 1 (Task 1): ChainBaseline is an ABC; instantiating it directly
    raises TypeError — diacritize is the abstract method."""
    _stub_nakdimon_oss(monkeypatch)
    from baselines._base import BaselineBase  # noqa: WPS433
    from baselines._chain import ChainBaseline  # noqa: WPS433

    assert issubclass(ChainBaseline, BaselineBase)
    # Abstract: cannot instantiate without overriding diacritize.
    assert "diacritize" in ChainBaseline.__abstractmethods__


def test_chain_does_not_override_run(monkeypatch):
    """Test 2 (Task 1): ChainBaseline does NOT override run() — the locked
    template-method contract holds (D-12 / I-1)."""
    _stub_nakdimon_oss(monkeypatch)
    from baselines._base import BaselineBase  # noqa: WPS433
    from baselines._chain import ChainBaseline  # noqa: WPS433

    assert "run" not in ChainBaseline.__dict__, "D-12: ChainBaseline must NOT override run()"
    assert ChainBaseline.run is BaselineBase.run


# ---------------------------------------------------------------------------
# Two-output pattern (realistic + diagnostic)
# ---------------------------------------------------------------------------


def test_chain_runs_realistic_and_diagnostic(monkeypatch, tmp_path):
    """Test 3 (Task 1) + Tests 1+2 (Task 2): full chain run produces both
    a realistic prediction file (counted) and a GT-fed diagnostic
    (NOT counted by SandboxRun.count())."""
    _stub_nakdimon_oss(monkeypatch)
    from baselines.biblia_nakdimon import BibliaNakdimonBaseline  # noqa: WPS433

    fid = "leningrad_devarim_shema_fixture"
    manifest = FakeManifest(
        folios=[FakeFolio(id=fid)],
        expected_reports_per_baseline={"biblia_nakdimon": 1},
    )
    gt_root = _gt_fixture(tmp_path, fid)

    fake_lines = _kraken_lines(fid, n=2)
    fake_image_path = tmp_path / "image-cache" / f"{fid}.jpg"

    with (
        patch("baselines._chain.recognize_lines", return_value=fake_lines),
        patch("baselines._chain.fetch_image", return_value=fake_image_path),
    ):
        bl = _ctor_chain(BibliaNakdimonBaseline, tmp_path, manifest, gt_root=gt_root)
        rc = bl.run()

    assert rc == 0

    realistic_path = tmp_path / "results" / "biblia_nakdimon" / f"{fid}.json"
    diag_path = tmp_path / "results" / "biblia_nakdimon" / "diagnostic" / f"{fid}.gt_fed.json"
    rm_path = tmp_path / "results" / "biblia_nakdimon" / "run_meta.json"
    assert realistic_path.exists(), "realistic prediction missing"
    assert diag_path.exists(), "GT-fed diagnostic missing"
    assert rm_path.exists()

    realistic = json.loads(realistic_path.read_text(encoding="utf-8"))
    diag = json.loads(diag_path.read_text(encoding="utf-8"))

    # Realistic chain: tier1 = Kraken's noisy text; tier2/3 = diacritized Kraken text
    assert realistic["lines"][0]["tier1"] == "KRAKEN_TEXT_1"
    assert realistic["lines"][0]["tier2"].startswith("DIAC(KRAKEN_TEXT_")
    assert realistic["lines"][0]["tier3"].startswith("DIAC(KRAKEN_TEXT_")
    # Realistic chain preserves Kraken confidence (D-04)
    assert 0.0 <= realistic["lines"][0]["kraken_confidence"] <= 1.0

    # Diagnostic: tier1 = GT consonants; tier2/3 = diacritized GT
    assert diag["lines"][0]["tier1"] == "שמע ישראל"
    assert diag["lines"][0]["tier2"].startswith("DIAC(")
    # Diagnostic does NOT carry kraken_confidence (no Kraken in this stream)
    assert "kraken_confidence" not in diag["lines"][0]


def test_chain_diagnostic_not_counted_toward_expected_total(monkeypatch, tmp_path):
    """Test 4 (Task 2 / D-15): SandboxRun.count() returns ONLY realistic
    predictions; D-15 bit-equality compares against
    expected_reports_per_baseline.biblia_nakdimon and IGNORES the
    diagnostic file. Run must succeed when expected=1 and 1 realistic
    prediction is written, regardless of the diagnostic also being there.
    """
    _stub_nakdimon_oss(monkeypatch)
    from baselines.biblia_nakdimon import BibliaNakdimonBaseline  # noqa: WPS433

    fid = "leningrad_devarim_shema_fixture"
    manifest = FakeManifest(
        folios=[FakeFolio(id=fid)],
        expected_reports_per_baseline={"biblia_nakdimon": 1},
    )
    gt_root = _gt_fixture(tmp_path, fid)

    with (
        patch("baselines._chain.recognize_lines", return_value=_kraken_lines(fid, n=1)),
        patch("baselines._chain.fetch_image", return_value=tmp_path / "fake.jpg"),
    ):
        bl = _ctor_chain(BibliaNakdimonBaseline, tmp_path, manifest, gt_root=gt_root)
        rc = bl.run()

    assert rc == 0
    # Realistic + diagnostic both promoted
    assert (tmp_path / "results" / "biblia_nakdimon" / f"{fid}.json").exists()
    assert (tmp_path / "results" / "biblia_nakdimon" / "diagnostic" / f"{fid}.gt_fed.json").exists()


# ---------------------------------------------------------------------------
# run_meta pin emission
# ---------------------------------------------------------------------------


def test_run_meta_pins_nakdimon_hash_set_others_null(monkeypatch, tmp_path):
    """Test 3 (Task 2): run_meta.pins.nakdimon_model_hash ==
    '8fd7722b8002a690'; kraken_model_hash populated; dictabert + llm null.
    """
    _stub_nakdimon_oss(monkeypatch)
    from baselines._kraken import KRAKEN_MODEL_HASH  # noqa: WPS433
    from baselines.biblia_nakdimon import BibliaNakdimonBaseline  # noqa: WPS433

    fid = "leningrad_devarim_shema_fixture"
    manifest = FakeManifest(
        folios=[FakeFolio(id=fid)],
        expected_reports_per_baseline={"biblia_nakdimon": 1},
    )
    gt_root = _gt_fixture(tmp_path, fid)

    with (
        patch("baselines._chain.recognize_lines", return_value=_kraken_lines(fid)),
        patch("baselines._chain.fetch_image", return_value=tmp_path / "fake.jpg"),
    ):
        bl = _ctor_chain(BibliaNakdimonBaseline, tmp_path, manifest, gt_root=gt_root)
        bl.run()

    rm = json.loads(
        (tmp_path / "results" / "biblia_nakdimon" / "run_meta.json").read_text(encoding="utf-8")
    )
    assert rm["pins"]["nakdimon_model_hash"] == "8fd7722b8002a690"
    assert rm["pins"]["kraken_model_hash"] == KRAKEN_MODEL_HASH
    assert rm["pins"]["dictabert_model_revision"] is None
    assert rm["pins"]["llm_pin_md_hash"] is None
    assert rm["baseline_id"] == "biblia_nakdimon"
    assert fid in rm["folios"]
    assert rm["folios"][fid]["line_count"] == 1


# ---------------------------------------------------------------------------
# A-3 enforcement: zero compute_oracle_rates references in BL-03 + chain
# ---------------------------------------------------------------------------


def test_a3_no_compute_oracle_rates_in_biblia_nakdimon():
    """Test 5 (Task 2 / A-3): biblia_nakdimon.py and _chain.py contain ZERO
    references to oracles.compute_oracles.compute_oracle_rates (or any
    `compute_oracle_rates` symbol). Phase 4 score-time only.

    Defense-in-depth — full enforcement also lives in Plan 03-08's
    contamination grep. Asserting here surfaces the violation in the
    BL-03 unit-tier failure output rather than only in the CI grep job.
    """
    repo = Path(__file__).resolve().parents[2]
    bn = (repo / "baselines" / "src" / "baselines" / "biblia_nakdimon.py").read_text(
        encoding="utf-8"
    )
    chain = (repo / "baselines" / "src" / "baselines" / "_chain.py").read_text(encoding="utf-8")
    assert "compute_oracle_rates" not in bn, (
        "A-3 violation: biblia_nakdimon.py references compute_oracle_rates; "
        "production baselines call diacritize() directly. Phase 4 score-time only."
    )
    assert "compute_oracle_rates" not in chain, (
        "A-3 violation: _chain.py references compute_oracle_rates; "
        "production baselines call diacritize() directly. Phase 4 score-time only."
    )


def test_biblia_nakdimon_imports_diacritize_directly():
    """Test 5 corollary: biblia_nakdimon.py imports diacritize from
    oracles.nakdimon_oss directly (per A-3 / D-21 revised)."""
    repo = Path(__file__).resolve().parents[2]
    src = (repo / "baselines" / "src" / "baselines" / "biblia_nakdimon.py").read_text(
        encoding="utf-8"
    )
    assert "from oracles.nakdimon_oss import diacritize" in src, (
        "A-3: biblia_nakdimon.py must import diacritize directly from oracles.nakdimon_oss"
    )


# ---------------------------------------------------------------------------
# GT-loader behavior
# ---------------------------------------------------------------------------


def test_load_gt_consonants_raises_when_missing(monkeypatch, tmp_path):
    """Test 4 (Task 1): _load_gt_consonants raises BaselineError when no
    GT file exists for the folio (instead of silently fabricating)."""
    _stub_nakdimon_oss(monkeypatch)
    from baselines._errors import BaselineError  # noqa: WPS433
    from baselines.biblia_nakdimon import BibliaNakdimonBaseline  # noqa: WPS433

    fid = "leningrad_devarim_shema_fixture"
    manifest = FakeManifest(
        folios=[FakeFolio(id=fid)],
        expected_reports_per_baseline={"biblia_nakdimon": 1},
    )
    empty_gt = tmp_path / "empty-gt"
    empty_gt.mkdir()

    bl = _ctor_chain(BibliaNakdimonBaseline, tmp_path, manifest, gt_root=empty_gt)
    folio = manifest.frozen_leningrad_folios()[0]
    with pytest.raises(BaselineError, match=r"D-01"):
        bl._load_gt_consonants(folio)


# ---------------------------------------------------------------------------
# Subclass contract — only diacritize() and class attrs are overridden
# ---------------------------------------------------------------------------


def test_biblia_nakdimon_overrides_only_diacritize_and_class_attrs():
    """Plan must_have: BibliaNakdimonBaseline subclass overrides ONLY
    diacritize() (no infer_folio override; no run override; no
    _compose_run_meta override).
    """
    repo = Path(__file__).resolve().parents[2]
    src_path = repo / "baselines" / "src" / "baselines" / "biblia_nakdimon.py"
    tree = ast.parse(src_path.read_text(encoding="utf-8"))
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    assert len(classes) == 1
    cls = classes[0]
    assert cls.name == "BibliaNakdimonBaseline"
    method_names = [c.name for c in cls.body if isinstance(c, ast.FunctionDef)]
    # The only method definition allowed is diacritize.
    assert method_names == ["diacritize"], (
        f"BibliaNakdimonBaseline must override ONLY diacritize(); found: {method_names!r}"
    )
    # Class attrs MUST set BASELINE_ID, DIACRITIZER_PIN_FIELD, DIACRITIZER_PIN_VALUE.
    attr_names: set[str] = set()
    for child in cls.body:
        if isinstance(child, ast.Assign):
            for tgt in child.targets:
                if isinstance(tgt, ast.Name):
                    attr_names.add(tgt.id)
        elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
            attr_names.add(child.target.id)
    for required in (
        "BASELINE_ID",
        "DIACRITIZER_PIN_FIELD",
        "DIACRITIZER_PIN_VALUE",
    ):
        assert required in attr_names, (
            f"BibliaNakdimonBaseline must declare class attr {required!r}"
        )
