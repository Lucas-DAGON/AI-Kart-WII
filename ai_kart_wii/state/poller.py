"""Background poller: GameManager is slower than the 60 Hz control loop, so state is
polled on its own thread and the control loop always uses the latest snapshot."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from ai_kart_wii.ipc.errors import GameManagerError
from ai_kart_wii.state.reader import RaceStateReader
from ai_kart_wii.state.resources import GAME_STATE_CACHE_READY
from ai_kart_wii.state.snapshot import PlayerState

log = logging.getLogger(__name__)


class StatePoller:
    def __init__(
        self,
        reader: RaceStateReader,
        hz: float = 30.0,
        retry_interval_s: float = 1.0,
        own_slot: int | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.reader = reader
        self.period = 1.0 / hz
        self.retry_interval_s = retry_interval_s
        self._fixed_slot = own_slot
        self._clock = clock

        self._lock = threading.Lock()
        self._state: PlayerState | None = None
        self._game_state: int | None = None
        self._slot: int | None = own_slot
        self._epoch = 0
        self._in_race = False
        self._track_id: int | None = None
        self._last_warning: dict[str, float] = {}
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.reads = 0
        self.failures = 0

    # ----------------------------------------------------------------- accessors
    def latest(self) -> PlayerState | None:
        with self._lock:
            return self._state

    @property
    def game_state(self) -> int | None:
        with self._lock:
            return self._game_state

    @property
    def epoch(self) -> int:
        """Increments every time a race becomes ready (new race or restart)."""
        with self._lock:
            return self._epoch

    @property
    def track_id(self) -> int | None:
        with self._lock:
            return self._track_id

    @property
    def own_slot(self) -> int | None:
        with self._lock:
            return self._slot

    # --------------------------------------------------------------------- logic
    def poll_once(self) -> bool:
        """One poll. Returns True when a fresh in-race state was stored."""
        try:
            game_state = self.reader.read_game_state()
            if game_state != GAME_STATE_CACHE_READY:
                self._leave_race(game_state)
                return False

            if not self._in_race:
                self._enter_race()
            slot = self._slot
            if slot is None:
                slot = self.reader.discover_own_slot()
                with self._lock:
                    self._slot = slot
                log.info("Own kart is slot %d", slot)
            state = self.reader.read_own_state(slot)
            with self._lock:
                self._state = state
                self._game_state = game_state
            self.reads += 1
            return True
        except GameManagerError as exc:
            self.failures += 1
            self._warn(f"{exc.code}: {exc}")
            with self._lock:
                self._state = None
            return False

    def _enter_race(self) -> None:
        self.reader.validator.reset_sequence()
        track_id: int | None
        try:
            track_id = self.reader.read_track_id()
        except GameManagerError:
            track_id = None
        with self._lock:
            self._in_race = True
            self._epoch += 1
            self._track_id = track_id
            if self._fixed_slot is None:
                self._slot = None  # re-discover: slots can change between races
        log.info("Race ready (epoch %d, Le-Code track id %s)", self._epoch, track_id)

    def _leave_race(self, game_state: int) -> None:
        with self._lock:
            self._game_state = game_state
            self._state = None
            was_in_race = self._in_race
            self._in_race = False
        if was_in_race:
            log.info("Race cache no longer ready (GameState=%s)", game_state)

    def _warn(self, message: str) -> None:
        now = self._clock()
        if now - self._last_warning.get(message, -1e9) >= 10.0:
            self._last_warning[message] = now
            log.warning("State poll failed: %s", message)

    # -------------------------------------------------------------------- thread
    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="state-poller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            started = self._clock()
            ok = self.poll_once()
            if ok:
                delay = max(0.0, self.period - (self._clock() - started))
            else:
                delay = self.retry_interval_s  # "retry periodically until it succeeds"
            self._stop.wait(delay)
