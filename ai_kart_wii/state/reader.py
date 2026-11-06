"""Reads the AI's own kart (and race info) through any GameManagerBackend."""

from __future__ import annotations

import logging
import time
from typing import Any, Sequence

from ai_kart_wii.ipc.backend import GameManagerBackend, ResourceRequest
from ai_kart_wii.ipc.errors import (
    GameManagerError,
    ResourceNotReady,
    error_from_message,
)
from ai_kart_wii.state.resources import (
    GAME_STATE,
    GAME_STATE_CACHE_READY,
    OWN_STATE_RESOURCES,
    PLAYER_TYPE_LOCAL,
    SLOT_COUNT,
    SLOT_DISCOVERY_RESOURCE,
    TRACK_ID,
)
from ai_kart_wii.state.snapshot import PlayerState
from ai_kart_wii.state.validation import StateValidator

log = logging.getLogger(__name__)


class RaceStateReader:
    def __init__(
        self,
        backend: GameManagerBackend,
        validator: StateValidator | None = None,
        resources: Sequence[str] = OWN_STATE_RESOURCES,
    ) -> None:
        self.backend = backend
        self.validator = validator or StateValidator()
        self.resources = tuple(resources)

    # ------------------------------------------------------------- race lifecycle
    def read_game_state(self) -> int:
        return int(self.backend.get(GAME_STATE))

    def is_race_ready(self) -> bool:
        return self.read_game_state() == GAME_STATE_CACHE_READY

    def read_track_id(self) -> int:
        """Le-Code track id (always readable, but only meaningful once a track is loaded)."""
        return int(self.backend.get(TRACK_ID))

    def wait_until_ready(
        self,
        stop: Any,
        poll_s: float = 1.0,
        sleep=time.sleep,
    ) -> bool:
        """Block until GameState == 2, retrying periodically. Returns False if stopped."""
        announced = False
        while not stop.is_set():
            try:
                if self.is_race_ready():
                    return True
                if not announced:
                    log.info("Waiting for the race cache (GameState != 2)...")
                    announced = True
            except GameManagerError as exc:
                log.warning("GameManager not ready: %s (retrying in %.1fs)", exc, poll_s)
            sleep(poll_s)
        return False

    # ------------------------------------------------------------ slot discovery
    def discover_own_slot(self) -> int:
        """The local player is the slot whose PlayerType is 0 ("Local")."""
        requests = [ResourceRequest(SLOT_DISCOVERY_RESOURCE, slot) for slot in range(SLOT_COUNT)]
        results = self.backend.get_many(requests)
        local = [
            slot
            for slot, result in enumerate(results)
            if result.success and result.value is not None and int(result.value) == PLAYER_TYPE_LOCAL
        ]
        if not local:
            failed = [r.error for r in results if not r.success]
            if failed:
                raise error_from_message(str(failed[0]))
            raise ResourceNotReady("No slot has PlayerType == 0 (local player) yet.")
        if len(local) > 1:
            log.info("Several local players found %s; using the lowest slot.", local)
        return local[0]

    # ------------------------------------------------------------------- reading
    def read_raw(self, slot: int, resources: Sequence[str] | None = None) -> tuple[dict[str, Any], float]:
        names = tuple(resources or self.resources)
        requests = [ResourceRequest(name, slot) for name in names]
        started = time.perf_counter()
        results = self.backend.get_many(requests)
        latency_ms = (time.perf_counter() - started) * 1000.0
        if len(results) != len(requests):
            raise GameManagerError(f"Expected {len(requests)} results, got {len(results)}")
        raw: dict[str, Any] = {}
        for request, result in zip(requests, results):
            if not result.success:
                raise error_from_message(f"{request.resource}: {result.error}")
            raw[request.resource] = result.value
        return raw, latency_ms

    def read_own_state(self, slot: int) -> PlayerState:
        raw, latency_ms = self.read_raw(slot)
        received_ns = time.perf_counter_ns()
        self.validator.check_raw(raw)
        self.validator.check_sequence(raw)
        return PlayerState.from_raw(slot, raw, received_ns=received_ns, read_latency_ms=latency_ms)

    def read_optional(self, slot: int, resources: Sequence[str]) -> dict[str, Any]:
        """Best-effort extra reads (e.g. human stick input); failures are skipped."""
        requests = [ResourceRequest(name, slot) for name in resources]
        out: dict[str, Any] = {}
        for request, result in zip(requests, self.backend.get_many(requests)):
            if result.success:
                out[request.resource] = result.value
        if out:
            self.validator.check_raw(out)
        return out
