"""BL-01 Task 2 unit tests: _llm_replay (D-10).

Coverage (per plan 03-07 Task 2 behavior):
- T1: write-mode invokes client_fn + writes one JSONL record with all D-10
      provenance fields; canonical prompt_hash deterministically derived.
- T2: image bytes referenced by sha256 in the persisted record (NOT inlined
      raw bytes).
- T3: replay-mode hit returns logged response WITHOUT calling client_fn.
- T4: replay-mode miss raises ReplayMissError naming the missing hash;
      does NOT fall through to a live call.
- T5: PIPE_BUF guard fires when a record exceeds 4096 bytes.
- T6: canonical_prompt_hash is sort-key invariant (dict reordering ->
      same hash).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from baselines._llm_replay import (
    PIPE_BUF,
    ReplayMissError,
    canonical_prompt_hash,
    llm_call_with_replay,
)


def _extract_meta(raw):
    """Provider-agnostic extractor used by these tests; mirrors the shape
    BL-01 will use (response, response_id, model_version_returned,
    token_counts, finish_reason)."""
    return {
        "response":               raw["text"],
        "response_id":            raw["id"],
        "model_version_returned": raw["model"],
        "token_counts":           raw["usage"],
        "finish_reason":          raw["stop_reason"],
    }


def _fake_request(text="prompt", img_sha="abc123") -> dict:
    return {
        "model":            "claude-opus-4-7",
        "max_tokens":       2048,
        "temperature":      0,
        "image_bytes_ref":  f"sha256:{img_sha}",
        "prompt":           text,
    }


def _fake_response(text="שמע ישראל") -> dict:
    return {
        "text":        text,
        "id":          "msg_01abcdef",
        "model":       "claude-opus-4-7-20260101",
        "usage":       {"input": 1234, "output": 12},
        "stop_reason": "end_turn",
    }


# ----------------------------------------------------------------------
# T1 + T2: write-mode + sha256 reference (not inlined)
# ----------------------------------------------------------------------


def test_replay_write_invokes_client_and_persists_record(tmp_path):
    log = tmp_path / "results" / "llm_vision" / "F1" / "llm_calls.jsonl"
    request = _fake_request()
    client_fn = MagicMock(return_value=_fake_response())

    meta = llm_call_with_replay(
        client_fn=client_fn,
        request=request,
        replay_log=log,
        replay=False,
        extract_response_meta=_extract_meta,
    )

    assert client_fn.call_count == 1
    assert meta["response"] == "שמע ישראל"
    assert log.exists()
    records = [json.loads(ln) for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(records) == 1
    rec = records[0]
    # D-10 required fields
    for field in (
        "prompt_hash",
        "request",
        "response",
        "response_id",
        "model_version_returned",
        "token_counts",
        "finish_reason",
        "timestamp",
    ):
        assert field in rec, field
    # D-10 image-bytes-by-reference (not inlined)
    assert rec["request"]["image_bytes_ref"] == "sha256:abc123"
    assert "image_bytes" not in rec["request"]
    # prompt_hash is canonical-JSON of request
    assert rec["prompt_hash"] == canonical_prompt_hash(request)


# ----------------------------------------------------------------------
# T3: replay-mode hit returns logged response WITHOUT calling client
# ----------------------------------------------------------------------


def test_replay_read_hit_does_not_call_client(tmp_path):
    log = tmp_path / "llm_calls.jsonl"
    request = _fake_request()
    # Seed the log with one prior record.
    seed = MagicMock(return_value=_fake_response("seed-text"))
    llm_call_with_replay(
        client_fn=seed, request=request, replay_log=log,
        replay=False, extract_response_meta=_extract_meta,
    )

    # Now in replay-mode the same request must hit and NOT call client_fn.
    blocked_client = MagicMock(side_effect=AssertionError("must NOT be called"))
    meta = llm_call_with_replay(
        client_fn=blocked_client,
        request=request,
        replay_log=log,
        replay=True,
        extract_response_meta=_extract_meta,
    )
    assert blocked_client.call_count == 0, "D-10: replay must not invoke client_fn"
    assert meta["response"] == "seed-text"
    # Provenance fields preserved through the replay path
    assert meta["model_version_returned"] == "claude-opus-4-7-20260101"
    assert meta["token_counts"] == {"input": 1234, "output": 12}


# ----------------------------------------------------------------------
# T4: replay-mode miss raises ReplayMissError; never falls through
# ----------------------------------------------------------------------


def test_replay_read_miss_raises_replay_miss_error(tmp_path):
    log = tmp_path / "llm_calls.jsonl"
    # Log contains record for request-A; we request request-B.
    request_a = _fake_request(text="prompt-A")
    request_b = _fake_request(text="prompt-B")
    seed = MagicMock(return_value=_fake_response())
    llm_call_with_replay(
        client_fn=seed, request=request_a, replay_log=log,
        replay=False, extract_response_meta=_extract_meta,
    )

    blocked_client = MagicMock(side_effect=AssertionError("must NOT be called"))
    expected_hash = canonical_prompt_hash(request_b)
    with pytest.raises(ReplayMissError, match=expected_hash[:16]):
        llm_call_with_replay(
            client_fn=blocked_client,
            request=request_b,
            replay_log=log,
            replay=True,
            extract_response_meta=_extract_meta,
        )
    assert blocked_client.call_count == 0, "D-10: must not fall through to live call"


def test_replay_read_miss_on_missing_log_file(tmp_path):
    """If the log file doesn't exist at all, replay-mode still raises
    ReplayMissError (NOT FileNotFoundError, NOT a silent fallthrough)."""
    log = tmp_path / "never-created.jsonl"
    blocked_client = MagicMock(side_effect=AssertionError("must NOT be called"))
    request = _fake_request()
    with pytest.raises(ReplayMissError):
        llm_call_with_replay(
            client_fn=blocked_client,
            request=request,
            replay_log=log,
            replay=True,
            extract_response_meta=_extract_meta,
        )
    assert blocked_client.call_count == 0


# ----------------------------------------------------------------------
# T5: PIPE_BUF guard
# ----------------------------------------------------------------------


def test_pipe_buf_guard_fires_on_oversized_record(tmp_path):
    """A record whose serialized bytes >= PIPE_BUF (4096) raises rather
    than silently writing a non-atomic append. This is the substrate for
    'image bytes by reference, not inlined' — if it ever fires, an image
    has been inlined."""
    log = tmp_path / "llm_calls.jsonl"
    huge_response = "א" * (PIPE_BUF // 2)  # multi-byte UTF-8 → > PIPE_BUF
    fake_resp = {
        "text":        huge_response,
        "id":          "x",
        "model":       "x",
        "usage":       {},
        "stop_reason": "end_turn",
    }
    client_fn = MagicMock(return_value=fake_resp)
    with pytest.raises(RuntimeError, match="PIPE_BUF"):
        llm_call_with_replay(
            client_fn=client_fn,
            request=_fake_request(),
            replay_log=log,
            replay=False,
            extract_response_meta=_extract_meta,
        )


# ----------------------------------------------------------------------
# T6: canonical hash is sort-key invariant
# ----------------------------------------------------------------------


def test_canonical_prompt_hash_is_sort_key_invariant():
    """Reordering keys in the request dict yields the same hash — the
    canonical-JSON normalization is what makes replay reproducible."""
    a = {"model": "x", "prompt": "p", "image_bytes_ref": "sha256:abc"}
    b = {"image_bytes_ref": "sha256:abc", "prompt": "p", "model": "x"}
    assert canonical_prompt_hash(a) == canonical_prompt_hash(b)


def test_canonical_prompt_hash_changes_on_request_change():
    """Different requests -> different hashes."""
    a = _fake_request(text="prompt-A")
    b = _fake_request(text="prompt-B")
    assert canonical_prompt_hash(a) != canonical_prompt_hash(b)
