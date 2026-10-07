"""Builders for the MIDI export tests: hand-built songs, performed in memory (no XML, no files)."""

import io
from collections.abc import Mapping, Sequence
from dataclasses import replace
from fractions import Fraction

import mido

from barbershop_tracks.core.midi import MidiExport, export_midi
from barbershop_tracks.core.timeline import perform_song
from barbershop_tracks.models import (
    Note,
    PerformedSong,
    RepeatKind,
    RepeatMark,
    TempoChange,
    TimeSignature,
)
from readiness_builders import (
    note,
    quartet_assignments,
    quartet_lines,
    song_of,
    tempo_at,
)

__all__ = ["decode", "exported", "performed_of", "quartet_assignments", "tempo_at"]


def performed_of(
    lines: Mapping[str, Sequence[Note]] | None = None,
    *,
    tempos: Sequence[TempoChange] | None = None,
    signatures: Sequence[TimeSignature] = (),
    measures: int = 4,
    backward_repeat_at: int | None = None,
) -> PerformedSong:
    song = song_of(
        lines if lines is not None else quartet_lines(), measures=measures, tempos=tempos
    )
    marks: tuple[RepeatMark, ...] = ()
    if backward_repeat_at is not None:
        marks = (RepeatMark(kind=RepeatKind.BACKWARD, measure_index=backward_repeat_at),)
    song = replace(song, time_signatures=tuple(signatures), repeat_marks=marks)
    return perform_song(song)


def exported(
    performed: PerformedSong | None = None, *, ppq: int = 480, **assign: str
) -> MidiExport:
    return export_midi(
        performed if performed is not None else performed_of(),
        quartet_assignments(**assign),
        ppq=ppq,
    )


def decode(data: bytes) -> mido.MidiFile:
    """An independent read of the bytes (mido), for assertions made directly in the tests."""
    return mido.MidiFile(file=io.BytesIO(data))


def whole_notes(pitch: object, count: int = 4) -> list[Note]:
    return [note(4 * i, 4, pitch) for i in range(count)]  # type: ignore[arg-type]


def fraction(value: str) -> Fraction:
    return Fraction(value)
