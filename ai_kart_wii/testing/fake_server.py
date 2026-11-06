"""Windows-only: serves FakeProtocolHandler on \\\\.\\pipe\\GameManager.

Lets the *real* C# GameManagerClient (through pythonnet) be tested without Dolphin:

    python -m ai_kart_wii fake-server      # terminal 1 (needs pywin32)
    python -m ai_kart_wii check            # terminal 2 (uses the real client)

UNVERIFIED (written without Windows). The pure protocol logic it relies on is
covered by tests/test_fake_protocol.py.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from ai_kart_wii.testing.fake_backend import FakeBackend
from ai_kart_wii.testing.fake_protocol import FakeProtocolHandler
from ai_kart_wii.testing.fake_race import FakeRace

log = logging.getLogger(__name__)

PIPE_NAME = r"\\.\pipe\GameManager"


class FakePipeServer:
    def __init__(self, race: FakeRace | None = None) -> None:
        self.race = race or FakeRace()
        self.registry: set[str] = set()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._serve, name="fake-gm-pipe", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def serve_forever(self) -> None:
        self._serve()

    def _serve(self) -> None:  # pragma: no cover - Windows only
        import win32file  # type: ignore[import-not-found]
        import win32pipe  # type: ignore[import-not-found]

        while not self._stop.is_set():
            handle = win32pipe.CreateNamedPipe(
                PIPE_NAME,
                win32pipe.PIPE_ACCESS_DUPLEX,
                win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT,
                win32pipe.PIPE_UNLIMITED_INSTANCES,
                65536, 65536, 0, None,
            )
            log.info("Fake GameManager waiting for a client on %s", PIPE_NAME)
            win32pipe.ConnectNamedPipe(handle, None)
            threading.Thread(target=self._client, args=(handle,), daemon=True).start()

    def _client(self, handle: Any) -> None:  # pragma: no cover - Windows only
        import win32file  # type: ignore[import-not-found]

        handler = FakeProtocolHandler(FakeBackend(self.race), self.registry)
        buffer = b""
        try:
            while not self._stop.is_set():
                _, chunk = win32file.ReadFile(handle, 65536)
                buffer += bytes(chunk)
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    reply = handler.handle_line(line.decode("utf-8"))
                    if reply is not None:
                        win32file.WriteFile(handle, (reply + "\n").encode("utf-8"))
        except Exception as exc:
            log.info("Fake client disconnected: %s", exc)
        finally:
            if handler.name:
                self.registry.discard(handler.name.lower())
            win32file.CloseHandle(handle)
