"""Unit tests for oracles.compute_oracles (D-21)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_prediction(tmp_path: Path, lines: list[str]) -> Path:
    path = tmp_path / "prediction.json"
    path.write_text(json.dumps({"lines": [{"tier2": ln} for ln in lines]}))
    return path


def test_nakdimon_mean_across_lines(tmp_path, monkeypatch):
    # Three lines with known per-line rates: 0.1, 0.3, 0.5 -> mean 0.3
    rates_iter = iter([(0.1, {}), (0.3, {}), (0.5, {})])
    monkeypatch.setattr(
        "oracles.compute_oracles.nakdimon_oss.disagreement_rate",
        lambda _line: next(rates_iter),
    )
    # DICTA disabled in this test
    monkeypatch.setattr(
        "oracles.compute_oracles.nakdan_hybrid.disagreement_rate",
        lambda _line: (None, {}),
    )
    from oracles.compute_oracles import compute_oracle_rates

    result = compute_oracle_rates(_write_prediction(tmp_path, ["a", "b", "c"]), with_dicta=False)
    assert result["nakdimon_disagreement_rate"] == pytest.approx(0.3, abs=1e-9)
    assert result["dicta_disagreement_rate"] is None
    assert result["audit"]["nakdimon_lines_scored"] == 3
    assert result["audit"]["dicta_lines_scored"] == 0


def test_dicta_mean_excludes_none_failures(tmp_path, monkeypatch):
    # 4 lines, DICTA returns: 0.4, None (failure), 0.6, None (failure)
    # Mean should be (0.4 + 0.6) / 2 = 0.5; failures = 2
    nak_iter = iter([(0.0, {})] * 4)
    dicta_iter = iter([(0.4, {}), (None, {}), (0.6, {}), (None, {})])
    monkeypatch.setattr(
        "oracles.compute_oracles.nakdimon_oss.disagreement_rate",
        lambda _line: next(nak_iter),
    )
    monkeypatch.setattr(
        "oracles.compute_oracles.nakdan_hybrid.disagreement_rate",
        lambda _line: next(dicta_iter),
    )
    from oracles.compute_oracles import compute_oracle_rates

    result = compute_oracle_rates(
        _write_prediction(tmp_path, ["a", "b", "c", "d"]), with_dicta=True
    )
    assert result["dicta_disagreement_rate"] == pytest.approx(0.5, abs=1e-9)
    assert result["audit"]["dicta_failures"] == 2
    assert result["audit"]["dicta_lines_scored"] == 2


def test_all_dicta_failures_returns_none(tmp_path, monkeypatch):
    nak_iter = iter([(0.2, {}), (0.4, {})])
    monkeypatch.setattr(
        "oracles.compute_oracles.nakdimon_oss.disagreement_rate",
        lambda _line: next(nak_iter),
    )
    monkeypatch.setattr(
        "oracles.compute_oracles.nakdan_hybrid.disagreement_rate",
        lambda _line: (None, {"error": "endpoint down"}),
    )
    from oracles.compute_oracles import compute_oracle_rates

    result = compute_oracle_rates(_write_prediction(tmp_path, ["a", "b"]), with_dicta=True)
    assert result["dicta_disagreement_rate"] is None
    assert result["nakdimon_disagreement_rate"] == pytest.approx(0.3, abs=1e-9)
    assert result["audit"]["dicta_failures"] == 2


def test_audit_contains_model_hash_and_timestamp(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "oracles.compute_oracles.nakdimon_oss.disagreement_rate",
        lambda _line: (0.0, {}),
    )
    monkeypatch.setattr(
        "oracles.compute_oracles.nakdimon_oss.MODEL_HASH",
        "deadbeefdeadbeef",
    )
    from oracles.compute_oracles import compute_oracle_rates

    result = compute_oracle_rates(_write_prediction(tmp_path, ["a"]), with_dicta=False)
    assert result["audit"]["model_hash"] == "deadbeefdeadbeef"
    assert "computed_at_iso" in result["audit"]
    assert result["audit"]["computed_at_iso"].endswith("Z")


def test_empty_prediction_returns_zero_rate(tmp_path, monkeypatch):
    from oracles.compute_oracles import compute_oracle_rates

    result = compute_oracle_rates(_write_prediction(tmp_path, []), with_dicta=False)
    assert result["nakdimon_disagreement_rate"] == 0.0
    assert result["audit"]["nakdimon_lines_scored"] == 0


def test_scorer_text_shape_accepted(tmp_path, monkeypatch):
    """D-21 deviation: golden fixture's prediction is {folio_id, text, metamarks}.

    compute_oracle_rates must accept the scorer's prediction shape directly so
    the same function can drive the contract test (Task 2/3) without a separate
    extractor. Treats the single `text` field as a single line.
    """
    monkeypatch.setattr(
        "oracles.compute_oracles.nakdimon_oss.disagreement_rate",
        lambda _line: (0.42, {}),
    )
    monkeypatch.setattr(
        "oracles.compute_oracles.nakdan_hybrid.disagreement_rate",
        lambda _line: (0.55, {}),
    )
    pred_path = tmp_path / "scorer_pred.json"
    pred_path.write_text(
        json.dumps(
            {
                "folio_id": "g_deut_6_4_5",
                "text": "שמע ישראל",
                "metamarks": [],
            }
        )
    )
    from oracles.compute_oracles import compute_oracle_rates

    result = compute_oracle_rates(pred_path, with_dicta=True)
    assert result["nakdimon_disagreement_rate"] == pytest.approx(0.42, abs=1e-9)
    assert result["dicta_disagreement_rate"] == pytest.approx(0.55, abs=1e-9)
    assert result["audit"]["nakdimon_lines_scored"] == 1
    assert result["audit"]["dicta_lines_scored"] == 1
