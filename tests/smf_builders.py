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


def track(*events: bytes, length: int = 0) -> bytes:
    """A track of ``events``; ``length`` ticks pass after the last one before the track ends."""
    body = b"".join(events) + variable(length) + b"\xff\x2f\x00"
    return b"MTrk" + struct.pack(">I", len(body)) + body


def midi(*tracks: bytes, division: int = 480) -> bytes:
    return b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), division) + b"".join(tracks)


def ritardando_from(bpm: float, quarters: int = 4) -> bytes:
    """``bpm`` for a beat and a half, then slower in two steps, then back to ``bpm``.

    The file plays ``quarters`` quarter notes in all (the length of the score it goes with).
    """
    steps = [tempo_event(0, bpm), tempo_event(720, bpm * 0.9), tempo_event(240, bpm * 0.75)]
    return midi(track(*steps, tempo_event(960, bpm), length=(quarters - 4) * 480))
