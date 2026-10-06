"""Cue, grace and unpitched notes, and the duration/type consistency check."""

from fractions import Fraction
from pathlib import Path

import pytest

from barbershop_tracks.core.musicxml import ParseResult
from barbershop_tracks.core.musicxml.duration_type import TYPE_QUARTERS, notated_quarters
from barbershop_tracks.models import Part, Severity
from xml_builders import attributes, measure, note, parse_text, quarters, score

pytestmark = pytest.mark.usefixtures("no_network")

FOUR = quarters(("C", 4), ("D", 4), ("E", 4), ("F", 4))
UNPITCHED = (
    "<note><unpitched><display-step>E</display-step><display-octave>4</display-octave>"
    "</unpitched><duration>2</duration><voice>1</voice></note>"
)


def _parse(tmp_path: Path, *parts: str) -> ParseResult:
    return parse_text(tmp_path, score(*parts))


def _line(result: ParseResult, line_id: str = "P1/s1/v1") -> Part:
    assert result.song is not None
    return next(p for p in result.song.parts if p.part_id == line_id)


def _issue(result: ParseResult, code: str):  # type: ignore[no-untyped-def]
    return next(i for i in result.issues if i.code == code)


# --- cue notes ------------------------------------------------------------------------


def test_cue_note_advances_the_timeline_but_is_not_a_singer_event(tmp_path: Path) -> None:
    body = quarters(("C", 4)) + note("G", 4, 2, extra="<cue/>") + quarters(("D", 4), ("E", 4))
    result = _parse(tmp_path, measure(1, body, attrs=attributes()))
    assert [e.start for e in _line(result).events] == [0, 2, 3]  # the cue held beat 2
    assert [e.midi_note for e in _line(result).events] == [60, 62, 64]


def test_cue_note_is_a_warning_with_line_measure_and_beat(tmp_path: Path) -> None:
    body = quarters(("C", 4)) + note("G", 4, 2, extra="<cue/>") + quarters(("D", 4))
    issue = _issue(_parse(tmp_path, measure(1, body, attrs=attributes())), "CUE_NOTE_SKIPPED")
    assert issue.severity is Severity.WARNING
    assert (issue.part_id, issue.measure, issue.beat) == ("P1/s1/v1", 1, 2)


def test_cue_notes_alone_do_not_block_generation(tmp_path: Path) -> None:
    body = note("G", 4, 2, extra="<cue/>") + quarters(("D", 4), ("E", 4), ("F", 4))
    assert not _parse(tmp_path, measure(1, body, attrs=attributes())).issues.has_errors


def test_cue_chord_note_does_not_advance(tmp_path: Path) -> None:
    body = (
        note("C", 4, 2)
        + note("G", 4, 2, extra="<chord/><cue/>")
        + quarters(("D", 4), ("E", 4), ("F", 4))
    )
    result = _parse(tmp_path, measure(1, body, attrs=attributes()))
    assert [e.start for e in _line(result).events] == [0, 1, 2, 3]
    assert "CUE_NOTE_SKIPPED" in [i.code for i in result.issues]


def test_cue_note_with_unreadable_voice_falls_back_to_the_part(tmp_path: Path) -> None:
    body = note("G", 4, 2, voice=None, extra="<cue/>") + quarters(("D", 4), ("E", 4), ("F", 4))
    result = _parse(tmp_path, measure(1, body, attrs=attributes()))
    issue = _issue(result, "CUE_NOTE_SKIPPED")
    assert issue.part_id == "P1"  # no line could be determined, so the part is the best we have
    assert "VOICE_MISSING" not in [i.code for i in result.issues]  # it is not a singer note


def test_cue_note_contributes_to_the_measure_length(tmp_path: Path) -> None:
    m1 = measure(1, note("G", 4, 8, extra="<cue/>"), attrs=attributes())
    m2 = measure(2, quarters(("C", 4), ("D", 4), ("E", 4), ("F", 4)))
    result = _parse(tmp_path, m1 + m2)
    assert _line(result).events[0].start == 4  # measure 2 begins after the cue measure
    assert [i.code for i in result.issues] == ["CUE_NOTE_SKIPPED"]  # no spurious incompleteness


# --- grace notes ----------------------------------------------------------------------


def _grace(voice: str | None = "1") -> str:
    voice_xml = f"<voice>{voice}</voice>" if voice is not None else ""
    return f"<note><grace/><pitch><step>B</step><octave>3</octave></pitch>{voice_xml}</note>"


def test_grace_note_is_an_error_and_takes_no_time(tmp_path: Path) -> None:
    result = _parse(tmp_path, measure(1, _grace() + FOUR, attrs=attributes()))
    issue = _issue(result, "UNSUPPORTED_GRACE_NOTE")
    assert issue.severity is Severity.ERROR
    assert [e.start for e in _line(result).events] == [0, 1, 2, 3]
    assert result.issues.has_errors


def test_grace_note_location(tmp_path: Path) -> None:
    body = quarters(("C", 4), ("D", 4)) + _grace() + quarters(("E", 4), ("F", 4))
    issue = _issue(_parse(tmp_path, measure(3, body, attrs=attributes())), "UNSUPPORTED_GRACE_NOTE")
    assert (issue.part_id, issue.measure, issue.beat) == ("P1/s1/v1", 3, 3)


def test_grace_note_without_a_voice_is_located_at_the_part(tmp_path: Path) -> None:
    result = _parse(tmp_path, measure(1, _grace(None) + FOUR, attrs=attributes()))
    assert _issue(result, "UNSUPPORTED_GRACE_NOTE").part_id == "P1"


def test_grace_that_is_also_a_cue_is_a_grace_note(tmp_path: Path) -> None:
    grace_cue = (
        "<note><grace/><cue/><pitch><step>B</step><octave>3</octave></pitch><voice>1</voice></note>"
    )
    result = _parse(tmp_path, measure(1, grace_cue + FOUR, attrs=attributes()))
    codes = [i.code for i in result.issues]
    assert "UNSUPPORTED_GRACE_NOTE" in codes
    assert "CUE_NOTE_SKIPPED" not in codes


# --- unpitched notes ------------------------------------------------------------------


def test_unpitched_note_is_an_error_but_advances_time(tmp_path: Path) -> None:
    body = UNPITCHED + quarters(("C", 4), ("D", 4))
    result = _parse(tmp_path, measure(1, body, attrs=attributes()))
    issue = _issue(result, "UNSUPPORTED_UNPITCHED_NOTE")
    assert issue.severity is Severity.ERROR
    assert (issue.part_id, issue.measure, issue.beat) == ("P1/s1/v1", 1, 1)
    assert [e.start for e in _line(result).events] == [1, 2]
    assert result.issues.has_errors


def test_the_temporary_note_kind_code_is_gone(tmp_path: Path) -> None:
    body = _grace() + UNPITCHED + note("G", 4, 2, extra="<cue/>") + FOUR
    codes = {i.code for i in _parse(tmp_path, measure(1, body, attrs=attributes())).issues}
    assert "NOTE_KIND_NOT_SUPPORTED_YET" not in codes
    assert {"UNSUPPORTED_GRACE_NOTE", "UNSUPPORTED_UNPITCHED_NOTE", "CUE_NOTE_SKIPPED"} <= codes


# --- duration / type consistency -------------------------------------------------------


def _typed(step: str, duration: int, type_name: str, *, dots: int = 0, tm: str = "") -> str:
    dot_xml = "<dot/>" * dots
    return note(step, 4, duration, type_xml=f"<type>{type_name}</type>{dot_xml}{tm}")


@pytest.mark.parametrize(
    ("type_name", "dots", "duration"),
    [
        ("quarter", 0, 2),
        ("half", 0, 4),
        ("eighth", 0, 1),
        ("quarter", 1, 3),  # dotted quarter = 3/2 quarter = 3 divisions
        ("half", 1, 6),
    ],
)
def test_consistent_types_give_no_warning(
    tmp_path: Path, type_name: str, dots: int, duration: int
) -> None:
    body = _typed("C", duration, type_name, dots=dots)
    filler = note("D", 4, 8 - duration, voice="1")
    assert "DURATION_TYPE_MISMATCH" not in [
        i.code for i in _parse(tmp_path, measure(1, body + filler, attrs=attributes())).issues
    ]


def test_tuplet_ratio_is_part_of_the_expected_duration(tmp_path: Path) -> None:
    tm = (
        "<time-modification><actual-notes>3</actual-notes>"
        "<normal-notes>2</normal-notes></time-modification>"
    )
    triplets = "".join(_typed(s, 1, "eighth", tm=tm) for s in "CDE")
    body = triplets + _typed("F", 3, "quarter") + _typed("G", 6, "half")
    result = _parse(tmp_path, measure(1, body, attrs=attributes(divisions="3")))
    assert "DURATION_TYPE_MISMATCH" not in [i.code for i in result.issues]


def test_mismatch_is_a_warning_and_the_duration_wins(tmp_path: Path) -> None:
    # <type> says quarter, but <duration> 4 at divisions 2 is a half note's worth of time.
    body = _typed("C", 4, "quarter") + quarters(("D", 4), ("E", 4))
    result = _parse(tmp_path, measure(1, body, attrs=attributes()))
    issue = _issue(result, "DURATION_TYPE_MISMATCH")
    assert issue.severity is Severity.WARNING
    assert (issue.part_id, issue.measure, issue.beat) == ("P1/s1/v1", 1, 1)
    first = _line(result).events[0]
    assert first.duration == 2  # <duration> 4 at divisions 2: NOT changed to the notated quarter
    assert not result.issues.has_errors or "DURATION_TYPE_MISMATCH" not in {
        i.code for i in result.issues.errors
    }


def test_missing_type_is_permitted_and_silent(tmp_path: Path) -> None:
    result = _parse(tmp_path, measure(1, FOUR, attrs=attributes()))
    assert not result.issues


def test_whole_measure_rest_is_excluded(tmp_path: Path) -> None:
    body = (
        '<note><rest measure="yes"/><duration>8</duration><voice>1</voice><type>whole</type></note>'
    )
    assert not _parse(tmp_path, measure(1, body, attrs=attributes())).issues


def test_normal_type_makes_the_comparison_ambiguous_so_it_is_skipped(tmp_path: Path) -> None:
    tm = (
        "<time-modification><actual-notes>3</actual-notes><normal-notes>2</normal-notes>"
        "<normal-type>16th</normal-type></time-modification>"
    )
    body = _typed("C", 1, "eighth", tm=tm) + _typed("D", 4, "half")
    assert "DURATION_TYPE_MISMATCH" not in [
        i.code for i in _parse(tmp_path, measure(1, body, attrs=attributes())).issues
    ]


@pytest.mark.parametrize(
    "tm",
    [
        "<time-modification><actual-notes>x</actual-notes>"
        "<normal-notes>2</normal-notes></time-modification>",
        "<time-modification><actual-notes>0</actual-notes>"
        "<normal-notes>2</normal-notes></time-modification>",
        "<time-modification><normal-notes>2</normal-notes></time-modification>",
    ],
)
def test_incomplete_time_modification_skips_the_check(tmp_path: Path, tm: str) -> None:
    body = _typed("C", 3, "eighth", tm=tm) + note("D", 4, 5)
    assert "DURATION_TYPE_MISMATCH" not in [
        i.code for i in _parse(tmp_path, measure(1, body, attrs=attributes())).issues
    ]


def test_unknown_type_is_not_checked(tmp_path: Path) -> None:
    body = note("C", 4, 8, type_xml="<type>gigantic</type>")
    assert not _parse(tmp_path, measure(1, body, attrs=attributes())).issues


# --- the type table and the pure helper -----------------------------------------------


def test_type_table_is_exact() -> None:
    assert TYPE_QUARTERS["quarter"] == 1
    assert TYPE_QUARTERS["whole"] == 4
    assert TYPE_QUARTERS["breve"] == 8
    assert TYPE_QUARTERS["eighth"] == Fraction(1, 2)
    assert TYPE_QUARTERS["1024th"] == Fraction(1, 256)
    assert len(TYPE_QUARTERS) == 14


def test_notated_quarters_for_double_dots_and_tuplets() -> None:
    import xml.etree.ElementTree as ET

    double_dotted = ET.fromstring("<note><type>eighth</type><dot/><dot/></note>")
    assert notated_quarters(double_dotted) == Fraction(7, 8)
    triplet = ET.fromstring(
        "<note><type>eighth</type><time-modification><actual-notes>3</actual-notes>"
        "<normal-notes>2</normal-notes></time-modification></note>"
    )
    assert notated_quarters(triplet) == Fraction(1, 3)
    assert notated_quarters(ET.fromstring("<note/>")) is None
