"""Where a note is, in words a singer uses: ``bar 3, beat 2``. No engine and no Qt."""

from collections.abc import Sequence
from fractions import Fraction

from barbershop_tracks.core.synthesis.plan import MeasureMark, MeterPoint


def beat_text(beat: Fraction) -> str:
    whole, rest = divmod(beat, 1)
    if rest == 0:
        return str(int(whole))
    if rest.denominator == 2:
        return f"{int(whole)}\u00bd"
    return f"{float(beat):.2f}".rstrip("0").rstrip(".")


def _meter_at(start: Fraction, meters: Sequence[MeterPoint]) -> MeterPoint | None:
    found: MeterPoint | None = None
    for point in meters:
        if point.position > start:
            break
        found = point
    return found


def position_label(
    start: Fraction, meters: Sequence[MeterPoint], measures: Sequence[MeasureMark] = ()
) -> str:
    """``bar 3, beat 2`` for a quarter-note position; plain beats when the meter is unknown.

    With the performed ``measures`` the bar is the number the SCORE gives that measure (a pickup
    bar is ``bar 0``), so the place can be found in the score; a repeated measure says which time
    it is played.
    Without them (a plan built by hand) the bars are counted from the start.
    """
    if measures:
        for mark in measures:
            if mark.start <= start < mark.start + mark.length:
                meter = _meter_at(start, meters)
                full = meter.measure_length if meter is not None else mark.length
                offset = start - mark.start
                if mark.length < full and mark.start == measures[0].start:
                    offset += full - mark.length  # a pickup bar sounds on the last beats of its bar
                unit = Fraction(4, meter.beat_type) if meter is not None else Fraction(1)
                label = f"bar {mark.number}, beat {beat_text(offset / unit + 1)}"
                return label + (f" (time {mark.visit})" if mark.visit > 1 else "")
    if not meters or meters[0].position != 0:
        return f"beat {beat_text(start + 1)}"
    segment = meters[0]
    bars_before = 0
    for point in meters:
        if point.position > start:
            break
        length = Fraction(4 * segment.beats, segment.beat_type)
        if point is not segment:
            bars_before += int((point.position - segment.position) / length)
            segment = point
    length = Fraction(4 * segment.beats, segment.beat_type)
    inside = start - segment.position
    bar = bars_before + int(inside // length) + 1
    beat = (inside % length) / Fraction(4, segment.beat_type) + 1
    return f"bar {bar}, beat {beat_text(beat)}"
