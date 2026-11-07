"""Turn a DTM + an external video into a recorded run (schema 1) for imitation learning.

The video is NOT copied (it is large): meta.json stores its path and the sync offset.
samples.jsonl gets one line per video frame with the human's action for that moment.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from ai_kart_wii.control.actions import ControlScheme, DrivingAction
from ai_kart_wii.recording.dtm import DtmMovie
from ai_kart_wii.recording.format import META_FILE, SAMPLES_FILE, SCHEMA_VERSION


def to_driving_action(poll, scheme: ControlScheme | None = None) -> DrivingAction:
    return (scheme or ControlScheme()).to_driving(poll.to_controller_action())


def import_dtm(
    movie: DtmMovie,
    runs_dir: str | Path,
    *,
    video_path: str | Path | None,
    video_frames: int,
    offset_frames: int,
    video_fps: float = 60.0,
    track_id: int | None = None,
    label: str = "dtm",
    scheme: ControlScheme | None = None,
    scale: float = 1.0,
    frame_ranges: list[tuple[int, int]] | None = None,
) -> Path:
    """video frame v <-> DTM frame round(v * scale) + offset_frames.

    scale is 1.0 when the video holds exactly one image per VI frame (Dolphin frame dump).
    Use video_fps_dtm / video_fps if the video was re-encoded to another frame rate.
    Frames outside the DTM (or outside `frame_ranges`, in DTM frames) are skipped.
    """
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = Path(runs_dir) / f"{stamp}_track{track_id if track_id is not None else 'x'}_{label}"
    out.mkdir(parents=True, exist_ok=False)
    written = 0
    with open(out / SAMPLES_FILE, "w", encoding="utf-8") as handle:
        for v in range(video_frames):
            dtm_frame = round(v * scale) + offset_frames
            if not 0 <= dtm_frame < movie.header.frame_count:
                continue
            if frame_ranges is not None and not any(a <= dtm_frame < b for a, b in frame_ranges):
                continue
            poll = movie.frame_input(dtm_frame)
            action = to_driving_action(poll, scheme)
            handle.write(json.dumps({
                "i": v, "dtm_frame": dtm_frame, "has_frame": True, "race_frame": None,
                "state": None, "state_age_ms": None, "action": None,
                "human": {
                    "StickX": round((poll.stick_x - 128) / 100.0, 4),
                    "StickY": round((poll.stick_y - 128) / 100.0, 4),
                    "buttons": sorted(poll.buttons), "l": poll.l, "r": poll.r,
                    "driving": {"steer": action.steer, "accelerate": action.accelerate, "brake": action.brake,
                                "drift": action.drift, "use_item": action.use_item, "rear_view": action.rear_view},
                },
            }) + "\n")
            written += 1
    meta = {
        "schema": SCHEMA_VERSION, "source": "dtm", "track_id": track_id, "slot": None, "fps": video_fps,
        "video_path": str(video_path) if video_path else None, "video_frame_origin": 0,
        "dtm_offset_frames": offset_frames, "dtm_scale": scale, "frames": written, "game_id": movie.header.game_id,
        "finished": True,
    }
    (out / META_FILE).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return out
