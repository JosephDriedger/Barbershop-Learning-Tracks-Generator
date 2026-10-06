"""The derived performance-order representation. The source ``Song`` is never changed.

A repeat makes one written measure sound several times, so a source note has no single "visit":
each *performed occurrence* of it does. Visits, transitions and global performed positions
therefore live here, in objects derived from the ``Song``, and never on ``Note`` or
``ValidationIssue``.

Identity of a measure is its source **index**, never its display number.
"""

from bisect import bisect_right
from dataclasses import dataclass, field
from enum import Enum
from fractions import Fraction

from barbershop_tracks.models.note import Note
from barbershop_tracks.models.part import Part
from barbershop_tracks.models.song import Song
from barbershop_tracks.models.timing import require_int, to_fraction
from barbershop_tracks.models.validation import ValidationResult


class TransitionKind(Enum):
    """How playback arrived at a performed measure from the one before it."""

    START = "start"  # the first measure played
    SEQUENTIAL = "sequential"  # ordinary source adjacency: the next written measure
    REPEAT_JUMP = "repeat_jump"  # a backward repeat was taken: back to the start of the section
    REPEAT_EXIT = "repeat_exit"  # a repeat finished its last pass: on to the next written measure


@dataclass(frozen=True, slots=True, kw_only=True)
class PlayedMeasure:
    """One measure as it is performed: a source measure plus which time it is being played."""

    source_index: int
    number: int  # display number of the source measure
    visit: int  # 1 the first time this written measure is played, 2 the second, ...
    performed_index: int  # 0-based position in the performed order
    performed_start: Fraction
    length: Fraction
    arrival: TransitionKind

    def __post_init__(self) -> None:
        require_int(self.source_index, name="source_index")
        require_int(self.visit, name="visit")
        require_int(self.performed_index, name="performed_index")
        if self.source_index < 0 or self.performed_index < 0:
            raise ValueError("indices must not be negative")
        if self.visit < 1:
            raise ValueError("visit must be at least 1")
        object.__setattr__(self, "performed_start", to_fraction(self.performed_start, name="start"))
        object.__setattr__(self, "length", to_fraction(self.length, name="length"))
        if self.performed_start < 0 or self.length < 0:
            raise ValueError("start and length must not be negative")
        if not isinstance(self.arrival, TransitionKind):
            raise TypeError("arrival must be a TransitionKind")

    @property
    def performed_end(self) -> Fraction:
        return self.performed_start + self.length


@dataclass(frozen=True, slots=True)
class PerformancePlan:
    """The order in which source measures are played, as contiguous performed measures."""

    played: tuple[PlayedMeasure, ...] = ()
    _starts: tuple[Fraction, ...] = field(init=False, repr=False, compare=False, default=())

    def __post_init__(self) -> None:
        played = tuple(self.played)
        cursor = Fraction(0)
        for position, measure in enumerate(played):
            if not isinstance(measure, PlayedMeasure):
                raise TypeError("played must contain only PlayedMeasure objects")
            if measure.performed_index != position:
                raise ValueError("performed_index must equal the position in the plan")
            if measure.performed_start != cursor:
                raise ValueError("performed measures must be contiguous")
            if (measure.arrival is TransitionKind.START) != (position == 0):
                raise ValueError("only the first performed measure arrives by START")
            cursor = measure.performed_end
        object.__setattr__(self, "played", played)
        object.__setattr__(self, "_starts", tuple(m.performed_start for m in played))

    @property
    def end(self) -> Fraction:
        """The performed length in quarter notes."""
        return self.played[-1].performed_end if self.played else Fraction(0)

    @property
    def is_identity(self) -> bool:
        """True if every written measure is played once, in written order."""
        return all(m.source_index == i and m.visit == 1 for i, m in enumerate(self.played))

    @property
    def jump_positions(self) -> frozenset[Fraction]:
        """Performed positions at which playback lands after a repeat jump."""
        return frozenset(
            m.performed_start for m in self.played if m.arrival is TransitionKind.REPEAT_JUMP
        )

    def locate(self, position: Fraction) -> PlayedMeasure | None:
        """The performed measure containing ``position`` (``None`` if outside the plan)."""
        at = bisect_right(self._starts, position) - 1
        if at < 0:
            return None
        measure = self.played[at]
        if position < measure.performed_end or (
            position == measure.performed_start == measure.performed_end
        ):
            return measure
        return None

    def visits_of(self, source_index: int) -> tuple[PlayedMeasure, ...]:
        return tuple(m for m in self.played if m.source_index == source_index)


@dataclass(frozen=True, slots=True, kw_only=True)
class NoteOccurrence:
    """Where one performed note came from: the provenance of an expanded source note."""

    part_id: str
    source_event_index: int  # index into the source part's ``events``
    measure_index: int | None  # source measure identity (``None`` if the song has no measures)
    visit: int
    performed_start: Fraction

    def __post_init__(self) -> None:
        require_int(self.source_event_index, name="source_event_index")
        require_int(self.visit, name="visit")
        if self.visit < 1:
            raise ValueError("visit must be at least 1")
        object.__setattr__(self, "performed_start", to_fraction(self.performed_start, name="start"))


@dataclass(frozen=True, slots=True)
class PerformedLine:
    """One voice line in performed order.

    ``part.events`` are ordinary chronological ``Note`` copies on the performed timeline (the
    source notes themselves when nothing is repeated). ``occurrences[i]`` is the provenance of
    ``part.events[i]``; ``occurrence_of`` finds it from the note itself, including a note taken
    from a ``PerformanceNote.source`` built from this line.
    """

    part: Part
    occurrences: tuple[NoteOccurrence, ...]
    _by_note: dict[int, NoteOccurrence] = field(
        init=False, repr=False, compare=False, default_factory=dict
    )

    def __post_init__(self) -> None:
        occurrences = tuple(self.occurrences)
        if len(occurrences) != len(self.part.events):
            raise ValueError("there must be one occurrence per event")
        object.__setattr__(self, "occurrences", occurrences)
        lookup = {id(note): occ for note, occ in zip(self.part.events, occurrences, strict=True)}
        object.__setattr__(self, "_by_note", lookup)

    @property
    def part_id(self) -> str:
        return self.part.part_id

    def occurrence_of(self, note: Note) -> NoteOccurrence:
        """The provenance of ``note``, which must be one of this line's events."""
        try:
            return self._by_note[id(note)]
        except KeyError:
            raise KeyError("note is not an event of this performed line") from None


@dataclass(frozen=True, slots=True)
class PerformedSong:
    """A song in performance order. ``song`` is the literal source, referenced and unchanged."""

    song: Song
    plan: PerformancePlan
    lines: tuple[PerformedLine, ...]
    issues: ValidationResult

    def line(self, part_id: str) -> PerformedLine | None:
        return next((line for line in self.lines if line.part_id == part_id), None)
