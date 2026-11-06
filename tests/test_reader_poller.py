import pytest

from ai_kart_wii.ipc.errors import GameManagerUnavailable, ResourceNotReady
from ai_kart_wii.state.poller import StatePoller
from ai_kart_wii.state.reader import RaceStateReader


def test_wait_until_ready_retries_through_cache_build(backend, race):
    race.begin_race()  # state 1, ready after 30 frames
    reader = RaceStateReader(backend)
    ticks = []

    def sleep(_):
        ticks.append(1)
        race.step(10)

    class Stop:
        def is_set(self):
            return False

    assert reader.wait_until_ready(Stop(), poll_s=0.0, sleep=sleep) is True
    assert 1 <= len(ticks) <= 5


def test_wait_survives_gamemanager_errors(backend, race):
    race.begin_race(instant=True)
    backend.inject_failures(GameManagerUnavailable("down"), GameManagerUnavailable("down"))
    reader = RaceStateReader(backend)

    class Stop:
        def is_set(self):
            return False

    assert reader.wait_until_ready(Stop(), poll_s=0.0, sleep=lambda _: None) is True


def test_discover_own_slot(backend, race):
    race.own_slot = 5
    race.begin_race(instant=True)
    assert RaceStateReader(backend).discover_own_slot() == 5


def test_discover_slot_not_ready(backend):
    with pytest.raises(ResourceNotReady):
        RaceStateReader(backend).discover_own_slot()


def test_read_own_state(backend, race):
    race.begin_race(instant=True)
    race.step(5)
    reader = RaceStateReader(backend)
    state = reader.read_own_state(0)
    assert state.race_frame == 5 and state.slot == 0 and state.team_name == "Purple"
    assert state.position.x == pytest.approx(12000.0, rel=0.01)
    assert reader.validator.counts == {}


def test_poller_lifecycle_and_epoch(backend, race):
    poller = StatePoller(RaceStateReader(backend))
    assert poller.poll_once() is False and poller.latest() is None
    race.begin_race(instant=True)
    assert poller.poll_once() is True
    assert poller.epoch == 1 and poller.own_slot == 0 and poller.track_id == 0
    race.end_race()
    assert poller.poll_once() is False and poller.latest() is None
    race.begin_race(instant=True)  # restart
    poller.poll_once()
    assert poller.epoch == 2


def test_poller_survives_errors(backend, race):
    race.begin_race(instant=True)
    poller = StatePoller(RaceStateReader(backend))
    backend.inject_failures(GameManagerUnavailable("blip"))
    assert poller.poll_once() is False
    assert poller.failures == 1
    assert poller.poll_once() is True
