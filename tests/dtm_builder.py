"""Builds small synthetic DTM files with the same layout as real Dolphin recordings."""

import struct


def gc(buttons0=0, buttons1=0, l=0, r=0, sx=128, sy=128, connected=True):
    b1 = buttons1 | (0x40 if connected else 0)
    return bytes([buttons0, b1, l, r, sx, sy, 128, 128])


def wiimote(size=19):
    return bytes([size]) + bytes(range(1, size + 1))


def build_dtm(frames, polls_per_frame=2, pad_fn=None, game_id=b"MTWP01", tiny_wiimote_every=0):
    """pad_fn(frame, poll) -> 8-byte connected GC record. Adds 2 unconnected ports + wiimote noise."""
    body = bytearray()
    records = 0
    for f in range(frames):
        for p in range(polls_per_frame):
            body += (pad_fn(f, p) if pad_fn else gc())
            body += gc(connected=False) * 2
            body += wiimote(19) + wiimote(25) + wiimote(19)
            records += 3 + 3
            if tiny_wiimote_every and (f * polls_per_frame + p) % tiny_wiimote_every == 0:
                body += bytes([1, 0]) * 2  # size-1 Wiimote records seen in the Bowser's Castle recording
                records += 2
    header = bytearray(256)
    header[0:4] = b"DTM\x1a"
    header[4:10] = game_id
    header[10] = 1
    header[11] = 0xD7
    struct.pack_into("<QQQ", header, 0x0D, frames, records, 0)
    header[0x51:0x57] = b"Vulkan"
    header[0x8B] = 1
    return bytes(header) + bytes(body)
