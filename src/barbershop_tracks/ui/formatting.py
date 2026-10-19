"""Words and numbers for people: note names, bar/beat positions, durations. No Qt here."""

from fractions import Fraction

from barbershop_tracks.core.synthesis.positions import beat_text
from barbershop_tracks.core.synthesis.positions import position_label as position_label

_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def note_name(midi: int) -> str:
    """``64`` -> ``E4`` (middle C is C4)."""
    return f"{_NAMES[midi % 12]}{midi // 12 - 1}"


def duration_label(quarters: Fraction) -> str:
    if quarters == 1:
        return "1 beat"
    return (
        f"{beat_text(quarters)} beats"
        if quarters.denominator <= 2
        else f"{float(quarters):.2f} beats"
    )


def clock(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 60}:{total % 60:02d}"


def sentence(text: str) -> str:
    """``the score has no tempo`` -> ``The score has no tempo`` (only a lower-case first letter)."""
    return text[:1].upper() + text[1:] if text[:1].islower() else text
