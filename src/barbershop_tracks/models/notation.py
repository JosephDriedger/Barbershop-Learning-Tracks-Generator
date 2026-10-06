"""Informational notation data preserved from the source score.

Nothing here takes part in sounding-pitch calculation. In particular a clef's octave
change is display information only; ``PitchTransform`` is the sole authority for the
written-to-sounding relationship.
"""

from dataclasses import dataclass
from fractions import Fraction

from barbershop_tracks.models.timing import require_int, to_fraction


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceLine:
    """Identity of one logical voice line in the source: part, staff and voice.

    Printed as ``P1/s1/v2``. It says *where the notes were written*; it does not say who
    sings them. Voice ids are strings, are only unique within a staff, and may be
    non-contiguous (MuseScore numbers voices across staves: 1, 2, 5, 6).
    """

    part_id: str
    staff: int
    voice: str

    def __post_init__(self) -> None:
        require_int(self.staff, name="staff")
        if self.staff < 1:
            raise ValueError("staff must be at least 1")
        for name, value in (("part_id", self.part_id), ("voice", self.voice)):
            if not value or "/" in value:
                raise ValueError(f"{name} must be non-empty and must not contain '/'")

    def __str__(self) -> str:
        return f"{self.part_id}/s{self.staff}/v{self.voice}"


@dataclass(frozen=True, slots=True, kw_only=True)
class ClefChange:
    """A clef that becomes active at ``position`` on one staff of one source part.

    ``position`` is the exact quarter-note position on the timeline and ``measure`` the
    source measure number. Informational only: it never affects pitch.
    """

    part_id: str
    staff: int
    sign: str
    line: int | None = None
    octave_change: int = 0
    measure: int
    position: Fraction

    def __post_init__(self) -> None:
        require_int(self.staff, name="staff")
        require_int(self.octave_change, name="octave_change")
        require_int(self.measure, name="measure")
        position = to_fraction(self.position, name="position")
        if not self.part_id:
            raise ValueError("part_id must not be empty")
        if self.staff < 1:
            raise ValueError("staff must be at least 1")
        if not self.sign:
            raise ValueError("sign must not be empty")
        if self.line is not None:
            require_int(self.line, name="line")
            if self.line < 1:
                raise ValueError("line must be at least 1")
        if self.measure < 0:
            raise ValueError("measure must not be negative")
        if position < 0:
            raise ValueError("position must not be negative")
        object.__setattr__(self, "position", position)
