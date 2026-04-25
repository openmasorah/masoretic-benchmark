"""LLM replay log writer + replay-mode reader (D-10).

Per D-10:
  - Every LLM call writes ONE record to results/llm_vision/<folio_id>/llm_calls.jsonl
  - Image bytes are referenced by sha256, NOT inlined (request carries
    ``image_bytes_ref: "sha256:..."``).
  - Replay mode (``replay=True``) RAISES on hash miss; never silently falls
    through to a live API call.
  - Record shape: ``{prompt_hash, request, response, response_id,
                       model_version_returned, token_counts, finish_reason,
                       timestamp}``.

Atomic append via ``os.O_APPEND | os.O_CREAT`` (PIPE_BUF-safe) — reuses the
pattern from ``oracles/_audit.py``. No fcntl, no lock files.

The replay log is the substrate for the contamination unit test (Plan 03-08)
which greps the recorded ``request.prompt`` field for any UXLC fragment
(D-05 boundary).
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

PIPE_BUF = 4096


class ReplayMissError(Exception):
    """Replay-mode hash not found in log file. NEVER falls through to a
    live call (D-10 contract)."""


def canonical_prompt_hash(request: dict) -> str:
    """sha256 of the canonical-JSON-encoded request.

    Canonicalization: ``json.dumps(request, sort_keys=True, ensure_ascii=False)``
    encoded as UTF-8. The replay reader re-derives this hash on lookup, so the
    request dict must be reproducible byte-equal across runs.
    """
    canonical = json.dumps(request, sort_keys=True, ensure_ascii=False).encode(
        "utf-8"
    )
    return hashlib.sha256(canonical).hexdigest()


def _iter_records(log_path: Path) -> Iterator[dict]:
    """Yield JSON records from `log_path`. Empty/missing file yields nothing."""
    if not log_path.exists():
        return
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _atomic_append(log_path: Path, record: dict) -> None:
    """Append a single JSONL record atomically.

    POSIX guarantees write atomicity for buffers smaller than PIPE_BUF
    (4096 bytes) on a single ``os.write()`` call against an O_APPEND fd.
    Records exceeding PIPE_BUF lose this guarantee; we raise rather than
    fall back silently.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = (
        json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    if len(line) >= PIPE_BUF:
        raise RuntimeError(
            f"D-10 replay record exceeds PIPE_BUF ({len(line)} >= {PIPE_BUF}); "
            f"split image bytes by reference (not inlined)."
        )
    flags = (
        os.O_APPEND | os.O_CREAT | os.O_WRONLY | getattr(os, "O_CLOEXEC", 0)
    )
    fd = os.open(log_path, flags, 0o644)
    try:
        n = os.write(fd, line)
        if n != len(line):
            raise RuntimeError(f"short write {n}/{len(line)} on {log_path}")
    finally:
        os.close(fd)


def llm_call_with_replay(
    *,
    client_fn: Callable[..., Any],
    request: dict,
    replay_log: Path,
    replay: bool,
    extract_response_meta: Callable[[Any], dict],
) -> dict:
    """Single entry point for any LLM call in BL-01.

    Args:
        client_fn: Callable that takes ``**request`` kwargs and returns the
            provider's raw response object (anthropic.types.Message OR
            google.genai.types.GenerateContentResponse).
        request: Canonical request dict — MUST include
            ``image_bytes_ref: "sha256:..."`` where image bytes are
            referenced by sha256, NOT inlined as base64 (D-10).
        replay_log: Path to ``<folio_dir>/llm_calls.jsonl``. Created if needed.
        replay: If True, look up the prompt_hash in the log; raise
            ReplayMissError on miss. NEVER falls through to a live call.
        extract_response_meta: Callable that extracts
            ``{response, response_id, model_version_returned, token_counts,
            finish_reason}`` from the provider's raw response (different
            shape per provider).

    Returns:
        ``{response, response_id, model_version_returned, token_counts,
            finish_reason}`` — provider-agnostic meta dict.
    """
    prompt_hash = canonical_prompt_hash(request)

    if replay:
        for rec in _iter_records(replay_log):
            if rec["prompt_hash"] == prompt_hash:
                return {
                    "response":               rec["response"],
                    "response_id":            rec.get("response_id"),
                    "model_version_returned": rec.get("model_version_returned"),
                    "token_counts":           rec.get("token_counts"),
                    "finish_reason":          rec.get("finish_reason"),
                }
        raise ReplayMissError(
            f"D-10 replay miss: prompt_hash {prompt_hash} not in {replay_log}"
        )

    raw = client_fn(**request)
    meta = extract_response_meta(raw)
    record = {
        "prompt_hash":            prompt_hash,
        "request":                request,
        "response":               meta["response"],
        "response_id":            meta.get("response_id"),
        "model_version_returned": meta.get("model_version_returned"),
        "token_counts":           meta.get("token_counts"),
        "finish_reason":          meta.get("finish_reason"),
        "timestamp":              datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ),
    }
    _atomic_append(replay_log, record)
    return meta
