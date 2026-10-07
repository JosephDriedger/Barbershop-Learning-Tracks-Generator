"""Expanding a ``Song`` into performance order: ``perform_song``.

The source ``Song`` and its ``Note`` objects are never modified. For a score with nothing to
repeat the performed lines contain the *same* ``Note`` objects. Otherwise each performed
occurrence of a note is a shifted copy (``dataclasses.replace`` with a new ``start``; pitch,
lyrics, ``measure`` and ``beat`` are untouched) and its provenance, including the visit, is kept
in a ``NoteOccurrence`` rather than on the note.

Ties are resolved **after** expansion, over the performed traversal. A repeat jump is never
written adjacency, so a tie never crosses one: the tie start before the jump and the tied-to note
after it are copied with their tie flag cleared (the tied-to note is a new attack, never
dropped) and each case is reported as ``TIE_BROKEN_BY_REPEAT``. Across ``SEQUENTIAL`` and
``REPEAT_EXIT`` transitions the written tie is kept.

Tempo and meter are rebuilt from the visited regions: explicit events replay on every visit at
their shifted positions; the carried tempo is a query (``effective_tempo_at``), never synthesised.
Meter events are the explicit declarations only; the meter in force is
``PerformedSong.effective_meter_at``, the written context of the measure being played.
"""

from bisect import bisect_right
from dataclasses import dataclass, replace
from fractions import Fraction
from itertools import pairwise

from barbershop_tracks.core.timeline.repeats import plan_performance
from barbershop_tracks.core.timeline.ties import merge_tied_notes
from barbershop_tracks.models import (
    LocatedIssue,
    MeasureSpan,
    Note,
    NoteOccurrence,
    Part,
    PerformanceLocation,
    PerformancePlan,
    PerformedLine,
    PerformedMeterEvent,
    PerformedSong,
    PlayedMeasure,
    Severity,
    Song,
    TempoChange,
    TimeSignature,
    TransitionKind,
    ValidationIssue,
)

_ORDINAL_SUFFIX = {1: "first", 2: "second", 3: "third"}


def perform_song(song: Song) -> PerformedSong:
    """Expand ``song`` into performance order and resolve ties over that order."""
    planned = plan_performance(song.measures, song.repeat_marks, song.ending_spans)
    plan = planned.plan
    located: list[LocatedIssue] = [LocatedIssue(issue) for issue in planned.issues]
    lines: list[PerformedLine] = []
    merged = []
    for part in song.parts:
        line, line_issues = _perform_line(part, song.measures, plan)
        result = merge_tied_notes(line.part.events, part_id=part.part_id)
        located.extend(line_issues)
        for issue, note in zip(result.issues, result.issue_notes, strict=True):
            located.append(LocatedIssue(issue, _location(plan, note.start)))
        lines.append(line)
        merged.append(result.notes)
    return PerformedSong(
        song=song,
        plan=plan,
        lines=tuple(lines),
        merged=tuple(merged),
        located_issues=tuple(located),
        tempo_events=_perform_tempo(song, plan),
        meter_events=_perform_meter(song, plan),
    )


def _location(plan: PerformancePlan, position: Fraction) -> PerformanceLocation | None:
    played = plan.locate(position)
    if played is None:
        return None
    return PerformanceLocation(
        measure_index=played.source_index,
        number=played.number,
        visit=played.visit,
        performed_position=position,
        performed_measure_index=played.performed_index,
        repeat_pass=played.repeat_pass,
        endings=played.endings,
    )


# --- notes -----------------------------------------------------------------------------------


@dataclass(slots=True)
class _Chunk:
    """The notes of one performed measure, in order."""

    played: PlayedMeasure
    notes: list[Note]
    sources: list[int]


def _perform_line(
    part: Part, measures: tuple[MeasureSpan, ...], plan: PerformancePlan
) -> tuple[PerformedLine, list[LocatedIssue]]:
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
        return PerformedLine(part=part, occurrences=occurrences), []

    issues: list[LocatedIssue] = []
    by_measure: dict[int, list[tuple[int, Note]]] = {}
    for index, note, where in located:
        if where is None:
            issues.append(
                LocatedIssue(
                    ValidationIssue(
                        severity=Severity.ERROR,
                        code="NOTE_OUTSIDE_MEASURES",
                        message="a note lies outside every measure, so it cannot be placed in "
                        "the repeats",
                        part_id=part.part_id,
                        measure=note.measure,
                    )
                )
            )
            continue
        by_measure.setdefault(where, []).append((index, note))
    chunks: list[_Chunk] = []
    for played in plan.played:
        shift = played.performed_start - measures[played.source_index].start
        entries = by_measure.get(played.source_index, [])
        chunks.append(
            _Chunk(
                played=played,
                notes=[
                    note if not shift else replace(note, start=note.start + shift)
                    for _, note in entries
                ],
                sources=[index for index, _ in entries],
            )
        )
    for before, after in pairwise(chunks):
        if after.played.arrival is TransitionKind.REPEAT_JUMP:
            issues.extend(_break_ties(part.part_id, before, after))
    events = [note for chunk in chunks for note in chunk.notes]
    occurrences_list = [
        NoteOccurrence(
            part_id=part.part_id,
            source_event_index=index,
            measure_index=chunk.played.source_index,
            visit=chunk.played.visit,
            performed_start=note.start,
        )
        for chunk in chunks
        for index, note in zip(chunk.sources, chunk.notes, strict=True)
    ]
    return PerformedLine(part=part.with_events(events), occurrences=tuple(occurrences_list)), issues


def _shifted(note: Note, shift: Fraction) -> Note:
    return note if not shift else replace(note, start=note.start + shift)


def _break_ties(part_id: str, before: _Chunk, after: _Chunk) -> list[LocatedIssue]:
    """Cut the ties that would cross a repeat jump and report each side once."""
    issues: list[LocatedIssue] = []
    end = before.played.performed_end
    tails = [i for i, n in enumerate(before.notes) if n.tied_to_next and n.end == end]
    for i in tails:
        before.notes[i] = replace(before.notes[i], tied_to_next=False)
    if tails:
        issues.append(_broken(part_id, before.played, before.notes[tails[0]], len(tails), "leaves"))
    start = after.played.performed_start
    heads = [i for i, n in enumerate(after.notes) if n.tied_from_previous and n.start == start]
    for i in heads:
        after.notes[i] = replace(after.notes[i], tied_from_previous=False)
    if heads:
        issues.append(_broken(part_id, after.played, after.notes[heads[0]], len(heads), "enters"))
    return issues


def _broken(part_id: str, played: PlayedMeasure, note: Note, count: int, side: str) -> LocatedIssue:
    what = "a tie" if count == 1 else f"{count} ties"
    if side == "leaves":
        message = (
            f"{what} leaving the end of this measure is not held across the repeat jump that "
            "follows (ties never cross a repeat jump); the note is played at its own length"
        )
    else:
        message = (
            f"the tied-to note{'' if count == 1 else 's'} at the start of this measure follow"
            f"{'s' if count == 1 else ''} a repeat jump, not the written measure before it, so "
            f"{'it is' if count == 1 else 'they are'} sung as a new attack, not dropped"
        )
    issue = ValidationIssue(
        severity=Severity.WARNING,
        code="TIE_BROKEN_BY_REPEAT",
        message=message,
        part_id=part_id,
        measure=note.measure,
        beat=note.beat,
    )
    location = PerformanceLocation(
        measure_index=played.source_index,
        number=played.number,
        visit=played.visit,
        performed_position=note.start,
        performed_measure_index=played.performed_index,
        repeat_pass=played.repeat_pass,
        endings=played.endings,
    )
    return LocatedIssue(issue, location)


# --- tempo and meter ---------------------------------------------------------------------------


def _perform_tempo(song: Song, plan: PerformancePlan) -> tuple[TempoChange, ...]:
    if plan.is_identity or not song.measures:
        return song.tempo_map
    chosen: dict[Fraction, TempoChange] = {}
    last = len(song.measures) - 1
    for played in plan.played:
        span = song.measures[played.source_index]
        shift = played.performed_start - span.start
        for event in song.tempo_map:
            inside = span.start <= event.position < span.end
            boundary = played.source_index == last and event.position == span.end
            if not (inside or boundary):
                continue
            position = event.position + shift
            if inside or position not in chosen:  # an event that starts a measure wins a tie
                chosen[position] = TempoChange(position=position, bpm=event.bpm)
    return tuple(chosen[position] for position in sorted(chosen))


def _perform_meter(song: Song, plan: PerformancePlan) -> tuple[PerformedMeterEvent, ...]:
    """The explicit declarations met on each visit; a jump or an inherited meter adds none."""
    if not plan.played:
        return tuple(
            PerformedMeterEvent(signature=signature, measure_index=None)
            for signature in song.time_signatures
        )
    declared_at = {signature.position: signature for signature in song.time_signatures}
    events: list[PerformedMeterEvent] = []
    for played in plan.played:
        signature = declared_at.get(song.measures[played.source_index].start)
        if signature is None:
            continue
        events.append(
            PerformedMeterEvent(
                signature=TimeSignature(
                    position=played.performed_start,
                    beats=signature.beats,
                    beat_type=signature.beat_type,
                ),
                measure_index=played.source_index,
                visit=played.visit,
            )
        )
    return tuple(events)
