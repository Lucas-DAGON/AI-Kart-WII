"""On-disk layout of a recorded run (schema 1).

    recorded_runs/<YYYYmmdd-HHMMSS>_track<id>_<label>/
        meta.json      schema, track id, slot, fps, video name, notes
        video.mp4      captured frames (or frames/000001.png... when mp4 is unavailable)
        samples.jsonl  one JSON object per frame, in order:
            {"i": frame index, "t_ns": perf_counter_ns, "race_frame": int|null,
             "state_age_ms": float|null, "state": {...}|null,
             "action": {...}|null,          # what the AI sent
             "human": {...}|null}           # what the human did (stick/buttons)

`race_frame` (RaceFrameCounter) is the key for aligning images and memory data when
GameManager reads are slower than the 60 Hz capture.
"""

SCHEMA_VERSION = 1
META_FILE = "meta.json"
SAMPLES_FILE = "samples.jsonl"
VIDEO_FILE = "video.mp4"
FRAMES_DIR = "frames"
