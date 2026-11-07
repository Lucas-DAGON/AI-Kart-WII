import cv2
import numpy as np
import pytest

from ai_kart_wii.calibration import estimate_yaw_sign
from ai_kart_wii.geometry import wrap_angle
from ai_kart_wii.recording.sync import estimate_offset, horizontal_shift_series
from ai_kart_wii.testing.fake_race import FakeRace
from ai_kart_wii.control.actions import ControllerAction


def stick_signal(n, seed=3):
    rng = np.random.default_rng(seed)
    out, value = [], 0.0
    for _ in range(n):
        if rng.random() < 0.03:
            value = rng.choice([-1.0, -0.5, 0.0, 0.5, 1.0])
        out.append(value)
    return np.array(out)


def test_estimate_offset_on_synthetic_series():
    stick = stick_signal(3000)
    true_offset = 137  # video frame v <-> stick[v + 137]
    shift = np.convolve(stick, np.ones(5) / 5, mode="same")[true_offset:true_offset + 2400] * -3.0
    shift += np.random.default_rng(0).normal(0, 0.2, len(shift))
    est = estimate_offset(stick, shift, max_offset=400)
    assert est.offset_frames == pytest.approx(true_offset, abs=3)
    assert est.sign == -1 and est.correlation > 0.5 and est.confidence > 0.1


def test_phase_correlation_measures_scrolling_video():
    rng = np.random.default_rng(5)
    texture = rng.integers(0, 255, (90, 1200, 3), dtype=np.uint8)
    texture = cv2.GaussianBlur(texture, (0, 0), 2)
    xs = np.cumsum([0, 4, 4, 4, -3, -3, 0, 0, 6, 6])
    frames = [texture[:, 400 + x: 400 + x + 160] for x in xs]
    frames = [cv2.resize(f, (160, 90)) for f in frames]
    shifts = horizontal_shift_series(frames)
    assert np.sign(shifts[1]) == np.sign(shifts[2]) != 0
    assert np.sign(shifts[1]) == -np.sign(shifts[5])  # scrolling direction reverses


def drive_samples(race, stick, frames=200):
    out = []
    race.begin_race(instant=True)
    for i in range(frames):
        race.apply(ControllerAction(stick_x=stick(i), buttons=frozenset({"A"})))
        race.step()
        k = race.kart
        import math
        out.append((race.value("StickX", 0), math.sin(k.yaw), math.cos(k.yaw), k.speed))
    return out


def test_yaw_sign_positive_when_stick_right_increases_yaw():
    import math
    samples = drive_samples(FakeRace(), lambda i: math.sin(i / 15.0))
    result = estimate_yaw_sign(samples)
    assert result.positive_yaw_is_right is True and result.correlation > 0.8


def test_yaw_sign_flips_with_mirrored_game():
    import math
    samples = drive_samples(FakeRace(), lambda i: math.sin(i / 15.0))
    mirrored = [(s, -dx, dz, v) for s, dx, dz, v in samples]
    assert estimate_yaw_sign(mirrored).positive_yaw_is_right is False


def test_yaw_calibration_inconclusive_when_idle():
    samples = [(0.0, 0.0, 1.0, 0.0)] * 100
    assert estimate_yaw_sign(samples).positive_yaw_is_right is None


def make_shift(stick, idx_of_video_frame, count, noise=0.2, seed=0):
    """Image shift per video frame: -3 * smoothed stick sampled at the matching DTM frame."""
    smooth = np.convolve(stick, np.ones(5) / 5, mode="same")
    shift = np.array([smooth[idx_of_video_frame(v)] for v in range(count)]) * -3.0
    return shift + np.random.default_rng(seed).normal(0, noise, count)


def test_windows_constant_offset_when_video_is_just_cut_short():
    from ai_kart_wii.recording.sync import estimate_offset_windows, fit_drift

    stick = stick_signal(6000, seed=11)
    shift = make_shift(stick, lambda v: v, 5400)  # same timeline, video ends earlier
    windows = estimate_offset_windows(stick, shift, windows=4, max_offset=300)
    assert all(abs(w.offset_frames) <= 3 for w in windows)
    fit = fit_drift(windows)
    assert fit is not None and abs(fit.scale - 1.0) < 0.002


def test_windows_detect_dropped_frames_as_drift():
    from ai_kart_wii.recording.sync import estimate_offset_windows, fit_drift

    stick = stick_signal(6000, seed=12)
    # video has fewer images than DTM frames: DTM idx = 1.03 * v + 40
    shift = make_shift(stick, lambda v: int(round(1.03 * v + 40)), 5400)
    windows = estimate_offset_windows(stick, shift, windows=4, max_offset=400)
    offsets = [w.offset_frames for w in windows]
    assert offsets == sorted(offsets) and offsets[-1] - offsets[0] > 100
    fit = fit_drift(windows)
    assert fit.scale == pytest.approx(1.03, abs=0.004) and fit.offset == pytest.approx(40, abs=25)


def test_offset_inside_window_uses_global_frame_numbers():
    stick = stick_signal(6000, seed=13)
    shift = make_shift(stick, lambda v: v + 90, 4000)
    est = estimate_offset(stick, shift, max_offset=300, video_start=2000, video_end=3500)
    assert est.offset_frames == pytest.approx(90, abs=3) and est.video_start == 2000
