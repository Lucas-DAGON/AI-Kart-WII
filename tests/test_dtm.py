import os
from pathlib import Path

import numpy as np
import pytest

from ai_kart_wii.control.actions import ControlScheme, ControllerAction, DrivingAction
from ai_kart_wii.recording import dtm
from ai_kart_wii.recording.dtm_import import import_dtm
from ai_kart_wii.training.dataset import RecordedRun
from dtm_builder import build_dtm, gc

A, B, X, Y, DPAD_UP = 0x02, 0x04, 0x08, 0x10, 0x40
R_DIG, L_DIG = 0x08, 0x04


def test_header_and_connected_filter():
    movie = dtm.parse(build_dtm(10))
    assert movie.header.game_id == "MTWP01" and movie.header.frame_count == 10
    assert len(movie.polls) == 20 and movie.polls_per_frame == 2.0
    assert movie.wiimote_records == 60 and movie.header.video_backend == "Vulkan"


def test_buttons_sticks_and_dpad_up_is_not_mistaken_for_wiimote():
    def pad(f, p):
        if f == 3:
            return gc(DPAD_UP | A, 0, sx=228)  # D-pad up (0x40) must stay a GC record
        if f == 4:
            return gc(A | X, R_DIG, r=255, sx=28)
        return gc()

    movie = dtm.parse(build_dtm(6, pad_fn=pad))
    up = movie.frame_input(3)
    assert up.buttons == {"A", "DPAD_UP"} and up.stick_x == 228
    drift = movie.frame_input(4)
    assert {"A", "X", "R_DIGITAL"} <= drift.buttons and drift.r == 255
    action = drift.to_controller_action()
    assert action.stick_x == pytest.approx(-1.0) and action.r == 1.0 and "R_DIGITAL" not in action.buttons


def test_corrupt_stream_is_rejected():
    data = bytearray(build_dtm(5))
    data[-3:] = b""  # truncate
    with pytest.raises(dtm.DtmError):
        dtm.parse(bytes(data))
    with pytest.raises(dtm.DtmError):
        dtm.parse(b"NOPE" + bytes(300))


def test_scheme_inverse_roundtrip():
    scheme = ControlScheme()
    original = DrivingAction(steer=0.5, accelerate=True, brake=False, drift=True, use_item=True, rear_view=True, trick="up")
    pad = scheme.to_controller(original)
    assert {"A", "X", "DPAD_UP"} <= pad.buttons
    assert scheme.to_driving(pad) == original


def test_import_writes_aligned_samples_and_dataset_reads_meta(tmp_path):
    movie = dtm.parse(build_dtm(20, pad_fn=lambda f, p: gc(A if f >= 5 else 0, sx=128 + f)))
    out = import_dtm(movie, tmp_path, video_path=tmp_path / "x.mp4", video_frames=15, offset_frames=3, track_id=8)
    run = RecordedRun(out)
    samples = list(run.samples())
    assert len(samples) == 15
    assert samples[0]["dtm_frame"] == 3 and samples[0]["human"]["driving"]["accelerate"] is False
    assert samples[2]["dtm_frame"] == 5 and samples[2]["human"]["driving"]["accelerate"] is True
    assert run.meta["dtm_offset_frames"] == 3 and run.meta["source"] == "dtm"
    # negative offset skips frames before the DTM starts
    out2 = import_dtm(movie, tmp_path, video_path=None, video_frames=10, offset_frames=-4, label="neg")
    assert len(list(RecordedRun(out2).samples())) == 6


REAL = Path(os.environ.get("AI_KART_WII_TEST_DTM", "/mnt/user-data/uploads/MKWII_TW_Luigi_s_Circuit__008_szs_.dtm"))


@pytest.mark.skipif(not REAL.exists(), reason="real DTM not available")
def test_real_recording_parses_consistently():
    movie = dtm.load(REAL)
    assert movie.header.game_id == "MTWP01"
    assert len(movie.polls) == 2 * movie.header.frame_count + 1
    summary = movie.summary()
    assert summary["button_frames"]["A"] > 10000


def test_tiny_wiimote_records_and_start_button_are_not_confused():
    from dtm_builder import build_dtm, gc

    def pad(f, p):
        return gc(0x01 | A, 0) if f == 2 else gc(A)  # Start pressed: byte0 == 0x01 == tiny wiimote size

    movie = dtm.parse(build_dtm(6, pad_fn=pad, tiny_wiimote_every=3))
    assert len(movie.polls) == 12
    assert movie.frame_input(2).buttons >= {"START", "A"}
    assert "START" not in movie.frame_input(3).buttons


def test_driving_segments_and_scale_and_ranges(tmp_path):
    from ai_kart_wii.recording.segments import driving_segments

    def pad(f, p):
        racing = 900 <= f < 2100
        steer = 128 + (60 if (f // 20) % 2 else -60) if racing else 128
        return gc(A if racing or f < 40 else 0, sx=steer)

    movie = dtm.parse(build_dtm(2400, pad_fn=pad))
    assert driving_segments(movie, min_seconds=10) == [(900, 2100)]  # short early A taps are ignored

    out = import_dtm(movie, tmp_path, video_path=None, video_frames=900, offset_frames=0, scale=2.0,
                     frame_ranges=[(900, 2100)])
    samples = list(RecordedRun(out).samples())
    assert samples[0]["dtm_frame"] == 900 and samples[-1]["dtm_frame"] < 2100
    assert all(s["dtm_frame"] % 2 == 0 for s in samples)  # scale 2.0: every second DTM frame


BOWSER = Path("/mnt/user-data/uploads/MKWII_TW_Bowser_s_Castle__00C_szs_.dtm")


@pytest.mark.skipif(not BOWSER.exists(), reason="real DTM not available")
def test_real_bowser_recording_has_dpad_and_parses():
    movie = dtm.load(BOWSER)
    counts = movie.summary()["button_frames"]
    assert movie.header.frame_count == 37027 and len(movie.polls) == 2 * 37027 + 1
    assert counts["DPAD_UP"] > 1000 and counts["DPAD_LEFT"] > 0 and counts["DPAD_RIGHT"] > 0


def test_segments_bridge_short_releases_but_split_separate_races():
    from ai_kart_wii.recording.segments import driving_segments

    def pad(f, p):
        steer = 128 + (60 if (f // 20) % 2 else -60)
        in_race1 = 300 <= f < 2000
        in_bullet = 1000 <= f < 1240  # 4 s without A (bullet bill / fell off the map), no steering
        in_race2 = 3600 <= f < 5000   # 27 s of menus in between
        if in_bullet:
            return gc(0, 0)
        if in_race1 or in_race2:
            return gc(A, sx=steer)
        return gc()

    movie = dtm.parse(build_dtm(5200, pad_fn=pad))
    assert driving_segments(movie, min_seconds=10) == [(300, 2000), (3600, 5000)]


def test_segment_tail_is_trimmed_after_last_activity():
    from ai_kart_wii.recording.segments import driving_segments

    def pad(f, p):
        if 300 <= f < 1500:
            return gc(A, sx=128 + (60 if (f // 20) % 2 else -60))
        if 1500 <= f < 1800:  # results screen: A pressed again, no driving
            return gc(A)
        return gc()

    movie = dtm.parse(build_dtm(2000, pad_fn=pad))
    assert driving_segments(movie, min_seconds=10) == [(300, 1560)]
