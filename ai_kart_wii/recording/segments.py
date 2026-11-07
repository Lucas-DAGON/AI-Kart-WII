"""Find the driving parts of a DTM (the rest is menus, loading and waiting).

Heuristic: during a race the player holds A and steers. A is released now and then without
the race being over (bullet bill, falling off the map: no A needed), so releases shorter than
`merge_gap_frames` (default 8 s) are bridged. Between two races there are results/voting screens,
which last longer. Menus can also have A held, so segments additionally need real steering
activity. The result is a *suggestion*: check the boundaries once on your own footage.
"""

from __future__ import annotations

from ai_kart_wii.recording.dtm import STICK_CENTER, STICK_RADIUS, DtmMovie


def driving_segments(
    movie: DtmMovie,
    min_seconds: float = 20.0,
    merge_gap_frames: int = 480,
    steer_threshold: float = 0.15,
    min_steer_fraction: float = 0.05,
    tail_frames: int = 60,
) -> list[tuple[int, int]]:
    """(start_frame, end_frame) pairs in DTM VI frames, end exclusive."""
    frames = list(movie.frames())
    runs: list[list[int]] = []
    start: int | None = None
    for i, poll in enumerate(frames + [None]):  # type: ignore[list-item]
        pressed = poll is not None and "A" in poll.buttons
        if pressed and start is None:
            start = i
        elif not pressed and start is not None:
            if runs and start - runs[-1][1] <= merge_gap_frames:
                runs[-1][1] = i
            else:
                runs.append([start, i])
            start = None

    def active(poll) -> bool:
        steering = abs(poll.stick_x - STICK_CENTER) / STICK_RADIUS > steer_threshold
        return steering or bool(poll.buttons & {"R_DIGITAL", "B", "DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT"})

    result: list[tuple[int, int]] = []
    for begin, end in runs:
        if (end - begin) < min_seconds * 60:
            continue
        flags = [active(p) for p in frames[begin:end]]
        steering = sum(abs(p.stick_x - STICK_CENTER) / STICK_RADIUS > steer_threshold for p in frames[begin:end])
        if steering / (end - begin) < min_steer_fraction:
            continue
        # Trim the tail: after the finish line A is often pressed again on the results
        # screen without any driving. End the segment shortly after the last real activity.
        last_active = max(i for i, flag in enumerate(flags) if flag)
        end = min(end, begin + last_active + 1 + tail_frames)
        result.append((begin, end))
    return result
