"""The Python-facing interface to GameManager.

Two implementations exist:
  * PythonNetBackend (ipc/pythonnet_client.py)  - the real thing, wraps the C# client.
  * FakeBackend      (testing/fake_backend.py)  - in-memory, for tests and demos.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NamedTuple, Protocol, Sequence, runtime_checkable


class ResourceRequest(NamedTuple):
    resource: str
    player_id: int | None = None


@dataclass(frozen=True, slots=True)
class ResourceResult:
    success: bool
    value: Any = None
    error: str | None = None


@runtime_checkable
class GameManagerBackend(Protocol):
    def connect(self, timeout_s: float = 30.0) -> None:
        """Connect to the pipe. Raises GameManagerUnavailable on failure."""

    def register(self, name: str) -> None: ...

    def get(self, resource: str, player_id: int | None = None) -> Any:
        """Read one resource. Raises a GameManagerError subclass on failure."""

    def get_many(self, requests: Sequence[ResourceRequest]) -> list[ResourceResult]:
        """One IPC round trip. Items fail individually (success=False)."""

    def close(self) -> None: ...

    @property
    def connected(self) -> bool: ...
