"""Expanding a ``Song`` into performance order: ``perform_song``.

The source ``Song`` and its ``Note`` objects are never modified. For a score with nothing to
repeat the performed lines contain the *same* ``Note`` objects. Otherwise each performed
occurrence of a note is a shifted copy (``dataclasses.replace`` with a new ``start`` only; pitch,
lyrics, ties, ``measure`` and ``beat`` are untouched) and its provenance, including the visit, is
kept in a ``NoteOccurrence`` rather than on the note.

Ties and lyrics are *not* reinterpreted here (M3d2); this step only proves the performed order
and the exact global positions.
"""

from bisect import bisect_right
from dataclasses import replace

from barbershop_tracks.core.issues import IssueCollector
from barbershop_tracks.core.timeline.repeats import plan_performance
from barbershop_tracks.models import (
    MeasureSpan,
    Note,
    NoteOccurrence,
    Part,
    PerformancePlan,
    PerformedLine,
    PerformedSong,
    Song,
)


def perform_song(song: Song) -> PerformedSong:
    """Expand ``song`` into performance order."""
    planned = plan_performance(song.measures, song.repeat_marks)
    issues = IssueCollector()
    issues.extend(planned.issues)
    lines = tuple(_perform_line(part, song.measures, planned.plan, issues) for part in song.parts)
    return PerformedSong(song=song, plan=planned.plan, lines=lines, issues=issues.result())


def _perform_line(
    part: Part,
    measures: tuple[MeasureSpan, ...],
    plan: PerformancePlan,
    issues: IssueCollector,
) -> PerformedLine:
    starts = [span.start for span in measures]

    def measure_of(note: Note) -> int | None:
        if not measures:
            return None
        at = bisect_right(starts, note.start) - 1
        return at if 0 <= at < len(measures) and note.start < measures[at].end else None

    located = [(index, note, measure_of(note)) for index, note in enumerate(part.events)]
    if plan.is_identity:
        occurrences = tuple(
            NoteOccurrence(
                part_id=part.part_id,
                source_event_index=index,
                measure_index=where,
                visit=1,
                performed_start=note.start,
            )
            for index, note, where in located
        )
        return PerformedLine(part=part, occurrences=occurrences)

    by_measure: dict[int, list[tuple[int, Note]]] = {}
    for index, note, where in located:
        if where is None:
            issues.error(
                "NOTE_OUTSIDE_MEASURES",
                "a note lies outside every measure, so it cannot be placed in the repeats",
                part_id=part.part_id,
                measure=note.measure,
            )
            continue
        by_measure.setdefault(where, []).append((index, note))
    events: list[Note] = []
    occurrences_list: list[NoteOccurrence] = []
    for played in plan.played:
        shift = played.performed_start - measures[played.source_index].start
        for index, note in by_measure.get(played.source_index, ()):
            events.append(note if not shift else replace(note, start=note.start + shift))
            occurrences_list.append(
                NoteOccurrence(
                    part_id=part.part_id,
                    source_event_index=index,
                    measure_index=played.source_index,
                    visit=played.visit,
                    performed_start=note.start + shift,
                )
            )
    return PerformedLine(part=part.with_events(events), occurrences=tuple(occurrences_list))
