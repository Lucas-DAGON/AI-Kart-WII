from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class Frame:
    image: np.ndarray  # H x W x 3, BGR, uint8
    index: int  # grab counter
    timestamp_ns: int  # time.perf_counter_ns() right after the grab

    @property
    def size(self) -> tuple[int, int]:
        return int(self.image.shape[1]), int(self.image.shape[0])
