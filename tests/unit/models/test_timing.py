from fractions import Fraction

import pytest

from barbershop_tracks.models import Note, Pitch, Step, TempoChange, TimeSignature
from barbershop_tracks.models.timing import to_fraction


def _note(start: Fraction, duration: Fraction) -> Note:
    return Note(
        start=start,
        duration=duration,
        measure=1,
        beat=Fraction(1),
        written_pitch=Pitch(Step.C, 4),
    )


def test_to_fraction_accepts_fraction_and_int() -> None:
    assert to_fraction(Fraction(1, 3)) == Fraction(1, 3)
    assert to_fraction(2) == Fraction(2)
    assert isinstance(to_fraction(2), Fraction)


@pytest.mark.parametrize("bad", [0.5, 1.0, True, "1", None])
def test_to_fraction_rejects_floats_and_other_types(bad: object) -> None:
    with pytest.raises(TypeError, match="Fraction or int"):
        to_fraction(bad)


def test_exact_fraction_timing_has_no_drift() -> None:
    eighth = Fraction(1, 2)
    notes = [_note(i * eighth, eighth) for i in range(8)]
    assert notes[-1].end == Fraction(4)
    assert sum((n.duration for n in notes), Fraction(0)) == Fraction(4)


def test_note_values_in_quarter_note_units() -> None:
    assert _note(Fraction(0), Fraction(1)).duration == 1  # quarter
    assert _note(Fraction(0), Fraction(1, 2)).duration == Fraction(1, 2)  # eighth
    assert _note(Fraction(0), Fraction(2)).duration == 2  # half


def test_triplet_eighths_sum_exactly_to_a_quarter() -> None:
    third = Fraction(1, 3)
    triplet = [_note(i * third, third) for i in range(3)]
    assert triplet[-1].end == Fraction(1)
    assert sum((n.duration for n in triplet), Fraction(0)) == Fraction(1)


def test_triplet_beats_are_not_representable_as_floats() -> None:
    # Documents why floats are rejected: 3 x float(1/3) != 1 in some orderings.
    with pytest.raises(TypeError, match="Fraction or int"):
        _note(Fraction(0), 1 / 3)  # type: ignore[arg-type]


def test_integer_input_is_normalized_to_fraction() -> None:
    note = Note(start=0, duration=1, measure=1, beat=1, written_pitch=Pitch(Step.C, 4))  # type: ignore[arg-type]
    assert isinstance(note.start, Fraction)
    assert isinstance(note.duration, Fraction)
    assert isinstance(note.beat, Fraction)


def test_time_signature_measure_length() -> None:
    assert TimeSignature(position=Fraction(0), beats=4, beat_type=4).measure_length == 4
    assert TimeSignature(position=Fraction(0), beats=6, beat_type=8).measure_length == 3
    assert TimeSignature(position=Fraction(0), beats=3, beat_type=4).measure_length == 3
    assert TimeSignature(position=Fraction(0), beats=2, beat_type=2).measure_length == 4


@pytest.mark.parametrize(("beats", "beat_type"), [(0, 4), (4, 0), (4, 3), (-1, 4)])
def test_time_signature_rejects_invalid_values(beats: int, beat_type: int) -> None:
    with pytest.raises(ValueError, match="beat"):
        TimeSignature(position=Fraction(0), beats=beats, beat_type=beat_type)


def test_tempo_change_is_exact_and_validated() -> None:
    tempo = TempoChange(position=Fraction(0), bpm=Fraction(185, 2))
    assert tempo.bpm == Fraction(92.5)
    with pytest.raises(ValueError, match="bpm"):
        TempoChange(position=Fraction(0), bpm=Fraction(0))
    with pytest.raises(ValueError, match="position"):
        TempoChange(position=Fraction(-1), bpm=Fraction(60))
    with pytest.raises(TypeError, match="Fraction or int"):
        TempoChange(position=Fraction(0), bpm=92.5)  # type: ignore[arg-type]
