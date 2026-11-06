"""Find the Dolphin render area from the OS (works borderless or windowed).

Windows-only (ctypes + user32). The pure helpers (selection, cropping) are
OS-independent and unit-tested; the Win32 enumeration is UNVERIFIED here.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Callable, Protocol, Sequence


@dataclass(frozen=True, slots=True)
class Region:
    left: int
    top: int
    width: int
    height: int

    @property
    def area(self) -> int:
        return self.width * self.height

    def cropped(self, left: int = 0, top: int = 0, right: int = 0, bottom: int = 0) -> "Region":
        width = self.width - left - right
        height = self.height - top - bottom
        if width <= 0 or height <= 0:
            raise ValueError(f"Crop leaves nothing of {self}")
        return Region(self.left + left, self.top + top, width, height)


@dataclass(frozen=True, slots=True)
class WindowInfo:
    title: str
    client: Region  # client area in screen pixels


class RegionLocator(Protocol):
    def locate(self) -> Region | None: ...


def select_window(
    windows: Sequence[WindowInfo],
    include: str,
    exclude: str = "",
    min_size: tuple[int, int] = (320, 240),
) -> WindowInfo | None:
    """Pick the largest window whose title matches `include` and not `exclude`."""
    include_re = re.compile(include, re.IGNORECASE)
    exclude_re = re.compile(exclude, re.IGNORECASE) if exclude else None
    matches = [
        w
        for w in windows
        if include_re.search(w.title)
        and not (exclude_re and exclude_re.search(w.title))
        and w.client.width >= min_size[0]
        and w.client.height >= min_size[1]
    ]
    return max(matches, key=lambda w: w.client.area, default=None)


class FixedRegionLocator:
    def __init__(self, region: Region) -> None:
        self.region = region

    def locate(self) -> Region | None:
        return self.region


class Win32RegionLocator:
    """Locates the Dolphin window's client area in physical screen pixels."""

    def __init__(
        self,
        include: str = r"Dolphin",
        exclude: str = r"AI-Kart|GameManager",
        min_size: tuple[int, int] = (320, 240),
        crop: tuple[int, int, int, int] = (0, 0, 0, 0),  # left, top, right, bottom
        enumerate_windows: Callable[[], list[WindowInfo]] | None = None,
    ) -> None:
        self.include, self.exclude, self.min_size, self.crop = include, exclude, min_size, crop
        self._enumerate = enumerate_windows or self._enumerate_win32
        if enumerate_windows is None:
            _make_dpi_aware()

    def locate(self) -> Region | None:
        window = select_window(self._enumerate(), self.include, self.exclude, self.min_size)
        if window is None:
            return None
        left, top, right, bottom = self.crop
        return window.client.cropped(left, top, right, bottom)

    @staticmethod
    def _enumerate_win32() -> list[WindowInfo]:  # pragma: no cover - Windows only
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        found: list[WindowInfo] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def callback(hwnd: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            rect = wintypes.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(rect))
            origin = wintypes.POINT(0, 0)
            user32.ClientToScreen(hwnd, ctypes.byref(origin))
            found.append(
                WindowInfo(
                    buffer.value,
                    Region(origin.x, origin.y, rect.right - rect.left, rect.bottom - rect.top),
                )
            )
            return True

        user32.EnumWindows(callback, 0)
        return found


_dpi_done = False


def _make_dpi_aware() -> None:
    """Without this Windows reports scaled coordinates and the capture region is off."""
    global _dpi_done
    if _dpi_done or sys.platform != "win32":
        return
    _dpi_done = True
    try:  # pragma: no cover - Windows only
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
