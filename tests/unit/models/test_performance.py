from fractions import Fraction

import pytest

from barbershop_tracks.models import Lyric, Note, PerformanceNote, Pitch, PitchTransform, Step

F = Fraction
ONE = F(1)
MIDDLE_C = Pitch(Step.C, 4)


def note(start: int, pitch: Pitch | None = MIDDLE_C, duration: F = ONE, lyric: str = "") -> Note:
    return Note(
        start=F(start),
        duration=duration,
        measure=1,
        beat=F(1) + start,
        written_pitch=pitch,
        lyrics=(Lyric(text=lyric),) if lyric else (),
    )


def test_single_note() -> None:
    source = note(2, lyric="la")
    performed = PerformanceNote(source=(source,))
    assert performed.start == 2
    assert performed.duration == 1
    assert performed.end == 3
    assert performed.pitch == Pitch(Step.C, 4)
    assert performed.lyrics == source.lyrics
    assert performed.measure == 1
    assert performed.beat == 3
    assert not performed.is_tied_group


def test_rest() -> None:
    performed = PerformanceNote(source=(note(0, None),))
    assert performed.is_rest
    assert performed.pitch is None


def test_tied_group_derives_everything_from_the_sources() -> None:
    a, b = note(0, lyric="la", duration=F(1, 3)), note(0, duration=F(2, 3))
    b = Note(
        start=F(1, 3), duration=F(2, 3), measure=1, beat=F(4, 3), written_pitch=Pitch(Step.C, 4)
    )
    performed = PerformanceNote(source=(a, b))
    assert performed.start == 0
    assert performed.duration == 1
    assert performed.end == 1
    assert performed.lyrics == a.lyrics  # the continuation makes no new attack


def test_enharmonic_group_keeps_the_first_spelling() -> None:
    a = note(0, Pitch(Step.C, 4, F(1)))
    b = note(1, Pitch(Step.D, 4, F(-1)))
    performed = PerformanceNote(source=(a, b))
    assert str(performed.pitch) == "C#4"
    assert [str(s.written_pitch) for s in performed.source] == ["C#4", "Db4"]


def test_sounding_pitch_uses_the_transform() -> None:
    a = Note(
        start=F(0),
        duration=F(1),
        measure=1,
        beat=F(1),
        written_pitch=Pitch(Step.C, 5),
        transform=PitchTransform(octave_change=-1),
    )
    assert PerformanceNote(source=(a,)).pitch == Pitch(Step.C, 4)


def test_empty_source_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one"):
        PerformanceNote(source=())


def test_non_note_source_is_rejected() -> None:
    with pytest.raises(TypeError, match="Note"):
        PerformanceNote(source=("x",))  # type: ignore[arg-type]


def test_group_with_a_gap_is_rejected() -> None:
    with pytest.raises(ValueError, match="back to back"):
        PerformanceNote(source=(note(0), note(2)))


def test_group_with_different_sounding_pitches_is_rejected() -> None:
    with pytest.raises(ValueError, match="same sounding pitch"):
        PerformanceNote(source=(note(0), note(1, Pitch(Step.D, 4))))


def test_group_with_a_rest_is_rejected() -> None:
    with pytest.raises(ValueError, match="rest"):
        PerformanceNote(source=(note(0), note(1, None)))


def test_list_source_is_stored_as_a_tuple() -> None:
    performed = PerformanceNote(source=[note(0)])  # type: ignore[arg-type]
    assert isinstance(performed.source, tuple)


def test_performance_note_is_immutable() -> None:
    performed = PerformanceNote(source=(note(0),))
    with pytest.raises(AttributeError):
        performed.source = ()  # type: ignore[misc]
