import math

import numpy as np
import pytest

from ai_kart_wii.agent.waypoint import WaypointFollowerAgent
from ai_kart_wii.capture.source import SyntheticFrameSource
from ai_kart_wii.control.actions import DrivingAction
from ai_kart_wii.map.navigation import Navigator, flatten_main_route
from ai_kart_wii.runtime.loop import DrivingLoop
from ai_kart_wii.state.poller import StatePoller
from ai_kart_wii.state.reader import RaceStateReader
from ai_kart_wii.testing.fake_controller import FakeController
from ai_kart_wii.testing.fake_track import SURFACE_ROAD, FakeMapProvider, make_oval_track


def test_flatten_follows_links_and_stops_on_loop():
    track = make_oval_track(points=10)
    assert flatten_main_route(track.enemy_paths).shape == (10, 3)


def test_navigator_hint_sign_and_surface(backend, race):
    race.begin_race(instant=True)
    state = RaceStateReader(backend).read_own_state(0)
    hint = Navigator(make_oval_track()).hint(state)
    # The oval is run counter-clockwise from the start: target lies to the left (-x), i.e. negative error
    assert hint.heading_error < 0
    assert hint.surface.surface_type == SURFACE_ROAD
    assert hint.lateral_offset < 1.0


def build_loop(backend, race, **extra):
    poller = StatePoller(RaceStateReader(backend))
    controller = FakeController(race)
    loop = DrivingLoop(frames=SyntheticFrameSource(64, 48), poller=poller, agent=extra.pop("agent", WaypointFollowerAgent()),
                       controller=controller, maps=FakeMapProvider(), **extra)
    return loop, poller, controller


def drive(loop, poller, race, frames):
    for i in range(frames):
        race.step()
        if i % 2 == 0:
            poller.poll_once()
        loop.step()


def test_follower_completes_laps_and_stays_on_road(backend, race):
    race.begin_race(instant=True)
    loop, poller, _ = build_loop(backend, race)
    worst = 0.0
    for i in range(2400):
        race.step()
        if i % 2 == 0:
            poller.poll_once()
        r = loop.step()
        if r.observation.nav:
            worst = max(worst, r.observation.nav.lateral_offset)
    assert race.completion > 3.0
    assert worst < 1200.0  # never wildly off the route


def test_idle_and_neutral_before_race_ready(backend, race):
    loop, poller, controller = build_loop(backend, race)
    result = loop.step()
    assert result.action is None and not controller.history[-1].buttons


def test_agent_reset_and_map_reload_on_restart(backend, race):
    class Spy:
        resets = 0
        def reset(self): Spy.resets += 1
        def act(self, observation): return DrivingAction()

    race.begin_race(instant=True)
    loop, poller, _ = build_loop(backend, race, agent=Spy())
    drive(loop, poller, race, 10)
    race.end_race(); poller.poll_once(); race.begin_race(instant=True)
    drive(loop, poller, race, 10)
    assert Spy.resets == 2
