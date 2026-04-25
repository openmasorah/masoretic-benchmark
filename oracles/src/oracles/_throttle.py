"""D-10: 1-QPS token-bucket throttle for the DICTA Nakdan endpoint."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class TokenBucket:
    """Token-bucket throttle with reservation-based concurrency safety.

    Implemented as a "next-available timestamp" rather than a tokens+last
    pair so that contending threads serialize correctly: each ``acquire()``
    call reserves the next slot under the lock, then sleeps until that slot
    arrives. This is the standard fix for the bug where N threads each see
    the same depleted bucket, each compute the same 1-token wait, and sleep
    in parallel — silently violating the QPS contract.

    With ``burst=1.0``: emits at most 1 request per ``1/rate_per_sec``.
    """

    rate_per_sec: float = 1.0
    burst: float = 1.0
    _next_available: float = field(default_factory=time.monotonic)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def acquire(self) -> float:
        """Block until a token is available. Returns wait_ms for audit log."""
        period = 1.0 / self.rate_per_sec
        # Earliest moment the bucket is "as full" as one burst-window again.
        burst_window = self.burst * period
        with self._lock:
            now = time.monotonic()
            # The next available slot is whichever is later: now (if we're
            # idle and within the burst credit) or the previously reserved
            # slot. Burst credit collapses any "now - burst_window" backlog.
            scheduled = max(self._next_available, now - burst_window)
            wait_s = max(0.0, scheduled - now)
            # Reserve THIS slot and advance _next_available by one period.
            self._next_available = scheduled + period
        if wait_s > 0:
            time.sleep(wait_s)
        return wait_s * 1000.0


DICTA_BUCKET = TokenBucket(rate_per_sec=1.0, burst=1.0)
