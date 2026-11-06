"""Real GameManager backend: a thin synchronous wrapper around the C# client.

All protocol logic stays in GameManager.Shared (GameManagerClient); this file only
converts between Python and .NET types. Library updates therefore need no Python
changes unless the public C# API changes.

UNVERIFIED (no Windows/.NET available when written). Points most likely to need a
tweak on first run are marked `# PYTHONNET:`.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Sequence

from ai_kart_wii.ipc.backend import ResourceRequest, ResourceResult
from ai_kart_wii.ipc.dotnet_loader import SharedLibrary, load_shared_library
from ai_kart_wii.ipc.errors import (
    GameManagerError,
    GameManagerUnavailable,
    error_from_code,
)

log = logging.getLogger(__name__)


class PythonNetBackend:
    def __init__(self, dll_path: str | None = None, runtime_config: str | None = None) -> None:
        self._lib: SharedLibrary = load_shared_library(dll_path, runtime_config)
        self._client: Any = self._lib.GameManagerClient()
        self._connected = False

    # ------------------------------------------------------------------ connect
    def connect(self, timeout_s: float = 30.0) -> None:
        from System.Threading import CancellationTokenSource  # type: ignore[import-not-found]

        cts = CancellationTokenSource(int(timeout_s * 1000))
        try:
            self._client.ConnectAsync(cts.Token).GetAwaiter().GetResult()
        except Exception as exc:
            raise GameManagerUnavailable(
                f"Could not connect to the GameManager pipe within {timeout_s:.0f}s: {exc}"
            ) from exc
        finally:
            cts.Dispose()
        self._connected = True

    def register(self, name: str) -> None:
        try:
            self._client.RegisterAsync(name, self._no_token()).GetAwaiter().GetResult()
        except Exception as exc:
            raise self._translate(exc) from exc

    @property
    def connected(self) -> bool:
        return self._connected

    # --------------------------------------------------------------------- read
    def get(self, resource: str, player_id: int | None = None) -> Any:
        from System.Text.Json import JsonElement  # type: ignore[import-not-found]

        try:
            task = self._client.GetAsync[JsonElement](  # PYTHONNET: generic method call
                resource, self._nullable_int(player_id), self._no_token()
            )
            element = task.GetAwaiter().GetResult()
        except Exception as exc:
            raise self._translate(exc) from exc
        return self._json_to_python(element)

    def get_many(self, requests: Sequence[ResourceRequest]) -> list[ResourceResult]:
        from System.Collections.Generic import List  # type: ignore[import-not-found]

        request_type = self._lib.IpcResourceRequest
        net_requests = List[request_type]()
        for request in requests:
            item = request_type()
            item.Resource = request.resource
            item.PlayerId = self._nullable_int(request.player_id)
            net_requests.Add(item)

        try:
            net_results = self._client.GetManyAsync(net_requests, self._no_token()).GetAwaiter().GetResult()
        except Exception as exc:
            raise self._translate(exc) from exc

        results: list[ResourceResult] = []
        for item in net_results:
            if item.Success:
                results.append(ResourceResult(True, self._json_to_python(item.Value)))
            else:
                results.append(ResourceResult(False, None, str(item.Error)))
        return results

    # -------------------------------------------------------------------- misc
    def reload_dynamic_cache(self) -> None:
        self._client.ReloadDynamicCacheAsync(self._no_token()).GetAwaiter().GetResult()

    def close(self) -> None:
        if not self._connected:
            return
        try:
            self._client.DisposeAsync().AsTask().GetAwaiter().GetResult()
        except Exception as exc:  # pragma: no cover
            log.debug("Dispose failed: %s", exc)
        self._connected = False

    # ----------------------------------------------------------------- helpers
    @staticmethod
    def _no_token() -> Any:
        from System.Threading import CancellationToken  # type: ignore[import-not-found]

        return CancellationToken()  # default struct == CancellationToken.None

    @staticmethod
    def _nullable_int(value: int | None) -> Any:
        if value is None:
            return None
        # PYTHONNET: if passing a plain int to `int?` is rejected, use Nullable[Int32](value).
        return int(value)

    @staticmethod
    def _json_to_python(value: Any) -> Any:
        """The server sends System.Text.Json elements; turn them into Python values."""
        if value is None:
            return None
        get_raw = getattr(value, "GetRawText", None)  # PYTHONNET: boxed JsonElement
        if get_raw is not None:
            return json.loads(str(get_raw()))
        return value

    def _translate(self, exc: Exception) -> GameManagerError:
        code = getattr(exc, "Code", None)  # GameManagerIpcException.Code
        message = str(getattr(exc, "Message", None) or exc)
        if code:
            return error_from_code(str(code), message)
        name = type(exc).__name__
        if name in ("IOException", "ObjectDisposedException", "InvalidOperationException"):
            self._connected = False
            return GameManagerUnavailable(message)
        return GameManagerError(message)
