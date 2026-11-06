import cv2
import numpy as np

from ai_kart_wii.capture.window import Region, WindowInfo, Win32RegionLocator, select_window
from ai_kart_wii.items.detector import TemplateItemDetector


def windows():
    return [
        WindowInfo("Dolphin 2603 | JIT64 | MTWP01", Region(100, 50, 1280, 720)),
        WindowInfo("Dolphin", Region(0, 0, 400, 300)),
        WindowInfo("AI-Kart-WII Dolphin console", Region(0, 0, 1920, 1080)),
        WindowInfo("Notepad", Region(0, 0, 1920, 1080)),
    ]


def test_select_largest_matching_window_excluding_own_console():
    chosen = select_window(windows(), "Dolphin", "AI-Kart|GameManager")
    assert chosen.client.width == 1280


def test_locator_applies_crop():
    locator = Win32RegionLocator(enumerate_windows=windows, crop=(0, 40, 0, 20))
    assert locator.locate() == Region(100, 90, 1280, 660)


def test_locator_none_when_no_window():
    assert Win32RegionLocator(include="Nothing", enumerate_windows=windows).locate() is None


def test_template_detector_finds_scaled_item(tmp_path):
    rng = np.random.default_rng(1)
    icon = rng.integers(0, 255, (32, 32, 3), dtype=np.uint8)
    cv2.imwrite(str(tmp_path / "banana.png"), icon)
    cv2.imwrite(str(tmp_path / "star.png"), rng.integers(0, 255, (32, 32, 3), dtype=np.uint8))
    frame = np.zeros((960, 1280, 3), dtype=np.uint8)  # 2x reference width
    big = cv2.resize(icon, (64, 64), interpolation=cv2.INTER_LINEAR)
    frame[60:124, 40:104] = big
    detector = TemplateItemDetector(tmp_path, reference_width=640, threshold=0.6)
    result = detector.detect(frame)
    assert result.name == "banana" and result.score > 0.8
    assert detector.detect(np.zeros_like(frame)).name is None


def test_recorder_roundtrip(tmp_path, backend, race):
    from ai_kart_wii.agent.waypoint import WaypointFollowerAgent
    from ai_kart_wii.capture.source import SyntheticFrameSource
    from ai_kart_wii.recording.recorder import MemoryInputSource, SessionRecorder
    from ai_kart_wii.runtime.loop import DrivingLoop
    from ai_kart_wii.state.poller import StatePoller
    from ai_kart_wii.state.reader import RaceStateReader
    from ai_kart_wii.testing.fake_controller import FakeController
    from ai_kart_wii.testing.fake_track import FakeMapProvider
    from ai_kart_wii.training.dataset import RecordedRun, list_runs

    race.begin_race(instant=True)
    reader = RaceStateReader(backend)
    poller = StatePoller(reader)
    poller.poll_once()
    rec = SessionRecorder(tmp_path, 0, 0, 60, "test", MemoryInputSource(reader, poller), input_every=2)
    loop = DrivingLoop(frames=SyntheticFrameSource(64, 48), poller=poller, agent=WaypointFollowerAgent(),
                       controller=FakeController(race), maps=FakeMapProvider(), recorder=rec)
    for i in range(30):
        race.step(); poller.poll_once(); loop.step()
    rec.close()

    runs = list_runs(tmp_path)
    assert len(runs) == 1
    run = RecordedRun(runs[0])
    pairs = list(run)
    assert len(pairs) == 30 and run.meta["finished"] is True
    frame, sample = pairs[10]
    assert frame is not None and frame.shape[:2] == (48, 64)
    assert sample["race_frame"] == 11 and sample["action"] is not None and "StickX" in sample["human"]
