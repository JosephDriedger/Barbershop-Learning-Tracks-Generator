"""Planning plain repeats: which source measures are played, in what order.

Pure: a measure table and repeat marks in, a ``PerformancePlan`` and issues out. Notes are not
touched here (see ``expand``). The supported structure is deliberately small and fully
determined:

* a forward repeat opens a section; the next backward repeat closes it and the section is
  played ``times`` times in total (absent: 2);
* a backward repeat with no repeat sign before it repeats from the beginning of the score;
* a forward repeat that is never closed is played straight through (one WARNING);
* a forward while another is open (nesting, or debris) is ``REPEAT_NESTED_UNSUPPORTED``;
* a backward that follows an earlier backward without its own forward is
  ``REPEAT_START_AMBIGUOUS`` (applications disagree on where it returns to).

Any error leaves the plan as the identity (written order, each measure once), so the result is
defined while the ERROR blocks generation.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from barbershop_tracks.core.issues import IssueCollector
from barbershop_tracks.models import (
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


def plan_performance(measures: Sequence[MeasureSpan], marks: Sequence[RepeatMark]) -> PlanResult:
    """The performance order for ``measures`` under ``marks``."""
    issues = IssueCollector()
    sections = _sections(measures, marks, issues)
    if sections is not None and _size(measures, sections) > MAX_PERFORMED_MEASURES:
        issues.error(
            "REPEAT_EXPANSION_TOO_LARGE",
            f"the repeats would perform more than {MAX_PERFORMED_MEASURES} measures",
        )
        sections = None
    if sections is None:
        sections = []
    plan = _build(measures, sections)
    return PlanResult(plan=plan, issues=issues.result())


def _sections(
    measures: Sequence[MeasureSpan], marks: Sequence[RepeatMark], issues: IssueCollector
) -> list[_Section] | None:
    """The repeat sections in order, or ``None`` if the structure cannot be interpreted."""
    ordered = sorted(marks, key=lambda m: (m.measure_index, m.kind is RepeatKind.BACKWARD))
    sections: list[_Section] = []
    open_at: int | None = None
    seen_any = False
    for mark in ordered:
        number = measures[mark.measure_index].number
        if mark.kind is RepeatKind.FORWARD:
            if open_at is not None:
                issues.error(
                    "REPEAT_NESTED_UNSUPPORTED",
                    f"a forward repeat at measure {number} begins before the forward repeat at "
                    f"measure {measures[open_at].number} was closed; nested repeats are not "
                    "supported, and an unclosed outer repeat is not guessed at",
                    measure=number,
                )
                return None
            open_at = mark.measure_index
        elif open_at is not None:
            sections.append(_Section(open_at, mark.measure_index, mark.times or DEFAULT_PASSES))
            open_at = None
        elif not seen_any:
            sections.append(_Section(0, mark.measure_index, mark.times or DEFAULT_PASSES))
        else:
            issues.error(
                "REPEAT_START_AMBIGUOUS",
                f"the backward repeat at measure {number} follows an earlier repeat and has no "
                "forward repeat of its own, so where it returns to is not defined (it could "
                "be the score start, the previous forward repeat, or the end of the previous "
                "repeat); add a forward repeat",
                measure=number,
            )
            return None
        seen_any = True
    if open_at is not None:
        issues.warning(
            "REPEAT_FORWARD_UNUSED",
            f"the forward repeat at measure {measures[open_at].number} has no backward repeat; "
            "it is played straight through",
            measure=measures[open_at].number,
        )
    return sections


def _size(measures: Sequence[MeasureSpan], sections: Sequence[_Section]) -> int:
    extra = sum((s.last - s.first + 1) * (s.passes - 1) for s in sections)
    return len(measures) + extra


def _build(measures: Sequence[MeasureSpan], sections: Sequence[_Section]) -> PerformancePlan:
    order: list[tuple[int, TransitionKind]] = []
    visits: dict[int, int] = {}
    after_section = False
    index = 0
    by_first = {s.first: s for s in sections}
    while index < len(measures):
        section = by_first.get(index)
        if section is None:
            order.append((index, TransitionKind.REPEAT_EXIT if after_section else _next(order)))
            after_section = False
            index += 1
            continue
        for played_pass in range(section.passes):
            for position in range(section.first, section.last + 1):
                if position == section.first:
                    if played_pass:
                        kind = TransitionKind.REPEAT_JUMP
                    else:
                        kind = TransitionKind.REPEAT_EXIT if after_section else _next(order)
                else:
                    kind = TransitionKind.SEQUENTIAL
                order.append((position, kind))
        after_section = True
        index = section.last + 1
    played: list[PlayedMeasure] = []
    cursor = Fraction(0)
    for performed_index, (source, kind) in enumerate(order):
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
            )
        )
        cursor += span.length
    return PerformancePlan(played=tuple(played))


def _next(order: Sequence[tuple[int, TransitionKind]]) -> TransitionKind:
    return TransitionKind.SEQUENTIAL if order else TransitionKind.START
