"""Loads GameManager.Shared.dll into the current process through pythonnet.

UNVERIFIED: written without access to a Windows/.NET machine. First things to
check on your side: that pythonnet starts the coreclr runtime, and that
`clr.AddReference("GameManager.Shared")` finds the DLL.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_kart_wii.config import app_root
from ai_kart_wii.ipc.errors import GameManagerError

ENV_DLL = "AI_KART_WII_GM_SHARED_DLL"
ENV_RUNTIME_CONFIG = "AI_KART_WII_RUNTIME_CONFIG"
DLL_NAME = "GameManager.Shared.dll"


@dataclass
class SharedLibrary:
    """Handles to the .NET types we use (filled once the DLL is loaded)."""

    GameManagerClient: Any
    IpcResourceRequest: Any
    dll_path: Path


_loaded: SharedLibrary | None = None


def candidate_dll_paths(explicit: str | None) -> list[Path]:
    root = app_root()
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    if os.environ.get(ENV_DLL):
        candidates.append(Path(os.environ[ENV_DLL]))
    candidates += [
        root / DLL_NAME,
        root / "dotnet" / DLL_NAME,
        root.parent / "dotnet" / DLL_NAME,
        Path.cwd() / DLL_NAME,
        Path.cwd() / "dotnet" / DLL_NAME,
    ]
    # Development layout: build output of the submodule next to the solution.
    for parent in list(Path(__file__).resolve().parents)[:8]:
        base = parent / "libraries" / "GameManager.Shared" / "GameManager.Shared"
        for config in ("Release", "Debug"):
            candidates.append(base / "bin" / config / "net10.0" / DLL_NAME)
    return candidates


def find_dll(explicit: str | None = None) -> Path:
    candidates = candidate_dll_paths(explicit)
    for path in candidates:
        if path.is_file():
            return path.resolve()
    searched = "\n  ".join(str(p) for p in candidates[:10])
    raise GameManagerError(
        f"{DLL_NAME} not found. Build it (see README) and set "
        f"gameManager.dll_path or {ENV_DLL}. Searched:\n  {searched}"
    )


def find_runtime_config(explicit: str | None = None) -> Path | None:
    for raw in (explicit, os.environ.get(ENV_RUNTIME_CONFIG)):
        if raw and Path(raw).is_file():
            return Path(raw).resolve()
    root = app_root()
    for path in (
        root / "dotnet" / "ai_kart_wii.runtimeconfig.json",
        root.parent / "dotnet" / "ai_kart_wii.runtimeconfig.json",
        Path.cwd() / "dotnet" / "ai_kart_wii.runtimeconfig.json",
    ):
        if path.is_file():
            return path.resolve()
    return None


def load_shared_library(
    dll_path: str | None = None, runtime_config: str | None = None
) -> SharedLibrary:
    global _loaded
    if _loaded is not None:
        return _loaded

    dll = find_dll(dll_path)
    config = find_runtime_config(runtime_config)

    try:
        from pythonnet import load as pythonnet_load

        if config is not None:
            pythonnet_load("coreclr", runtime_config=str(config))
        else:
            pythonnet_load("coreclr")
        import clr  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - needs pythonnet/.NET
        raise GameManagerError(f"Could not start the .NET runtime via pythonnet: {exc}") from exc

    sys.path.append(str(dll.parent))
    clr.AddReference("GameManager.Shared")  # pragma: no cover

    from GameManager.Shared.Client import GameManagerClient  # type: ignore[import-not-found]
    from GameManager.Shared.Ipc import IpcResourceRequest  # type: ignore[import-not-found]

    _loaded = SharedLibrary(GameManagerClient, IpcResourceRequest, dll)
    return _loaded
