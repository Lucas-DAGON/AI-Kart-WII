import pytest

from ai_kart_wii.control.actions import ControllerAction, ControlScheme, DrivingAction
from ai_kart_wii.control.restart import DEFAULT_STEPS, press_sequence, restart_race
from ai_kart_wii.control.virtual_pad import GC_TO_XUSB, ViGEmController
from ai_kart_wii.testing.fake_controller import FakeController


class FakePad:
    def __init__(self):
        self.calls = []

    def press_button(self, button): self.calls.append(("press", button))
    def release_button(self, button): self.calls.append(("release", button))
    def left_joystick_float(self, x_value_float, y_value_float): self.calls.append(("left", x_value_float, y_value_float))
    def right_joystick_float(self, x_value_float, y_value_float): self.calls.append(("right", x_value_float, y_value_float))
    def left_trigger_float(self, value_float): self.calls.append(("lt", value_float))
    def right_trigger_float(self, value_float): self.calls.append(("rt", value_float))
    def update(self): self.calls.append(("update",))


class FakeVg:
    class XUSB_BUTTON:
        pass


for _name in set(GC_TO_XUSB.values()):
    setattr(FakeVg.XUSB_BUTTON, f"XUSB_GAMEPAD_{_name}", f"btn:{_name}")


def test_scheme_maps_driving_to_gamecube():
    pad = ControlScheme().to_controller(DrivingAction(steer=-2.0, accelerate=True, drift=True, use_item=True))
    assert pad.stick_x == -1.0 and pad.buttons == frozenset({"A"}) and pad.r == 1.0 and pad.l == 1.0


def test_unknown_button_rejected():
    with pytest.raises(ValueError):
        ControllerAction(buttons=frozenset({"TURBO"})).clamped()


def test_vigem_press_release_and_axes():
    pad = FakePad()
    c = ViGEmController(pad=pad, vg_module=FakeVg)
    pad.calls.clear()
    c.apply(ControllerAction(stick_x=0.5, r=1.0, buttons=frozenset({"A", "Z"})))
    presses = {call[1] for call in pad.calls if call[0] == "press"}
    assert presses == {"btn:A", "btn:RIGHT_SHOULDER"}
    assert ("left", 0.5, 0.0) in pad.calls and ("rt", 1.0) in pad.calls
    pad.calls.clear()
    c.apply(ControllerAction(buttons=frozenset({"A"})))
    assert ("release", "btn:RIGHT_SHOULDER") in pad.calls
    assert not any(call[0] == "press" for call in pad.calls)


def test_press_sequence_is_start_down_a():
    fake = FakeController()
    press_sequence(fake, DEFAULT_STEPS, sleep=lambda _: None)
    pressed = [next(iter(a.buttons)) for a in fake.history if a.buttons]
    assert pressed == ["START", "DPAD_DOWN", "A"]
    assert not fake.history[-1].buttons


def test_restart_waits_for_cache_rebuild(backend, race):
    race.begin_race(instant=True)
    from ai_kart_wii.state.reader import RaceStateReader

    reader = RaceStateReader(backend)
    fake = FakeController()
    state = {"n": 0}

    def sleep(_):
        state["n"] += 1
        if state["n"] == 7:      # after the 3 button steps (6 sleeps) the game restarts
            race.begin_race()
        race.step(10)

    t = {"v": 0.0}
    ok = restart_race(fake, reader, sleep=sleep, clock=lambda: t.__setitem__("v", t["v"] + 0.1) or t["v"], timeout_s=30)
    assert ok is True
