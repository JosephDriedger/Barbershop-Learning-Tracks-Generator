"""Source structure facts read literally from a score: the measure table and repeat signs.

These are source facts, like tempo and meter. They say what the file contains; they never say
what is played (that is the derived ``PerformancePlan``).
"""

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction

from barbershop_tracks.models.timing import require_int, to_fraction


class RepeatKind(Enum):
    FORWARD = "forward"  # start of a repeated section
    BACKWARD = "backward"  # end of a repeated section


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasureSpan:
    """One source measure on the source timeline.

    ``index`` is the stable 0-based position of the measure in the score and **is its
    identity**. ``number`` is only the display number (``raw_number`` is the text as written, or
    ``None`` if absent); display numbers may repeat, be ``0`` or be non-numeric, so they are never
    used to identify a measure. ``length`` is the actual parsed length in quarter notes, so a
    pickup keeps its true length.
    """

    index: int
    number: int
    start: Fraction
    length: Fraction
    raw_number: str | None = None
    implicit: bool = False

    def __post_init__(self) -> None:
        require_int(self.index, name="index")
        require_int(self.number, name="number")
        if self.index < 0:
            raise ValueError("index must not be negative")
        start = to_fraction(self.start, name="start")
        length = to_fraction(self.length, name="length")
        if start < 0:
            raise ValueError("start must not be negative")
        if length < 0:
            raise ValueError("length must not be negative")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "length", length)

    @property
    def end(self) -> Fraction:
        return self.start + self.length


@dataclass(frozen=True, slots=True, kw_only=True)
class RepeatMark:
    """A repeat sign: a forward at the start of ``measure_index`` or a backward at its end.

    ``times`` is the total number of passes written on a backward repeat, or ``None`` if the
    score does not say (the planner then plays the section twice).
    """

    kind: RepeatKind
    measure_index: int
    times: int | None = None

    def __post_init__(self) -> None:
        require_int(self.measure_index, name="measure_index")
        if not isinstance(self.kind, RepeatKind):
            raise TypeError("kind must be a RepeatKind")
        if self.measure_index < 0:
            raise ValueError("measure_index must not be negative")
        if self.times is not None:
            require_int(self.times, name="times")
            if self.times < 1:
                raise ValueError("times must be at least 1")
            if self.kind is RepeatKind.FORWARD:
                raise ValueError("a forward repeat has no times")
