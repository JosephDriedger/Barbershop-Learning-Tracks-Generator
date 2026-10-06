"""Pitch with preserved spelling."""

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction

from barbershop_tracks.models.timing import require_int, to_fraction


class Step(Enum):
    """Diatonic note letter."""

    C = "C"
    D = "D"
    E = "E"
    F = "F"
    G = "G"
    A = "A"
    B = "B"

    @property
    def semitone(self) -> int:
        """Semitones above C within the octave."""
        return _STEP_SEMITONES[self]


_STEP_SEMITONES: dict[Step, int] = {
    Step.C: 0,
    Step.D: 2,
    Step.E: 4,
    Step.F: 5,
    Step.G: 7,
    Step.A: 9,
    Step.B: 11,
}

MIN_OCTAVE = -1
MAX_OCTAVE = 9
MAX_ALTER = 2


@dataclass(frozen=True, slots=True)
class Pitch:
    """A pitch spelled as step + alteration + octave (scientific notation, C4 = middle C).

    This is the *sounding* pitch spelling. Any written-vs-sounding transposition
    (transposing instruments, octave clefs) is resolved by the score reader before a
    ``Pitch`` is created, so the model never holds two possibly-contradicting pitches.

    Spelling is preserved: ``C#4`` and ``Db4`` are different values (``!=``) even though
    they sound the same in equal temperament (``sounds_like`` is True, ``midi_note`` equal).
    ``alter`` is in semitones (+1 sharp, -1 flat, +-2 double). Non-integer alterations
    (microtones) are representable but have no equal-tempered ``midi_note``.
    """

    step: Step
    octave: int
    alter: Fraction = Fraction(0)

    def __post_init__(self) -> None:
        if not isinstance(self.step, Step):
            raise TypeError("step must be a Step")
        require_int(self.octave, name="octave")
        alter = to_fraction(self.alter, name="alter")
        if not MIN_OCTAVE <= self.octave <= MAX_OCTAVE:
            raise ValueError(f"octave must be between {MIN_OCTAVE} and {MAX_OCTAVE}")
        if abs(alter) > MAX_ALTER:
            raise ValueError(f"alter must be within +-{MAX_ALTER} semitones")
        object.__setattr__(self, "alter", alter)
        if alter.denominator == 1 and not 0 <= self.midi_note <= 127:
            raise ValueError("pitch is outside the MIDI range 0-127")

    @property
    def is_equal_tempered(self) -> bool:
        """True when ``alter`` is a whole number of semitones."""
        return self.alter.denominator == 1

    @property
    def midi_note(self) -> int:
        """Sounding equal-tempered MIDI note number (C4 = 60)."""
        if not self.is_equal_tempered:
            raise ValueError(f"{self} is microtonal and has no MIDI note number")
        return 12 * (self.octave + 1) + self.step.semitone + int(self.alter)

    def sounds_like(self, other: "Pitch") -> bool:
        """True if both pitches have the same equal-tempered sounding pitch."""
        return self.midi_note == other.midi_note

    def __str__(self) -> str:
        if self.alter == 0:
            accidental = ""
        elif self.is_equal_tempered:
            symbol = "#" if self.alter > 0 else "b"
            accidental = symbol * abs(int(self.alter))
        else:
            accidental = f"({'+' if self.alter > 0 else ''}{self.alter})"
        return f"{self.step.value}{accidental}{self.octave}"
