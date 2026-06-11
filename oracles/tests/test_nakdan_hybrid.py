"""Unit + live-oracle tests for oracles.nakdan_hybrid (ORA-02)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import requests
from oracles._errors import OracleMalformed, OracleUnavailable

SAMPLE_RESPONSE = {
    "data": [
        {
            "sep": False,
            "str": "שמע",
            "nakdan": {"word": "שמע", "options": [{"w": "שָׁמַע", "levelChoice": 0}]},
        },
        {"sep": True, "str": " "},
        {
            "sep": False,
            "str": "ישראל",
            "nakdan": {"word": "ישראל", "options": [{"w": "יִשְׂרָאֵל", "levelChoice": 0}]},
        },
    ]
}


def _mock_response(status: int, body: dict | None = None):
    m = MagicMock()
    m.status_code = status
    if body is None:
        m.json.side_effect = ValueError("no body")
    else:
        m.json.return_value = body
    return m


def test_diacritize_happy_path(tmp_path, monkeypatch):
    monkeypatch.setattr("oracles._audit._AUDIT_DIR", tmp_path / "audit")
    monkeypatch.setattr("oracles.nakdan_hybrid.DICTA_BUCKET.acquire", lambda: 0.0)
    monkeypatch.setattr("oracles.nakdan_hybrid._resolve_ip", lambda _u: "44.220.229.181")
    with patch(
        "oracles.nakdan_hybrid.requests.post", return_value=_mock_response(200, SAMPLE_RESPONSE)
    ) as mp:
        from oracles.nakdan_hybrid import diacritize

        out = diacritize("שמע ישראל")
    assert out == "שָׁמַע יִשְׂרָאֵל"
    assert mp.call_count == 1
    # Audit record written
    audit_files = list((tmp_path / "audit").glob("dicta_*.jsonl"))
    assert len(audit_files) == 1
    rec = json.loads(audit_files[0].read_text().strip())
    for key in (
        "ts_iso",
        "endpoint_url",
        "resolved_ip",
        "request_sha256",
        "request_bytes",
        "response_status",
        "response_sha256",
        "response_bytes",
        "latency_ms",
        "throttle_wait_ms",
        "scorer_run_id",
        "folio_id",
    ):
        assert key in rec, f"missing audit field: {key}"
    assert rec["resolved_ip"] == "44.220.229.181"
    assert rec["response_status"] == 200


def test_4xx_raises_oracle_unavailable_no_retry(monkeypatch):
    monkeypatch.setattr("oracles.nakdan_hybrid.DICTA_BUCKET.acquire", lambda: 0.0)
    with patch("oracles.nakdan_hybrid.requests.post", return_value=_mock_response(400)) as mp:
        from oracles.nakdan_hybrid import diacritize

        with pytest.raises(OracleUnavailable, match="HTTP 400"):
            diacritize("שמע")
    assert mp.call_count == 1, "4xx must NEVER retry (D-11)"


def test_5xx_retries_then_succeeds(monkeypatch, tmp_path):
    monkeypatch.setattr("oracles._audit._AUDIT_DIR", tmp_path / "audit")
    monkeypatch.setattr("oracles.nakdan_hybrid.DICTA_BUCKET.acquire", lambda: 0.0)
    monkeypatch.setattr("oracles.nakdan_hybrid._resolve_ip", lambda _u: "1.2.3.4")
    # Speed: shrink tenacity wait by patching wait_exponential with a no-op
    monkeypatch.setattr("oracles.nakdan_hybrid._post.retry.wait", lambda *a, **kw: 0)
    responses = [_mock_response(503), _mock_response(503), _mock_response(200, SAMPLE_RESPONSE)]
    with patch("oracles.nakdan_hybrid.requests.post", side_effect=responses) as mp:
        from oracles.nakdan_hybrid import diacritize

        out = diacritize("שמע ישראל")
    assert mp.call_count == 3
    assert out == "שָׁמַע יִשְׂרָאֵל"


def test_5xx_max_retries_raises_oracle_unavailable(monkeypatch):
    monkeypatch.setattr("oracles.nakdan_hybrid.DICTA_BUCKET.acquire", lambda: 0.0)
    monkeypatch.setattr("oracles.nakdan_hybrid._post.retry.wait", lambda *a, **kw: 0)
    with patch("oracles.nakdan_hybrid.requests.post", return_value=_mock_response(503)) as mp:
        from oracles.nakdan_hybrid import diacritize

        with pytest.raises(OracleUnavailable, match="max retries exhausted"):
            diacritize("שמע")
    assert mp.call_count == 3, "tenacity stop_after_attempt(3) caps at 3 calls"


def test_timeout_retries_then_succeeds(monkeypatch, tmp_path):
    monkeypatch.setattr("oracles._audit._AUDIT_DIR", tmp_path / "audit")
    monkeypatch.setattr("oracles.nakdan_hybrid.DICTA_BUCKET.acquire", lambda: 0.0)
    monkeypatch.setattr("oracles.nakdan_hybrid._resolve_ip", lambda _u: "1.2.3.4")
    monkeypatch.setattr("oracles.nakdan_hybrid._post.retry.wait", lambda *a, **kw: 0)
    side_effects = [requests.Timeout("slow"), _mock_response(200, SAMPLE_RESPONSE)]
    with patch("oracles.nakdan_hybrid.requests.post", side_effect=side_effects) as mp:
        from oracles.nakdan_hybrid import diacritize

        out = diacritize("שמע ישראל")
    assert mp.call_count == 2
    assert "שָׁמַע" in out


def test_malformed_response_raises_oracle_malformed(monkeypatch, tmp_path):
    monkeypatch.setattr("oracles._audit._AUDIT_DIR", tmp_path / "audit")
    monkeypatch.setattr("oracles.nakdan_hybrid.DICTA_BUCKET.acquire", lambda: 0.0)
    with patch(
        "oracles.nakdan_hybrid.requests.post",
        return_value=_mock_response(200, body={"unexpected": "shape"}),
    ):
        from oracles.nakdan_hybrid import diacritize

        with pytest.raises(OracleMalformed):
            diacritize("שמע")


def test_disagreement_rate_returns_none_on_oracle_unavailable(monkeypatch):
    def _raise(_):
        raise OracleUnavailable("HTTP 400")

    monkeypatch.setattr("oracles.nakdan_hybrid.diacritize", _raise)
    from oracles.nakdan_hybrid import disagreement_rate

    rate, meta = disagreement_rate("שָׁמַע")
    assert rate is None
    assert meta["oracle"] == "nakdan_hybrid"
    assert "HTTP 400" in meta["error"]


def test_disagreement_rate_returns_none_on_oracle_malformed(monkeypatch):
    def _raise(_):
        raise OracleMalformed("bad shape")

    monkeypatch.setattr("oracles.nakdan_hybrid.diacritize", _raise)
    from oracles.nakdan_hybrid import disagreement_rate

    rate, meta = disagreement_rate("שָׁמַע")
    assert rate is None
    assert meta["error"].startswith("bad shape")


def test_disagreement_rate_zero_for_perfect_oracle_across_sof_pasuq(monkeypatch):
    """Mirror of the nakdimon_oss ORA-04 fix for the DICTA hybrid oracle.

    A perfect oracle over a multi-verse prediction with a mid-text sof pasuq must
    yield rate 0.0; the prediction must be reduced to the oracle-reproducible
    (tier-2) view before factoring so the standalone sof pasuq cluster does not
    shift every downstream pairing.
    """
    from oracles._strip import strip_to_with_nikkud

    prediction = "שְׁמַע יִשְׂרָאֵל׃ וְאָהַבְתָּ"
    perfect = strip_to_with_nikkud(prediction)
    monkeypatch.setattr("oracles.nakdan_hybrid.diacritize", lambda skeleton: perfect)

    from oracles.nakdan_hybrid import disagreement_rate

    rate, meta = disagreement_rate(prediction)
    assert rate == 0.0, f"perfect oracle gave nonzero rate {rate} (meta={meta})"


def test_throttle_acquire_called_before_post(monkeypatch, tmp_path):
    monkeypatch.setattr("oracles._audit._AUDIT_DIR", tmp_path / "audit")
    monkeypatch.setattr("oracles.nakdan_hybrid._resolve_ip", lambda _u: "1.2.3.4")
    order = []
    monkeypatch.setattr(
        "oracles.nakdan_hybrid.DICTA_BUCKET.acquire", lambda: order.append("acquire") or 0.0
    )

    def _post_observed(*a, **kw):
        order.append("post")
        return _mock_response(200, SAMPLE_RESPONSE)

    with patch("oracles.nakdan_hybrid.requests.post", side_effect=_post_observed):
        from oracles.nakdan_hybrid import diacritize

        diacritize("שמע ישראל")
    assert order == ["acquire", "post"], f"throttle must precede post; got {order}"


@pytest.mark.live_oracles
def test_live_diacritize_smoke(tmp_path, monkeypatch):
    monkeypatch.setattr("oracles._audit._AUDIT_DIR", tmp_path / "audit")
    from oracles.nakdan_hybrid import diacritize

    out = diacritize("שמע ישראל")
    assert isinstance(out, str)
    assert len(out) > 0
    files = list((tmp_path / "audit").glob("dicta_*.jsonl"))
    assert len(files) == 1
    rec = json.loads(files[0].read_text().strip())
    assert rec["response_status"] == 200
    assert rec["resolved_ip"] != "unresolved"
