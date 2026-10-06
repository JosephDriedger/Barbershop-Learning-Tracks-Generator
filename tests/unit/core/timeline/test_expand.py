"""Expanding a Song into performance order: exact positions, provenance, immutability."""

import copy
from fractions import Fraction

import pytest

from barbershop_tracks.core.timeline import perform_song
from barbershop_tracks.models import (
    MeasureSpan,
    Note,
    Part,
    Pitch,
    RepeatKind,
    RepeatMark,
    Song,
    Step,
    TransitionKind,
)

STEPS = [Step.C, Step.D, Step.E, Step.F, Step.G]


def make_song(
    count: int,
    marks: list[RepeatMark],
    *,
    lengths: list[int] | None = None,
    parts: int = 1,
) -> Song:
    """One quarter note per beat of every measure; the pitch step names the measure."""
    lengths = lengths or [4] * count
    spans, start = [], 0
    for index, length in enumerate(lengths):
        spans.append(
            MeasureSpan(
                index=index, number=index + 1, start=Fraction(start), length=Fraction(length)
            )
        )
        start += length
    built = []
    for p in range(parts):
        events = [
            Note(
                start=span.start + beat,
                duration=Fraction(1),
                measure=span.number,
                beat=Fraction(1 + beat),
                written_pitch=Pitch(STEPS[span.index % 5], 4),
            )
            for span in spans
            for beat in range(int(span.length))
        ]
        built.append(Part(part_id=f"P{p + 1}/s1/v1", name=f"P{p + 1}", events=tuple(events)))
    return Song(title="t", parts=tuple(built), measures=tuple(spans), repeat_marks=tuple(marks))


F0 = RepeatMark(kind=RepeatKind.FORWARD, measure_index=0)


def back(index: int, times: int | None = None) -> RepeatMark:
    return RepeatMark(kind=RepeatKind.BACKWARD, measure_index=index, times=times)


def test_a_song_without_repeats_is_performed_as_written_with_the_same_notes() -> None:
    song = make_song(3, [])
    performed = perform_song(song)
    line = performed.lines[0]
    assert performed.plan.is_identity
    assert all(a is b for a, b in zip(line.part.events, song.parts[0].events, strict=True))
    assert [o.visit for o in line.occurrences] == [1] * 12
    assert [o.measure_index for o in line.occurrences][:5] == [0, 0, 0, 0, 1]
    assert not performed.issues


def test_repeated_notes_are_shifted_to_exact_global_positions() -> None:
    performed = perform_song(make_song(3, [F0, back(1)]))
    starts = [e.start for e in performed.lines[0].part.events]
    assert starts == [Fraction(i) for i in range(20)]  # 2 measures twice, then one: 5 * 4 beats
    assert [e.written_pitch.step for e in performed.lines[0].part.events if e.written_pitch][
        ::4
    ] == [Step.C, Step.D, Step.C, Step.D, Step.E]


def test_source_measure_and_beat_are_not_rewritten() -> None:
    performed = perform_song(make_song(2, [F0, back(1)]))
    events = performed.lines[0].part.events
    assert [e.measure for e in events] == [1] * 4 + [2] * 4 + [1] * 4 + [2] * 4
    assert [e.beat for e in events][:4] == [1, 2, 3, 4]
    assert [e.beat for e in events][8:12] == [1, 2, 3, 4]


def test_each_expanded_note_records_its_provenance() -> None:
    performed = perform_song(make_song(2, [F0, back(1, 3)]))
    line = performed.lines[0]
    third_visit = [o for o in line.occurrences if o.visit == 3]
    assert len(third_visit) == 8
    first = third_visit[0]
    assert first.part_id == "P1/s1/v1"
    assert first.measure_index == 0
    assert first.source_event_index == 0  # the first source note, played a third time
    assert first.performed_start == 16
    note = line.part.events[line.occurrences.index(first)]
    assert line.occurrence_of(note) is first


def test_occurrence_lookup_rejects_foreign_notes() -> None:
    song = make_song(2, [F0, back(1)])
    line = perform_song(song).lines[0]
    with pytest.raises(KeyError):
        line.occurrence_of(copy.deepcopy(song.parts[0].events[5]))  # equal, but not this object


def test_one_source_note_gives_several_occurrences_and_none_is_mutated() -> None:
    song = make_song(2, [F0, back(1, 3)])
    before = copy.deepcopy(song)
    performed = perform_song(song)
    assert song == before
    assert performed.song is song
    source = song.parts[0].events[0]
    copies = [e for e in performed.lines[0].part.events if e.written_pitch == source.written_pitch]
    assert len([e for e in copies if e.beat == 1 and e.measure == 1]) == 3
    assert source.start == 0  # the source note keeps its own position


def test_all_parts_follow_the_same_plan() -> None:
    performed = perform_song(make_song(3, [F0, back(1)], parts=2))
    a, b = performed.lines
    assert [e.start for e in a.part.events] == [e.start for e in b.part.events]
    assert [o.visit for o in a.occurrences] == [o.visit for o in b.occurrences]


def test_a_pickup_and_a_short_final_measure_shift_by_exact_fractions() -> None:
    song = make_song(3, [back(2)], lengths=[1, 4, 3])
    performed = perform_song(song)
    events = performed.lines[0].part.events
    assert [e.start for e in events] == [Fraction(i) for i in range(16)]
    assert performed.plan.end == 16
    jump = performed.plan.played[3]
    assert jump.source_index == 0
    assert jump.performed_start == 8
    assert jump.arrival is TransitionKind.REPEAT_JUMP
    assert events[8].measure == 1  # the pickup note, written in measure 1 of this table
    assert performed.lines[0].occurrences[8].measure_index == 0


def test_notes_outside_every_measure_are_reported_not_dropped_silently() -> None:
    song = make_song(2, [F0, back(1)])
    stray = Note(
        start=Fraction(99),
        duration=Fraction(1),
        measure=30,
        beat=Fraction(1),
        written_pitch=Pitch(Step.C, 4),
    )
    part = song.parts[0].with_events((*song.parts[0].events, stray))
    song = Song(title="t", parts=(part,), measures=song.measures, repeat_marks=song.repeat_marks)
    performed = perform_song(song)
    assert [i.code for i in performed.issues] == ["NOTE_OUTSIDE_MEASURES"]
    assert performed.issues.has_errors


def test_a_song_with_no_measure_table_is_the_identity() -> None:
    note = Note(
        start=Fraction(0), duration=Fraction(1), measure=1, beat=Fraction(1), written_pitch=None
    )
    song = Song(title="t", parts=(Part(part_id="p", name="p", events=(note,)),))
    performed = perform_song(song)
    assert performed.lines[0].occurrences[0].measure_index is None
    assert performed.lines[0].part.events[0] is note


def test_an_invalid_structure_leaves_the_written_order() -> None:
    nested = [F0, RepeatMark(kind=RepeatKind.FORWARD, measure_index=1), back(2), back(3)]
    performed = perform_song(make_song(5, nested))
    assert performed.issues.has_errors
    assert performed.plan.is_identity
    assert [e.start for e in performed.lines[0].part.events] == [Fraction(i) for i in range(20)]
