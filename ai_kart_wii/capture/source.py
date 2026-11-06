"""Frame sources: real screen capture (mss) and a synthetic one for tests."""

from __future__ import annotations

import logging
import time
from typing import Callable, Protocol

import numpy as np

from ai_kart_wii.capture.frame import Frame
from ai_kart_wii.capture.window import Region, RegionLocator

log = logging.getLogger(__name__)


class FrameSource(Protocol):
    def grab(self) -> Frame | None:
        """Newest frame, or None when the game window cannot be found right now."""

    def close(self) -> None: ...


class MssFrameSource:
    """Screen-region capture with mss. Re-locates the window periodically so moving
    or resizing Dolphin (or switching between borderless and windowed) just works."""

    def __init__(self, locator: RegionLocator, relocate_every: int = 120) -> None:
        import mss  # lazy: only needed for real capture

        self._sct = mss.MSS() if hasattr(mss, "MSS") else mss.mss()
        self._locator = locator
        self._relocate_every = max(1, relocate_every)
        self._region: Region | None = None
        self._grabs = 0
        self._index = 0

    def grab(self) -> Frame | None:
        if self._region is None or self._grabs % self._relocate_every == 0:
            region = self._locator.locate()
            if region is not None and region != self._region:
                log.info("Capture region: %s", region)
            self._region = region
        self._grabs += 1
        if self._region is None:
            return None
        shot = self._sct.grab(
            {"left": self._region.left, "top": self._region.top,
             "width": self._region.width, "height": self._region.height}
        )
        image = np.asarray(shot)[:, :, :3]  # BGRA -> BGR
        self._index += 1
        return Frame(np.ascontiguousarray(image), self._index, time.perf_counter_ns())

    def close(self) -> None:
        self._sct.close()


class SyntheticFrameSource:
    """Deterministic frames for tests: a gradient whose brightness encodes the index."""

    def __init__(self, width: int = 640, height: int = 480, provider: Callable[[int], np.ndarray] | None = None) -> None:
        self.width, self.height = width, height
        self._provider = provider
        self._index = 0

    def grab(self) -> Frame | None:
        self._index += 1
        if self._provider is not None:
            image = self._provider(self._index)
        else:
            image = np.full((self.height, self.width, 3), self._index % 256, dtype=np.uint8)
        return Frame(image, self._index, time.perf_counter_ns())

    def close(self) -> None:
        pass
