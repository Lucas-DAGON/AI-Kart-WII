from __future__ import annotations

import dataclasses
import json
import logging
import time
from pathlib import Path
from typing import Any, Callable, Protocol

import cv2

from ai_kart_wii.recording.format import (
    FRAMES_DIR, META_FILE, SAMPLES_FILE, SCHEMA_VERSION, VIDEO_FILE,
)
from ai_kart_wii.runtime.loop import StepResult

log = logging.getLogger(__name__)


class InputSource(Protocol):
    """Where a *human's* inputs come from while recording imitation data."""

    def read(self) -> dict[str, Any] | None: ...


class MemoryInputSource:
    """Reads StickX/StickY/InputFlags from game memory (slow: GameManager rate).

    Swap for a faster source (e.g. reading the physical pad) once the recording method
    from the wiki article is decided.
    """

    def __init__(self, reader, poller) -> None:
        self.reader, self.poller = reader, poller

    def read(self) -> dict[str, Any] | None:
        from ai_kart_wii.state.resources import RECORDING_INPUT_RESOURCES
        from ai_kart_wii.ipc.errors import GameManagerError

        slot = self.poller.own_slot
        if slot is None:
            return None
        try:
            return self.reader.read_optional(slot, RECORDING_INPUT_RESOURCES)
        except GameManagerError:
            return None


class SessionRecorder:
    def __init__(
        self,
        runs_dir: str | Path,
        track_id: int | None,
        slot: int | None,
        fps: int = 60,
        label: str = "run",
        input_source: InputSource | None = None,
        input_every: int = 6,
        clock: Callable[[], float] = time.time,
    ) -> None:
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(clock()))
        self.dir = Path(runs_dir) / f"{stamp}_track{track_id if track_id is not None else 'x'}_{label}"
        self.dir.mkdir(parents=True, exist_ok=False)
        self.track_id, self.slot, self.fps = track_id, slot, fps
        self.input_source, self.input_every = input_source, max(1, input_every)
        self._samples = open(self.dir / SAMPLES_FILE, "w", encoding="utf-8")
        self._writer: cv2.VideoWriter | None = None
        self._png_mode = False
        self._count = 0
        self._last_human: dict[str, Any] | None = None
        self._write_meta(extra={})

    def _write_meta(self, extra: dict[str, Any]) -> None:
        meta = {
            "schema": SCHEMA_VERSION, "track_id": self.track_id, "slot": self.slot, "fps": self.fps,
            "video": VIDEO_FILE if not self._png_mode else FRAMES_DIR, "frames": self._count, **extra,
        }
        (self.dir / META_FILE).write_text(json.dumps(meta, indent=2), encoding="utf-8")

    def _open_video(self, width: int, height: int) -> None:
        writer = cv2.VideoWriter(str(self.dir / VIDEO_FILE), cv2.VideoWriter_fourcc(*"mp4v"), self.fps, (width, height))
        if writer.isOpened():
            self._writer = writer
            return
        log.warning("mp4 writer unavailable; falling back to PNG frames")
        self._png_mode = True
        (self.dir / FRAMES_DIR).mkdir(exist_ok=True)

    def record(self, step: StepResult) -> None:
        frame = step.observation.frame
        if frame is not None:
            if self._writer is None and not self._png_mode:
                self._open_video(*frame.size)
            if self._png_mode:
                cv2.imwrite(str(self.dir / FRAMES_DIR / f"{self._count + 1:06d}.png"), frame.image)
            else:
                self._writer.write(frame.image)  # type: ignore[union-attr]

        if self.input_source is not None and step.step % self.input_every == 0:
            self._last_human = self.input_source.read()

        state = step.observation.state
        sample = {
            "i": self._count,
            "t_ns": frame.timestamp_ns if frame else None,
            "has_frame": frame is not None,
            "race_frame": state.race_frame if state else None,
            "state_age_ms": round(step.observation.state_age_ms, 2) if state else None,
            "state": state.to_dict() if state else None,
            "action": dataclasses.asdict(step.action) if step.action else None,
            "human": self._last_human,
        }
        self._samples.write(json.dumps(sample) + "\n")
        self._count += 1

    def close(self) -> None:
        self._samples.close()
        if self._writer is not None:
            self._writer.release()
        self._write_meta(extra={"finished": True})
