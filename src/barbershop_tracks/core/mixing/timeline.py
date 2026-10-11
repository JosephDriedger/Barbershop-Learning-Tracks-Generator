"""The package length, derived from the score and never from the stems.

The performed score has an exact length in quarter notes and an exact tempo map (``Fraction``
BPM). The exact duration in seconds is a rational number; the number of sample frames is that
duration times the sample rate **rounded up** (``ceil``). Rounding up means no performed time is
ever cut off, and the output exceeds the exact duration by less than one frame (23 microseconds at
44.1 kHz). ``round`` or ``floor`` would shorten the package by up to one frame.
"""

import math
from collections.abc import Sequence
from fractions import Fraction

from barbershop_tracks.core.mixing.errors import MixConfigurationError
from barbershop_tracks.core.synthesis import TempoPoint


def exact_seconds(tempo: Sequence[TempoPoint], position: Fraction) -> Fraction:
    """Exact seconds at a quarter-note ``position`` under a piecewise-constant tempo map."""
    if not tempo or tempo[0].position != 0:
        raise MixConfigurationError("MIX_TEMPO_MISSING", "the tempo map needs an entry at zero")
    total = Fraction(0)
    for index, point in enumerate(tempo):
        if position <= point.position:
            break
        following = tempo[index + 1].position if index + 1 < len(tempo) else None
        end = position if following is None or position < following else following
        total += (end - point.position) * 60 / point.bpm
    return total


def duration_frames(tempo: Sequence[TempoPoint], length: Fraction, sample_rate: int) -> int:
    """Frames in the package: ``ceil(exact seconds * sample_rate)``."""
    if length <= 0:
        raise MixConfigurationError("MIX_LENGTH", f"the performed length {length} must be positive")
    if sample_rate <= 0:
        raise MixConfigurationError("MIX_RATE", f"sample rate {sample_rate} must be positive")
    return math.ceil(exact_seconds(tempo, length) * sample_rate)
