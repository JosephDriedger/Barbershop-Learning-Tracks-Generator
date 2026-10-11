"""Words and numbers for people: note names, bar/beat positions, durations. No Qt here."""

from collections.abc import Sequence
from fractions import Fraction

from barbershop_tracks.core.synthesis import MeterPoint

_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def note_name(midi: int) -> str:
    """``64`` -> ``E4`` (middle C is C4)."""
    return f"{_NAMES[midi % 12]}{midi // 12 - 1}"


def _beat_text(beat: Fraction) -> str:
    whole, rest = divmod(beat, 1)
    if rest == 0:
        return str(int(whole))
    if rest.denominator == 2:
        return f"{int(whole)}½"
    return f"{float(beat):.2f}".rstrip("0").rstrip(".")


def position_label(start: Fraction, meters: Sequence[MeterPoint]) -> str:
    """``bar 3, beat 2`` for a quarter-note position; plain beats when the meter is unknown."""
    if not meters or meters[0].position != 0:
        return f"beat {_beat_text(start + 1)}"
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
    return f"bar {bar}, beat {_beat_text(beat)}"


def duration_label(quarters: Fraction) -> str:
    if quarters == 1:
        return "1 beat"
    return (
        f"{_beat_text(quarters)} beats"
        if quarters.denominator <= 2
        else f"{float(quarters):.2f} beats"
    )


def clock(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 60}:{total % 60:02d}"
