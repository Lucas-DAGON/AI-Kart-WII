from __future__ import annotations

import time
from typing import Callable


class Pacer:
    """Fixed-rate ticker. If a tick is late it resyncs instead of bursting to catch up."""

    def __init__(
        self,
        hz: float,
        clock: Callable[[], float] = time.perf_counter,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.period = 1.0 / hz
        self._clock, self._sleep = clock, sleep
        self._next = clock() + self.period
        self.overruns = 0

    def wait(self) -> None:
        now = self._clock()
        remaining = self._next - now
        if remaining > 0:
            self._sleep(remaining)
            self._next += self.period
        else:
            self.overruns += 1
            self._next = now + self.period
