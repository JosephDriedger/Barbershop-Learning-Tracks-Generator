from dataclasses import fields
from fractions import Fraction

import pytest

from barbershop_tracks.models import IDENTITY_TRANSFORM, Note, Pitch, PitchTransform, Step

SHARP = Fraction(1)
FLAT = Fraction(-1)
OCTAVE_DOWN = PitchTransform(octave_change=-1)
OCTAVE_UP = PitchTransform(octave_change=1)


def _note(written: Pitch, transform: PitchTransform = IDENTITY_TRANSFORM) -> Note:
    return Note(
        start=Fraction(0),
        duration=Fraction(1),
        measure=1,
        beat=Fraction(1),
        written_pitch=written,
        transform=transform,
    )


# 1. ordinary C4 with identity transformation


def test_identity_transform_leaves_c4_unchanged() -> None:
    c4 = Pitch(Step.C, 4)
    assert IDENTITY_TRANSFORM.is_identity
    assert PitchTransform().is_identity
    assert IDENTITY_TRANSFORM.apply(c4) == c4
    note = _note(c4)
    assert note.written_pitch == c4
    assert note.sounding_pitch == c4
    assert note.midi_note == 60
    assert note.transform.is_identity


def test_note_defaults_to_identity_transform() -> None:
    assert _note(Pitch(Step.G, 3)).transform == IDENTITY_TRANSFORM


# 2. C#4 vs Db4 spelling preservation


def test_enharmonic_spellings_stay_distinct_through_identity() -> None:
    c_sharp = _note(Pitch(Step.C, 4, SHARP))
    d_flat = _note(Pitch(Step.D, 4, FLAT))
    assert c_sharp.sounding_pitch != d_flat.sounding_pitch
    assert str(c_sharp.sounding_pitch) == "C#4"
    assert str(d_flat.sounding_pitch) == "Db4"
    assert c_sharp.midi_note == d_flat.midi_note == 61


def test_enharmonic_spellings_stay_distinct_through_octave_shift() -> None:
    c_sharp = _note(Pitch(Step.C, 4, SHARP), OCTAVE_DOWN)
    d_flat = _note(Pitch(Step.D, 4, FLAT), OCTAVE_DOWN)
    assert str(c_sharp.sounding_pitch) == "C#3"
    assert str(d_flat.sounding_pitch) == "Db3"
    assert c_sharp.midi_note == d_flat.midi_note == 49


# 3. octave-down notation resolves to the expected sounding pitch


def test_octave_down_transform_for_tenor_notation() -> None:
    note = _note(Pitch(Step.C, 5), OCTAVE_DOWN)
    assert note.written_pitch == Pitch(Step.C, 5)  # as notated
    assert note.sounding_pitch == Pitch(Step.C, 4)
    assert note.midi_note == 60


# 4. octave-up transformation


def test_octave_up_transform() -> None:
    note = _note(Pitch(Step.C, 4), OCTAVE_UP)
    assert note.written_pitch == Pitch(Step.C, 4)
    assert note.sounding_pitch == Pitch(Step.C, 5)
    assert note.midi_note == 72


# 5. B# spelling preserved across an octave boundary


def test_b_sharp_keeps_its_written_octave_and_spelling() -> None:
    b_sharp = Pitch(Step.B, 3, SHARP)
    note = _note(b_sharp)
    assert note.sounding_pitch == b_sharp
    assert note.sounding_pitch is not None
    assert note.sounding_pitch.octave == 3
    assert note.midi_note == 60  # sounds as middle C, still spelled B#3


def test_b_sharp_under_octave_shifts() -> None:
    b_sharp = Pitch(Step.B, 3, SHARP)
    up = _note(b_sharp, OCTAVE_UP)
    down = _note(b_sharp, OCTAVE_DOWN)
    assert str(up.sounding_pitch) == "B#4"
    assert up.midi_note == 72
    assert str(down.sounding_pitch) == "B#2"
    assert down.midi_note == 48


def test_c_flat_keeps_its_octave_across_the_boundary() -> None:
    c_flat = _note(Pitch(Step.C, 4, FLAT))
    assert str(c_flat.sounding_pitch) == "Cb4"
    assert c_flat.midi_note == 59


# 6. accidental spelling remains unchanged after transformation where appropriate


@pytest.mark.parametrize("transform", [OCTAVE_UP, OCTAVE_DOWN, PitchTransform(octave_change=2)])
@pytest.mark.parametrize(
    "written",
    [
        Pitch(Step.F, 4, SHARP),
        Pitch(Step.B, 4, FLAT),
        Pitch(Step.E, 4, Fraction(2)),
        Pitch(Step.G, 4, Fraction(-2)),
    ],
)
def test_octave_shifts_never_change_step_or_accidental(
    written: Pitch, transform: PitchTransform
) -> None:
    sounding = transform.apply(written)
    assert sounding.step is written.step
    assert sounding.alter == written.alter
    assert sounding.octave == written.octave + transform.octave_change


def test_transposing_interval_respells_by_interval_not_by_guess() -> None:
    # B-flat instrument: sounding is a major second (diatonic -1, chromatic -2) below written.
    b_flat_instrument = PitchTransform(diatonic=-1, chromatic=-2)
    assert str(b_flat_instrument.apply(Pitch(Step.C, 5))) == "Bb4"
    assert str(b_flat_instrument.apply(Pitch(Step.C, 5, SHARP))) == "B4"
    assert str(b_flat_instrument.apply(Pitch(Step.D, 5, FLAT))) == "Cb5"
    # E-flat instrument (e.g. alto sax): a major sixth down, written C -> sounding Eb.
    e_flat_instrument = PitchTransform(diatonic=-5, chromatic=-9)
    assert str(e_flat_instrument.apply(Pitch(Step.C, 5))) == "Eb4"


def test_transform_with_octave_component_combines_with_interval() -> None:
    # Tenor saxophone: major ninth down = diatonic -1, chromatic -2, octave -1.
    tenor_sax = PitchTransform(diatonic=-1, chromatic=-2, octave_change=-1)
    assert str(tenor_sax.apply(Pitch(Step.C, 5))) == "Bb3"
    assert tenor_sax.total_steps == -8
    assert tenor_sax.total_semitones == -14


# 7. transformation and sounding pitch cannot contradict one another


def test_sounding_pitch_cannot_be_supplied_independently() -> None:
    with pytest.raises(TypeError, match="sounding_pitch"):
        Note(  # type: ignore[call-arg]
            start=Fraction(0),
            duration=Fraction(1),
            measure=1,
            beat=Fraction(1),
            written_pitch=Pitch(Step.C, 5),
            transform=OCTAVE_DOWN,
            sounding_pitch=Pitch(Step.C, 5),
        )


def test_note_has_no_second_pitch_field() -> None:
    assert {f.name for f in fields(Note) if "pitch" in f.name} == {"written_pitch"}


def test_sounding_pitch_is_derived_deterministically() -> None:
    note = _note(Pitch(Step.D, 5, FLAT), OCTAVE_DOWN)
    assert note.sounding_pitch == note.sounding_pitch
    assert note.sounding_pitch == OCTAVE_DOWN.apply(Pitch(Step.D, 5, FLAT))


def test_note_is_immutable_so_pitch_and_transform_cannot_drift() -> None:
    note = _note(Pitch(Step.C, 5), OCTAVE_DOWN)
    with pytest.raises(AttributeError):
        note.transform = IDENTITY_TRANSFORM  # type: ignore[misc]
    with pytest.raises(AttributeError):
        note.written_pitch = Pitch(Step.C, 3)  # type: ignore[misc]


@pytest.mark.parametrize(
    ("diatonic", "chromatic"),
    [(1, -2), (-1, 2), (2, -1), (-3, 5)],
)
def test_transform_components_in_opposite_directions_are_rejected(
    diatonic: int, chromatic: int
) -> None:
    with pytest.raises(ValueError, match="contradict"):
        PitchTransform(diatonic=diatonic, chromatic=chromatic)


def test_octave_component_contradicting_the_interval_is_rejected() -> None:
    with pytest.raises(ValueError, match="contradict"):
        PitchTransform(diatonic=-1, chromatic=14, octave_change=-1)


def test_unspellable_result_is_rejected_when_the_note_is_built() -> None:
    # C## written, raised a chromatic semitone with no letter change would need a triple sharp.
    with pytest.raises(ValueError, match="alter"):
        _note(Pitch(Step.C, 4, Fraction(2)), PitchTransform(chromatic=1))


def test_result_outside_midi_range_is_rejected_when_the_note_is_built() -> None:
    with pytest.raises(ValueError, match=r"octave|MIDI range"):
        _note(Pitch(Step.C, -1), OCTAVE_DOWN)
    with pytest.raises(ValueError, match=r"octave|MIDI range"):
        _note(Pitch(Step.G, 9), OCTAVE_UP)


def test_rest_cannot_carry_a_transform() -> None:
    with pytest.raises(ValueError, match="rest"):
        Note(
            start=Fraction(0),
            duration=Fraction(1),
            measure=1,
            beat=Fraction(1),
            transform=OCTAVE_DOWN,
        )


def test_transform_components_must_be_ints() -> None:
    with pytest.raises(TypeError, match="diatonic"):
        PitchTransform(diatonic=1.0)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="octave_change"):
        PitchTransform(octave_change=True)


# 8. fractional/microtonal alteration stays explicit


def test_microtonal_written_pitch_is_preserved_and_has_no_midi_note() -> None:
    quarter_flat = Pitch(Step.E, 4, Fraction(-1, 2))
    note = _note(quarter_flat)
    assert note.written_pitch == quarter_flat
    assert note.sounding_pitch == quarter_flat
    with pytest.raises(ValueError, match="microtonal"):
        _ = note.midi_note


def test_microtonal_alteration_survives_octave_shift_without_rounding() -> None:
    quarter_sharp = Pitch(Step.F, 4, Fraction(1, 2))
    note = _note(quarter_sharp, OCTAVE_DOWN)
    assert note.sounding_pitch == Pitch(Step.F, 3, Fraction(1, 2))
    assert note.sounding_pitch is not None
    assert not note.sounding_pitch.is_equal_tempered
    with pytest.raises(ValueError, match="microtonal"):
        _ = note.midi_note


def test_microtonal_alteration_survives_interval_transposition() -> None:
    quarter_flat = Pitch(Step.E, 5, Fraction(-1, 2))
    sounding = PitchTransform(diatonic=-1, chromatic=-2).apply(quarter_flat)
    assert sounding == Pitch(Step.D, 5, Fraction(-1, 2))
    assert str(sounding) == "D(-1/2)5"


def test_rest_has_no_midi_note() -> None:
    rest = Note.rest(start=Fraction(0), duration=Fraction(1), measure=1, beat=Fraction(1))
    assert rest.midi_note is None
    assert rest.sounding_pitch is None
