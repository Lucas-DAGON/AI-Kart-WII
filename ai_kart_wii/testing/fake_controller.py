from __future__ import annotations

from ai_kart_wii.control.actions import ControllerAction
from ai_kart_wii.testing.fake_race import FakeRace


class FakeController:
    """Records every action; optionally forwards it to a FakeRace."""

    def __init__(self, race: FakeRace | None = None) -> None:
        self.race = race
        self.history: list[ControllerAction] = []
        self.closed = False

    def apply(self, action: ControllerAction) -> None:
        self.history.append(action)
        if self.race is not None:
            self.race.apply(action)

    def neutral(self) -> None:
        self.apply(ControllerAction())

    def close(self) -> None:
        self.closed = True
