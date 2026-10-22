"""The tempo changes of a MIDI file: what a notation program plays, read from its own export.

MuseScore writes a ritardando, a fermata and "a tempo" into its MusicXML as plain text, with no
tempo attached, but it plays them: its MIDI export carries them as tempo events (a ritardando as a
staircase of small steps, a fermata as a slower stretch, "a tempo" as the return). Reading that
export gives the tempo the person hears in MuseScore, with nothing guessed about how much a "rit."
slows down. Only the tempo events are read here; the notes of the MIDI file are never used.
"""

import struct
from fractions import Fraction

from barbershop_tracks.models import TempoChange

# bpm is rounded to a multiple of 1/1024: a MIDI tempo is a whole number of microseconds per quarter
# note, so it is never quite the value that was meant (63 is 62.9999995), and a multiple of 1/1024
# is exact as a double, so the project file can state it without a quantisation error
_STEP = 1024
_TEMPO = 0x51


class MidiTempoError(ValueError):
    """The file is not a MIDI file BLT can read the tempo of."""


def _variable(data: bytes, at: int) -> tuple[int, int]:
    value = 0
    while True:
        if at >= len(data):
            raise MidiTempoError("the MIDI file ends in the middle of an event")
        byte = data[at]
        at += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, at


def _track_tempos(body: bytes) -> list[tuple[int, int]]:
    """(tick, microseconds per quarter) of every tempo event of one track."""
    found: list[tuple[int, int]] = []
    at = tick = 0
    status = 0
    while at < len(body):
        delta, at = _variable(body, at)
        tick += delta
        if at >= len(body):
            break
        lead = body[at]
        if lead == 0xFF:  # a meta event
            kind = body[at + 1]
            length, after = _variable(body, at + 2)
            payload = body[after : after + length]
            if kind == _TEMPO and length == 3:
                found.append((tick, int.from_bytes(payload, "big")))
            at = after + length
        elif lead in (0xF0, 0xF7):  # system exclusive
            length, after = _variable(body, at + 1)
            at = after + length
        else:
            if lead & 0x80:
                status = lead
                at += 1
            if not status:
                raise MidiTempoError("the MIDI file has data before its first event")
            at += 1 if status & 0xF0 in (0xC0, 0xD0) else 2
    return found


def read_tempo_changes(data: bytes) -> tuple[TempoChange, ...]:
    """The tempo changes of a MIDI file, in order, equal ones merged, positions in quarters."""
    if len(data) < 14 or data[:4] != b"MThd":
        raise MidiTempoError("not a MIDI file")
    _format, tracks, division = struct.unpack(">HHH", data[8:14])
    if division & 0x8000 or division == 0:
        raise MidiTempoError("the MIDI file counts time in frames, not in quarter notes")
    events: dict[int, int] = {}
    at = 14
    for _ in range(tracks):
        if data[at : at + 4] != b"MTrk":
            raise MidiTempoError("the MIDI file has a damaged track")
        (length,) = struct.unpack(">I", data[at + 4 : at + 8])
        body = data[at + 8 : at + 8 + length]
        at += 8 + length
        for tick, microseconds in _track_tempos(body):
            if microseconds > 0:
                events[tick] = microseconds  # a later event at the same tick replaces an earlier
    changes: list[TempoChange] = []
    for tick in sorted(events):
        bpm = Fraction(round(Fraction(60_000_000, events[tick]) * _STEP), _STEP)
        if changes and changes[-1].bpm == bpm:
            continue  # the same tempo goes on
        changes.append(TempoChange(position=Fraction(tick, division), bpm=bpm))
    return tuple(changes)
