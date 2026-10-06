"""A note or rest in the performance timeline."""

from dataclasses import dataclass, field
from fractions import Fraction

from barbershop_tracks.models.lyric import Lyric
from barbershop_tracks.models.pitch import Pitch
from barbershop_tracks.models.pitch_transform import PitchTransform
from barbershop_tracks.models.timing import require_int, to_fraction


@dataclass(frozen=True, slots=True, kw_only=True)
class Note:
    """A sounding note (``written_pitch`` set) or a rest (``written_pitch`` is ``None``).

    ``start`` and ``duration`` are exact quarter-note ``Fraction`` values on the
    performance timeline. ``measure`` and ``beat`` record where the note was written in
    the source: ``measure`` is the source measure number (0 is allowed for a pickup) and
    ``beat`` is the 1-based position in the measure counted in quarter notes (1 is the
    downbeat, 5/2 is a half quarter after beat 2).

    Pitch: the note stores the pitch as written in the source (``written_pitch``) and the
    ``transform`` that applies to it (identity by default). The sounding pitch is derived,
    never stored, so the two cannot contradict each other.

    Invariants: duration is positive, start is not negative, a rest carries no lyrics, no
    ties and only the identity transform, and the sounding pitch must be derivable.
    """

    start: Fraction
    duration: Fraction
    measure: int
    beat: Fraction
    written_pitch: Pitch | None = None
    transform: PitchTransform = field(default_factory=PitchTransform)
    tied_to_next: bool = False
    tied_from_previous: bool = False
    lyrics: tuple[Lyric, ...] = ()

    def __post_init__(self) -> None:
        start = to_fraction(self.start, name="start")
        duration = to_fraction(self.duration, name="duration")
        beat = to_fraction(self.beat, name="beat")
        require_int(self.measure, name="measure")
        lyrics = tuple(self.lyrics)
        if start < 0:
            raise ValueError("start must not be negative")
        if duration <= 0:
            raise ValueError("duration must be positive")
        if self.measure < 0:
            raise ValueError("measure must not be negative")
        if beat < 1:
            raise ValueError("beat must be at least 1")
        if self.written_pitch is not None and not isinstance(self.written_pitch, Pitch):
            raise TypeError("written_pitch must be a Pitch or None")
        if not isinstance(self.transform, PitchTransform):
            raise TypeError("transform must be a PitchTransform")
        if not all(isinstance(lyric, Lyric) for lyric in lyrics):
            raise TypeError("lyrics must contain only Lyric objects")
        if self.written_pitch is None:
            if lyrics or self.tied_to_next or self.tied_from_previous:
                raise ValueError("a rest cannot have lyrics or ties")
            if not self.transform.is_identity:
                raise ValueError("a rest cannot have a pitch transform")
        else:
            self.transform.apply(self.written_pitch)  # fail early if not derivable
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "duration", duration)
        object.__setattr__(self, "beat", beat)
        object.__setattr__(self, "lyrics", lyrics)

    @classmethod
    def rest(cls, *, start: Fraction, duration: Fraction, measure: int, beat: Fraction) -> "Note":
        """Build a rest."""
        return cls(start=start, duration=duration, measure=measure, beat=beat)

    @property
    def is_rest(self) -> bool:
        return self.written_pitch is None

    @property
    def sounding_pitch(self) -> Pitch | None:
        """The pitch that sounds: ``transform`` applied to ``written_pitch`` (None for a rest)."""
        if self.written_pitch is None:
            return None
        return self.transform.apply(self.written_pitch)

    @property
    def midi_note(self) -> int | None:
        """Sounding equal-tempered MIDI note (None for a rest).

        Raises ``ValueError`` for a microtonal pitch rather than rounding.
        """
        pitch = self.sounding_pitch
        return None if pitch is None else pitch.midi_note

    @property
    def end(self) -> Fraction:
        return self.start + self.duration
