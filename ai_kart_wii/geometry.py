"""Small geometry helpers shared by state, map and agents.

Game coordinates: X and Z are the horizontal plane, Y is up (Mario Kart Wii).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# VERIFY IN GAME: is a positive yaw (atan2(dirX, dirZ) increasing) a turn to the
# right? Everything that turns "heading error" into a steering value goes through
# this single constant, so flipping it here fixes every agent at once.
YAW_POSITIVE_IS_RIGHT: bool = True


@dataclass(frozen=True, slots=True)
class Vec3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __add__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def scaled(self, k: float) -> "Vec3":
        return Vec3(self.x * k, self.y * k, self.z * k)

    def norm(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def horizontal_norm(self) -> float:
        return math.hypot(self.x, self.z)

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


def wrap_angle(angle: float) -> float:
    """Wrap to (-pi, pi]."""
    wrapped = (angle + math.pi) % (2.0 * math.pi) - math.pi
    return math.pi if wrapped == -math.pi else wrapped


def yaw_from_direction(dx: float, dz: float) -> float:
    return math.atan2(dx, dz)


def bearing(origin: Vec3, target: Vec3) -> float:
    """Yaw of the horizontal vector origin -> target."""
    return math.atan2(target.x - origin.x, target.z - origin.z)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
