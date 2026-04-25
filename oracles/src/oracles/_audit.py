"""D-15 / D-16: atomic JSONL audit append for DICTA calls.

Concurrency safety (Pitfall 7): writes go through os.open(O_APPEND|O_CREAT|O_CLOEXEC)
+ a single os.write() per record. POSIX guarantees write atomicity for buffers
smaller than PIPE_BUF (4096 bytes). We assert serialized record size < 4096.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PIPE_BUF = 4096
_AUDIT_DIR = Path(__file__).resolve().parents[2] / "audit"


def _audit_path_for(ts: datetime) -> Path:
    return _AUDIT_DIR / f"dicta_{ts.strftime('%Y-%m-%d')}.jsonl"


def append_audit_record(**fields: Any) -> Path:
    """Append a single JSONL audit record. Returns the file path written.

    Required D-16 fields: ts_iso, endpoint_url, resolved_ip, request_sha256,
    request_bytes, response_status, response_sha256, response_bytes,
    latency_ms, throttle_wait_ms, scorer_run_id, folio_id.
    """
    if "ts_iso" not in fields:
        fields["ts_iso"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    ts = datetime.fromisoformat(fields["ts_iso"].replace("Z", "+00:00"))
    path = _audit_path_for(ts)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = (json.dumps(fields, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    if len(line) >= PIPE_BUF:
        raise ValueError(f"audit record exceeds PIPE_BUF: {len(line)} >= {PIPE_BUF}")
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(path, flags, 0o644)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)
    return path
