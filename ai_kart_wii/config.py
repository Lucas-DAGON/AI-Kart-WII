"""Application configuration (plain dataclasses, optionally loaded from JSON)."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any


def app_root() -> Path:
    """Folder that holds data next to the code (or next to the exe when frozen)."""
    if getattr(sys, "frozen", False):  # PyInstaller
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def default_training_dir() -> Path:
    return app_root() / "training"


@dataclass
class GameManagerConfig:
    # Name used in GameManager's children.json / Register call.
    client_name: str = "AI-Kart-WIIManager"
    # Path to GameManager.Shared.dll. None = search the usual places.
    dll_path: str | None = None
    runtime_config: str | None = None
    connect_timeout_s: float = 30.0
    # Retry period while GameManager / the race cache is not ready.
    retry_interval_s: float = 1.0


@dataclass
class CaptureConfig:
    backend: str = "mss"  # "mss" | "synthetic" (tests)
    fps: int = 60
    # Regex matched against visible top-level window titles.
    window_title_regex: str = r"Dolphin"
    # Titles that must NOT match (e.g. our own console window).
    window_title_exclude_regex: str = r"AI-Kart|GameManager"
    min_window_size: tuple[int, int] = (320, 240)
    # Pixels to cut from the window's client area (menu bar, status bar, borders)
    # in case Dolphin is NOT rendering in its own borderless/exclusive window.
    crop_left: int = 0
    crop_top: int = 0
    crop_right: int = 0
    crop_bottom: int = 0
    # Re-locate the window every N grabs (handles moving/resizing the window).
    relocate_every: int = 120
    # Fixed region override (left, top, width, height) in screen pixels.
    fixed_region: tuple[int, int, int, int] | None = None


@dataclass
class ControlConfig:
    backend: str = "vigem"  # "vigem" | "fake"
    pad_index: int = 0
    stick_deadzone: float = 0.0


@dataclass
class RuntimeConfig:
    control_hz: int = 60
    state_poll_hz: int = 30
    # None = discover the local player slot automatically (PlayerType == 0).
    own_slot: int | None = None
    item_detect_every: int = 6
    verbose_validation: bool = False


@dataclass
class PathsConfig:
    training_dir: str = field(default_factory=lambda: str(default_training_dir()))
    szs_dir: str | None = None  # games/MTW/DEV/szs (used by the future map library)

    @property
    def recorded_runs(self) -> Path:
        return Path(self.training_dir) / "recorded_runs"

    @property
    def logs(self) -> Path:
        return Path(self.training_dir) / "logs"

    @property
    def models(self) -> Path:
        return Path(self.training_dir) / "models"


@dataclass
class AppConfig:
    game_manager: GameManagerConfig = field(default_factory=GameManagerConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    control: ControlConfig = field(default_factory=ControlConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)

    @classmethod
    def load(cls, path: str | Path | None) -> "AppConfig":
        config = cls()
        if path is None:
            return config
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        _apply(config, data)
        return config


def _apply(target: Any, data: dict[str, Any]) -> None:
    known = {f.name for f in fields(target)}
    for key, value in data.items():
        if key not in known:
            raise ValueError(f"Unknown config key '{key}' for {type(target).__name__}")
        current = getattr(target, key)
        if is_dataclass(current) and isinstance(value, dict):
            _apply(current, value)
        else:
            setattr(target, key, tuple(value) if isinstance(value, list) else value)
