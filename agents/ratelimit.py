"""Keep API calls under a provider's requests-per-minute limit."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Awaitable, Callable

WINDOW_SECONDS = 60.0


class RateLimiter:
    """At most `per_minute` calls in any 60-second window, shared by all its users."""

    def __init__(
        self,
        per_minute: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if per_minute < 1:
            raise ValueError("per_minute must be at least 1")
        self.per_minute = per_minute
        self._clock = clock
        self._sleep = sleep
        self._calls: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a call is allowed, then count it."""
        async with self._lock:
            while True:
                now = self._clock()
                while self._calls and now - self._calls[0] >= WINDOW_SECONDS:
                    self._calls.popleft()
                if len(self._calls) < self.per_minute:
                    self._calls.append(now)
                    return
                await self._sleep(WINDOW_SECONDS - (now - self._calls[0]))
