"""Fixed-window, in-memory rate limiter.

Scope: one API process. Each Uvicorn worker keeps its own counters, so the effective
limit is multiplied by the worker count. Replace with a shared store before scaling out.
"""

import math
import time
from collections.abc import Callable

from app.core.errors import ApiError


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic, max_keys: int = 50_000):
        self._clock = clock
        self._max_keys = max_keys
        self._windows: dict[str, tuple[float, int]] = {}

    def hit(self, key: str, limit: int, window_seconds: int) -> None:
        """Count one request for key; raise 429 once the window's limit is exceeded."""
        now = self._clock()
        started, count = self._windows.get(key, (now, 0))
        if now - started >= window_seconds:
            started, count = now, 0
        count += 1
        if len(self._windows) >= self._max_keys and key not in self._windows:
            self._evict(now, window_seconds)
        self._windows[key] = (started, count)
        if count > limit:
            retry_after = max(1, math.ceil(started + window_seconds - now))
            raise ApiError(
                429,
                "RATE_LIMITED",
                "Too many requests. Try again later.",
                retryable=True,
                headers={"Retry-After": str(retry_after)},
            )

    def reset(self, key: str) -> None:
        self._windows.pop(key, None)

    def _evict(self, now: float, window_seconds: int) -> None:
        expired = [k for k, (start, _) in self._windows.items() if now - start >= window_seconds]
        for key in expired:
            del self._windows[key]
        if len(self._windows) >= self._max_keys:
            # Still full of active keys: drop the oldest windows to bound memory.
            for key, _ in sorted(self._windows.items(), key=lambda item: item[1][0])[
                : self._max_keys // 10
            ]:
                del self._windows[key]
