"""Range checks for values coming from GameManager (verbose, rate-limited logging).

Several fields in memory.json are flagged uncertain. Every rule here is PROVISIONAL:
it encodes what we *expect*, so a violation is a prompt to verify the layout/units,
not proof that the data is wrong. Adjust RULES as you verify fields in game.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

log = logging.getLogger("ai_kart_wii.validation")


@dataclass(frozen=True, slots=True)
class Rule:
    minimum: float | None = None
    maximum: float | None = None
    allowed: frozenset[int] | None = None
    note: str = ""


@dataclass(frozen=True, slots=True)
class Violation:
    resource: str
    value: Any
    reason: str


def _r(lo: float | None, hi: float | None, note: str = "") -> Rule:
    return Rule(minimum=lo, maximum=hi, note=note)


RULES: dict[str, Rule] = {
    "GameState": Rule(allowed=frozenset({0, 1, 2}), note="lifecycle at 0x80000CF6"),
    "PlayerType": Rule(allowed=frozenset({0, 1, 2, 3, 4, 5}), note="0 Local, 1 CPU, 3 Ghost, 4 Online"),
    "TeamId": Rule(allowed=frozenset({0, 1}), note="0 Purple, 1 Blue"),
    "RacePosition": _r(1, 12),
    "RaceCompletion": _r(-1.0, 12.0, "float; exact semantics unverified"),
    "RaceCompletionMax": _r(-1.0, 12.0),
    "CurrentLap": _r(0, 9, "uint16 per mkw-structures; dump suggests uint8 at +0x24"),
    "CurrentLapCandidate": _r(0, 9),
    "MaxLap": _r(1, 9),
    "LapCount": _r(1, 9),
    "CurrentKcp": _r(0, 255),
    "MaxKcp": _r(0, 255),
    "CheckpointId": _r(0, 5000),
    "RaceFrameCounter": _r(0, 2**31),
    "VehicleSpeed": _r(-150.0, 400.0, "units/frame, bounds are a guess"),
    "DriftState": _r(0, 3),
    "MtCharge": _r(0, 1000),
    "SmtCharge": _r(0, 1500),
    "StarTimer": _r(0, 2000),
    "MegaTimer": _r(0, 2000),
    "ShockTimer": _r(0, 2000),
    "CrushTimer": _r(0, 2000),
    "BoostTypes": _r(0, 0xFFFF),
    "RespawnState": _r(0, 10),
    "PreRespawnTimer": _r(-1, 2000),
    "SolidOutOfBoundsTimer": _r(-1, 2000),
    "AirTime": _r(0, 100000),
    "DirectionX": _r(-1.01, 1.01, "unit vector component"),
    "DirectionY": _r(-1.01, 1.01),
    "DirectionZ": _r(-1.01, 1.01),
    "PhysicsPositionX": _r(-1e6, 1e6),
    "PhysicsPositionY": _r(-1e6, 1e6),
    "PhysicsPositionZ": _r(-1e6, 1e6),
    "StickX": _r(-1.01, 1.01),
    "StickY": _r(-1.01, 1.01),
    "LeCodeTrackId": _r(0, 0xFFFF),
}


def check_value(name: str, value: Any) -> Violation | None:
    rule = RULES.get(name)
    if rule is None or value is None:
        return None
    if isinstance(value, (bytes, bytearray, str, list, dict)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return Violation(name, value, "not a number")
    if not math.isfinite(number):
        return Violation(name, value, "not finite")
    if rule.allowed is not None and int(number) not in rule.allowed:
        return Violation(name, value, f"not one of {sorted(rule.allowed)}")
    if rule.minimum is not None and number < rule.minimum:
        return Violation(name, value, f"below {rule.minimum}")
    if rule.maximum is not None and number > rule.maximum:
        return Violation(name, value, f"above {rule.maximum}")
    return None


class StateValidator:
    """Validates raw reads and cross-checks consecutive snapshots.

    Logging is rate-limited: the first `burst` occurrences of each distinct problem
    are logged, then every `every`-th. With verbose=True everything is logged.
    """

    # Largest plausible horizontal jump between two reads before we call it a teleport
    # (respawn / bug). Units are game units; provisional.
    TELEPORT_UNITS = 6000.0

    def __init__(self, verbose: bool = False, burst: int = 3, every: int = 200) -> None:
        self.verbose = verbose
        self.burst = burst
        self.every = every
        self.counts: dict[str, int] = {}
        self.checked = 0
        self._last_frame: int | None = None
        self._last_pos: tuple[float, float] | None = None

    # ---------------------------------------------------------------- raw values
    def check_raw(self, raw: Mapping[str, Any]) -> list[Violation]:
        self.checked += 1
        problems: list[Violation] = []
        for name, value in raw.items():
            violation = check_value(name, value)
            if violation:
                problems.append(violation)
        problems.extend(self._cross_checks(raw))
        for violation in problems:
            self._report(violation)
        if self.verbose:
            log.debug("raw read: %s", dict(raw))
        return problems

    def _cross_checks(self, raw: Mapping[str, Any]) -> Iterable[Violation]:
        lap16 = raw.get("CurrentLap")
        lap8 = raw.get("CurrentLapCandidate")
        max_lap = raw.get("MaxLap")
        if lap16 is not None and lap8 is not None and lap16 != lap8:
            hint = " (looks like a uint8 read as uint16: bytes 01 00)" if lap16 == int(lap8) * 256 else ""
            yield Violation(
                "CurrentLap", lap16,
                f"CurrentLap(uint16)={lap16} differs from CurrentLapCandidate(uint8)={lap8}{hint}",
            )
        if lap8 is not None and max_lap is not None and int(lap8) > int(max_lap) + 1:
            yield Violation("CurrentLapCandidate", lap8, f"exceeds MaxLap={max_lap}")
        kcp, max_kcp = raw.get("CurrentKcp"), raw.get("MaxKcp")
        if kcp is not None and max_kcp is not None and int(kcp) > int(max_kcp):
            yield Violation("CurrentKcp", kcp, f"exceeds MaxKcp={max_kcp}")
        dx, dy, dz = raw.get("DirectionX"), raw.get("DirectionY"), raw.get("DirectionZ")
        if None not in (dx, dy, dz):
            length = math.sqrt(float(dx) ** 2 + float(dy) ** 2 + float(dz) ** 2)  # type: ignore[arg-type]
            if length < 0.9 or length > 1.1:
                yield Violation("Direction", (dx, dy, dz), f"vector length {length:.3f}, expected ~1")

    # ------------------------------------------------------- consecutive snapshots
    def check_sequence(self, raw: Mapping[str, Any]) -> list[Violation]:
        problems: list[Violation] = []
        frame = raw.get("RaceFrameCounter")
        if frame is not None:
            frame = int(frame)
            if self._last_frame is not None and frame < self._last_frame:
                problems.append(Violation("RaceFrameCounter", frame, f"went backwards from {self._last_frame} (restart?)"))
                self._last_pos = None
            self._last_frame = frame
        if "PhysicsPositionX" in raw and "PhysicsPositionZ" in raw:
            pos = (float(raw["PhysicsPositionX"]), float(raw["PhysicsPositionZ"]))
            if self._last_pos is not None:
                jump = math.hypot(pos[0] - self._last_pos[0], pos[1] - self._last_pos[1])
                if jump > self.TELEPORT_UNITS:
                    problems.append(Violation("PhysicsPosition", pos, f"jumped {jump:.0f} units between reads"))
            self._last_pos = pos
        for violation in problems:
            self._report(violation)
        return problems

    def reset_sequence(self) -> None:
        self._last_frame = None
        self._last_pos = None

    # ------------------------------------------------------------------- logging
    def _report(self, violation: Violation) -> None:
        key = f"{violation.resource}: {violation.reason}"
        count = self.counts.get(key, 0) + 1
        self.counts[key] = count
        if self.verbose or count <= self.burst or count % self.every == 0:
            log.warning("[validation] %s = %r -> %s (seen %d)", violation.resource, violation.value, violation.reason, count)

    def summary(self) -> str:
        if not self.counts:
            return f"validation: {self.checked} reads, no violations"
        lines = [f"validation: {self.checked} reads, {sum(self.counts.values())} violations"]
        lines += [f"  {n:6d}x {key}" for key, n in sorted(self.counts.items(), key=lambda kv: -kv[1])]
        return "\n".join(lines)
