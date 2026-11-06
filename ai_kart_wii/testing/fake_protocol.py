"""Speaks GameManager's real wire format (newline-delimited JSON) on top of FakeBackend.

JSON shapes were derived from GameManager.Shared / GameManagerIpcServer:
  request : {"RequestId","Operation","Resource","PlayerId","Value","MessageType":"Request"}
  response: {"RequestId","Success","Value","MessageType":"Response","Error":{"Code","Message"}|null}
Enums are strings; property names are PascalCase (System.Text.Json defaults).
"""

from __future__ import annotations

import json
from typing import Any

from ai_kart_wii.ipc.errors import GameManagerError
from ai_kart_wii.testing.fake_backend import FakeBackend
from ai_kart_wii.ipc.backend import ResourceRequest


class FakeProtocolHandler:
    """One instance per connected client."""

    registered_names: set[str] = set()

    def __init__(self, backend: FakeBackend, registry: set[str] | None = None) -> None:
        self.backend = backend
        self.backend.connect()
        self.registry = registry if registry is not None else set()
        self.name: str | None = None

    def handle_line(self, line: str) -> str | None:
        line = line.strip()
        if not line:
            return None
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            return self._error(0, "INVALID_REQUEST", "Invalid JSON request.")
        message_type = message.get("MessageType")
        if message_type == "Response":
            return None  # reply to a GetStatus child request; nothing to do
        if message_type != "Request":
            return None

        request_id = int(message.get("RequestId", 0))
        operation = message.get("Operation")
        try:
            if operation == "Ping":
                return self._ok(request_id, "PONG")
            if operation == "Register":
                return self._register(request_id, message.get("Value"))
            if operation == "GetResource":
                resource = message.get("Resource")
                if resource is None:
                    return self._error(request_id, "INVALID_RESOURCE", "No resource was specified.")
                return self._ok(request_id, self.backend.get(resource, message.get("PlayerId")))
            if operation == "GetResources":
                items = message.get("Value") or []
                requests = [ResourceRequest(i["Resource"], i.get("PlayerId")) for i in items]
                results = self.backend.get_many(requests)
                return self._ok(
                    request_id,
                    [{"Success": r.success, "Value": r.value, "Error": r.error} for r in results],
                )
            if operation == "SetResource":
                if message.get("Value") is None:
                    return self._error(request_id, "INVALID_VALUE", "No value was provided.")
                return self._ok(request_id, None)
            if operation == "ReloadDynamicCache":
                return self._ok(request_id, "Dynamic cache reloaded successfully.")
            return self._error(request_id, "UNKNOWN_OPERATION", f"Unknown operation '{operation}'.")
        except GameManagerError as exc:
            return self._error(request_id, exc.code, str(exc))

    # ------------------------------------------------------------------ helpers
    def _register(self, request_id: int, name: Any) -> str:
        if not name or not str(name).strip():
            return self._error(request_id, "INVALID_VALUE", "A valid child name is required.")
        lowered = str(name).lower()
        if lowered in self.registry:
            return self._error(request_id, "INVALID_REQUEST", "A child with that reference already exists.")
        self.registry.add(lowered)
        self.name = str(name)
        return self._ok(request_id, str(name))

    @staticmethod
    def _ok(request_id: int, value: Any) -> str:
        return json.dumps(
            {"RequestId": request_id, "Success": True, "Value": value, "MessageType": "Response", "Error": None}
        )

    @staticmethod
    def _error(request_id: int, code: str, message: str) -> str:
        return json.dumps(
            {
                "RequestId": request_id,
                "Success": False,
                "Value": None,
                "MessageType": "Response",
                "Error": {"Code": code, "Message": message},
            }
        )
