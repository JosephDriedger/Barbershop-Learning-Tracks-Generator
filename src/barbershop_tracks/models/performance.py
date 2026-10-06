"""Derived performed events. Source ``Note``s are never replaced or mutated."""

from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise

from barbershop_tracks.models.lyric import Lyric
from barbershop_tracks.models.note import Note
from barbershop_tracks.models.pitch import Pitch


@dataclass(frozen=True, slots=True)
class PerformanceNote:
    """One performed attack: a single source note, or several tied source notes merged.

    ``source`` is the only stored fact; everything else is derived from it, so a
    ``PerformanceNote`` cannot contradict the notes it came from. The source notes keep their
    written pitches, spellings, transforms and lyrics, which makes the origin of a performed
    note easy to debug without any back-reference.

    Invariants: ``source`` is non-empty; a rest stands alone; the members of a tied group are
    all sounding, back-to-back in time (each starts exactly where the previous one ends) and
    share one exact sounding pitch (spellings may differ, e.g. C#4 tied to Db4).

    Not coupled to MIDI ticks, OpenUtau, FFmpeg or Qt.
    """

    source: tuple[Note, ...]

    def __post_init__(self) -> None:
        source = tuple(self.source)
        if not source:
            raise ValueError("a performance note needs at least one source note")
        if not all(isinstance(note, Note) for note in source):
            raise TypeError("source must contain only Note objects")
        object.__setattr__(self, "source", source)
        if len(source) == 1:
            return
        if any(note.is_rest for note in source):
            raise ValueError("a rest cannot be part of a tied group")
        first_height = _height(source[0])
        for previous, note in pairwise(source):
            if note.start != previous.end:
                raise ValueError("tied source notes must be back to back")
            if _height(note) != first_height:
                raise ValueError("tied source notes must have the same sounding pitch")

    @property
    def start(self) -> Fraction:
        return self.source[0].start

    @property
    def duration(self) -> Fraction:
        return sum((note.duration for note in self.source), Fraction(0))

    @property
    def end(self) -> Fraction:
        return self.source[-1].end

    @property
    def is_rest(self) -> bool:
        return self.source[0].is_rest

    @property
    def pitch(self) -> Pitch | None:
        """The representative **sounding** pitch of this performed attack; ``None`` for a rest.

        It is the first source note's *sounding* pitch (written pitch with its transform
        applied), not the source's written pitch. A tied group has exactly one sounding
        height (``pitch.absolute_semitones``) even when its source notes were written with
        different spellings (C#4 then Db4); the individual written pitches stay available in
        ``source``.
        """
        return self.source[0].sounding_pitch

    @property
    def lyrics(self) -> tuple[Lyric, ...]:
        """The first source note's lyrics. Continuation notes make no new attack."""
        return self.source[0].lyrics

    @property
    def measure(self) -> int:
        return self.source[0].measure

    @property
    def beat(self) -> Fraction:
        return self.source[0].beat

    @property
    def is_tied_group(self) -> bool:
        return len(self.source) > 1


def _height(note: Note) -> Fraction:
    pitch = note.sounding_pitch
    if pitch is None:  # pragma: no cover - rests are rejected before this is called
        raise ValueError("a rest has no pitch")
    return pitch.absolute_semitones
