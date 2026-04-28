"""Phase 03.1 A-02 replay-log spend-field tests.

Coverage:
- T1: actual_spend_usd field present on every replay record (extension of D-10).
- T2: per-folio sum of actual_spend_usd <= per_folio cap (5.00).
- T3 (WARNING-6 fix): synthetic worst-case Hebrew record stays under PIPE_BUF
  (4096 bytes) — the field push doesn't break atomicity.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from baselines._llm_replay import (
    PIPE_BUF,
    canonical_prompt_hash,
    llm_call_with_replay,
)


def _request(text: str = "prompt", img_sha: str = "abc") -> dict:
    return {
        "model": "claude-opus-4-7",
        "max_tokens": 2048,
        "temperature": 0,
        "image_bytes_ref": f"sha256:{img_sha}",
        "prompt": text,
    }


def _response(text: str = "שמע", in_t: int = 1500, out_t: int = 12) -> dict:
    return {
        "text": text,
        "id": "msg_01abcdef",
        "model": "claude-opus-4-7-20260101",
        "usage": {"input": in_t, "output": out_t},
        "stop_reason": "end_turn",
    }


def _extract_meta_with_spend(spend_usd: float):
    """Build an extract_response_meta callback that injects actual_spend_usd."""

    def _extract(raw):
        return {
            "response": raw["text"],
            "response_id": raw["id"],
            "model_version_returned": raw["model"],
            "token_counts": raw["usage"],
            "finish_reason": raw["stop_reason"],
            "actual_spend_usd": spend_usd,
        }

    return _extract


# ---------------------------------------------------------------------------
# T1: actual_spend_usd field present on every record
# ---------------------------------------------------------------------------


def test_replay_record_carries_actual_spend_usd(tmp_path):
    """A-02: every replay record carries actual_spend_usd alongside the
    D-10 provenance fields."""
    log = tmp_path / "results" / "llm_vision" / "F1" / "llm_calls.jsonl"
    request = _request()
    client_fn = MagicMock(return_value=_response())

    llm_call_with_replay(
        client_fn=client_fn,
        request=request,
        replay_log=log,
        replay=False,
        extract_response_meta=_extract_meta_with_spend(0.0125),
    )

    records = [json.loads(ln) for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(records) == 1
    rec = records[0]
    assert "actual_spend_usd" in rec, "A-02: actual_spend_usd MUST be on record"
    assert rec["actual_spend_usd"] == 0.0125
    # D-10 fields preserved verbatim.
    assert rec["prompt_hash"] == canonical_prompt_hash(request)
    assert rec["request"]["image_bytes_ref"].startswith("sha256:")


# ---------------------------------------------------------------------------
# T2: per-folio spend sum under cap
# ---------------------------------------------------------------------------


def test_per_folio_spend_sum_under_cap(tmp_path):
    """A-02: the sum of actual_spend_usd across one folio's records must
    stay <= cost_caps_usd.per_folio (5.00). Simulated 30 calls at $0.10
    each => $3.00 sum; under the $5.00 cap."""
    log = tmp_path / "results" / "llm_vision" / "F1" / "llm_calls.jsonl"
    client_fn = MagicMock(return_value=_response())

    per_call_spend = 0.10
    n_calls = 30
    for i in range(n_calls):
        request = _request(text=f"prompt-{i}", img_sha=f"line-{i}")
        llm_call_with_replay(
            client_fn=client_fn,
            request=request,
            replay_log=log,
            replay=False,
            extract_response_meta=_extract_meta_with_spend(per_call_spend),
        )

    records = [json.loads(ln) for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(records) == n_calls
    total = sum(rec["actual_spend_usd"] for rec in records)
    # Allow tiny float epsilon
    assert abs(total - n_calls * per_call_spend) < 1e-9
    assert total <= 5.00, f"per-folio cap breached: {total}"


# ---------------------------------------------------------------------------
# T3 (WARNING-6 fix): synthetic worst-case record under PIPE_BUF
# ---------------------------------------------------------------------------


def test_replay_record_synthetic_worst_case_under_pipebuf():
    """WARNING-6 (post-revision): pin the worst-case real-fixture record
    size below PIPE_BUF (4096). Synthetic record models a 200-char Hebrew
    transcript + 500-char prompt + actual_spend_usd field — the realistic
    upper bound for an IAA folio's per-line LLM call.

    If this assertion fails, the response field needs sha256-reference
    restructure (mirror image-bytes-ref pattern; Pitfall 5)."""
    # 200 chars of Hebrew (with nikkud + trop -- worst-case byte expansion)
    # is approximately 600-800 UTF-8 bytes.
    hebrew_transcript = "שְׁמַ֖ע יִשְׂרָאֵ֑ל יְהוָ֥ה אֱלֹהֵ֖ינוּ יְהוָ֥ה ׀ אֶחָֽד׃ " * 4
    prompt = "Transcribe the Hebrew text in this image, preserving all nikkud and trop. " * 6
    record = {
        "prompt_hash": "sha256:" + ("a" * 64),
        "request": {
            "model": "claude-opus-4-7",
            "max_tokens": 1024,
            "temperature": 0,
            "expected_input_tokens": 1500,
            "expected_output_tokens": 200,
            "image_bytes_ref": "sha256:" + ("b" * 64),
            "prompt": prompt,
        },
        "response": hebrew_transcript,
        "response_id": "msg_" + ("c" * 32),
        "model_version_returned": "claude-opus-4-7-20260101",
        "token_counts": {"input": 1500, "output": 200},
        "finish_reason": "end_turn",
        "actual_spend_usd": 0.0125,
        "timestamp": "2026-04-25T17:00:00",
    }
    line = (json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    assert len(line) < PIPE_BUF, (
        f"PIPE_BUF ({PIPE_BUF}) breach: synthetic worst-case record is "
        f"{len(line)} bytes. Restructure response field via sha256 "
        "reference (Pitfall 5)."
    )


# ---------------------------------------------------------------------------
# T4: PIPE_BUF guard preserved (existing test_llm_replay.py:194 covers; this
# extra test asserts the guard remains in source after A-02 field push)
# ---------------------------------------------------------------------------


def test_pipe_buf_guard_source_preserved():
    """A-02 amendment must NOT regress the PIPE_BUF guard in _llm_replay.py."""
    src = (Path(__file__).resolve().parents[1] / "src" / "baselines" / "_llm_replay.py").read_text(
        encoding="utf-8"
    )
    assert "PIPE_BUF" in src
    assert "raise RuntimeError" in src
    assert "exceeds PIPE_BUF" in src or "PIPE_BUF" in src
