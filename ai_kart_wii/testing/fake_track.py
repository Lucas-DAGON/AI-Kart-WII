"""A synthetic oval track used by tests, the demo and the fake game."""

from __future__ import annotations

import math

from ai_kart_wii.geometry import Vec3
from ai_kart_wii.map.interface import (
    Checkpoint,
    CollisionHit,
    PathGroup,
    PathPoint,
    TrackData,
)

SURFACE_ROAD = 0
SURFACE_OFFROAD = 1


class OvalCollision:
    def __init__(self, a: float, b: float, half_width: float) -> None:
        self.a, self.b, self.half_width = a, b, half_width

    def query(self, position: Vec3) -> CollisionHit | None:
        r = math.hypot(position.x / self.a, position.z / self.b)
        # approximate distance from the ellipse centre-line
        distance = abs(r - 1.0) * min(self.a, self.b)
        surface = SURFACE_ROAD if distance <= self.half_width else SURFACE_OFFROAD
        return CollisionHit(surface_type=surface)


def oval_point(a: float, b: float, phi: float) -> tuple[float, float]:
    return a * math.cos(phi), b * math.sin(phi)


def make_oval_track(
    le_code_track_id: int = 0,
    a: float = 12000.0,
    b: float = 7000.0,
    points: int = 72,
    lap_count: int = 3,
    half_width: float = 600.0,
) -> TrackData:
    path = []
    for i in range(points):
        x, z = oval_point(a, b, 2 * math.pi * i / points)
        path.append(PathPoint(Vec3(x, 0.0, z), scale=1.0))
    group = PathGroup(index=0, points=tuple(path), next=(0,))
    checkpoints = tuple(
        Checkpoint(
            index=i,
            left=oval_point(a - half_width, b - half_width, 2 * math.pi * i / 12),
            right=oval_point(a + half_width, b + half_width, 2 * math.pi * i / 12),
            key=1 if i == 0 else 0,
        )
        for i in range(12)
    )
    return TrackData(
        le_code_track_id=le_code_track_id,
        name="FakeOval",
        lap_count=lap_count,
        checkpoints=checkpoints,
        enemy_paths=(group,),
        collision=OvalCollision(a, b, half_width),
    )


class FakeMapProvider:
    def __init__(self, tracks: dict[int, TrackData] | None = None) -> None:
        self.tracks = tracks or {0: make_oval_track(0)}
        self.loaded: list[int] = []

    def load_track(self, le_code_track_id: int) -> TrackData:
        self.loaded.append(le_code_track_id)
        try:
            return self.tracks[le_code_track_id]
        except KeyError:
            raise KeyError(f"Unknown fake track {le_code_track_id}") from None
