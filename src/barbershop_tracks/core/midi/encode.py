"""``MidiPlan`` -> Standard MIDI File bytes (format 1). Written by hand, not by a library.

The bytes are fully ours: no running status, no library defaults, no inserted events. Reading them
back (``verify.py``) goes through ``mido``, a deliberately independent path.
"""

import struct

from barbershop_tracks.core.midi.errors import MidiExportError
from barbershop_tracks.core.midi.model import EventKind, MidiEvent, MidiPlan

_MAX_DELTA = 0x0FFFFFFF  # the largest variable-length quantity (four bytes)


def vlq(value: int) -> bytes:
    if not 0 <= value <= _MAX_DELTA:
        raise MidiExportError("MIDI_DELTA_OUT_OF_RANGE", f"delta time {value} cannot be encoded")
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(out))


def _meta(kind: int, payload: bytes) -> bytes:
    return bytes([0xFF, kind]) + vlq(len(payload)) + payload


def _event_bytes(event: MidiEvent) -> bytes:
    kind = event.kind
    if kind is EventKind.TRACK_NAME:
        return _meta(0x03, event.text.encode("ascii"))
    if kind is EventKind.TEMPO:
        return _meta(0x51, event.data[0].to_bytes(3, "big"))
    if kind is EventKind.TIME_SIGNATURE:
        return _meta(0x58, bytes(event.data))
    if kind is EventKind.END_OF_TRACK:
        return _meta(0x2F, b"")
    if event.channel is None:
        raise MidiExportError("MIDI_EVENT_INVALID", "a note event needs a channel")
    status = (0x90 if kind is EventKind.NOTE_ON else 0x80) | event.channel
    return bytes([status, event.data[0], event.data[1]])


def encode_midi(plan: MidiPlan) -> bytes:
    chunks = [b"MThd" + struct.pack(">IHHH", 6, 1, len(plan.tracks), plan.ppq)]
    for track in plan.tracks:
        keys = [event.sort_key for event in track.events]
        if keys != sorted(keys):
            raise MidiExportError("MIDI_EVENT_ORDER", f"track {track.name} is not in event order")
        if not track.events or track.events[-1].kind is not EventKind.END_OF_TRACK:
            raise MidiExportError("MIDI_EVENT_ORDER", f"track {track.name} lacks an end of track")
        body = bytearray()
        last = 0
        for event in track.events:
            body += vlq(event.tick - last) + _event_bytes(event)
            last = event.tick
        chunks.append(b"MTrk" + struct.pack(">I", len(body)) + bytes(body))
    return b"".join(chunks)
