"""Reads recorded runs back (video frames + aligned samples)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import cv2
import numpy as np

from ai_kart_wii.recording.format import FRAMES_DIR, META_FILE, SAMPLES_FILE, VIDEO_FILE


class RecordedRun:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.meta: dict[str, Any] = json.loads((self.path / META_FILE).read_text(encoding="utf-8"))

    def samples(self) -> Iterator[dict[str, Any]]:
        with open(self.path / SAMPLES_FILE, encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield json.loads(line)

    def frames(self) -> Iterator[np.ndarray]:
        video = self.path / VIDEO_FILE
        if video.exists():
            capture = cv2.VideoCapture(str(video))
            try:
                while True:
                    ok, image = capture.read()
                    if not ok:
                        return
                    yield image
            finally:
                capture.release()
        else:
            for png in sorted((self.path / FRAMES_DIR).glob("*.png")):
                yield cv2.imread(str(png), cv2.IMREAD_COLOR)

    def __iter__(self) -> Iterator[tuple[np.ndarray | None, dict[str, Any]]]:
        """(frame, sample) pairs; frames only exist for samples with has_frame."""
        frames = self.frames()
        for sample in self.samples():
            yield (next(frames, None) if sample.get("has_frame") else None), sample


def list_runs(runs_dir: str | Path) -> list[Path]:
    return sorted(p.parent for p in Path(runs_dir).glob(f"*/{META_FILE}"))
