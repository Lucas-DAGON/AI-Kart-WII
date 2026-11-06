from __future__ import annotations

from typing import Protocol, runtime_checkable

from ai_kart_wii.control.actions import DrivingAction
from ai_kart_wii.env.observation import Observation


@runtime_checkable
class Agent(Protocol):
    def reset(self) -> None:
        """Called at the start of every race (also after a restart)."""

    def act(self, observation: Observation) -> DrivingAction: ...
