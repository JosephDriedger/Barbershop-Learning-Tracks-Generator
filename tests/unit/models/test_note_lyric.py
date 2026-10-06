from fractions import Fraction

import pytest

from barbershop_tracks.models import Lyric, LyricSegment, Melisma, Note, Pitch, Step, Syllabic

C4 = Pitch(Step.C, 4)


def _sounding(**overrides: object) -> Note:
    values: dict[str, object] = {
        "start": Fraction(0),
        "duration": Fraction(1),
        "measure": 1,
        "beat": Fraction(1),
        "written_pitch": C4,
    }
    values.update(overrides)
    return Note(**values)  # type: ignore[arg-type]


# --- rests and invariants -------------------------------------------------------------


def test_rest_has_no_pitch() -> None:
    rest = Note.rest(start=Fraction(1), duration=Fraction(1, 2), measure=1, beat=Fraction(2))
    assert rest.is_rest
    assert rest.written_pitch is None
    assert rest.sounding_pitch is None
    assert rest.midi_note is None
    assert rest.end == Fraction(3, 2)


def test_sounding_note_is_not_a_rest() -> None:
    assert not _sounding().is_rest


def test_rest_cannot_have_lyrics() -> None:
    with pytest.raises(ValueError, match="rest"):
        Note(
            start=Fraction(0),
            duration=Fraction(1),
            measure=1,
            beat=Fraction(1),
            lyrics=(Lyric(text="la"),),
        )


@pytest.mark.parametrize("tie", ["tied_to_next", "tied_from_previous"])
def test_rest_cannot_be_tied(tie: str) -> None:
    with pytest.raises(ValueError, match="rest"):
        Note(start=Fraction(0), duration=Fraction(1), measure=1, beat=Fraction(1), **{tie: True})  # type: ignore[arg-type]


def test_rest_factory_cannot_smuggle_a_pitch() -> None:
    with pytest.raises(TypeError):
        Note.rest(  # type: ignore[call-arg]
            start=Fraction(0), duration=Fraction(1), measure=1, beat=Fraction(1), written_pitch=C4
        )


@pytest.mark.parametrize("duration", [Fraction(0), Fraction(-1), Fraction(-1, 3)])
def test_non_positive_duration_is_rejected(duration: Fraction) -> None:
    with pytest.raises(ValueError, match="duration must be positive"):
        _sounding(duration=duration)


def test_negative_start_is_rejected() -> None:
    with pytest.raises(ValueError, match="start"):
        _sounding(start=Fraction(-1, 4))


def test_float_duration_is_rejected() -> None:
    with pytest.raises(TypeError, match="Fraction or int"):
        _sounding(duration=0.5)


@pytest.mark.parametrize(("measure", "beat"), [(-1, Fraction(1)), (1, Fraction(1, 2))])
def test_invalid_position_in_measure_is_rejected(measure: int, beat: Fraction) -> None:
    with pytest.raises(ValueError, match=r"measure|beat"):
        _sounding(measure=measure, beat=beat)


def test_pickup_measure_zero_is_allowed() -> None:
    assert _sounding(measure=0, beat=Fraction(4)).measure == 0


def test_beat_can_be_fractional() -> None:
    assert _sounding(beat=Fraction(5, 2)).beat == Fraction(5, 2)


def test_tie_information_is_stored() -> None:
    note = _sounding(tied_to_next=True, tied_from_previous=True)
    assert note.tied_to_next
    assert note.tied_from_previous
    plain = _sounding()
    assert not plain.tied_to_next
    assert not plain.tied_from_previous


def test_note_is_immutable() -> None:
    note = _sounding()
    with pytest.raises(AttributeError):
        note.start = Fraction(1)  # type: ignore[misc]


def test_non_lyric_in_lyrics_is_rejected() -> None:
    with pytest.raises(TypeError, match="Lyric"):
        _sounding(lyrics=("la",))


# --- lyrics ---------------------------------------------------------------------------


def test_lyric_text_and_syllabic_are_preserved_exactly() -> None:
    lyric = Lyric(text="Beau", syllabic=Syllabic.BEGIN)
    assert lyric.text == "Beau"
    assert lyric.syllabic is Syllabic.BEGIN
    assert lyric.verse == "1"
    assert lyric.melisma is Melisma.NONE


def test_lyric_text_is_never_normalized() -> None:
    odd = "  Mm-  "
    assert Lyric(text=odd).text == odd


def test_all_syllabic_states_are_representable() -> None:
    assert {s.name for s in Syllabic} == {"SINGLE", "BEGIN", "MIDDLE", "END"}


def test_source_lyrics_keep_openutau_markers_as_plain_text() -> None:
    # The model never interprets or transforms OpenUtau conventions.
    for text in ("+", "+~", "-", "[l ih v]"):
        assert Lyric(text=text).text == text


def test_verse_numbers_are_preserved_per_lyric() -> None:
    note = _sounding(lyrics=(Lyric(text="Oh", verse="1"), Lyric(text="Ah", verse="2")))
    assert [lyric.verse for lyric in note.lyrics] == ["1", "2"]


def test_melisma_is_represented_with_extension_lyrics() -> None:
    start = Lyric(text="love", syllabic=Syllabic.SINGLE, melisma=Melisma.START)
    cont = Lyric.extension(Melisma.CONTINUE)
    stop = Lyric.extension(Melisma.STOP)
    assert start.melisma is Melisma.START
    assert not cont.has_text
    assert cont.syllabic is None
    assert stop.melisma is Melisma.STOP


def test_extension_lyric_must_be_continue_or_stop() -> None:
    with pytest.raises(ValueError, match="continuation"):
        Lyric.extension(Melisma.START)
    with pytest.raises(ValueError, match="continuation"):
        Lyric.extension(Melisma.NONE)


def test_text_requires_syllabic_and_empty_text_forbids_it() -> None:
    with pytest.raises(ValueError, match="syllabic"):
        Lyric(text="la", syllabic=None)
    with pytest.raises(ValueError, match="syllabic"):
        Lyric(text="", syllabic=Syllabic.SINGLE, melisma=Melisma.STOP)


def test_empty_verse_is_rejected() -> None:
    with pytest.raises(ValueError, match="verse"):
        Lyric(text="la", verse="")


def test_elision_is_representable_and_preserved() -> None:
    lyric = Lyric(
        text="the",
        elided=[LyricSegment(text="ir", syllabic=Syllabic.SINGLE, joiner="‿")],  # type: ignore[arg-type]
    )
    assert lyric.is_elided
    assert lyric.text == "the"
    assert lyric.full_text == "the‿ir"
    assert isinstance(lyric.elided, tuple)


def test_lyric_without_elision() -> None:
    lyric = Lyric(text="la")
    assert not lyric.is_elided
    assert lyric.full_text == "la"


def test_empty_elided_segment_is_rejected() -> None:
    with pytest.raises(ValueError, match="text"):
        LyricSegment(text="")


def test_source_lyric_is_independent_of_any_other_representation() -> None:
    lyric = Lyric(text="ti", syllabic=Syllabic.MIDDLE)
    note = _sounding(lyrics=(lyric,))
    assert note.lyrics[0] is lyric
    assert note.lyrics[0].text == "ti"
