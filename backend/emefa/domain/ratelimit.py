"""Failure-based rate limiting for code-guarded endpoints."""

from __future__ import annotations

import time
from collections import deque

GLOBAL_KEY = "*"


class FailureLimiter:
    """Blocks a key (and the whole instance) after repeated failures in a window.

    Only failed attempts count, so legitimate users are never throttled.
    State is in-process, which matches the single-container deployment; the
    global bucket bounds distributed attempts across source addresses.
    """

    def __init__(
        self,
        max_failures: int,
        window_seconds: int,
        global_max_failures: int | None = None,
        clock=time.monotonic,
    ) -> None:
        if max_failures < 1 or window_seconds < 1:
            raise ValueError("max_failures and window_seconds must be positive")
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.global_max_failures = global_max_failures or max_failures * 4
        self._clock = clock
        self._failures: dict[str, deque[float]] = {}

    def _prune(self, key: str) -> deque[float]:
        bucket = self._failures.setdefault(key, deque())
        horizon = self._clock() - self.window_seconds
        while bucket and bucket[0] < horizon:
            bucket.popleft()
        if not bucket and key != GLOBAL_KEY:
            del self._failures[key]
            return deque()
        return bucket

    def allow(self, key: str) -> bool:
        if len(self._prune(GLOBAL_KEY)) >= self.global_max_failures:
            return False
        return len(self._prune(key)) < self.max_failures

    def record_failure(self, key: str) -> None:
        now = self._clock()
        self._failures.setdefault(key, deque()).append(now)
        self._failures.setdefault(GLOBAL_KEY, deque()).append(now)
