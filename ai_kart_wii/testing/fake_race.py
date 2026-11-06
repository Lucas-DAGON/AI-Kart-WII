"""A tiny deterministic Mario-Kart-like simulation behind the fake GameManager.

It only has to be good enough to close the loop in tests: a kart with throttle,
brake and steering on an oval, producing the same resource names the real game
exposes (memory.json) with the same lifecycle (GameState 0 -> 1 -> 2).
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from typing import Any

from ai_kart_wii.control.actions import ControllerAction
from ai_kart_wii.testing.fake_track import oval_point

DT = 1.0 / 60.0


@dataclass
class KartSim:
    x: float
    z: float
    yaw: float = 0.0  # direction = (sin yaw, 0, cos yaw); positive yaw = turning right
    speed: float = 0.0  # units / frame
    max_speed: float = 80.0
    accel: float = 1.2
    brake: float = 3.0
    drag: float = 0.01
    turn_rate: float = 0.045  # rad / frame at full lock

    def step(self, accelerate: bool, braking: bool, steer: float) -> None:
        if accelerate:
            self.speed = min(self.max_speed, self.speed + self.accel)
        if braking:
            self.speed = max(-20.0, self.speed - self.brake)
        self.speed *= 1.0 - self.drag
        grip = min(1.0, abs(self.speed) / 20.0)
        self.yaw += steer * self.turn_rate * grip
        self.x += math.sin(self.yaw) * self.speed
        self.z += math.cos(self.yaw) * self.speed


class FakeRace:
    """Shared by FakeBackend (reads) and FakeController (writes)."""

    CACHE_BUILD_FRAMES = 30

    def __init__(
        self,
        a: float = 12000.0,
        b: float = 7000.0,
        lap_count: int = 3,
        own_slot: int = 0,
        le_code_track_id: int = 0,
        slots: int = 12,
    ) -> None:
        self.a, self.b = a, b
        self.lap_count = lap_count
        self.own_slot = own_slot
        self.le_code_track_id = le_code_track_id
        self.slots = slots
        self.lock = threading.RLock()
        self.game_state = 0
        self.race_frame = 0
        self._build_countdown = 0
        self.kart = KartSim(x=a, z=0.0, yaw=0.0)
        self._unwrapped_phi = 0.0
        self._last_phi = 0.0
        self.action = ControllerAction()
        self.pressed_log: list[ControllerAction] = []

    # ----------------------------------------------------------- lifecycle
    def begin_race(self, instant: bool = False) -> None:
        """Game asks MTWManager for a cache (state 1); ready after a few frames."""
        with self.lock:
            self.kart = KartSim(x=self.a, z=0.0, yaw=0.0)
            self._unwrapped_phi = 0.0
            self._last_phi = 0.0
            self.race_frame = 0
            if instant:
                self.game_state = 2
            else:
                self.game_state = 1
                self._build_countdown = self.CACHE_BUILD_FRAMES

    def end_race(self) -> None:
        with self.lock:
            self.game_state = 0

    def apply(self, action: ControllerAction) -> None:
        with self.lock:
            self.action = action
            self.pressed_log.append(action)

    def step(self, frames: int = 1) -> None:
        with self.lock:
            for _ in range(frames):
                if self.game_state == 1:
                    self._build_countdown -= 1
                    if self._build_countdown <= 0:
                        self.game_state = 2
                    continue
                if self.game_state != 2:
                    continue
                act = self.action
                self.kart.step("A" in act.buttons, "B" in act.buttons, act.stick_x)
                self.race_frame += 1
                phi = math.atan2(self.kart.z / self.b, self.kart.x / self.a)
                delta = (phi - self._last_phi + math.pi) % (2 * math.pi) - math.pi
                self._unwrapped_phi += delta
                self._last_phi = phi

    # -------------------------------------------------------------- derived
    @property
    def completion(self) -> float:
        return max(0.0, self._unwrapped_phi / (2 * math.pi))

    # --------------------------------------------------------------- values
    def value(self, name: str, slot: int | None) -> Any:
        with self.lock:
            if name == "GameState":
                return self.game_state
            if name == "LeCodeTrackId":
                return self.le_code_track_id
            if name == "GameId":
                return "MTWP01"
            return self._race_value(name, 0 if slot is None else slot)

    def _race_value(self, name: str, slot: int) -> Any:
        mine = slot == self.own_slot
        k = self.kart
        lap = min(int(self.completion) + 1, self.lap_count)
        table: dict[str, Any] = {
            "PlayerType": 0 if mine else 1,
            "TeamId": slot % 2,
            "RaceFrameCounter": self.race_frame,
            "PhysicsPositionX": k.x if mine else 0.0,
            "PhysicsPositionY": 0.0,
            "PhysicsPositionZ": k.z if mine else 0.0,
            "DirectionX": math.sin(k.yaw) if mine else 0.0,
            "DirectionY": 0.0,
            "DirectionZ": math.cos(k.yaw) if mine else 1.0,
            "VehicleSpeed": k.speed if mine else 0.0,
            "RaceCompletion": self.completion if mine else 0.0,
            "RaceCompletionMax": self.completion if mine else 0.0,
            "RacePosition": 1 if mine else slot + 1,
            "CurrentLap": lap,
            "CurrentLapCandidate": lap,
            "MaxLap": self.lap_count,
            "LapCount": self.lap_count,
            "CurrentKcp": 0, "MaxKcp": 11, "CheckpointId": 0,
            "DriftState": 0, "MtCharge": 0, "SmtCharge": 0,
            "StarTimer": 0, "MegaTimer": 0, "ShockTimer": 0, "CrushTimer": 0,
            "BoostTypes": 0, "RespawnState": 0, "PreRespawnTimer": 0,
            "SolidOutOfBoundsTimer": 0, "AirTime": 0,
            "StickX": self.action.stick_x if mine else 0.0,
            "StickY": self.action.stick_y if mine else 0.0,
            "InputFlags0": 0, "InputFlags1": 0, "InputFlags2": 0, "InputFlags3": 0,
        }
        if name not in table:
            raise KeyError(name)
        return table[name]

    def start_position(self) -> tuple[float, float]:
        return oval_point(self.a, self.b, 0.0)
