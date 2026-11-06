"""Baseline driver: pure pursuit along the enemy path. No screenshots.

Uses the map reference data plus the AI player's own position/direction. It is the
reference the learned (screenshot-only) agents are measured and bootstrapped against.
"""

from __future__ import annotations

import math

from ai_kart_wii.control.actions import DrivingAction
from ai_kart_wii.env.observation import Observation
from ai_kart_wii.geometry import YAW_POSITIVE_IS_RIGHT, clamp


class WaypointFollowerAgent:
    def __init__(self, gain: float = 1.6, brake_error: float = 1.2, full_lock_error: float = 0.5) -> None:
        self.gain = gain
        self.brake_error = brake_error  # radians: sharper than this -> lift off / brake
        self.full_lock_error = full_lock_error

    def reset(self) -> None:
        pass

    def act(self, observation: Observation) -> DrivingAction:
        nav = observation.nav
        if nav is None:
            return DrivingAction(steer=0.0, accelerate=True)
        error = nav.heading_error if YAW_POSITIVE_IS_RIGHT else -nav.heading_error
        steer = clamp(error / self.full_lock_error * self.gain, -1.0, 1.0)
        too_sharp = abs(nav.heading_error) > self.brake_error
        return DrivingAction(steer=steer, accelerate=not too_sharp, brake=too_sharp and _fast(observation))


def _fast(observation: Observation) -> bool:
    state = observation.state
    return state is not None and math.fabs(state.speed) > 30.0
