"""Turns (PlayerState, TrackData) into steering-relevant hints for agents."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ai_kart_wii.geometry import Vec3, bearing, wrap_angle
from ai_kart_wii.map.interface import CollisionHit, PathGroup, TrackData
from ai_kart_wii.state.snapshot import PlayerState


@dataclass(frozen=True, slots=True)
class NavHint:
    nearest_index: int
    target: Vec3
    heading_error: float  # radians; target_yaw - current_yaw, wrapped. Sign: see geometry
    distance_to_target: float
    lateral_offset: float  # distance to the route polyline's nearest point
    route_progress: float  # 0..1 along the flattened route
    surface: CollisionHit | None


def flatten_main_route(groups: tuple[PathGroup, ...]) -> np.ndarray:
    """Follow the first `next` link from group 0 until it loops or ends.

    Returns an (N, 3) array. Branching routes (shortcuts) are ignored for now.
    """
    if not groups:
        return np.zeros((0, 3))
    by_index = {g.index: g for g in groups}
    current = groups[0].index
    seen: set[int] = set()
    points: list[tuple[float, float, float]] = []
    while current in by_index and current not in seen:
        seen.add(current)
        group = by_index[current]
        points.extend(p.position.as_tuple() for p in group.points)
        if not group.next:
            break
        current = group.next[0]
    return np.asarray(points, dtype=np.float64)


class Navigator:
    def __init__(self, track: TrackData, lookahead_points: int = 6, closed: bool = True) -> None:
        self.track = track
        self.route = flatten_main_route(track.enemy_paths)
        if len(self.route) < 2:
            raise ValueError(f"Track {track.le_code_track_id} has no usable enemy path")
        self.lookahead_points = lookahead_points
        self.closed = closed
        self._last_index: int | None = None

    def hint(self, state: PlayerState, speed_scale: float = 0.0) -> NavHint:
        pos = np.array([state.position.x, state.position.z])
        xz = self.route[:, [0, 2]]
        dist = np.hypot(xz[:, 0] - pos[0], xz[:, 1] - pos[1])
        nearest = int(np.argmin(dist))
        n = len(self.route)
        look = self.lookahead_points + int(speed_scale)
        target_idx = (nearest + look) % n if self.closed else min(nearest + look, n - 1)
        tx, ty, tz = self.route[target_idx]
        target = Vec3(float(tx), float(ty), float(tz))
        target_yaw = bearing(state.position, target)
        error = wrap_angle(target_yaw - state.yaw)
        self._last_index = nearest
        return NavHint(
            nearest_index=nearest,
            target=target,
            heading_error=error,
            distance_to_target=float(math.hypot(tx - pos[0], tz - pos[1])),
            lateral_offset=float(dist[nearest]),
            route_progress=nearest / n,
            surface=self.track.collision.query(state.position) if self.track.collision else None,
        )
