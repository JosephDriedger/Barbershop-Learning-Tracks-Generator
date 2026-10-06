"""Musical time primitives.

All musical positions and durations are ``fractions.Fraction`` values in quarter-note
units (quarter = 1, eighth = 1/2, triplet eighth = 1/3). Floats are rejected so that
rounding error can never enter the timeline. MIDI ticks do not appear in the domain model.
"""

from dataclasses import dataclass
from fractions import Fraction


def to_fraction(value: object, *, name: str = "value") -> Fraction:
    """Return ``value`` as an exact ``Fraction``.

    Accepts ``Fraction`` and ``int``. Rejects ``float`` (and ``bool``) with ``TypeError``
    because binary floating point cannot represent tuplet durations exactly.
    """
    if isinstance(value, bool) or not isinstance(value, Fraction | int):
        raise TypeError(f"{name} must be a Fraction or int, not {type(value).__name__}")
    return Fraction(value)


def require_int(value: object, *, name: str) -> int:
    """Return ``value`` if it is a real ``int`` (``bool`` is rejected)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int, not {type(value).__name__}")
    return value


@dataclass(frozen=True, slots=True, kw_only=True)
class TempoChange:
    """A tempo in quarter notes per minute, effective from ``position`` onward."""

    position: Fraction
    bpm: Fraction

    def __post_init__(self) -> None:
        position = to_fraction(self.position, name="position")
        bpm = to_fraction(self.bpm, name="bpm")
        if position < 0:
            raise ValueError("tempo position must not be negative")
        if bpm <= 0:
            raise ValueError("bpm must be positive")
        object.__setattr__(self, "position", position)
        object.__setattr__(self, "bpm", bpm)


@dataclass(frozen=True, slots=True, kw_only=True)
class TimeSignature:
    """A time signature effective from ``position`` (quarter notes) onward."""

    position: Fraction
    beats: int
    beat_type: int

    def __post_init__(self) -> None:
        position = to_fraction(self.position, name="position")
        require_int(self.beats, name="beats")
        require_int(self.beat_type, name="beat_type")
        if position < 0:
            raise ValueError("time signature position must not be negative")
        if self.beats <= 0:
            raise ValueError("beats must be positive")
        if self.beat_type <= 0 or self.beat_type & (self.beat_type - 1):
            raise ValueError("beat_type must be a positive power of two")
        object.__setattr__(self, "position", position)

    @property
    def measure_length(self) -> Fraction:
        """Length of one measure in quarter notes (6/8 -> 3, 4/4 -> 4)."""
        return Fraction(4 * self.beats, self.beat_type)
