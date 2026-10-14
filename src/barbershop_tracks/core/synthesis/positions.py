"""Where a note is, in words a singer uses: ``bar 3, beat 2``. No engine and no Qt."""

from collections.abc import Sequence
from fractions import Fraction

from barbershop_tracks.core.synthesis.plan import MeterPoint


def beat_text(beat: Fraction) -> str:
    whole, rest = divmod(beat, 1)
    if rest == 0:
        return str(int(whole))
    if rest.denominator == 2:
        return f"{int(whole)}\u00bd"
    return f"{float(beat):.2f}".rstrip("0").rstrip(".")


def position_label(start: Fraction, meters: Sequence[MeterPoint]) -> str:
    """``bar 3, beat 2`` for a quarter-note position; plain beats when the meter is unknown."""
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
