"""Virtual Xbox 360 controller through ViGEmBus (vgamepad).

Dolphin must be configured so its GameCube controller port reads this virtual
pad, using the table below (or edit GC_TO_XUSB and Dolphin's mapping to match).

UNVERIFIED: written without Windows/ViGEmBus. vgamepad is imported lazily so the
rest of the package works anywhere.
"""

from __future__ import annotations

from typing import Any

from ai_kart_wii.control.actions import NEUTRAL, ControllerAction

# GameCube input  ->  Xbox 360 name used by vgamepad.XUSB_BUTTON.XUSB_GAMEPAD_<name>
GC_TO_XUSB: dict[str, str] = {
    "A": "A",
    "B": "B",
    "X": "X",
    "Y": "Y",
    "Z": "RIGHT_SHOULDER",
    "START": "START",
    "DPAD_UP": "DPAD_UP",
    "DPAD_DOWN": "DPAD_DOWN",
    "DPAD_LEFT": "DPAD_LEFT",
    "DPAD_RIGHT": "DPAD_RIGHT",
}
# Analog: L -> left trigger, R -> right trigger, stick -> left stick, C-stick -> right stick.


class ViGEmController:
    def __init__(self, pad: Any | None = None, vg_module: Any | None = None) -> None:
        if vg_module is None:
            import vgamepad as vg  # type: ignore[import-not-found]

            vg_module = vg
        self._vg = vg_module
        self._pad = pad if pad is not None else vg_module.VX360Gamepad()
        self._held: set[str] = set()
        self.apply(NEUTRAL)

    def _button(self, gc_name: str) -> Any:
        return getattr(self._vg.XUSB_BUTTON, f"XUSB_GAMEPAD_{GC_TO_XUSB[gc_name]}")

    def apply(self, action: ControllerAction) -> None:
        action = action.clamped()
        wanted = set(action.buttons)
        for name in self._held - wanted:
            self._pad.release_button(button=self._button(name))
        for name in wanted - self._held:
            self._pad.press_button(button=self._button(name))
        self._held = wanted
        self._pad.left_joystick_float(x_value_float=action.stick_x, y_value_float=action.stick_y)
        self._pad.right_joystick_float(x_value_float=action.c_x, y_value_float=action.c_y)
        self._pad.left_trigger_float(value_float=action.l)
        self._pad.right_trigger_float(value_float=action.r)
        self._pad.update()

    def neutral(self) -> None:
        self.apply(NEUTRAL)

    def close(self) -> None:
        try:
            self.neutral()
        finally:
            self._pad = None
