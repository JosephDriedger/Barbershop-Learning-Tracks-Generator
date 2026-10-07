"""The song: metadata, parts, and tempo/meter maps. No parsing or validation here."""

from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise
from pathlib import Path

from barbershop_tracks.models.notation import ClefChange
from barbershop_tracks.models.part import Part
from barbershop_tracks.models.structure import EndingSpan, MeasureSpan, RepeatMark
from barbershop_tracks.models.timing import TempoChange, TimeSignature
from barbershop_tracks.models.voice import VoiceRole


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceMetadata:
    """Where a song came from. All fields are optional."""

    path: Path | None = None
    format_name: str | None = None  # e.g. "MusicXML"
    format_version: str | None = None
    software: str | None = None  # the exporting application, if recorded


@dataclass(frozen=True, slots=True, kw_only=True)
class Song:
    """A complete score as plain data.

    Structural invariants only: part ids are unique, and the tempo and time-signature
    maps are in strictly increasing position order. Musical correctness (four voices,
    monophony, lyrics, ...) is the validator's job, not the model's.
    """

    title: str
    composer: str | None = None
    arranger: str | None = None
    parts: tuple[Part, ...] = ()
    tempo_map: tuple[TempoChange, ...] = ()
    time_signatures: tuple[TimeSignature, ...] = ()
    source: SourceMetadata = SourceMetadata()
    clef_changes: tuple[ClefChange, ...] = ()
    measures: tuple[MeasureSpan, ...] = ()
    repeat_marks: tuple[RepeatMark, ...] = ()
    ending_spans: tuple[EndingSpan, ...] = ()

    def __post_init__(self) -> None:
        parts = tuple(self.parts)
        object.__setattr__(self, "clef_changes", tuple(self.clef_changes))
        measures = tuple(self.measures)
        repeat_marks = tuple(self.repeat_marks)
        ending_spans = tuple(self.ending_spans)
        tempo_map = tuple(self.tempo_map)
        time_signatures = tuple(self.time_signatures)
        part_ids = [part.part_id for part in parts]
        if len(set(part_ids)) != len(part_ids):
            raise ValueError("part ids must be unique")
        _require_strictly_increasing([t.position for t in tempo_map], "tempo_map")
        _require_strictly_increasing([s.position for s in time_signatures], "time_signatures")
        _check_structure(measures, repeat_marks, ending_spans)
        object.__setattr__(self, "measures", measures)
        object.__setattr__(self, "repeat_marks", repeat_marks)
        object.__setattr__(self, "ending_spans", ending_spans)
        object.__setattr__(self, "parts", parts)
        object.__setattr__(self, "tempo_map", tempo_map)
        object.__setattr__(self, "time_signatures", time_signatures)

    def part_by_id(self, part_id: str) -> Part | None:
        return next((part for part in self.parts if part.part_id == part_id), None)

    def parts_for_role(self, role: VoiceRole) -> tuple[Part, ...]:
        """All parts explicitly assigned ``role`` (more than one is a validation matter)."""
        return tuple(part for part in self.parts if part.role is role)

    @property
    def duration(self) -> Fraction:
        """End of the longest part in quarter notes (0 if there are no parts)."""
        return max((part.end for part in self.parts), default=Fraction(0))


def _require_strictly_increasing(positions: list[Fraction], name: str) -> None:
    if any(later <= earlier for earlier, later in pairwise(positions)):
        raise ValueError(f"{name} positions must be strictly increasing")


def _check_structure(
    measures: tuple[MeasureSpan, ...],
    marks: tuple[RepeatMark, ...],
    spans: tuple[EndingSpan, ...],
) -> None:
    for position, span in enumerate(measures):
        if not isinstance(span, MeasureSpan):
            raise TypeError("measures must contain only MeasureSpan objects")
        if span.index != position:
            raise ValueError("measure indices must be 0, 1, 2, ... in order")
        if position and span.start != measures[position - 1].end:
            raise ValueError("measures must be contiguous")
    for mark in marks:
        if not isinstance(mark, RepeatMark):
            raise TypeError("repeat_marks must contain only RepeatMark objects")
        if mark.measure_index >= len(measures):
            raise ValueError("a repeat mark refers to a measure that does not exist")
    previous_end = -1
    for ending in sorted(spans, key=lambda s: s.start_index):
        if not isinstance(ending, EndingSpan):
            raise TypeError("ending_spans must contain only EndingSpan objects")
        if ending.end_index >= len(measures):
            raise ValueError("an ending refers to a measure that does not exist")
        if ending.start_index <= previous_end:
            raise ValueError("ending spans must not overlap")
        previous_end = ending.end_index
