from __future__ import annotations

from ai_kart_wii.control.actions import ControllerAction


class NullController:
    """Does nothing (used while recording a human, who holds the real pad)."""

    def apply(self, action: ControllerAction) -> None: ...
    def neutral(self) -> None: ...
    def close(self) -> None: ...
