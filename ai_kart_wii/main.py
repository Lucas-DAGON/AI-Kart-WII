"""Command line entry point.

    python -m ai_kart_wii demo         # fake game, no Dolphin needed (works anywhere)
    python -m ai_kart_wii check        # connect to the real GameManager, read & validate state
    python -m ai_kart_wii run          # AI plays (needs Dolphin, GameManager, ViGEmBus)
    python -m ai_kart_wii record       # record your own play for imitation learning
    python -m ai_kart_wii fake-server  # Windows: fake GameManager on the real pipe
"""

from __future__ import annotations

import argparse
import logging
import threading
import time

from ai_kart_wii.agent.waypoint import WaypointFollowerAgent
from ai_kart_wii.config import AppConfig
from ai_kart_wii.ipc.backend import GameManagerBackend
from ai_kart_wii.ipc.errors import GameManagerError
from ai_kart_wii.logging_setup import setup_logging
from ai_kart_wii.runtime.loop import DrivingLoop
from ai_kart_wii.state.poller import StatePoller
from ai_kart_wii.state.reader import RaceStateReader
from ai_kart_wii.state.validation import StateValidator

log = logging.getLogger("ai_kart_wii")


def connect_with_retry(backend: GameManagerBackend, cfg: AppConfig, stop: threading.Event) -> bool:
    """Retry periodically until GameManager accepts us (it may start after the AI)."""
    while not stop.is_set():
        try:
            backend.connect(cfg.game_manager.connect_timeout_s)
            backend.register(cfg.game_manager.client_name)
            log.info("Connected to GameManager as '%s'", cfg.game_manager.client_name)
            return True
        except GameManagerError as exc:
            log.warning("GameManager connection failed: %s (retry in %.1fs)", exc, cfg.game_manager.retry_interval_s)
            stop.wait(cfg.game_manager.retry_interval_s)
    return False


def make_real_backend(cfg: AppConfig) -> GameManagerBackend:
    from ai_kart_wii.ipc.pythonnet_client import PythonNetBackend

    return PythonNetBackend(cfg.game_manager.dll_path, cfg.game_manager.runtime_config)


def make_frame_source(cfg: AppConfig):
    from ai_kart_wii.capture.source import MssFrameSource
    from ai_kart_wii.capture.window import FixedRegionLocator, Region, Win32RegionLocator

    c = cfg.capture
    if c.fixed_region:
        locator = FixedRegionLocator(Region(*c.fixed_region))
    else:
        locator = Win32RegionLocator(
            c.window_title_regex, c.window_title_exclude_regex, c.min_window_size,
            (c.crop_left, c.crop_top, c.crop_right, c.crop_bottom),
        )
    return MssFrameSource(locator, c.relocate_every)


def cmd_demo(cfg: AppConfig, args: argparse.Namespace) -> int:
    """Closed loop against the fake game: proves the whole pipeline end to end."""
    from ai_kart_wii.capture.source import SyntheticFrameSource
    from ai_kart_wii.map.interface import MapProvider  # noqa: F401
    from ai_kart_wii.testing.fake_backend import FakeBackend
    from ai_kart_wii.testing.fake_controller import FakeController
    from ai_kart_wii.testing.fake_race import FakeRace
    from ai_kart_wii.testing.fake_track import FakeMapProvider

    race = FakeRace()
    backend = FakeBackend(race)
    backend.connect()
    reader = RaceStateReader(backend, StateValidator(verbose=cfg.runtime.verbose_validation))
    poller = StatePoller(reader, own_slot=cfg.runtime.own_slot)
    controller = FakeController(race)
    loop = DrivingLoop(
        frames=SyntheticFrameSource(), poller=poller, agent=WaypointFollowerAgent(),
        controller=controller, maps=FakeMapProvider(),
    )
    race.begin_race()
    for i in range(args.frames):
        race.step()
        if i % 2 == 0:  # state polled at ~30 Hz, loop at 60 Hz
            poller.poll_once()
        loop.step()
    state = poller.latest()
    print(f"frames={args.frames} race_frame={race.race_frame} completion={race.completion:.2f} "
          f"lap={state.lap if state else '-'}/{race.lap_count}")
    print(reader.validator.summary())
    return 0


def cmd_check(cfg: AppConfig, args: argparse.Namespace) -> int:
    stop = threading.Event()
    backend = make_real_backend(cfg)
    if not connect_with_retry(backend, cfg, stop):
        return 1
    reader = RaceStateReader(backend, StateValidator(verbose=True))
    poller = StatePoller(reader, own_slot=cfg.runtime.own_slot)
    try:
        for _ in range(args.reads):
            if poller.poll_once():
                s = poller.latest()
                print(f"slot={s.slot} frame={s.race_frame} pos=({s.position.x:.0f},{s.position.y:.0f},{s.position.z:.0f}) "
                      f"speed={s.speed:.1f} lap={s.lap}/{s.max_lap} place={s.race_position} "
                      f"team={s.team_name} latency={s.read_latency_ms:.1f}ms")
            else:
                print(f"not ready (GameState={poller.game_state})")
            time.sleep(0.5)
    finally:
        print(reader.validator.summary())
        backend.close()
    return 0


def _build_live(cfg: AppConfig, stop: threading.Event):
    from ai_kart_wii.control.virtual_pad import ViGEmController

    backend = make_real_backend(cfg)
    if not connect_with_retry(backend, cfg, stop):
        raise SystemExit(1)
    reader = RaceStateReader(backend, StateValidator(verbose=cfg.runtime.verbose_validation))
    poller = StatePoller(reader, cfg.runtime.state_poll_hz, cfg.game_manager.retry_interval_s, cfg.runtime.own_slot)
    return backend, reader, poller, make_frame_source(cfg), ViGEmController()


def cmd_run(cfg: AppConfig, args: argparse.Namespace) -> int:
    from ai_kart_wii.map.interface import PythonNetMapProvider

    stop = threading.Event()
    backend, reader, poller, frames, controller = _build_live(cfg, stop)
    loop = DrivingLoop(
        frames=frames, poller=poller, agent=WaypointFollowerAgent(), controller=controller,
        maps=PythonNetMapProvider(cfg.paths.szs_dir), item_every=cfg.runtime.item_detect_every,
    )
    poller.start()
    try:
        loop.run(stop, hz=cfg.runtime.control_hz)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set(); poller.stop(); controller.close(); frames.close(); backend.close()
        print(reader.validator.summary())
    return 0


def cmd_record(cfg: AppConfig, args: argparse.Namespace) -> int:
    from ai_kart_wii.agent.base import Agent  # noqa: F401
    from ai_kart_wii.control.actions import DrivingAction
    from ai_kart_wii.control.fake_pad import NullController
    from ai_kart_wii.recording.recorder import MemoryInputSource, SessionRecorder

    class Passive:
        def reset(self) -> None: ...
        def act(self, observation): return DrivingAction()

    stop = threading.Event()
    backend = make_real_backend(cfg)
    if not connect_with_retry(backend, cfg, stop):
        return 1
    reader = RaceStateReader(backend, StateValidator(verbose=cfg.runtime.verbose_validation))
    poller = StatePoller(reader, cfg.runtime.state_poll_hz, cfg.game_manager.retry_interval_s, cfg.runtime.own_slot)
    frames = make_frame_source(cfg)
    poller.start()
    print("Waiting for a race... (Ctrl+C to stop)")
    recorder = None
    try:
        while poller.latest() is None and not stop.is_set():
            time.sleep(0.2)
        recorder = SessionRecorder(cfg.paths.recorded_runs, poller.track_id, poller.own_slot,
                                   cfg.capture.fps, args.label, MemoryInputSource(reader, poller))
        loop = DrivingLoop(frames=frames, poller=poller, agent=Passive(), controller=NullController(), recorder=recorder)
        print(f"Recording to {recorder.dir}")
        loop.run(stop, hz=cfg.capture.fps)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set(); poller.stop(); frames.close(); backend.close()
        if recorder:
            recorder.close()
    return 0


def cmd_fake_server(cfg: AppConfig, args: argparse.Namespace) -> int:
    from ai_kart_wii.testing.fake_race import FakeRace
    from ai_kart_wii.testing.fake_server import FakePipeServer

    race = FakeRace()
    race.begin_race(instant=True)
    server = FakePipeServer(race)
    server.start()
    print("Fake GameManager running (Ctrl+C to stop). The kart does not move unless something steps the race.")
    try:
        while True:
            race.step()
            time.sleep(1 / 60)
    except KeyboardInterrupt:
        server.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ai_kart_wii")
    parser.add_argument("--config", help="JSON config file")
    parser.add_argument("--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo"); demo.add_argument("--frames", type=int, default=3000)
    check = sub.add_parser("check"); check.add_argument("--reads", type=int, default=20)
    sub.add_parser("run")
    rec = sub.add_parser("record"); rec.add_argument("--label", default="human")
    sub.add_parser("fake-server")
    args = parser.parse_args(argv)

    cfg = AppConfig.load(args.config)
    setup_logging(cfg.paths.logs, args.verbose or cfg.runtime.verbose_validation)
    handlers = {"demo": cmd_demo, "check": cmd_check, "run": cmd_run, "record": cmd_record, "fake-server": cmd_fake_server}
    return handlers[args.command](cfg, args)


if __name__ == "__main__":
    raise SystemExit(main())
