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
from barbershop_tracks.models.performance import PerformanceNote
from barbershop_tracks.models.song import Song
from barbershop_tracks.models.timing import TempoChange, TimeSignature, require_int, to_fraction
from barbershop_tracks.models.validation import ValidationIssue, ValidationResult


class TransitionKind(Enum):
    """How playback arrived at a performed measure from the one before it."""

    START = "start"  # the first measure played
    SEQUENTIAL = "sequential"  # ordinary source adjacency: the next written measure
    REPEAT_JUMP = "repeat_jump"  # a backward repeat was taken: back to the start of the section
    REPEAT_EXIT = "repeat_exit"  # a repeat finished its last pass: on to the next written measure
    ENDING_SKIP = "ending_skip"  # an ending that is not the next written one was selected

    @property
    def is_discontinuity(self) -> bool:
        """True if performed state must not be assumed continuous across this arrival.

        The single place that knows which kinds break written adjacency; ties, lyrics and any
        future stateful interpretation go through it (or ``discontinuity_positions``).
        """
        return self in _DISCONTINUITIES


_DISCONTINUITIES = frozenset({TransitionKind.REPEAT_JUMP, TransitionKind.ENDING_SKIP})


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
    # the 1-based pass through the containing repeat or volta group; None outside a repeat
    # context. NOT ``visit`` (how often this written measure itself has been played)
    repeat_pass: int | None = None
    # the pass set of the ending being played (empty outside an ending)
    endings: tuple[int, ...] = ()

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
        if self.repeat_pass is not None:
            require_int(self.repeat_pass, name="repeat_pass")
            if self.repeat_pass < 1:
                raise ValueError("repeat_pass must be at least 1")
        object.__setattr__(self, "endings", tuple(self.endings))

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

    @property
    def discontinuity_positions(self) -> frozenset[Fraction]:
        """Positions reached by an arrival that is not written adjacency.

        A repeat jump or a skipped ending. Stateful interpretation (ties, lyrics) asks whether
        the traversal crossed one of these, not which kind it was; the kind stays on each
        ``PlayedMeasure.arrival``.
        """
        return frozenset(m.performed_start for m in self.played if m.arrival.is_discontinuity)

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


_ORDINALS = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth"}


@dataclass(frozen=True, slots=True, kw_only=True)
class PerformanceLocation:
    """Where in the performance something happened, keeping the source measure identity.

    ``measure_index`` is the source measure (the identity); ``number`` is only its display
    number. ``visit`` says which time that written measure is being played, and
    ``performed_measure_index`` is the 0-based position in the performed order.
    """

    measure_index: int
    number: int
    visit: int
    performed_position: Fraction
    performed_measure_index: int
    repeat_pass: int | None = None
    endings: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        require_int(self.measure_index, name="measure_index")
        require_int(self.visit, name="visit")
        require_int(self.performed_measure_index, name="performed_measure_index")
        if self.visit < 1:
            raise ValueError("visit must be at least 1")
        object.__setattr__(
            self, "performed_position", to_fraction(self.performed_position, name="position")
        )

    def describe(self) -> str:
        """For example ``"measure 3, second visit"``."""
        ordinal = _ORDINALS.get(self.visit, f"{self.visit}th")
        text = f"measure {self.number}, {ordinal} visit"
        if self.repeat_pass is not None:
            text += f", pass {self.repeat_pass}"
        if self.endings:
            text += ", ending " + ",".join(str(n) for n in self.endings)
        return text


@dataclass(frozen=True, slots=True)
class LocatedIssue:
    """A finding together with its performance location (``None`` if it has no single place)."""

    issue: ValidationIssue
    location: PerformanceLocation | None = None

    def __str__(self) -> str:
        where = f" [{self.location.describe()}]" if self.location is not None else ""
        return f"{self.issue}{where}"


@dataclass(frozen=True, slots=True, kw_only=True)
class PerformedMeterEvent:
    """An **explicit** time-signature declaration met during the performed traversal.

    It exists only where the score itself declares a time signature in a measure that is played;
    a measure that merely inherits a meter never has one, and a repeat jump never creates one.
    ``signature.position`` is the performed position; ``measure_index`` and ``visit`` say which
    visit of which written measure declared it. The meter that *applies* at a position is a
    different question: ``PerformedSong.effective_meter_at``.
    """

    signature: TimeSignature
    measure_index: int | None
    visit: int = 1


@dataclass(frozen=True, slots=True)
class PerformedSong:
    """A song in performance order. ``song`` is the literal source, referenced and unchanged.

    * ``lines`` / ``merged``: per line, the performed notes and the tie-merged attacks (ties are
      resolved over the performed traversal, never across a repeat jump);
    * ``tempo_events``: the **explicit** source tempo events, repeated at their shifted performed
      positions on every visit. Carried tempo is not stored: ``effective_tempo_at`` answers it;
    * ``meter_events``: the explicit time-signature declarations met on each visit, nothing else.
      The meter in force is the query ``effective_meter_at``: the written context of the measure
      being played, so it is restored on a jump without any declaration being invented;
    * ``located_issues``: every finding of the performance stage, with its location.
    """

    song: Song
    plan: PerformancePlan
    lines: tuple[PerformedLine, ...]
    merged: tuple[tuple[PerformanceNote, ...], ...]
    located_issues: tuple[LocatedIssue, ...] = ()
    tempo_events: tuple[TempoChange, ...] = ()
    meter_events: tuple[PerformedMeterEvent, ...] = ()

    def __post_init__(self) -> None:
        if len(self.merged) != len(self.lines):
            raise ValueError("there must be one merged tuple per line")

    @property
    def issues(self) -> ValidationResult:
        return ValidationResult.of(located.issue for located in self.located_issues)

    def line(self, part_id: str) -> PerformedLine | None:
        return next((line for line in self.lines if line.part_id == part_id), None)

    def attacks(self, part_id: str) -> tuple[PerformanceNote, ...]:
        """The tie-merged performed attacks of one line."""
        for line, notes in zip(self.lines, self.merged, strict=True):
            if line.part_id == part_id:
                return notes
        raise KeyError(part_id)

    def location_of(self, note: Note) -> PerformanceLocation | None:
        """The performance location of a performed note (``None`` outside the plan)."""
        played = self.plan.locate(note.start)
        if played is None:
            return None
        return PerformanceLocation(
            measure_index=played.source_index,
            number=played.number,
            visit=played.visit,
            performed_position=note.start,
            performed_measure_index=played.performed_index,
            repeat_pass=played.repeat_pass,
            endings=played.endings,
        )

    def effective_tempo_at(self, position: Fraction) -> TempoChange | None:
        """The tempo in force at ``position``: the last explicit event at or before it.

        Tempo is performance state, so it carries across a repeat jump; nothing is invented
        for a position before the first tempo event.
        """
        found = None
        for event in self.tempo_events:
            if event.position > position:
                break
            found = event
        return found

    def effective_meter_at(self, position: Fraction) -> TimeSignature | None:
        """The meter in force at ``position``; ``position`` of the result is the measure start.

        A measure's meter is the one in force at that measure in the *written* score, so after a
        repeat jump the destination plays under its own written meter, whether or not it declares
        one. Nothing is added to ``meter_events`` for that. ``None`` before any meter exists.
        """
        played = self.plan.locate(position)
        if played is None:
            return self._last_declared(position)
        span = self.song.measures[played.source_index]
        found = None
        for signature in self.song.time_signatures:
            if signature.position > span.start:
                break
            found = signature
        if found is None:
            return None
        return TimeSignature(
            position=played.performed_start, beats=found.beats, beat_type=found.beat_type
        )

    def _last_declared(self, position: Fraction) -> TimeSignature | None:
        found = None
        for event in self.meter_events:
            if event.signature.position > position:
                break
            found = event.signature
        return found
