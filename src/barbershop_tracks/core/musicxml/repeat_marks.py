"""Reading repeat signs from ``<barline>`` elements, and reconciling them across parts.

MusicXML semantics, not any application's: a forward repeat sits at the *left* barline of the
measure it starts, a backward repeat at the *right* barline of the measure it ends. Any other
combination is outside what is interpreted and is an ERROR; it is never silently attached to
the containing measure. ``times`` is the total number of passes (spec: a non-negative integer
with no default; absent means 2 here, a documented choice). Endings are not handled here
(``ENDING_NOT_SUPPORTED_YET``).
"""

import xml.etree.ElementTree as ET
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from barbershop_tracks.core.issues import IssueCollector
from barbershop_tracks.models import RepeatKind, RepeatMark

DEFAULT_TIMES = 2
MAX_TIMES = 16

Report = Callable[[str, str], None]  # (code, message)


@dataclass(frozen=True, slots=True)
class RawRepeat:
    """A repeat sign as read from one barline of one part."""

    kind: RepeatKind
    times: int | None
    measure_index: int


def read_repeat(
    barline: ET.Element,
    *,
    measure_index: int,
    content_before: bool,
    error: Report,
    warn: Report,
) -> RawRepeat | None:
    """The repeat sign on ``barline``, or ``None`` (with an issue) if it cannot be interpreted.

    ``content_before`` says whether notes, rests or moves already occurred in the measure.
    """
    repeat = barline.find("repeat")
    if repeat is None:
        return None
    direction = repeat.get("direction")
    if direction not in ("forward", "backward"):
        error("REPEAT_DIRECTION_INVALID", f"a <repeat> has direction {direction!r}")
        return None
    kind = RepeatKind(direction)
    location = barline.get("location", "right")
    if location not in ("left", "right"):
        error("REPEAT_MID_MEASURE", "a repeat sign in the middle of a measure is not supported")
        return None
    wanted = "left" if kind is RepeatKind.FORWARD else "right"
    if location != wanted:
        error(
            "REPEAT_BARLINE_PLACEMENT",
            f"a {direction} repeat is at the {location} barline (the default is 'right'); "
            f"M3d interprets a forward repeat only at the left barline and a backward repeat "
            "only at the right barline of a measure, and does not guess otherwise",
        )
        return None
    if location == "left" and content_before:
        error(
            "REPEAT_MID_MEASURE", "a forward repeat after the notes of a measure is not supported"
        )
        return None
    if repeat.get("after-jump") == "yes":
        error(
            "REPEAT_AFTER_JUMP_UNSUPPORTED",
            "a repeat played only after a D.C./D.S. jump is not supported",
        )
        return None
    usable, times = _read_times(repeat, kind, error=error, warn=warn)
    if not usable:
        return None
    return RawRepeat(kind=kind, times=times, measure_index=measure_index)


def _read_times(
    repeat: ET.Element, kind: RepeatKind, *, error: Report, warn: Report
) -> tuple[bool, int | None]:
    """``(usable, times)``; ``times`` is ``None`` if absent. Unusable values are reported."""
    raw = repeat.get("times")
    if raw is None:
        return True, None
    if kind is RepeatKind.FORWARD:
        warn("REPEAT_TIMES_IGNORED", "'times' on a forward repeat is ignored")
        return True, None
    text = raw.strip()
    if not (text.isascii() and text.isdigit()) or int(text) < 1:
        error(
            "REPEAT_TIMES_INVALID",
            f"repeat times={raw!r} is not a positive whole number of passes",
        )
        return False, None
    value = int(text)
    if value > MAX_TIMES:
        error("REPEAT_TIMES_EXCESSIVE", f"repeat times={value} exceeds the limit of {MAX_TIMES}")
        return False, None
    if value == 1:
        warn("REPEAT_TIMES_ONE", "repeat times=1 plays the section once; there is no repeat")
    return True, value


def _signature(mark: RepeatMark) -> tuple[str, int, int]:
    """What makes two repeat structures the same: boundaries and resolved pass counts."""
    passes = (mark.times or DEFAULT_TIMES) if mark.kind is RepeatKind.BACKWARD else 0
    return (mark.kind.value, mark.measure_index, passes)


def reconcile_marks(
    per_part: Sequence[tuple[str, Sequence[RawRepeat]]],
    measure_numbers: Sequence[int],
    issues: IssueCollector,
) -> tuple[RepeatMark, ...]:
    """The one repeat structure every part agrees on.

    Parts agree when their ordered ``(kind, measure, resolved passes)`` lists are equal (an
    absent ``times`` equals an explicit 2). Otherwise ``REPEAT_STRUCTURE_CONFLICT`` is reported
    for the first difference and no structure is returned, so parts are never expanded onto
    incompatible timelines.
    """
    if not per_part:
        return ()
    ordered = [
        (part_id, sorted(raws, key=lambda r: (r.measure_index, r.kind is RepeatKind.BACKWARD)))
        for part_id, raws in per_part
    ]
    marks = [
        tuple(RepeatMark(kind=r.kind, measure_index=r.measure_index, times=r.times) for r in raws)
        for _, raws in ordered
    ]
    reference_id, reference = ordered[0][0], marks[0]
    for (part_id, _), other in zip(ordered[1:], marks[1:], strict=True):
        signatures = [_signature(m) for m in reference], [_signature(m) for m in other]
        if signatures[0] == signatures[1]:
            continue
        where = _first_difference(reference, other)
        issues.error(
            "REPEAT_STRUCTURE_CONFLICT",
            f"part '{part_id}' has a different repeat structure from part '{reference_id}'"
            f" (first difference: {_describe(reference, other, where)}); parts cannot be "
            "expanded onto different timelines",
            part_id=part_id,
            measure=_number_at(measure_numbers, reference, other, where),
        )
        return ()
    return reference


def _first_difference(a: Sequence[RepeatMark], b: Sequence[RepeatMark]) -> int:
    for position, (x, y) in enumerate(zip(a, b, strict=False)):
        if _signature(x) != _signature(y):
            return position
    return min(len(a), len(b))


def _describe(a: Sequence[RepeatMark], b: Sequence[RepeatMark], position: int) -> str:
    def show(marks: Sequence[RepeatMark]) -> str:
        if position >= len(marks):
            return "no further repeat sign"
        mark = marks[position]
        return f"{mark.kind.value} at measure index {mark.measure_index}"

    return f"{show(a)} versus {show(b)}"


def _number_at(
    numbers: Sequence[int], a: Sequence[RepeatMark], b: Sequence[RepeatMark], position: int
) -> int | None:
    for marks in (b, a):
        if position < len(marks) and marks[position].measure_index < len(numbers):
            return numbers[marks[position].measure_index]
    return None
