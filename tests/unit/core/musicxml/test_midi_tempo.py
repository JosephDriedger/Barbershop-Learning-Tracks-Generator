"""The tempo changes of a MIDI file: what MuseScore plays, read from its export."""

import struct
from fractions import Fraction

import pytest

from barbershop_tracks.core.musicxml.midi_tempo import MidiTempoError, read_tempo_changes
from smf_builders import midi, tempo_event, track


def test_a_constant_tempo_is_exact_even_though_midi_rounds_it() -> None:
    (only,) = read_tempo_changes(midi(track(tempo_event(0, 63))))
    assert (only.position, only.bpm) == (
        Fraction(0),
        Fraction(63),
    )  # 60 000 000 / 952 381 is 62.9999995


def test_a_ritardando_staircase_and_the_return_are_read_in_order() -> None:
    steps = [(0, 63.0), (720, 61.03125), (120, 59.0625), (1920, 31.5), (480, 63.0)]
    changes = read_tempo_changes(midi(track(*(tempo_event(d, b) for d, b in steps))))
    assert [(c.position, float(c.bpm)) for c in changes] == [
        (Fraction(0), 63.0),
        (Fraction(3, 2), 61.03125),
        (Fraction(7, 4), 59.0625),
        (Fraction(23, 4), 31.5),
        (Fraction(27, 4), 63.0),
    ]


def test_every_value_is_exact_as_a_double_so_the_project_file_needs_no_rounding() -> None:
    changes = read_tempo_changes(midi(track(tempo_event(0, 63), tempo_event(120, 61.03125))))
    assert all(Fraction(float(c.bpm)) == c.bpm for c in changes)


def test_a_position_is_in_quarter_notes_whatever_the_division() -> None:
    change = read_tempo_changes(
        midi(track(tempo_event(0, 90), tempo_event(2879, 60)), division=480)
    )
    assert change[1].position == Fraction(2879, 480)
    other = read_tempo_changes(midi(track(tempo_event(0, 90), tempo_event(960, 60)), division=960))
    assert other[1].position == 1


def test_the_same_tempo_going_on_is_one_change() -> None:
    changes = read_tempo_changes(midi(track(tempo_event(0, 63), tempo_event(720, 63))))
    assert len(changes) == 1


def test_a_later_event_at_the_same_moment_replaces_an_earlier_one() -> None:
    changes = read_tempo_changes(midi(track(tempo_event(0, 120), tempo_event(0, 63))))
    assert [float(c.bpm) for c in changes] == [63.0]


def test_tempo_events_of_every_track_count_and_notes_are_ignored() -> None:
    note_on = bytes([0x00, 0x90, 60, 64]) + bytes([0x10, 62, 64])  # the second uses running status
    note_off = bytes([0x10, 0x80, 60, 0])
    conductor = track(tempo_event(0, 63))
    voices = track(note_on, note_off, tempo_event(448, 60))  # the notes took 32 ticks: tick 480
    changes = read_tempo_changes(midi(conductor, voices))
    assert [(c.position, float(c.bpm)) for c in changes] == [
        (Fraction(0), 63.0),
        (Fraction(1), 60.0),
    ]


def test_a_file_without_tempo_events_has_none() -> None:
    assert read_tempo_changes(midi(track())) == ()


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not a midi file at all",
        b"MThd" + struct.pack(">IHHH", 6, 1, 1, 0x8000 | 25),  # SMPTE frames, not quarters
        b"MThd" + struct.pack(">IHHH", 6, 1, 1, 480) + b"XXXX\x00\x00\x00\x00",
    ],
)
def test_what_is_not_a_midi_file_with_quarter_note_time_is_refused(data: bytes) -> None:
    with pytest.raises(MidiTempoError):
        read_tempo_changes(data)
