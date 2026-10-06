from fractions import Fraction

import pytest

from barbershop_tracks.models import Pitch, Step


def test_middle_c_is_midi_60() -> None:
    assert Pitch(Step.C, 4).midi_note == 60
    assert Pitch(Step.A, 4).midi_note == 69
    assert Pitch(Step.C, -1).midi_note == 0


def test_enharmonic_spellings_are_distinct_but_sound_alike() -> None:
    c_sharp = Pitch(Step.C, 4, Fraction(1))
    d_flat = Pitch(Step.D, 4, Fraction(-1))
    assert c_sharp != d_flat
    assert c_sharp.midi_note == d_flat.midi_note == 61
    assert c_sharp.sounds_like(d_flat)


def test_spelling_is_preserved() -> None:
    pitch = Pitch(Step.D, 4, Fraction(-1))
    assert pitch.step is Step.D
    assert pitch.alter == -1
    assert pitch.octave == 4
    assert str(pitch) == "Db4"
    assert str(Pitch(Step.C, 4, Fraction(1))) == "C#4"
    assert str(Pitch(Step.F, 3, Fraction(2))) == "F##3"
    assert str(Pitch(Step.B, 3, Fraction(-2))) == "Bbb3"
    assert str(Pitch(Step.E, 5)) == "E5"


def test_octave_boundary_spellings_keep_their_written_octave() -> None:
    b_sharp = Pitch(Step.B, 3, Fraction(1))
    c_flat = Pitch(Step.C, 4, Fraction(-1))
    assert b_sharp.midi_note == 60
    assert c_flat.midi_note == 59
    assert b_sharp.octave == 3
    assert c_flat.octave == 4


def test_microtonal_alter_is_representable_but_has_no_midi_note() -> None:
    quarter_flat = Pitch(Step.E, 4, Fraction(-1, 2))
    assert not quarter_flat.is_equal_tempered
    with pytest.raises(ValueError, match="microtonal"):
        _ = quarter_flat.midi_note


def test_integer_alter_is_normalized_to_fraction() -> None:
    pitch = Pitch(Step.C, 4, 1)  # type: ignore[arg-type]
    assert isinstance(pitch.alter, Fraction)


def test_float_alter_is_rejected() -> None:
    with pytest.raises(TypeError, match="Fraction or int"):
        Pitch(Step.C, 4, 1.0)  # type: ignore[arg-type]


@pytest.mark.parametrize("octave", [-2, 10])
def test_octave_out_of_range_is_rejected(octave: int) -> None:
    with pytest.raises(ValueError, match="octave"):
        Pitch(Step.C, octave)


def test_pitch_outside_midi_range_is_rejected() -> None:
    with pytest.raises(ValueError, match="MIDI range"):
        Pitch(Step.A, 9)  # 132
    with pytest.raises(ValueError, match="MIDI range"):
        Pitch(Step.C, -1, Fraction(-1))  # -1


def test_excessive_alter_is_rejected() -> None:
    with pytest.raises(ValueError, match="alter"):
        Pitch(Step.C, 4, Fraction(3))


def test_non_integer_octave_is_rejected() -> None:
    with pytest.raises(TypeError, match="octave"):
        Pitch(Step.C, 4.0)  # type: ignore[arg-type]
