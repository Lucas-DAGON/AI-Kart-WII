"""Aligning a DTM (frame-exact inputs) with a separately recorded video.

Both run at ~60 fps but start at different moments. Two ways to line them up:

1. Manual:  video frame v  <->  DTM VI frame v + offset   (offset in frames, may be negative)
2. Automatic (EXPERIMENTAL): steering turns the camera, which shifts the picture
   sideways. We measure the horizontal global image shift between consecutive video
   frames (phase correlation) and cross-correlate it with the stick-X signal from the
   DTM; the lag with the strongest correlation is the offset. Validated on synthetic data
   only; check the result visually before trusting it on real footage.

Most robust option: replay the DTM in Dolphin with *frame dumping* enabled. That produces
one image per VI frame, so image i is exactly DTM frame i and no sync is needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

from ai_kart_wii.recording.dtm import STICK_CENTER, STICK_RADIUS, DtmMovie


def steering_signal(movie: DtmMovie) -> np.ndarray:
    """Stick X per VI frame, -1..1."""
    return np.array([np.clip((p.stick_x - STICK_CENTER) / STICK_RADIUS, -1, 1) for p in movie.frames()], dtype=np.float64)


def horizontal_shift_series(frames: Iterable[np.ndarray], size: tuple[int, int] = (160, 90)) -> np.ndarray:
    """Global horizontal shift (pixels at `size`) between consecutive frames."""
    shifts: list[float] = []
    previous: np.ndarray | None = None
    window = None
    for image in frames:
        gray = cv2.cvtColor(cv2.resize(image, size, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32)
        if window is None:
            window = cv2.createHanningWindow(size, cv2.CV_32F)
        if previous is not None:
            (dx, _dy), _response = cv2.phaseCorrelate(previous, gray, window)
            shifts.append(dx)
        previous = gray
    return np.array([0.0] + shifts, dtype=np.float64)


@dataclass(frozen=True)
class SyncEstimate:
    offset_frames: int  # video frame v corresponds to DTM frame v + offset_frames
    correlation: float  # peak normalised correlation (|r|), 0..1
    sign: int  # +1 / -1: sign of the relation (image shift vs stick), informational
    confidence: float  # peak minus the best correlation at a clearly different lag
    video_start: int = 0
    video_end: int = 0


def _smooth_norm(x: np.ndarray, smooth: int) -> np.ndarray:
    return np.convolve(x - x.mean(), np.ones(smooth) / smooth, mode="same")


def estimate_offset(
    stick: np.ndarray,
    shift: np.ndarray,
    max_offset: int = 1800,
    smooth: int = 9,
    video_start: int = 0,
    video_end: int | None = None,
    min_overlap: int = 120,
) -> SyncEstimate:
    """Find the offset g so that shift[v] ~ f(stick[v + g]) for v in [video_start, video_end).

    The correlation is computed on the overlap only, so partial overlaps are not favoured.
    """
    video_end = len(shift) if video_end is None else min(video_end, len(shift))
    seg = _smooth_norm(shift[video_start:video_end], smooth)
    sig = _smooth_norm(stick, smooth)
    scores: dict[int, float] = {}
    best = (-1.0, 0, 1)
    for g in range(-max_offset, max_offset + 1):
        a0 = video_start + g  # stick index of the window's first frame
        u0 = max(0, -a0)
        u1 = min(len(seg), len(sig) - a0)
        if u1 - u0 < min_overlap:
            continue
        a = sig[a0 + u0:a0 + u1]
        b = seg[u0:u1]
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        if denom == 0.0:
            continue
        r = float(np.dot(a, b)) / denom
        scores[g] = abs(r)
        if abs(r) > best[0]:
            best = (abs(r), g, 1 if r >= 0 else -1)
    peak, offset, sign = best
    others = [sc for g, sc in scores.items() if abs(g - offset) > 15]
    return SyncEstimate(offset, peak, sign, peak - (max(others) if others else 0.0), video_start, video_end)


def estimate_offset_windows(
    stick: np.ndarray,
    shift: np.ndarray,
    windows: int = 4,
    max_offset: int = 1800,
    smooth: int = 9,
) -> list[SyncEstimate]:
    """Offsets for consecutive slices of the video. Constant offsets = a clean 1:1 mapping
    (e.g. the recording was just cut short); offsets that grow or shrink = dropped/duplicated
    frames, i.e. a scale different from 1."""
    size = len(shift) // windows
    return [
        estimate_offset(stick, shift, max_offset, smooth, video_start=i * size,
                        video_end=len(shift) if i == windows - 1 else (i + 1) * size)
        for i in range(windows)
    ]


@dataclass(frozen=True)
class DriftFit:
    scale: float  # DTM frames per video frame
    offset: float  # DTM frame at video frame 0
    used_windows: int


def fit_drift(estimates: list[SyncEstimate], min_confidence: float = 0.03) -> DriftFit | None:
    """Least squares offset(v) = a*v + b over the trusted windows; scale = 1 + a."""
    good = [e for e in estimates if e.confidence >= min_confidence]
    if len(good) < 2:
        return None
    centers = np.array([(e.video_start + e.video_end) / 2 for e in good], dtype=np.float64)
    offsets = np.array([e.offset_frames for e in good], dtype=np.float64)
    weights = np.array([e.confidence for e in good], dtype=np.float64)
    a, b = np.polyfit(centers, offsets, 1, w=weights)
    return DriftFit(1.0 + float(a), float(b), len(good))


def read_video_frames(path: str | Path, limit: int | None = None) -> Iterable[np.ndarray]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise FileNotFoundError(f"Cannot open video {path}")
    try:
        count = 0
        while limit is None or count < limit:
            ok, image = capture.read()
            if not ok:
                return
            yield image
            count += 1
    finally:
        capture.release()


def video_info(path: str | Path) -> tuple[float, int]:
    capture = cv2.VideoCapture(str(path))
    try:
        return float(capture.get(cv2.CAP_PROP_FPS)), int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    finally:
        capture.release()
