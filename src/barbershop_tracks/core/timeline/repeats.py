"""Planning repeats and endings: which source measures are played, in what order.

Pure: a measure table, repeat marks and ending spans in, a ``PerformancePlan`` and issues out.
Notes are not touched here (see ``expand``). The supported structure is small and fully
determined.

Plain repeats (M3d):

* a forward repeat opens a section; the next backward repeat closes it and the section is
  played ``times`` times in total (absent: 2);
* a backward repeat with no repeat sign before it repeats from the beginning of the score;
* a forward repeat that is never closed is played straight through (one WARNING);
* a forward while another is open (nesting, or debris) is ``REPEAT_NESTED_UNSUPPORTED``;
* a backward that follows an earlier backward without its own forward is
  ``REPEAT_START_AMBIGUOUS`` (applications disagree on where it returns to).

Volta groups (M3e), derived from the ending spans and validated structurally (``volta.py``):
a repeat start, a body, endings that tile the measures after the body, a pass-to-ending mapping
that partitions ``1..N`` exactly, a backward repeat closing every ending but the last, and an
exit. The pass count comes from the endings only. Pass ``p`` plays the body and then the ending
whose pass set contains ``p``; arriving at an ending that is not written directly after the body
is an ``ENDING_SKIP``.

Any error leaves the plan as the identity (written order, each measure once), so the result is
defined while the ERROR blocks generation.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from barbershop_tracks.core.issues import IssueCollector
from barbershop_tracks.core.timeline.volta import VoltaGroup, build_groups
from barbershop_tracks.models import (
    EndingSpan,
    MeasureSpan,
    PerformancePlan,
    PlayedMeasure,
    RepeatKind,
    RepeatMark,
    TransitionKind,
    ValidationResult,
)

DEFAULT_PASSES = 2
MAX_PERFORMED_MEASURES = 10_000


@dataclass(frozen=True, slots=True)
class PlanResult:
    plan: PerformancePlan
    issues: ValidationResult


@dataclass(frozen=True, slots=True)
class _Section:
    first: int  # source index of the first measure
    last: int  # source index of the last measure
    passes: int
    group: VoltaGroup | None = None


@dataclass(frozen=True, slots=True)
class _Event:
    index: int
    kind: RepeatKind
    times: int | None = None
    group: VoltaGroup | None = None  # set for the synthetic close of a volta group


def plan_performance(
    measures: Sequence[MeasureSpan],
    marks: Sequence[RepeatMark],
    endings: Sequence[EndingSpan] = (),
) -> PlanResult:
    """The performance order for ``measures`` under repeat ``marks`` and ending spans."""
    issues = IssueCollector()
    sections = _sections(measures, marks, endings, issues)
    if sections is not None and _size(measures, sections) > MAX_PERFORMED_MEASURES:
        issues.error(
            "REPEAT_EXPANSION_TOO_LARGE",
            f"the repeats would perform more than {MAX_PERFORMED_MEASURES} measures",
        )
        sections = None
    plan = _build(measures, sections or [])
    return PlanResult(plan=plan, issues=issues.result())


def _sections(
    measures: Sequence[MeasureSpan],
    marks: Sequence[RepeatMark],
    endings: Sequence[EndingSpan],
    issues: IssueCollector,
) -> list[_Section] | None:
    """The repeat sections in order, or ``None`` if the structure cannot be interpreted."""
    groups = build_groups(measures, marks, endings, issues)
    if groups is None:
        return None
    consumed = {(i) for group in groups for i in group.back_marks}
    events = [
        _Event(m.measure_index, m.kind, m.times)
        for m in marks
        if not (m.kind is RepeatKind.BACKWARD and m.measure_index in consumed)
    ]
    events += [
        _Event(group.endings[-1].end_index, RepeatKind.BACKWARD, group=group) for group in groups
    ]
    events.sort(key=lambda e: (e.index, e.kind is RepeatKind.BACKWARD))
    sections: list[_Section] = []
    open_at: int | None = None
    seen_any = False
    for event in events:
        number = measures[event.index].number
        if event.kind is RepeatKind.FORWARD:
            if open_at is not None:
                issues.error(
                    "REPEAT_NESTED_UNSUPPORTED",
                    f"a forward repeat at measure {number} begins before the forward repeat at "
                    f"measure {measures[open_at].number} was closed; nested repeats are not "
                    "supported, and an unclosed outer repeat is not guessed at",
                    measure=number,
                )
                return None
            open_at = event.index
        else:
            start = open_at if open_at is not None else (0 if not seen_any else None)
            if start is None:
                issues.error(
                    "REPEAT_START_AMBIGUOUS",
                    f"the backward repeat at measure {number} follows an earlier repeat and has "
                    "no forward repeat of its own, so where it returns to is not defined (it "
                    "could be the score start, the previous forward repeat, or the end of the "
                    "previous repeat); add a forward repeat",
                    measure=number,
                )
                return None
            if event.group is not None:
                if start >= event.group.endings[0].start_index:
                    issues.error(
                        "ENDING_STRUCTURE_UNSUPPORTED",
                        f"the endings at measure {number} have no repeated body before them "
                        "(the repeat starts at or after the first ending)",
                        measure=number,
                    )
                    return None
                sections.append(_Section(start, event.index, event.group.passes, event.group))
            else:
                sections.append(_Section(start, event.index, event.times or DEFAULT_PASSES))
            open_at = None
        seen_any = True
    if open_at is not None:
        issues.warning(
            "REPEAT_FORWARD_UNUSED",
            f"the forward repeat at measure {measures[open_at].number} has no backward repeat; "
            "it is played straight through",
            measure=measures[open_at].number,
        )
    return sections


def _length(measures: Sequence[MeasureSpan], first: int, last: int) -> int:
    return last - first + 1


def _size(measures: Sequence[MeasureSpan], sections: Sequence[_Section]) -> int:
    extra = 0
    for s in sections:
        if s.group is None:
            extra += _length(measures, s.first, s.last) * (s.passes - 1)
            continue
        body = s.group.endings[0].start_index - s.first
        endings = [
            _length(measures, e.start_index, e.end_index)
            for p in range(s.passes)
            for e in [s.group.endings[s.group.pass_to_ending[p]]]
        ]
        covered = _length(measures, s.first, s.last)
        extra += body * s.passes + sum(endings) - covered
    return len(measures) + extra


_Entry = tuple[int, TransitionKind, int | None, tuple[int, ...]]


def _build(measures: Sequence[MeasureSpan], sections: Sequence[_Section]) -> PerformancePlan:
    order: list[_Entry] = []
    after_section = False
    index = 0
    by_first = {s.first: s for s in sections}

    def entering() -> TransitionKind:
        if after_section:
            return TransitionKind.REPEAT_EXIT
        return TransitionKind.SEQUENTIAL if order else TransitionKind.START

    while index < len(measures):
        section = by_first.get(index)
        if section is None:
            order.append((index, entering(), None, ()))
            after_section = False
            index += 1
            continue
        group = section.group
        body_last = section.last if group is None else group.endings[0].start_index - 1
        for played_pass in range(1, section.passes + 1):
            for position in range(section.first, body_last + 1):
                if position == section.first:
                    kind = TransitionKind.REPEAT_JUMP if played_pass > 1 else entering()
                else:
                    kind = TransitionKind.SEQUENTIAL
                order.append((position, kind, played_pass, ()))
            if group is None:
                continue
            ending = group.endings[group.pass_to_ending[played_pass - 1]]
            for position in range(ending.start_index, ending.end_index + 1):
                if position == ending.start_index:
                    adjacent = ending.start_index == body_last + 1
                    kind = TransitionKind.SEQUENTIAL if adjacent else TransitionKind.ENDING_SKIP
                else:
                    kind = TransitionKind.SEQUENTIAL
                order.append((position, kind, played_pass, ending.numbers))
        after_section = True
        index = section.last + 1
    played: list[PlayedMeasure] = []
    visits: dict[int, int] = {}
    cursor = Fraction(0)
    for performed_index, (source, kind, repeat_pass, ending_numbers) in enumerate(order):
        span = measures[source]
        visits[source] = visits.get(source, 0) + 1
        played.append(
            PlayedMeasure(
                source_index=source,
                number=span.number,
                visit=visits[source],
                performed_index=performed_index,
                performed_start=cursor,
                length=span.length,
                arrival=kind,
                repeat_pass=repeat_pass,
                endings=ending_numbers,
            )
        )
        cursor += span.length
    return PerformancePlan(played=tuple(played))
