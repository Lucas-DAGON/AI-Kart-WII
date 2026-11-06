"""Item detection from the HUD (the game exposes no readable item slot yet).

Templates: one PNG per item in a folder, file name = item name (e.g. `banana.png`),
cut from the in-game icon at `reference_width` pixels frame width. They are scaled to the
actual frame width at runtime. The HUD item box is searched inside a fractional ROI.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np


@dataclass(frozen=True, slots=True)
class ItemDetection:
    name: str | None  # None = empty item box / not recognised
    score: float


class ItemDetector(Protocol):
    def detect(self, image: np.ndarray) -> ItemDetection: ...


class NullItemDetector:
    def detect(self, image: np.ndarray) -> ItemDetection:
        return ItemDetection(None, 0.0)


class TemplateItemDetector:
    def __init__(
        self,
        template_dir: str | Path,
        roi: tuple[float, float, float, float] = (0.02, 0.02, 0.22, 0.26),  # x0,y0,x1,y1 fractions
        reference_width: int = 640,
        threshold: float = 0.7,
    ) -> None:
        self.roi, self.reference_width, self.threshold = roi, reference_width, threshold
        self.templates: dict[str, np.ndarray] = {}
        for path in sorted(Path(template_dir).glob("*.png")):
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is not None:
                self.templates[path.stem] = image
        self._scaled: dict[tuple[str, int], np.ndarray] = {}

    def _template(self, name: str, frame_width: int) -> np.ndarray:
        key = (name, frame_width)
        cached = self._scaled.get(key)
        if cached is None:
            scale = frame_width / self.reference_width
            base = self.templates[name]
            size = (max(1, int(base.shape[1] * scale)), max(1, int(base.shape[0] * scale)))
            cached = cv2.resize(base, size, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
            self._scaled[key] = cached
        return cached

    def detect(self, image: np.ndarray) -> ItemDetection:
        if not self.templates:
            return ItemDetection(None, 0.0)
        height, width = image.shape[:2]
        x0, y0, x1, y1 = self.roi
        crop = image[int(y0 * height): int(y1 * height), int(x0 * width): int(x1 * width)]
        best_name: str | None = None
        best_score = -1.0
        for name in self.templates:
            template = self._template(name, width)
            if template.shape[0] > crop.shape[0] or template.shape[1] > crop.shape[1]:
                continue
            result = cv2.matchTemplate(crop, template, cv2.TM_CCOEFF_NORMED)
            score = float(result.max())
            if score > best_score:
                best_name, best_score = name, score
        if best_name is None or best_score < self.threshold:
            return ItemDetection(None, max(best_score, 0.0))
        return ItemDetection(best_name, best_score)
