"""In-memory GameManager (wrapper level). Mirrors GameManager's real behaviour:
race resources are NOT_READY unless GameState == 2, dynamic resources need a player id,
unknown names are INVALID_RESOURCE."""

from __future__ import annotations

from typing import Any, Sequence

from ai_kart_wii.ipc.backend import ResourceRequest, ResourceResult
from ai_kart_wii.ipc.errors import (
    GameManagerError,
    GameManagerUnavailable,
    InvalidRequest,
    InvalidResource,
    ResourceNotReady,
    error_from_message,
)
from ai_kart_wii.state.resources import GAME_STATE_CACHE_READY, RESOURCES
from ai_kart_wii.testing.fake_race import FakeRace

_NOT_READY_TEXT = {
    0: "no race is loaded and the race cache is not available",
    1: "the game has requested a cache build, but the cache is not ready yet",
}


class FakeBackend:
    def __init__(self, race: FakeRace | None = None) -> None:
        self.race = race or FakeRace()
        self._connected = False
        self.registered_as: str | None = None
        self.get_calls = 0
        self.get_many_calls = 0
        self._failures: list[GameManagerError] = []
        self.refuse_connect_times = 0

    # --------------------------------------------------------- test controls
    def inject_failures(self, *errors: GameManagerError) -> None:
        """The next len(errors) read calls raise these, in order."""
        self._failures.extend(errors)

    def drop_connection(self) -> None:
        self._connected = False

    # -------------------------------------------------------------- Backend API
    def connect(self, timeout_s: float = 30.0) -> None:
        if self.refuse_connect_times > 0:
            self.refuse_connect_times -= 1
            raise GameManagerUnavailable("fake: pipe not available")
        self._connected = True

    def register(self, name: str) -> None:
        self._require_connected()
        self.registered_as = name

    @property
    def connected(self) -> bool:
        return self._connected

    def close(self) -> None:
        self._connected = False

    def get(self, resource: str, player_id: int | None = None) -> Any:
        self._require_connected()
        self.get_calls += 1
        self._maybe_fail()
        return self._read(resource, player_id)

    def get_many(self, requests: Sequence[ResourceRequest]) -> list[ResourceResult]:
        self._require_connected()
        self.get_many_calls += 1
        self._maybe_fail()
        results: list[ResourceResult] = []
        for request in requests:
            try:
                results.append(ResourceResult(True, self._read(request.resource, request.player_id)))
            except GameManagerError as exc:
                # The real server only forwards the message text for batched items.
                results.append(ResourceResult(False, None, str(exc)))
        return results

    # ------------------------------------------------------------------ helpers
    def _require_connected(self) -> None:
        if not self._connected:
            raise GameManagerUnavailable("fake: not connected")

    def _maybe_fail(self) -> None:
        if self._failures:
            raise self._failures.pop(0)

    def _read(self, resource: str, player_id: int | None) -> Any:
        spec = RESOURCES.get(resource)
        if spec is None:
            raise InvalidResource(f"Memory resource '{resource}' was not found.")
        state = self.race.game_state
        if spec.race_only and state != GAME_STATE_CACHE_READY:
            raise ResourceNotReady(
                f"Resource '{resource}' is not ready: {_NOT_READY_TEXT.get(state, 'unknown state')} (state={state})."
            )
        if spec.dynamic and player_id is None:
            raise InvalidRequest(f"Resource '{resource}' requires a player ID.")
        try:
            return self.race.value(resource, player_id)
        except KeyError:
            return 0  # valid resource we do not simulate: a harmless zero
