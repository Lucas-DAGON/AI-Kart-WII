"""Controller vocabulary.

Dolphin sees a *GameCube controller*, which is mapped to a virtual Xbox 360 pad
(ViGEmBus). ControllerAction therefore speaks GameCube; the Xbox mapping lives in
virtual_pad.py and the Dolphin-side mapping is something you configure once.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet

from ai_kart_wii.geometry import clamp

GC_BUTTONS = frozenset(
    {"A", "B", "X", "Y", "Z", "START", "DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT"}
)


@dataclass(frozen=True, slots=True)
class ControllerAction:
    """Low-level GameCube pad state. Sticks are -1..1 (right/up positive)."""

    stick_x: float = 0.0
    stick_y: float = 0.0
    c_x: float = 0.0
    c_y: float = 0.0
    l: float = 0.0  # analog trigger 0..1
    r: float = 0.0
    buttons: FrozenSet[str] = field(default_factory=frozenset)

    def clamped(self) -> "ControllerAction":
        unknown = self.buttons - GC_BUTTONS
        if unknown:
            raise ValueError(f"Unknown GameCube buttons: {sorted(unknown)}")
        return ControllerAction(
            clamp(self.stick_x, -1.0, 1.0), clamp(self.stick_y, -1.0, 1.0),
            clamp(self.c_x, -1.0, 1.0), clamp(self.c_y, -1.0, 1.0),
            clamp(self.l, 0.0, 1.0), clamp(self.r, 0.0, 1.0),
            self.buttons,
        )


NEUTRAL = ControllerAction()


@dataclass(frozen=True, slots=True)
class DrivingAction:
    """What an agent decides, independent of the physical button layout."""

    steer: float = 0.0  # -1 full left .. +1 full right
    accelerate: bool = True
    brake: bool = False
    drift: bool = False  # hop / drift button (future: not used by the basic driver)
    use_item: bool = False
    rear_view: bool = False
    # D-pad: "up" | "down" | "left" | "right" | None. Used for tricks in the air and, on
    # bikes, "up" on the ground is the wheelie.
    trick: str | None = None


@dataclass(frozen=True, slots=True)
class ControlScheme:
    """Maps driving meanings to GameCube inputs.

    Confirmed controls: A accelerate, B brake/reverse, R drift/hop, L use item,
    X rear view, D-pad tricks (bike: D-pad up on the ground = wheelie).
    """

    accelerate_button: str = "A"
    brake_button: str = "B"
    drift_trigger: str = "r"  # "l" or "r" analog trigger
    item_trigger: str = "l"
    rear_view_button: str = "X"

    def to_controller(self, action: DrivingAction) -> ControllerAction:
        buttons: set[str] = set()
        if action.accelerate:
            buttons.add(self.accelerate_button)
        if action.brake:
            buttons.add(self.brake_button)
        if action.rear_view:
            buttons.add(self.rear_view_button)
        if action.trick is not None:
            if action.trick not in ("up", "down", "left", "right"):
                raise ValueError(f"Unknown trick direction: {action.trick!r}")
            buttons.add(f"DPAD_{action.trick.upper()}")
        analog = {"l": 0.0, "r": 0.0}
        if action.drift:
            analog[self.drift_trigger] = 1.0
        if action.use_item:
            analog[self.item_trigger] = 1.0
        return ControllerAction(
            stick_x=clamp(action.steer, -1.0, 1.0),
            l=analog["l"],
            r=analog["r"],
            buttons=frozenset(buttons),
        )

    def to_driving(self, pad: ControllerAction) -> DrivingAction:
        """Inverse of to_controller: used to turn recorded human input into labels."""
        trick = next((d for d in ("up", "down", "left", "right") if f"DPAD_{d.upper()}" in pad.buttons), None)
        triggers = {"l": pad.l, "r": pad.r}
        return DrivingAction(
            steer=pad.stick_x,
            accelerate=self.accelerate_button in pad.buttons,
            brake=self.brake_button in pad.buttons,
            drift=triggers[self.drift_trigger] > 0.5,
            use_item=triggers[self.item_trigger] > 0.5,
            rear_view=self.rear_view_button in pad.buttons,
            trick=trick,
        )
