"""Volta groups: the structural relationship between a repeat and its endings.

A group is derived from the ending spans and the repeat marks and validated; it is **not** found
by scanning for adjacent ending measures. It has a body (the repeated section before the first
ending), the ending spans in source order tiling the measures after the body, a pass-to-ending
mapping, the backward repeats that jump back, and an exit. The repeat *start* (an open forward
repeat or the score beginning) is resolved by the planner, which owns repeat state.

Rules, each with its own diagnostic:

* the ending numbers partition ``1..N`` exactly: ``ENDING_PASS_DUPLICATE`` (a pass claimed twice),
  ``ENDING_PASS_MISSING`` (a pass nobody claims); nothing is renumbered;
* the last ending in source order is exactly ``{N}`` (it is the exit) and has no backward repeat;
  every other ending closes with a backward repeat that jumps back
  (``ENDING_WITHOUT_REPEAT`` / ``ENDING_STRUCTURE_UNSUPPORTED``). A lone ending is never given an
  implied partner: without a backward repeat it is ``ENDING_WITHOUT_REPEAT``, with one it is
  ``ENDING_STRUCTURE_UNSUPPORTED``;
* a repeat sign anywhere else inside the endings is ``ENDING_STRUCTURE_UNSUPPORTED``;
* ``times`` on those backward repeats must equal ``N`` (``REPEAT_TIMES_ENDINGS_CONFLICT``): the
  specification says ``times`` is not used with endings, and neither value is chosen over the other;
* the pass count is at most 16 (``REPEAT_TIMES_EXCESSIVE``).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from barbershop_tracks.core.issues import IssueCollector
from barbershop_tracks.models import EndingSpan, MeasureSpan, RepeatKind, RepeatMark

MAX_PASSES = 16


@dataclass(frozen=True, slots=True)
class VoltaGroup:
    """A validated repeat with endings (the repeat start is resolved by the planner)."""

    endings: tuple[EndingSpan, ...]  # in source order, tiling the measures after the body
    passes: int
    pass_to_ending: tuple[int, ...]  # for pass p (1-based), the index into ``endings``
    back_marks: tuple[int, ...]  # measure indices of the backward repeats that jump back

    @property
    def exit_index(self) -> int:
        """The measure after the last ending (may equal the number of measures: end of score)."""
        return self.endings[-1].end_index + 1


def _runs(endings: Sequence[EndingSpan]) -> list[list[EndingSpan]]:
    """Endings split where the measures are not contiguous."""
    runs: list[list[EndingSpan]] = []
    for ending in sorted(endings, key=lambda e: e.start_index):
        if runs and ending.start_index == runs[-1][-1].end_index + 1:
            runs[-1].append(ending)
        else:
            runs.append([ending])
    return runs


def build_groups(
    measures: Sequence[MeasureSpan],
    marks: Sequence[RepeatMark],
    endings: Sequence[EndingSpan],
    issues: IssueCollector,
) -> list[VoltaGroup] | None:
    """The validated groups in order, or ``None`` if any group is unusable (reported)."""
    groups: list[VoltaGroup] = []
    for run in _runs(endings):
        group = _group(run, measures, marks, issues)
        if group is None:
            return None
        groups.append(group)
    return groups


def _group(
    run: list[EndingSpan],
    measures: Sequence[MeasureSpan],
    marks: Sequence[RepeatMark],
    issues: IssueCollector,
) -> VoltaGroup | None:
    first, last = run[0], run[-1]
    where = measures[first.start_index].number

    def fail(code: str, message: str, measure: int | None = None) -> None:
        issues.error(code, message, measure=where if measure is None else measure)

    claimed: dict[int, int] = {}
    for position, ending in enumerate(run):
        for number in ending.numbers:
            if number in claimed:
                fail(
                    "ENDING_PASS_DUPLICATE",
                    f"pass {number} is claimed by two endings (measures "
                    f"{measures[run[claimed[number]].start_index].number} and "
                    f"{measures[ending.start_index].number})",
                    measures[ending.start_index].number,
                )
                return None
            claimed[number] = position
    passes = max(claimed)
    missing = [n for n in range(1, passes + 1) if n not in claimed]
    if missing:
        fail(
            "ENDING_PASS_MISSING",
            f"no ending is played on pass {', '.join(str(n) for n in missing)} "
            f"(the endings reach pass {passes}); endings must cover passes 1 to {passes} "
            "exactly and are never renumbered",
        )
        return None
    if passes > MAX_PASSES:
        fail("REPEAT_TIMES_EXCESSIVE", f"the endings reach pass {passes}, above {MAX_PASSES}")
        return None
    backward = {m.measure_index: m for m in marks if m.kind is RepeatKind.BACKWARD}
    forwards = [m.measure_index for m in marks if m.kind is RepeatKind.FORWARD]
    if any(first.start_index <= f <= last.end_index for f in forwards):
        fail("ENDING_STRUCTURE_UNSUPPORTED", "a forward repeat sits inside the endings")
        return None
    allowed = {e.end_index for e in run[:-1]}
    stray = [i for i in backward if first.start_index <= i <= last.end_index and i not in allowed]
    if stray:
        fail(
            "ENDING_STRUCTURE_UNSUPPORTED",
            "a backward repeat sits inside the endings but not at the end of an ending that "
            "jumps back (a last ending must not end with one)",
            measures[stray[0]].number,
        )
        return None
    if len(run) == 1:
        if last.end_index in backward:
            fail(
                "ENDING_STRUCTURE_UNSUPPORTED",
                "a single ending carries its own backward repeat; no second ending is implied "
                "and it is not looped as a plain repeat (write it as a plain repeat)",
            )
        else:
            fail(
                "ENDING_WITHOUT_REPEAT",
                "an ending has no backward repeat and no other ending, so no pass can reach it",
            )
        return None
    if last.numbers != (passes,):
        fail(
            "ENDING_STRUCTURE_UNSUPPORTED",
            f"the last ending (measure {measures[last.start_index].number}) must be played on "
            f"exactly the final pass {passes}; it is the exit and cannot be a jump-back ending",
            measures[last.start_index].number,
        )
        return None
    for ending in run[:-1]:
        mark = backward.get(ending.end_index)
        if mark is None:
            fail(
                "ENDING_WITHOUT_REPEAT",
                f"the ending at measure {measures[ending.start_index].number} is not the last "
                "but has no backward repeat, so playback cannot return for the next pass",
                measures[ending.end_index].number,
            )
            return None
        if mark.times is not None and mark.times != passes:
            fail(
                "REPEAT_TIMES_ENDINGS_CONFLICT",
                f"the repeat says times={mark.times} but the endings define {passes} passes; "
                "'times' is not used with endings and neither value is chosen",
                measures[ending.end_index].number,
            )
            return None
    return VoltaGroup(
        endings=tuple(run),
        passes=passes,
        pass_to_ending=tuple(claimed[p] for p in range(1, passes + 1)),
        back_marks=tuple(e.end_index for e in run[:-1]),
    )
