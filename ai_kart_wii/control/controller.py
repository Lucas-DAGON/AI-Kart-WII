from __future__ import annotations

from typing import Protocol, runtime_checkable

from ai_kart_wii.control.actions import ControllerAction


@runtime_checkable
class Controller(Protocol):
    def apply(self, action: ControllerAction) -> None:
        """Set the pad to this state (held until the next apply)."""

    def neutral(self) -> None: ...

    def close(self) -> None: ...
