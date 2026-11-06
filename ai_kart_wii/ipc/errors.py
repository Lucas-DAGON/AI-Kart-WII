"""Exceptions for the GameManager connection.

Codes mirror GameManager.Shared.Ipc.IpcErrorCodes.
"""

from __future__ import annotations


class GameManagerError(Exception):
    """Base class for every GameManager-related failure."""

    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str = "", code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class GameManagerUnavailable(GameManagerError):
    """Pipe missing / GameManager not running / connection dropped."""

    code = "PIPE_UNAVAILABLE"


class ResourceNotReady(GameManagerError):
    code = "RESOURCE_NOT_READY"


class ResourceUnavailable(GameManagerError):
    code = "RESOURCE_UNAVAILABLE"


class ReadFailed(GameManagerError):
    code = "READ_FAILED"


class InvalidResource(GameManagerError):
    code = "INVALID_RESOURCE"


class InvalidRequest(GameManagerError):
    code = "INVALID_REQUEST"


class InvalidGameState(GameManagerError):
    code = "INVALID_GAME_STATE"


_BY_CODE: dict[str, type[GameManagerError]] = {
    cls.code: cls
    for cls in (
        ResourceNotReady,
        ResourceUnavailable,
        ReadFailed,
        InvalidResource,
        InvalidRequest,
        InvalidGameState,
        GameManagerUnavailable,
    )
}


def error_from_code(code: str, message: str) -> GameManagerError:
    return _BY_CODE.get(code, GameManagerError)(message, code=code)


def error_from_message(message: str) -> GameManagerError:
    """Batched reads (GetResources) only carry the message text, not the code.

    TODO(GameManager): add `Code` to IpcResourceResult so this guessing can go away.
    """
    lowered = message.lower()
    if "is not ready" in lowered:
        return ResourceNotReady(message)
    if "not available for player" in lowered or "unavailable" in lowered:
        return ResourceUnavailable(message)
    if "was not found" in lowered:
        return InvalidResource(message)
    if "failed to read" in lowered:
        return ReadFailed(message)
    return GameManagerError(message)
