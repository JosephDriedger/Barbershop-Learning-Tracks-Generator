"""Tiny standard MIDI files made of tempo events, for the tests of the playback tempo."""

import struct


def variable(value: int) -> bytes:
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(out))


def tempo_event(delta: int, bpm: float) -> bytes:
    microseconds = round(60_000_000 / bpm)
    return variable(delta) + b"\xff\x51\x03" + microseconds.to_bytes(3, "big")


def track(*events: bytes) -> bytes:
    body = b"".join(events) + b"\x00\xff\x2f\x00"
    return b"MTrk" + struct.pack(">I", len(body)) + body


def midi(*tracks: bytes, division: int = 480) -> bytes:
    return b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), division) + b"".join(tracks)


def ritardando_from(bpm: float) -> bytes:
    """``bpm`` for a beat and a half, then slower in two steps, then back to ``bpm``."""
    steps = [tempo_event(0, bpm), tempo_event(720, bpm * 0.9), tempo_event(240, bpm * 0.75)]
    return midi(track(*steps, tempo_event(960, bpm)))
