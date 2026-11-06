"""The control loop: frame + latest state + map hint -> agent -> virtual pad."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable

from ai_kart_wii.agent.base import Agent
from ai_kart_wii.capture.source import FrameSource
from ai_kart_wii.control.actions import ControlScheme, ControllerAction, DrivingAction
from ai_kart_wii.control.controller import Controller
from ai_kart_wii.env.observation import Observation
from ai_kart_wii.items.detector import ItemDetection, ItemDetector
from ai_kart_wii.map.interface import MapProvider
from ai_kart_wii.map.navigation import Navigator
from ai_kart_wii.runtime.pacer import Pacer
from ai_kart_wii.state.poller import StatePoller

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StepResult:
    step: int
    observation: Observation
    action: DrivingAction | None  # None = idle (race not ready / no state)
    controller_action: ControllerAction


class DrivingLoop:
    def __init__(
        self,
        *,
        frames: FrameSource,
        poller: StatePoller,
        agent: Agent,
        controller: Controller,
        scheme: ControlScheme | None = None,
        maps: MapProvider | None = None,
        items: ItemDetector | None = None,
        item_every: int = 6,
        recorder=None,
        on_step: Callable[[StepResult], None] | None = None,
    ) -> None:
        self.frames, self.poller, self.agent, self.controller = frames, poller, agent, controller
        self.scheme = scheme or ControlScheme()
        self.maps, self.items, self.item_every = maps, items, max(1, item_every)
        self.recorder, self.on_step = recorder, on_step
        self.navigator: Navigator | None = None
        self.step_count = 0
        self._epoch_seen = -1
        self._last_item = ItemDetection(None, 0.0)

    # --------------------------------------------------------------- one tick
    def step(self) -> StepResult:
        frame = self.frames.grab()
        state = self.poller.latest()

        if state is not None and self.poller.epoch != self._epoch_seen:
            self._on_new_race()

        age_ms = (time.perf_counter_ns() - state.received_ns) / 1e6 if state else float("inf")
        nav = self.navigator.hint(state) if (state is not None and self.navigator) else None

        if frame is not None and self.items is not None and self.step_count % self.item_every == 0:
            self._last_item = self.items.detect(frame.image)

        observation = Observation(frame, state, age_ms, nav, self._last_item, self.step_count)
        if state is None:
            action = None
            pad = ControllerAction()  # neutral while the race is not ready
        else:
            action = self.agent.act(observation)
            pad = self.scheme.to_controller(action)
        self.controller.apply(pad)

        result = StepResult(self.step_count, observation, action, pad)
        if self.recorder is not None:
            self.recorder.record(result)
        if self.on_step is not None:
            self.on_step(result)
        self.step_count += 1
        return result

    def _on_new_race(self) -> None:
        self._epoch_seen = self.poller.epoch
        self.agent.reset()
        self.navigator = None
        track_id = self.poller.track_id
        if self.maps is not None and track_id is not None:
            try:
                self.navigator = Navigator(self.maps.load_track(track_id))
                log.info("Loaded map data for Le-Code track %d", track_id)
            except (KeyError, FileNotFoundError, NotImplementedError, ValueError) as exc:
                log.warning("No map data for track %s: %s (driving without it)", track_id, exc)

    # ---------------------------------------------------------------- running
    def run(self, stop: threading.Event, hz: float = 60.0, max_steps: int | None = None, pacer: Pacer | None = None) -> None:
        pacer = pacer or Pacer(hz)
        try:
            while not stop.is_set() and (max_steps is None or self.step_count < max_steps):
                self.step()
                pacer.wait()
        finally:
            self.controller.neutral()
            if pacer.overruns:
                log.info("Control loop overran its %.1f ms budget %d times", pacer.period * 1000, pacer.overruns)
