"""The musical transformation between a written (source) pitch and its sounding pitch."""

from dataclasses import dataclass

from barbershop_tracks.models.pitch import Pitch, Step
from barbershop_tracks.models.timing import require_int

_STEPS = tuple(Step)  # C, D, E, F, G, A, B in definition order
_STEPS_PER_OCTAVE = 7
_SEMITONES_PER_OCTAVE = 12


def _natural_midi(step: Step, octave: int) -> int:
    return _SEMITONES_PER_OCTAVE * (octave + 1) + step.semitone


@dataclass(frozen=True, slots=True, kw_only=True)
class PitchTransform:
    """What must be added to a *written* pitch to obtain the *sounding* pitch.

    This is the musical concept of a transposing interval, expressed as:

    - ``diatonic``: scale steps (letter names) to move, excluding whole octaves;
    - ``chromatic``: semitones to move, excluding whole octaves;
    - ``octave_change``: whole octaves to move.

    Examples: identity is ``PitchTransform()``; a tenor part notated an octave above where
    it sounds is ``octave_change=-1``; a B-flat instrument is ``diatonic=-1, chromatic=-2``.

    The sounding pitch (including its spelling) is derived deterministically by ``apply``;
    nothing stores a second, independently editable pitch. ``diatonic`` is explicit
    because the spelling of the sounding pitch cannot be recovered from ``chromatic``
    alone, and spellings are never guessed.
    """

    diatonic: int = 0
    chromatic: int = 0
    octave_change: int = 0

    def __post_init__(self) -> None:
        require_int(self.diatonic, name="diatonic")
        require_int(self.chromatic, name="chromatic")
        require_int(self.octave_change, name="octave_change")
        if self.total_steps * self.total_semitones < 0:
            raise ValueError(
                "diatonic and chromatic components contradict each other (opposite directions)"
            )

    @property
    def total_steps(self) -> int:
        return self.diatonic + _STEPS_PER_OCTAVE * self.octave_change

    @property
    def total_semitones(self) -> int:
        return self.chromatic + _SEMITONES_PER_OCTAVE * self.octave_change

    @property
    def is_identity(self) -> bool:
        return self.total_steps == 0 and self.total_semitones == 0

    def apply(self, written: Pitch) -> Pitch:
        """Return the sounding pitch for ``written``.

        The new letter and octave come from the diatonic motion; the alteration is then
        set so the pitch moves by exactly ``total_semitones``. Spelling is therefore
        preserved wherever the interval allows (a pure octave shift never changes the
        accidental), and fractional alterations stay fractional. Raises ``ValueError`` if
        the result cannot be spelled (alteration beyond a double sharp/flat) or falls
        outside the MIDI range.
        """
        index = _STEPS.index(written.step) + self.total_steps
        step = _STEPS[index % _STEPS_PER_OCTAVE]
        octave = written.octave + index // _STEPS_PER_OCTAVE
        natural_motion = _natural_midi(step, octave) - _natural_midi(written.step, written.octave)
        alter = written.alter + self.total_semitones - natural_motion
        return Pitch(step, octave, alter)


IDENTITY_TRANSFORM = PitchTransform()
