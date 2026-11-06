"""Contract for the future C# map library (KMP / KCL / model data).

The library will live under libraries/ and be wrapped through pythonnet like the
GameManager client. Until it exists, agents and the navigator only depend on the
types below, and tests use FakeMapProvider.

Open design points are listed in README.md ("Map library contract").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ai_kart_wii.geometry import Vec3


@dataclass(frozen=True, slots=True)
class Checkpoint:
    index: int
    left: tuple[float, float]  # (x, z) of the left end
    right: tuple[float, float]
    key: int = 0  # KMP key-checkpoint id (lap logic), 0 = normal


@dataclass(frozen=True, slots=True)
class PathPoint:
    position: Vec3
    scale: float = 1.0  # half-width hint (ENPT "deviation"/scale)


@dataclass(frozen=True, slots=True)
class PathGroup:
    """One KMP enemy-path group (ENPH). `next` are indices of following groups."""

    index: int
    points: tuple[PathPoint, ...]
    next: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class CollisionHit:
    surface_type: int  # KCL base type (road, offroad, wall, boost pad, ...)
    variant: int = 0
    height: float = 0.0
    normal: Vec3 = field(default_factory=lambda: Vec3(0.0, 1.0, 0.0))


@runtime_checkable
class CollisionQuery(Protocol):
    def query(self, position: Vec3) -> CollisionHit | None:
        """Surface under/at the position, or None when outside any triangle."""


@dataclass(frozen=True, slots=True)
class TrackData:
    le_code_track_id: int
    name: str
    lap_count: int
    checkpoints: tuple[Checkpoint, ...]
    enemy_paths: tuple[PathGroup, ...]
    item_paths: tuple[PathGroup, ...] = ()
    collision: CollisionQuery | None = None


@runtime_checkable
class MapProvider(Protocol):
    def load_track(self, le_code_track_id: int) -> TrackData:
        """Raises KeyError / FileNotFoundError when the track is unknown."""


class PythonNetMapProvider:
    """Placeholder for the real C# library wrapper.

    Wire this up once the library exists: load the DLL with
    ai_kart_wii.ipc.dotnet_loader-style code, locate "<id>.szs" in
    paths.szs_dir (games/MTW/DEV/szs; "_d" files are multiplayer variants we ignore),
    and convert the C# KMP/KCL objects into TrackData.
    """

    def __init__(self, szs_dir: str | None = None) -> None:
        self.szs_dir = szs_dir

    def load_track(self, le_code_track_id: int) -> TrackData:
        raise NotImplementedError("The C# map library is not available yet.")
