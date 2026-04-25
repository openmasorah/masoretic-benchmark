"""Secondary oracle: DICTA 2020 hybrid Nakdan API (ORA-02).

Endpoint (verified live 2026-04-24, RESEARCH.md):
  https://nakdan-u1-0.loadbalancer.dicta.org.il/api
  genre=rabbinic, 1 QPS throttle (D-10), 30s timeout + 3 retries on 5xx (D-11),
  4xx never retries.

Non-reproducible by design (D-12, D-20):
  - MODEL_HASH = None
  - No response cache (caveat in masoretic_eval.output_schema is the truth)
  - Endpoint URL is rotating (Pitfall 2): connection errors surface as
    OracleUnavailable; caller emits None per D-13.

Audit (D-15 / D-16): one JSONL record per successful call at
  oracles/audit/dicta_<YYYY-MM-DD>.jsonl
Includes resolved_ip via socket.gethostbyname (D-14) — provenance, not security.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import time
from datetime import UTC, datetime
from urllib.parse import urlparse

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from masoretic_eval.metrics.nakdimon import nakdimon_factoring
from oracles._audit import append_audit_record
from oracles._errors import OracleMalformed, OracleUnavailable
from oracles._strip import strip_to_consonantal
from oracles._throttle import DICTA_BUCKET

ENDPOINT_URL: str = "https://nakdan-u1-0.loadbalancer.dicta.org.il/api"
MODEL_HASH = None  # D-20: DICTA is non-reproducible.
_HEADERS = {
    "Content-Type": "text/plain;charset=UTF-8",
    "Origin": "https://nakdan.dicta.org.il",
}


class _Retryable(Exception):
    """Marker for tenacity: only transport + 5xx retry. 4xx is permanent."""


@retry(
    retry=retry_if_exception_type(_Retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),  # D-11: 1s, 2s, 4s
    reraise=True,
)
def _post(body: dict, timeout: float = 30.0) -> dict:
    """POST to DICTA. Returns parsed JSON or raises OracleUnavailable/Malformed.

    4xx => OracleUnavailable (never retried).
    5xx / transport => _Retryable (up to 3 attempts).
    Final raise on max-retry is _Retryable (caller maps via diacritize wrapper).
    """
    try:
        resp = requests.post(ENDPOINT_URL, headers=_HEADERS, json=body, timeout=timeout)
    except (requests.ConnectionError, requests.Timeout) as exc:
        raise _Retryable(str(exc)) from exc
    if 500 <= resp.status_code < 600:
        raise _Retryable(f"HTTP {resp.status_code}")
    if 400 <= resp.status_code < 500:
        raise OracleUnavailable(f"HTTP {resp.status_code} — permanent, not retried")
    try:
        return resp.json()
    except ValueError as exc:
        raise OracleMalformed(f"non-JSON response: {exc}") from exc


def _resolve_ip(url: str) -> str:
    host = urlparse(url).hostname or ""
    try:
        return socket.gethostbyname(host)
    except OSError:
        return "unresolved"


def _reconstruct(response_json: dict) -> str:
    """Concatenate top-choice diacritization from DICTA response.

    Schema: response['data'] is a list; sep tokens contribute item['str'];
    Nakdan-tagged tokens contribute item['nakdan']['options'][0]['w'].
    """
    if not isinstance(response_json, dict) or "data" not in response_json:
        raise OracleMalformed("response missing 'data' key")
    data = response_json["data"]
    if not isinstance(data, list):
        raise OracleMalformed("response['data'] is not a list")
    out = []
    for tok in data:
        if not isinstance(tok, dict):
            continue
        if tok.get("sep"):
            out.append(tok.get("str", ""))
        else:
            opts = tok.get("nakdan", {}).get("options") or []
            if opts:
                w = opts[0].get("w")
                if isinstance(w, str):
                    out.append(w)
    return "".join(out)


def diacritize(consonantal: str) -> str:
    """Return DICTA's Rabbinic-genre diacritization (ORA-02).

    Raises OracleUnavailable on 4xx / max-retry / transport error;
    OracleMalformed on shape mismatch. Caller catches and emits None.
    """
    body = {
        "task": "nakdan",
        "genre": "rabbinic",
        "data": consonantal,
        "addmorph": True,
        "keepmetagim": True,
        "keepqq": False,
        "nodageshdefmem": False,
        "patachma": False,
        "useTokenization": True,
    }
    wait_ms = DICTA_BUCKET.acquire()
    t0 = time.monotonic()
    try:
        response_json = _post(body)
    except _Retryable as exc:
        # Max-retry exhaustion on 5xx / transport: surface as OracleUnavailable
        # so the caller (disagreement_rate) can emit (None, meta) per D-13.
        raise OracleUnavailable(f"max retries exhausted: {exc}") from exc
    latency_ms = (time.monotonic() - t0) * 1000.0
    out = _reconstruct(response_json)
    body_bytes = json.dumps(body, sort_keys=True).encode("utf-8")
    resp_bytes = json.dumps(response_json, sort_keys=True, ensure_ascii=False).encode("utf-8")
    append_audit_record(
        ts_iso=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        endpoint_url=ENDPOINT_URL,
        resolved_ip=_resolve_ip(ENDPOINT_URL),
        request_sha256=hashlib.sha256(body_bytes).hexdigest(),
        request_bytes=len(body_bytes),
        response_status=200,
        response_sha256=hashlib.sha256(resp_bytes).hexdigest(),
        response_bytes=len(resp_bytes),
        latency_ms=int(latency_ms),
        throttle_wait_ms=int(wait_ms),
        scorer_run_id=os.environ.get("SCORER_RUN_ID", "unknown"),
        folio_id=os.environ.get("SCORER_FOLIO_ID", "unknown"),
    )
    return out


def disagreement_rate(prediction: str) -> tuple[float | None, dict]:
    """Per-line disagreement rate (D-02). Returns (None, meta) on failure (D-13)."""
    skeleton = strip_to_consonantal(prediction)
    try:
        oracle_text = diacritize(skeleton)
    except (OracleUnavailable, OracleMalformed) as exc:
        return None, {"oracle": "nakdan_hybrid", "error": str(exc)}
    result = nakdimon_factoring(prediction, oracle_text)
    return 1.0 - result.dec, {
        "oracle": "nakdan_hybrid",
        "dec": result.dec,
        "model_hash": None,
        "input_cp_count": len(prediction),
        "oracle_cp_count": len(oracle_text),
    }


__all__ = ["diacritize", "disagreement_rate", "MODEL_HASH", "ENDPOINT_URL"]
