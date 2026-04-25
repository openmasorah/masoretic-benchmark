import threading
import time

from oracles._throttle import TokenBucket


def test_first_acquire_no_wait():
    b = TokenBucket(rate_per_sec=1.0, burst=1.0)
    assert b.acquire() == 0.0


def test_second_immediate_acquire_waits():
    b = TokenBucket(rate_per_sec=1.0, burst=1.0)
    b.acquire()
    wait_ms = b.acquire()
    assert wait_ms >= 900.0, f"expected ~1000ms wait, got {wait_ms}"


def test_concurrent_acquires_respect_qps():
    b = TokenBucket(rate_per_sec=1.0, burst=1.0)
    results = []

    def worker():
        for _ in range(5):
            b.acquire()
            results.append(time.monotonic())

    threads = [threading.Thread(target=worker) for _ in range(10)]
    t0 = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - t0
    assert len(results) == 50
    assert elapsed >= 49.0, f"50 acquires at 1 QPS should take >=49s, got {elapsed:.1f}s"
