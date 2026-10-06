from fractions import Fraction
from pathlib import Path

import pytest

from barbershop_tracks.core.musicxml import ParseResult
from barbershop_tracks.models import IDENTITY_TRANSFORM, Note, Part, PitchTransform, Severity
from xml_builders import (
    attributes,
    measure,
    note,
    parse_text,
    quarters,
    score,
    transpose_xml,
)

pytestmark = pytest.mark.usefixtures("no_network")


def _parse(tmp_path: Path, *parts: str) -> ParseResult:
    return parse_text(tmp_path, score(*parts))


def _notes(result: ParseResult, line_id: str = "P1/s1/v1") -> tuple[Note, ...]:
    assert result.song is not None
    part: Part = next(p for p in result.song.parts if p.part_id == line_id)
    return part.events


def _codes(result: ParseResult) -> list[str]:
    return [issue.code for issue in result.issues]


def _one_measure(attrs: str, *notes: str) -> str:
    return measure(1, "".join(notes), attrs=attrs)


# --- written pitch --------------------------------------------------------------------


def test_pitch_is_read_exactly_as_written(tmp_path: Path) -> None:
    body = (
        quarters(("C", 4))
        + note("C", 4, 2, alter="1")
        + note("D", 4, 2, alter="-1")
        + quarters(("B", 3))
    )
    events = _notes(_parse(tmp_path, measure(1, body, attrs=attributes())))
    assert [str(e.written_pitch) for e in events] == ["C4", "C#4", "Db4", "B3"]
    assert events[1].midi_note == events[2].midi_note == 61  # same sound, distinct spelling
    assert events[1].written_pitch != events[2].written_pitch


def test_enharmonic_b_sharp_keeps_its_octave(tmp_path: Path) -> None:
    body = note("B", 3, 2, alter="1") + note("C", 4, 2, alter="-1")
    events = _notes(_parse(tmp_path, measure(1, body, attrs=attributes())))
    assert [str(e.written_pitch) for e in events] == ["B#3", "Cb4"]
    assert [e.midi_note for e in events] == [60, 59]


def test_microtonal_alter_is_exact_and_has_no_midi_note(tmp_path: Path) -> None:
    body = note("E", 4, 2, alter="-0.5")
    events = _notes(_parse(tmp_path, measure(1, body, attrs=attributes())))
    assert events[0].written_pitch is not None
    assert events[0].written_pitch.alter == Fraction(-1, 2)
    with pytest.raises(ValueError, match="microtonal"):
        _ = events[0].midi_note


@pytest.mark.parametrize("alter", ["1/2", "1e0", "abc", ""])
def test_invalid_alter_is_an_error(tmp_path: Path, alter: str) -> None:
    body = (
        note("E", 4, 2, alter=alter)
        if alter
        else (
            "<note><pitch><step>E</step><alter></alter><octave>4</octave></pitch>"
            "<duration>2</duration><voice>1</voice></note>"
        )
    )
    # An empty <alter/> is treated as absent; anything non-decimal is an error.
    result = _parse(tmp_path, measure(1, body, attrs=attributes()))
    assert ("PITCH_INVALID" in _codes(result)) == (alter != "")


@pytest.mark.parametrize("step", ["H", "c", ""])
def test_invalid_step_is_an_error(tmp_path: Path, step: str) -> None:
    body = (
        f"<note><pitch><step>{step}</step><octave>4</octave></pitch>"
        "<duration>2</duration><voice>1</voice></note>"
    )
    assert "PITCH_INVALID" in _codes(_parse(tmp_path, measure(1, body, attrs=attributes())))


def test_out_of_range_octave_is_an_error_not_a_crash(tmp_path: Path) -> None:
    result = _parse(tmp_path, measure(1, note("C", 12, 2), attrs=attributes()))
    issue = next(i for i in result.issues if i.code == "PITCH_OUT_OF_RANGE")
    assert issue.severity is Severity.ERROR
    assert issue.part_id == "P1/s1/v1"
    assert issue.measure == 1
    assert issue.beat == 1


def test_note_without_pitch_or_rest_is_an_error(tmp_path: Path) -> None:
    body = "<note><duration>2</duration><voice>1</voice></note>"
    assert "NOTE_WITHOUT_PITCH" in _codes(_parse(tmp_path, measure(1, body, attrs=attributes())))


def test_without_transpose_the_transform_is_the_identity(tmp_path: Path) -> None:
    events = _notes(_parse(tmp_path, measure(1, quarters(("C", 4)), attrs=attributes())))
    assert events[0].transform == IDENTITY_TRANSFORM
    assert events[0].sounding_pitch == events[0].written_pitch


# --- <transpose> ----------------------------------------------------------------------


def test_b_flat_instrument_transpose(tmp_path: Path) -> None:
    attrs = attributes(transpose=transpose_xml(diatonic=-1, chromatic="-2"))
    events = _notes(_parse(tmp_path, measure(1, quarters(("C", 5), ("D", 5)), attrs=attrs)))
    assert events[0].transform == PitchTransform(diatonic=-1, chromatic=-2)
    assert str(events[0].written_pitch) == "C5"  # preserved as written
    assert str(events[0].sounding_pitch) == "Bb4"
    assert [e.midi_note for e in events] == [70, 72]


def test_octave_change_transpose(tmp_path: Path) -> None:
    attrs = attributes(transpose=transpose_xml(chromatic="0", octave=-1))
    events = _notes(_parse(tmp_path, measure(1, quarters(("C", 4)), attrs=attrs)))
    assert events[0].transform == PitchTransform(octave_change=-1)
    assert events[0].midi_note == 48


def test_transpose_persists_into_later_measures(tmp_path: Path) -> None:
    m1 = measure(
        1,
        quarters(("C", 5), ("C", 5), ("C", 5), ("C", 5)),
        attrs=attributes(transpose=transpose_xml(diatonic=-1, chromatic="-2")),
    )
    m2 = measure(2, quarters(("C", 5), ("C", 5), ("C", 5), ("C", 5)))
    events = _notes(_parse(tmp_path, m1 + m2))
    assert {e.midi_note for e in events} == {70}


def test_new_transpose_replaces_the_old_one(tmp_path: Path) -> None:
    four = quarters(("C", 5), ("C", 5), ("C", 5), ("C", 5))
    m1 = measure(1, four, attrs=attributes(transpose=transpose_xml(diatonic=-1, chromatic="-2")))
    m2_attrs = f"<attributes>{transpose_xml(diatonic=-5, chromatic='-9')}</attributes>"
    m2 = measure(2, four, attrs=m2_attrs)
    events = _notes(_parse(tmp_path, m1 + m2))
    assert [e.midi_note for e in events[::4]] == [70, 63]  # Bb4 then Eb4


def test_zero_transpose_cancels_a_previous_one(tmp_path: Path) -> None:
    four = quarters(("C", 5), ("C", 5), ("C", 5), ("C", 5))
    m1 = measure(1, four, attrs=attributes(transpose=transpose_xml(diatonic=-1, chromatic="-2")))
    m2 = measure(2, four, attrs=f"<attributes>{transpose_xml(chromatic='0')}</attributes>")
    events = _notes(_parse(tmp_path, m1 + m2))
    assert [e.midi_note for e in events[::4]] == [70, 72]
    assert events[4].transform.is_identity


def test_numbered_transpose_applies_only_to_that_staff(tmp_path: Path) -> None:
    attrs = attributes(
        staves=2,
        clefs='<clef number="1"><sign>G</sign><line>2</line></clef>',
        transpose=transpose_xml(chromatic="0", octave=-1, number=1),
    )
    body = (
        note("C", 4, 8, staff=1, voice="1")
        + "<backup><duration>8</duration></backup>"
        + note("C", 4, 8, staff=2, voice="2")
    )
    result = _parse(tmp_path, measure(1, body, attrs=attrs))
    assert not result.issues
    assert _notes(result, "P1/s1/v1")[0].midi_note == 48
    assert _notes(result, "P1/s2/v2")[0].midi_note == 60


def test_unnumbered_transpose_applies_to_every_staff(tmp_path: Path) -> None:
    attrs = attributes(staves=2, transpose=transpose_xml(chromatic="0", octave=-1))
    body = (
        note("C", 4, 8, staff=1, voice="1")
        + "<backup><duration>8</duration></backup>"
        + note("C", 4, 8, staff=2, voice="2")
    )
    result = _parse(tmp_path, measure(1, body, attrs=attrs))
    assert _notes(result, "P1/s1/v1")[0].midi_note == 48
    assert _notes(result, "P1/s2/v2")[0].midi_note == 48


def test_unnumbered_transpose_replaces_staff_specific_ones(tmp_path: Path) -> None:
    four = note("C", 4, 8, staff=1, voice="1")
    m1 = measure(
        1,
        four,
        attrs=attributes(staves=2, transpose=transpose_xml(chromatic="0", octave=-1, number=1)),
    )
    m2 = measure(2, four, attrs=f"<attributes>{transpose_xml(chromatic='0')}</attributes>")
    events = _notes(_parse(tmp_path, m1 + m2))
    assert [e.midi_note for e in events] == [48, 60]


def test_missing_diatonic_with_nonzero_chromatic_is_not_spellable(tmp_path: Path) -> None:
    attrs = attributes(transpose=transpose_xml(chromatic="-2"))
    result = _parse(tmp_path, measure(1, quarters(("C", 5)), attrs=attrs))
    issue = next(i for i in result.issues if i.code == "TRANSPOSE_NOT_SPELLABLE")
    assert issue.severity is Severity.ERROR


def test_notes_under_an_unusable_transpose_are_left_out_not_guessed(tmp_path: Path) -> None:
    attrs = attributes(transpose=transpose_xml(chromatic="-2"))
    result = _parse(tmp_path, measure(1, quarters(("C", 5), ("D", 5)), attrs=attrs))
    assert result.song is not None
    assert result.song.parts == ()


@pytest.mark.parametrize(
    "transpose",
    [
        transpose_xml(diatonic=1, chromatic="-2"),  # opposite directions
        transpose_xml(diatonic=-1, chromatic="-2.5"),  # microtonal transposition
        "<transpose><diatonic>-1</diatonic></transpose>",  # no chromatic
        "<transpose><diatonic>x</diatonic><chromatic>-2</chromatic></transpose>",
        transpose_xml(chromatic="0", octave=0, number=0),  # invalid staff
    ],
)
def test_invalid_transpose_is_an_error(tmp_path: Path, transpose: str) -> None:
    result = _parse(tmp_path, measure(1, quarters(("C", 5)), attrs=attributes(transpose=transpose)))
    assert "TRANSPOSE_INVALID" in _codes(result)


def test_unspellable_result_is_reported_at_the_note(tmp_path: Path) -> None:
    attrs_ok = attributes(transpose=transpose_xml(diatonic=0, chromatic="1"))
    result = _parse(tmp_path, measure(1, note("C", 4, 2, alter="2"), attrs=attrs_ok))
    issue = next(i for i in result.issues if i.code == "TRANSPOSE_NOT_SPELLABLE")
    assert issue.part_id == "P1/s1/v1"
    assert issue.measure == 1
    assert issue.beat == 1


@pytest.mark.parametrize("double", ["<double/>", '<double above="yes"/>', '<double above="no"/>'])
def test_transpose_double_is_an_explicit_unsupported_error(tmp_path: Path, double: str) -> None:
    # MusicXML 4.0: <double> means the music is doubled an octave from what is written, a
    # second sounding note that PitchTransform cannot represent. It must never be ignored.
    transpose = f"<transpose><diatonic>-1</diatonic><chromatic>-2</chromatic>{double}</transpose>"
    result = _parse(tmp_path, measure(1, quarters(("C", 5)), attrs=attributes(transpose=transpose)))
    issue = next(i for i in result.issues if i.code == "TRANSPOSE_DOUBLE_UNSUPPORTED")
    assert issue.severity is Severity.ERROR
    assert result.issues.has_errors
    assert result.song is not None
    assert result.song.parts == ()  # no note is emitted under a transform we cannot honor


def test_transpose_without_double_is_unaffected(tmp_path: Path) -> None:
    attrs = attributes(transpose=transpose_xml(diatonic=-1, chromatic="-2"))
    result = _parse(tmp_path, measure(1, quarters(("C", 5)), attrs=attrs))
    assert "TRANSPOSE_DOUBLE_UNSUPPORTED" not in _codes(result)
    assert _notes(result)[0].midi_note == 70


def test_one_transform_object_describes_each_note(tmp_path: Path) -> None:
    attrs = attributes(transpose=transpose_xml(diatonic=-1, chromatic="-2"))
    events = _notes(_parse(tmp_path, measure(1, quarters(("C", 5), ("E", 5)), attrs=attrs)))
    assert len({e.transform for e in events}) == 1
