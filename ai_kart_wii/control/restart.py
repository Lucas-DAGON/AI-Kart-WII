"""Restart the race through the in-game pause menu: Start, Down, A.

The pause-menu layout of the mod is an assumption; adjust STEPS (and add a second
"A" if a confirmation dialog appears). After the sequence the game drops back to
GameState 0/1 and MTWManager rebuilds the cache, so we wait for state 2 again.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

from ai_kart_wii.control.actions import NEUTRAL, ControllerAction
from ai_kart_wii.control.controller import Controller
from ai_kart_wii.ipc.errors import GameManagerError
from ai_kart_wii.state.resources import GAME_STATE_CACHE_READY

log = logging.getLogger(__name__)

FRAME_S = 1.0 / 60.0


@dataclass(frozen=True)
class Step:
    action: ControllerAction
    hold_s: float
    pause_after_s: float


DEFAULT_STEPS: tuple[Step, ...] = (
    Step(ControllerAction(buttons=frozenset({"START"})), hold_s=3 * FRAME_S, pause_after_s=0.6),
    Step(ControllerAction(buttons=frozenset({"DPAD_DOWN"})), hold_s=3 * FRAME_S, pause_after_s=0.3),
    Step(ControllerAction(buttons=frozenset({"A"})), hold_s=3 * FRAME_S, pause_after_s=0.3),
)


def press_sequence(
    controller: Controller,
    steps: tuple[Step, ...] = DEFAULT_STEPS,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    for step in steps:
        controller.apply(step.action)
        sleep(step.hold_s)
        controller.apply(NEUTRAL)
        sleep(step.pause_after_s)


def restart_race(
    controller: Controller,
    reader: Any,
    *,
    steps: tuple[Step, ...] = DEFAULT_STEPS,
    timeout_s: float = 60.0,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> bool:
    """Press the restart sequence and wait for the race cache to be ready again."""
    press_sequence(controller, steps, sleep)
    deadline = clock() + timeout_s
    left_ready = False
    while clock() < deadline:
        try:
            state = reader.read_game_state()
        except GameManagerError:
            state = None
        if state is not None and state != GAME_STATE_CACHE_READY:
            left_ready = True
        elif state == GAME_STATE_CACHE_READY and left_ready:
            return True
        sleep(0.1)
    log.warning("Restart did not complete within %.0fs (left_ready=%s)", timeout_s, left_ready)
    return False
