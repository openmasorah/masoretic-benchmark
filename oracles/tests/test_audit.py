import json
import threading
from datetime import UTC, datetime

from oracles._audit import PIPE_BUF, _audit_path_for, append_audit_record


def _sample_record():
    return dict(
        ts_iso="2026-05-12T14:32:01.123Z",
        endpoint_url="https://nakdan-u1-0.loadbalancer.dicta.org.il/api",
        resolved_ip="44.220.229.181",
        request_sha256="a" * 64,
        request_bytes=247,
        response_status=200,
        response_sha256="f" * 64,
        response_bytes=893,
        latency_ms=412,
        throttle_wait_ms=0,
        scorer_run_id="run_2026-05-12_abc123",
        folio_id="leningrad_devarim_f195A",
    )


def test_record_under_pipe_buf():
    rec = _sample_record()
    encoded = (json.dumps(rec, sort_keys=True) + "\n").encode("utf-8")
    assert len(encoded) < PIPE_BUF, f"D-16 record must fit in PIPE_BUF; got {len(encoded)}"


def test_append_writes_valid_jsonl(tmp_path, monkeypatch):
    monkeypatch.setattr("oracles._audit._AUDIT_DIR", tmp_path / "audit")
    path = append_audit_record(**_sample_record())
    assert path.exists()
    line = path.read_text().strip()
    parsed = json.loads(line)
    assert parsed["folio_id"] == "leningrad_devarim_f195A"


def test_concurrent_appends_no_corruption(tmp_path, monkeypatch):
    monkeypatch.setattr("oracles._audit._AUDIT_DIR", tmp_path / "audit")

    def worker():
        for _ in range(100):
            append_audit_record(**_sample_record())

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    path = _audit_path_for(datetime(2026, 5, 12, tzinfo=UTC))
    lines = path.read_text().splitlines()
    assert len(lines) == 1000
    for line in lines:
        json.loads(line)  # raises if any line is corrupted
