"""Sync sliding-window rate limiter.

Used by `FinnhubNewsFetcher` to stay under the free-tier 60 calls/minute
limit. We keep this sync (deliberately not aiolimiter) because the
surrounding code is sync; introducing async just for one fetcher would
infect every caller with `await`.

Single-process CLI — not thread-safe, doesn't need to be.
"""

from __future__ import annotations

import time
from collections import deque


class RateLimiter:
    """Sliding-window: at most `max_calls` per `period_seconds` window.

    `acquire()` blocks (with `time.sleep`) until a slot is available, then
    records the new call. Ordering: token-then-record so back-to-back
    callers can't race past the limit.
    """

    def __init__(
        self,
        max_calls: int,
        period_seconds: float = 60.0,
        *,
        sleep_func: object = None,
    ) -> None:
        if max_calls <= 0:
            raise ValueError("max_calls must be positive")
        if period_seconds <= 0:
            raise ValueError("period_seconds must be positive")
        self._max = max_calls
        self._period = period_seconds
        # `sleep_func` injectable for tests.
        self._sleep = sleep_func or time.sleep
        self._times: deque[float] = deque()

    def acquire(self) -> None:
        now = time.monotonic()
        cutoff = now - self._period
        while self._times and self._times[0] < cutoff:
            self._times.popleft()

        if len(self._times) >= self._max:
            wait = self._period - (now - self._times[0])
            if wait > 0:
                self._sleep(wait)  # type: ignore[operator]
            self._times.popleft()

        self._times.append(time.monotonic())
