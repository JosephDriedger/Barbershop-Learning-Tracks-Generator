"""The song-wide time-signature map, reconciled across parts.

Each part records the *effective* meter at the start of every measure. Parts are compared by
what is in effect, not by what was written, so a part that declares nothing simply inherits
(only a meter that was actually established earlier; an unknown meter is never invented).
The map holds one ``TimeSignature`` per effective change: repeated declarations of the same
meter, in one part or several, produce one event (or none).

Disagreement between parts is ``TIME_SIGNATURE_CONFLICT``. A conflict is reported when it
**begins** or when the conflicting combination **changes**, not on every later measure in which
the same disagreement merely continues. When the parts agree again the conflict simply ends;
if it reappears later it is reported again. A part whose meter is unknown is not part of the
comparison (that is ``TIME_SIGNATURE_MISSING`` or ``TIME_SIGNATURE_UNSUPPORTED``, reported by
the part itself).
"""

from collections.abc import Sequence
from fractions import Fraction

from barbershop_tracks.core.musicxml.issues import IssueCollector
from barbershop_tracks.models import TimeSignature

MeterKey = tuple[int, int]  # (beats, beat_type)
_Combination = tuple[
    tuple[str, MeterKey], ...
]  # (part id, meter) for every part with a known meter


def build_meter_map(
    *,
    part_ids: Sequence[str],
    meters: Sequence[Sequence[MeterKey | None]],
    measure_numbers: Sequence[int],
    measure_lengths: Sequence[Fraction],
    issues: IssueCollector,
) -> tuple[TimeSignature, ...]:
    """Build the map from per-part effective meters.

    ``meters[p][i]`` is part ``p``'s effective meter at measure ``i`` (``None`` if unknown or
    unsupported; that part has already been reported). ``measure_numbers`` and
    ``measure_lengths`` come from the reference part; parts that disagree on length are reported
    elsewhere, so global positions here follow the reference.
    """
    result: list[TimeSignature] = []
    previous: MeterKey | None = None
    reported: _Combination | None = None  # the conflicting combination last reported, if any
    position = Fraction(0)
    count = min((len(m) for m in meters), default=0)
    count = min(count, len(measure_lengths))
    for index in range(count):
        known: _Combination = tuple(
            (part_ids[p], value) for p in range(len(meters)) if (value := meters[p][index])
        )
        distinct = {value for _, value in known}
        current = previous
        if len(distinct) > 1:
            if known != reported:
                reported = known
                _report_conflict(known, measure_numbers[index], issues)
            current = known[0][1]  # follow the first part so the map stays defined
        else:
            reported = None
            if distinct:
                current = next(iter(distinct))
        if current is not None and current != previous:
            result.append(TimeSignature(position=position, beats=current[0], beat_type=current[1]))
            previous = current
        position += measure_lengths[index]
    return tuple(result)


def _report_conflict(known: _Combination, measure: int, issues: IssueCollector) -> None:
    first_meter = known[0][1]
    clash_part = next(part for part, meter in known if meter != first_meter)
    everyone = ", ".join(f"part {part} has {_name(meter)}" for part, meter in known)
    issues.error(
        "TIME_SIGNATURE_CONFLICT",
        f"parts disagree about the meter from here ({everyone})",
        part_id=clash_part,
        measure=measure,
    )


def _name(meter: MeterKey) -> str:
    return f"{meter[0]}/{meter[1]}"
