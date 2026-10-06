"""A single score part."""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from fractions import Fraction
from itertools import pairwise

from barbershop_tracks.models.notation import SourceLine
from barbershop_tracks.models.note import Note
from barbershop_tracks.models.voice import VoiceRole


@dataclass(frozen=True, slots=True, kw_only=True)
class Part:
    """An ordered sequence of notes and rests from one source part.

    ``role`` is ``None`` until someone assigns it explicitly (``with_role``). The model
    never guesses a role from ``name``. ``events`` must be ordered by non-decreasing
    ``start``; simultaneous notes are representable (a validator reports them).

    A part read from a score is one logical voice line. ``source_line`` records its
    MusicXML part, staff and voice, and ``part_id`` is then exactly its text form
    (``P1/s1/v1``). ``name`` is a display name; ``source_name`` keeps the name as written
    in the source when it differs. A line is **not** a role: it says where notes were
    written, not who sings them.
    """

    part_id: str
    name: str
    events: tuple[Note, ...] = ()
    role: VoiceRole | None = None
    source_line: SourceLine | None = None
    source_name: str | None = None

    def __post_init__(self) -> None:
        events = tuple(self.events)
        if not self.part_id:
            raise ValueError("part_id must not be empty")
        if self.source_line is not None:
            if not isinstance(self.source_line, SourceLine):
                raise TypeError("source_line must be a SourceLine or None")
            if self.part_id != str(self.source_line):
                raise ValueError("part_id must equal the text form of source_line")
        if self.role is not None and not isinstance(self.role, VoiceRole):
            raise TypeError("role must be a VoiceRole or None")
        if not all(isinstance(event, Note) for event in events):
            raise TypeError("events must contain only Note objects")
        if any(later.start < earlier.start for earlier, later in pairwise(events)):
            raise ValueError("events must be ordered by start")
        object.__setattr__(self, "events", events)

    def with_role(self, role: VoiceRole | None) -> "Part":
        """Return a copy with an explicitly assigned role."""
        return replace(self, role=role)

    def with_events(self, events: Iterable[Note]) -> "Part":
        """Return a copy with different events."""
        return replace(self, events=tuple(events))

    @property
    def sounding_notes(self) -> tuple[Note, ...]:
        return tuple(event for event in self.events if not event.is_rest)

    @property
    def end(self) -> Fraction:
        """End of the last-ending event, or 0 for an empty part."""
        return max((event.end for event in self.events), default=Fraction(0))
