"""Reader for Dolphin movie files (.dtm): extracts the human's GameCube inputs.

Layout (verified on a real MTWP01 recording, see tests):
  * 256-byte header: magic "DTM\\x1a", game id, flags, VI frame count (u64 @0x0D),
    input count (u64 @0x15), ...
  * body: a stream of records in emulation order, mixed:
      - GameCube pad record, 8 bytes: byte0 buttons (Start,A,B,X,Y,Z,Up,Down = bits 0..7),
        byte1 (Left,Right,L,R,DiscChange,Reset,IsConnected(0x40),GetOrigin),
        then L, R, stickX, stickY, cX, cY (0..255, centre 128).
      - Wiimote record: 1 size byte + `size` bytes (sizes seen: 1, 13, 19, 25, 29, 30).
    The stream has no tags, so a record is classified by its look: it is a pad record when
    it is either a connected pad (IsConnected set, no DiscChange/Reset) or an exactly neutral
    unconnected port; anything else is a Wiimote record whose first byte is its size.
    The count of records must equal the header's input count and the stream must end exactly
    at the end of the file; `parse` raises if not, so a mis-parse is reported, not hidden.
  * Only records with IsConnected set are the real controller. In the sample the pad is
    polled exactly twice per VI frame (120 Hz).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from ai_kart_wii.control.actions import ControllerAction

HEADER_SIZE = 256
MAGIC = b"DTM\x1a"
MAX_WIIMOTE_SIZE = 64  # sizes seen so far: 1, 13, 19, 25, 29, 30
GC_RECORD = 8
STICK_CENTER = 128
STICK_RADIUS = 100.0  # a real GC stick reaches about +-100 around the centre

_BUTTONS_BYTE0 = ("START", "A", "B", "X", "Y", "Z", "DPAD_UP", "DPAD_DOWN")
_BUTTONS_BYTE1 = ("DPAD_LEFT", "DPAD_RIGHT", "L_DIGITAL", "R_DIGITAL")
FLAG_CONNECTED = 0x40


class DtmError(ValueError):
    pass


@dataclass(frozen=True)
class DtmHeader:
    game_id: str
    is_wii: bool
    controller_mask: int
    from_savestate: bool
    frame_count: int  # VI frames
    input_count: int  # records in the body (GC + Wiimote)
    lag_count: int
    rerecords: int
    video_backend: str
    pal60: bool


@dataclass(frozen=True, slots=True)
class GcPoll:
    buttons: frozenset[str]
    l: int
    r: int
    stick_x: int
    stick_y: int
    c_x: int
    c_y: int
    connected: bool

    def to_controller_action(self) -> ControllerAction:
        """Normalised GameCube action (sticks -1..1, triggers 0..1)."""
        def axis(v: int) -> float:
            return max(-1.0, min(1.0, (v - STICK_CENTER) / STICK_RADIUS))

        buttons = frozenset(b for b in self.buttons if not b.endswith("_DIGITAL"))
        return ControllerAction(
            stick_x=axis(self.stick_x), stick_y=axis(self.stick_y),
            c_x=axis(self.c_x), c_y=axis(self.c_y),
            l=self.l / 255.0, r=self.r / 255.0, buttons=buttons,
        )

    @staticmethod
    def from_bytes(raw: bytes) -> "GcPoll":
        b0, b1 = raw[0], raw[1]
        buttons = {name for i, name in enumerate(_BUTTONS_BYTE0) if b0 >> i & 1}
        buttons |= {name for i, name in enumerate(_BUTTONS_BYTE1) if b1 >> i & 1}
        return GcPoll(frozenset(buttons), raw[2], raw[3], raw[4], raw[5], raw[6], raw[7], bool(b1 & FLAG_CONNECTED))


class DtmMovie:
    def __init__(self, header: DtmHeader, polls: list[GcPoll], wiimote_records: int) -> None:
        self.header = header
        self.polls = polls  # connected pad polls only, in order
        self.wiimote_records = wiimote_records

    @property
    def polls_per_frame(self) -> float:
        return len(self.polls) / max(1, self.header.frame_count)

    @property
    def duration_s(self) -> float:
        return self.header.frame_count / 60.0

    def frame_polls(self, frame: int) -> list[GcPoll]:
        """Polls belonging to VI frame `frame` (uniform spread, 2 per frame in practice)."""
        n = len(self.polls)
        frames = self.header.frame_count
        start = round(frame * n / frames)
        end = round((frame + 1) * n / frames)
        return self.polls[start:max(end, start + 1)]

    def frame_input(self, frame: int) -> GcPoll:
        """The input the game most likely used for a frame: the last poll of that frame."""
        if not 0 <= frame < self.header.frame_count:
            raise IndexError(frame)
        return self.frame_polls(frame)[-1]

    def frames(self) -> Iterator[GcPoll]:
        for frame in range(self.header.frame_count):
            yield self.frame_input(frame)

    def summary(self) -> dict:
        counts: dict[str, int] = {}
        for poll in self.frames():
            for button in poll.buttons:
                counts[button] = counts.get(button, 0) + 1
        first_a = next((i for i, p in enumerate(self.frames()) if "A" in p.buttons), None)
        return {"game": self.header.game_id, "vi_frames": self.header.frame_count,
                "duration_s": round(self.duration_s, 2), "polls_per_frame": round(self.polls_per_frame, 3),
                "first_a_frame": first_a, "button_frames": counts}


def _is_pad_record(raw: bytes) -> bool:
    b0, b1 = raw[0], raw[1]
    if b1 & 0x30:  # DiscChange / Reset are never set in practice
        return False
    if b1 & FLAG_CONNECTED:
        return True
    # unconnected port: neutral buttons/triggers/sticks (GetOrigin bit may be set)
    return b0 == 0 and (b1 & 0x0F) == 0 and raw[2] == 0 and raw[3] == 0 and raw[4:8] == b"\x80\x80\x80\x80"


def parse_header(data: bytes) -> DtmHeader:
    if len(data) < HEADER_SIZE or data[:4] != MAGIC:
        raise DtmError("Not a Dolphin DTM file (bad magic)")
    frames, inputs, lag = struct.unpack_from("<QQQ", data, 0x0D)
    return DtmHeader(
        game_id=data[4:10].decode("ascii", "replace"),
        is_wii=bool(data[10]),
        controller_mask=data[11],
        from_savestate=bool(data[12]),
        frame_count=frames,
        input_count=inputs,
        lag_count=lag,
        rerecords=struct.unpack_from("<I", data, 0x2D)[0],
        video_backend=data[0x51:0x61].rstrip(b"\0").decode("ascii", "replace"),
        pal60=bool(data[0x8B]),
    )


def parse(data: bytes) -> DtmMovie:
    header = parse_header(data)
    body = memoryview(data)[HEADER_SIZE:]
    polls: list[GcPoll] = []
    position = 0
    records = 0
    wiimote = 0
    total = len(body)
    while position < total:
        raw = bytes(body[position:position + GC_RECORD])
        if len(raw) == GC_RECORD and _is_pad_record(raw):
            poll = GcPoll.from_bytes(raw)
            if poll.connected:
                polls.append(poll)
            position += GC_RECORD
        else:
            size_byte = body[position]
            if size_byte == 0 or size_byte > MAX_WIIMOTE_SIZE:
                raise DtmError(f"Unrecognised record at body offset {position} (first byte 0x{size_byte:02x})")
            position += 1 + size_byte
            wiimote += 1
        records += 1
    if position != total or records != header.input_count:
        raise DtmError(
            f"Record stream does not match the header (records={records}, expected {header.input_count}, "
            f"ended at {position}/{total}). A pad record may collide with a Wiimote size byte."
        )
    return DtmMovie(header, polls, wiimote)


def load(path: str | Path) -> DtmMovie:
    return parse(Path(path).read_bytes())
