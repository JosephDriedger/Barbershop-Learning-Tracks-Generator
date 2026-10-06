from fractions import Fraction
from pathlib import Path

import pytest

from barbershop_tracks.core.musicxml import ParseResult
from barbershop_tracks.models import Note, Part, Severity
from xml_builders import (
    attributes,
    backup,
    forward,
    measure,
    note,
    parse_text,
    quarters,
    rest,
    score,
)

pytestmark = pytest.mark.usefixtures("no_network")


def _parse(tmp_path: Path, *parts: str) -> ParseResult:
    return parse_text(tmp_path, score(*parts))


def _line(result: ParseResult, line_id: str) -> Part:
    assert result.song is not None
    return next(p for p in result.song.parts if p.part_id == line_id)


def _starts(part: Part) -> list[Fraction]:
    return [event.start for event in part.events]


def _codes(result: ParseResult) -> list[str]:
    return [issue.code for issue in result.issues]


# --- basic placement ------------------------------------------------------------------


def test_quarter_notes_get_exact_positions_and_beats(tmp_path: Path) -> None:
    body = measure(1, quarters(("C", 4), ("D", 4), ("E", 4), ("F", 4)), attrs=attributes())
    result = _parse(tmp_path, body)
    assert not result.issues
    line = _line(result, "P1/s1/v1")
    assert _starts(line) == [0, 1, 2, 3]
    assert [e.beat for e in line.events] == [1, 2, 3, 4]
    assert all(e.duration == 1 and e.measure == 1 for e in line.events)


def test_second_measure_starts_after_the_first(tmp_path: Path) -> None:
    m1 = measure(1, quarters(("C", 4), ("D", 4), ("E", 4), ("F", 4)), attrs=attributes())
    m2 = measure(2, quarters(("G", 4), ("A", 4), ("B", 4), ("C", 5)))
    line = _line(_parse(tmp_path, m1 + m2), "P1/s1/v1")
    assert _starts(line) == [0, 1, 2, 3, 4, 5, 6, 7]
    assert [e.measure for e in line.events] == [1, 1, 1, 1, 2, 2, 2, 2]
    assert line.events[4].beat == 1  # beat restarts in each source measure


def test_eighth_triplet_durations_are_exact_thirds(tmp_path: Path) -> None:
    body = (
        note("C", 4, 1) + note("D", 4, 1) + note("E", 4, 1)  # three triplet eighths, divisions=3
        + note("F", 4, 3) + note("G", 4, 6)
    )  # fmt: skip
    result = _parse(tmp_path, measure(1, body, attrs=attributes(divisions="3")))
    assert not result.issues
    line = _line(result, "P1/s1/v1")
    assert _starts(line) == [0, Fraction(1, 3), Fraction(2, 3), 1, 2]
    assert line.events[0].duration == Fraction(1, 3)


def test_divisions_can_change_between_measures(tmp_path: Path) -> None:
    m1 = measure(1, quarters(("C", 4), ("D", 4), ("E", 4), ("F", 4)), attrs=attributes())
    m2_body = "".join(note("G", 4, 4) for _ in range(4))  # divisions=4: 4 per quarter
    m2 = measure(2, m2_body, attrs=attributes(divisions="4", time=None, clefs=None))
    line = _line(_parse(tmp_path, m1 + m2), "P1/s1/v1")
    assert _starts(line)[4:] == [4, 5, 6, 7]
    assert all(e.duration == 1 for e in line.events[4:])


def test_decimal_divisions_are_exact(tmp_path: Path) -> None:
    body = note("C", 4, 1) * 1 + note("D", 4, 1) + note("E", 4, 1) + note("F", 4, 1)
    result = _parse(tmp_path, measure(1, body, attrs=attributes(divisions="0.5")))
    # duration 1 / divisions 0.5 = 2 quarter notes each, so the measure is overfull
    line = _line(result, "P1/s1/v1")
    assert line.events[0].duration == 2
    assert "MEASURE_DURATION_MISMATCH" in _codes(result)


def test_rests_are_kept_as_events(tmp_path: Path) -> None:
    body = rest(2) + quarters(("C", 4)) + rest(4)
    result = _parse(tmp_path, measure(1, body, attrs=attributes()))
    line = _line(result, "P1/s1/v1")
    assert [e.is_rest for e in line.events] == [True, False, True]
    assert line.events[2].duration == 2
    assert not result.issues


def test_whole_measure_rest(tmp_path: Path) -> None:
    body = '<note><rest measure="yes"/><duration>8</duration><voice>1</voice></note>'
    result = _parse(tmp_path, measure(1, body, attrs=attributes()))
    assert not result.issues
    assert _line(result, "P1/s1/v1").events[0].duration == 4


# --- backup / forward / chord ---------------------------------------------------------


def test_backup_places_a_second_voice_at_the_measure_start(tmp_path: Path) -> None:
    body = (
        quarters(("E", 5), ("F", 5), ("G", 5), ("A", 5), voice="1")
        + backup(8)
        + quarters(("C", 5), ("D", 5), ("E", 5), ("F", 5), voice="2")
    )
    result = _parse(tmp_path, measure(1, body, attrs=attributes()))
    assert not result.issues
    assert _starts(_line(result, "P1/s1/v1")) == [0, 1, 2, 3]
    assert _starts(_line(result, "P1/s1/v2")) == [0, 1, 2, 3]


def test_backup_to_the_middle_of_a_measure(tmp_path: Path) -> None:
    body = (
        quarters(("C", 4), ("D", 4), ("E", 4), ("F", 4))
        + backup(4)
        + quarters(("G", 4), ("A", 4), voice="2")
    )
    line = _line(_parse(tmp_path, measure(1, body, attrs=attributes())), "P1/s1/v2")
    assert _starts(line) == [2, 3]
    assert [e.beat for e in line.events] == [3, 4]


def test_forward_creates_a_gap_without_events(tmp_path: Path) -> None:
    body = (
        quarters(("C", 4), ("D", 4), ("E", 4), ("F", 4))
        + backup(8)
        + forward(4)
        + quarters(("G", 4), ("A", 4), voice="2")
    )
    result = _parse(tmp_path, measure(1, body, attrs=attributes()))
    assert not result.issues
    voice2 = _line(result, "P1/s1/v2")
    assert _starts(voice2) == [2, 3]
    assert not any(e.is_rest for e in voice2.events)  # a gap is not a rest


def test_forward_extends_the_measure(tmp_path: Path) -> None:
    m1 = measure(1, quarters(("C", 4), ("D", 4)) + forward(4), attrs=attributes())
    m2 = measure(2, quarters(("E", 4)))
    result = _parse(tmp_path, m1 + m2)
    assert _line(result, "P1/s1/v1").events[-1].start == 4
    # measure 1 is filled by the forward; only the short last measure is reported
    assert [(i.code, i.measure) for i in result.issues] == [("MEASURE_INCOMPLETE", 2)]


def test_sparse_voice_does_not_shorten_the_measure(tmp_path: Path) -> None:
    m1 = measure(1, quarters(("C", 4), ("D", 4)), attrs=attributes())  # no trailing rests
    m2 = measure(2, quarters(("E", 4)))
    result = _parse(tmp_path, m1 + m2)
    line = _line(result, "P1/s1/v1")
    assert line.events[-1].start == 4  # the second measure still begins at 4 quarters
    assert [(i.code, i.measure) for i in result.issues] == [
        ("MEASURE_INCOMPLETE", 1),
        ("MEASURE_INCOMPLETE", 2),
    ]
    assert all(i.severity is Severity.WARNING for i in result.issues)


def test_chord_notes_share_a_start_and_are_all_kept(tmp_path: Path) -> None:
    chord = note("E", 4, 2, extra="<chord/>") + note("G", 4, 2, extra="<chord/>")
    body = note("C", 4, 2) + chord + quarters(("D", 4), ("D", 4), ("D", 4))
    result = _parse(tmp_path, measure(1, body, attrs=attributes()))
    assert not result.issues
    events = _line(result, "P1/s1/v1").events
    assert [e.start for e in events] == [0, 0, 0, 1, 2, 3]
    assert [e.midi_note for e in events[:3]] == [60, 64, 67]


def test_chord_note_does_not_advance_the_cursor(tmp_path: Path) -> None:
    body = note("C", 4, 2) + note("E", 4, 4, extra="<chord/>") + note("D", 4, 2)
    line = _line(_parse(tmp_path, measure(1, body, attrs=attributes())), "P1/s1/v1")
    assert _starts(line) == [0, 0, 1]
    assert line.events[1].duration == 2  # the chord note keeps its own duration


def test_chord_without_a_preceding_note_is_an_error(tmp_path: Path) -> None:
    body = note("C", 4, 2, extra="<chord/>") + quarters(("D", 4))
    result = _parse(tmp_path, measure(1, body, attrs=attributes()))
    assert "CHORD_WITHOUT_PRECEDING_NOTE" in _codes(result)


def test_chord_right_after_backup_is_an_error(tmp_path: Path) -> None:
    body = quarters(("C", 4)) + backup(2) + note("E", 4, 2, extra="<chord/>")
    assert "CHORD_WITHOUT_PRECEDING_NOTE" in _codes(
        _parse(tmp_path, measure(1, body, attrs=attributes()))
    )


def test_backup_before_the_measure_start_is_an_error(tmp_path: Path) -> None:
    body = quarters(("C", 4)) + backup(8)
    result = _parse(tmp_path, measure(1, body, attrs=attributes()))
    issue = next(i for i in result.issues if i.code == "BACKUP_BEFORE_MEASURE_START")
    assert issue.severity is Severity.ERROR
    assert issue.measure == 1
    assert issue.beat == 2  # the cursor stood at beat 2 when the bad backup came


# --- pickups --------------------------------------------------------------------------


def test_pickup_measure_keeps_its_source_position(tmp_path: Path) -> None:
    pickup = measure(0, quarters(("G", 4)), attrs=attributes(), implicit=True)
    full = measure(1, quarters(("C", 5), ("B", 4), ("A", 4), ("G", 4)))
    result = _parse(tmp_path, pickup + full)
    assert not result.issues
    events = _line(result, "P1/s1/v1").events
    first = events[0]
    assert (first.measure, first.start, first.beat) == (0, Fraction(0), Fraction(1))
    assert [e.start for e in events] == [0, 1, 2, 3, 4]
    assert [e.measure for e in events] == [0, 1, 1, 1, 1]


def test_two_beat_pickup_has_exact_local_offsets(tmp_path: Path) -> None:
    pickup = measure(0, quarters(("E", 4), ("G", 4)), attrs=attributes(), implicit=True)
    full = measure(1, quarters(("C", 5), ("C", 5), ("C", 5), ("C", 5)))
    events = _line(_parse(tmp_path, pickup + full), "P1/s1/v1").events
    assert [(e.measure, e.beat, e.start) for e in events[:3]] == [
        (0, Fraction(1), Fraction(0)),
        (0, Fraction(2), Fraction(1)),
        (1, Fraction(1), Fraction(2)),
    ]


def test_short_implicit_measure_is_not_flagged(tmp_path: Path) -> None:
    pickup = measure(0, quarters(("G", 4)), attrs=attributes(), implicit=True)
    assert not _parse(tmp_path, pickup).issues


def test_non_implicit_short_measure_is_a_warning_not_an_error(tmp_path: Path) -> None:
    result = _parse(tmp_path, measure(1, quarters(("G", 4)), attrs=attributes()))
    assert [i.code for i in result.issues] == ["MEASURE_INCOMPLETE"]
    assert not result.issues.has_errors


def test_overfull_measure_is_an_error(tmp_path: Path) -> None:
    body = quarters(("C", 4), ("D", 4), ("E", 4), ("F", 4), ("G", 4))
    result = _parse(tmp_path, measure(1, body, attrs=attributes()))
    issue = next(i for i in result.issues if i.code == "MEASURE_DURATION_MISMATCH")
    assert issue.severity is Severity.ERROR
    assert issue.measure == 1


def test_implicit_measure_longer_than_the_meter_is_an_error(tmp_path: Path) -> None:
    body = quarters(("C", 4), ("D", 4), ("E", 4), ("F", 4), ("G", 4))
    result = _parse(tmp_path, measure(0, body, attrs=attributes(), implicit=True))
    assert "MEASURE_DURATION_MISMATCH" in _codes(result)


# --- meter needed for the timeline ----------------------------------------------------


def test_missing_time_signature_is_reported_once(tmp_path: Path) -> None:
    attrs = attributes(time=None)
    body1 = measure(1, quarters(("C", 4), ("D", 4)), attrs=attrs)
    body2 = measure(2, quarters(("E", 4)))
    result = _parse(tmp_path, body1 + body2)
    assert _codes(result).count("TIME_SIGNATURE_MISSING") == 1


@pytest.mark.parametrize(
    "time_xml",
    [
        "<time><senza-misura/></time>",
        "<time><beats>3+2</beats><beat-type>8</beat-type></time>",
        "<time><beats>3</beats><beat-type>4</beat-type><beats>2</beats><beat-type>8</beat-type></time>",
        "<time><beats>4</beats><beat-type>3</beat-type></time>",
        "<time><beats>0</beats><beat-type>4</beat-type></time>",
    ],
)
def test_unsupported_time_signatures_are_errors(tmp_path: Path, time_xml: str) -> None:
    attrs = f"<attributes><divisions>2</divisions>{time_xml}</attributes>"
    result = _parse(tmp_path, measure(1, quarters(("C", 4)), attrs=attrs))
    assert "TIME_SIGNATURE_UNSUPPORTED" in _codes(result)


def _time_xml(beats: int, beat_type: int) -> str:
    return (
        f"<attributes><time><beats>{beats}</beats>"
        f"<beat-type>{beat_type}</beat-type></time></attributes>"
    )


def test_time_signature_at_the_start_of_the_first_measure_is_supported(tmp_path: Path) -> None:
    body = quarters(("C", 4), ("D", 4), ("E", 4), ("F", 4))
    result = _parse(tmp_path, measure(1, body, attrs=attributes()))
    assert not result.issues


def test_time_signature_change_at_the_start_of_a_later_measure_is_supported(
    tmp_path: Path,
) -> None:
    m1 = measure(1, quarters(("C", 4), ("D", 4), ("E", 4), ("F", 4)), attrs=attributes())
    m2 = measure(2, quarters(("G", 4), ("A", 4), ("B", 4)), attrs=_time_xml(3, 4))
    m3 = measure(3, quarters(("C", 5), ("D", 5), ("E", 5)))
    result = _parse(tmp_path, m1 + m2 + m3)
    assert not result.issues
    starts = _starts(_line(result, "P1/s1/v1"))
    assert starts[4] == 4  # measure 2 (3/4) starts after the 4/4 measure
    assert starts[7] == 7  # measure 3 starts 3 quarter notes later


def test_time_signature_after_notes_have_advanced_the_cursor_is_an_error(tmp_path: Path) -> None:
    body = quarters(("C", 4), ("D", 4)) + _time_xml(3, 4) + quarters(("E", 4))
    result = _parse(tmp_path, measure(1, body, attrs=attributes()))
    issue = next(i for i in result.issues if i.code == "TIME_SIGNATURE_CHANGE_MID_MEASURE")
    assert issue.severity is Severity.ERROR
    assert issue.measure == 1
    assert issue.beat == 3  # the cursor stood at beat 3
    assert result.issues.has_errors


def test_time_signature_after_a_forward_to_a_nonzero_position_is_an_error(
    tmp_path: Path,
) -> None:
    body = forward(2) + _time_xml(3, 4) + quarters(("E", 4))
    result = _parse(tmp_path, measure(1, body, attrs=attributes()))
    assert "TIME_SIGNATURE_CHANGE_MID_MEASURE" in _codes(result)


def test_time_signature_after_a_backup_to_exactly_zero_is_allowed(tmp_path: Path) -> None:
    body = (
        quarters(("C", 4), ("D", 4), ("E", 4), ("F", 4))
        + backup(8)
        + _time_xml(4, 4)
        + quarters(("G", 3), ("A", 3), ("B", 3), ("C", 4), voice="2")
    )
    result = _parse(tmp_path, measure(1, body, attrs=attributes()))
    assert "TIME_SIGNATURE_CHANGE_MID_MEASURE" not in _codes(result)
    assert not result.issues.has_errors


def test_time_signature_after_a_backup_that_stops_short_of_zero_is_an_error(
    tmp_path: Path,
) -> None:
    body = quarters(("C", 4), ("D", 4), ("E", 4), ("F", 4)) + backup(6) + _time_xml(4, 4)
    result = _parse(tmp_path, measure(1, body, attrs=attributes()))
    assert "TIME_SIGNATURE_CHANGE_MID_MEASURE" in _codes(result)


def test_unsupported_mid_measure_meter_does_not_rebuild_the_timeline(tmp_path: Path) -> None:
    # The 3/4 declared after beat 2 is NOT applied: measure 1 keeps 4/4 and measure 2 starts
    # at 4 quarter notes, not at 3.
    m1 = measure(
        1,
        quarters(("C", 4), ("D", 4)) + _time_xml(3, 4) + quarters(("E", 4), ("F", 4)),
        attrs=attributes(),
    )
    m2 = measure(2, quarters(("G", 4), ("A", 4), ("B", 4), ("C", 5)))
    result = _parse(tmp_path, m1 + m2)
    line = _line(result, "P1/s1/v1")
    assert [e.start for e in line.events] == [0, 1, 2, 3, 4, 5, 6, 7]
    assert result.issues.has_errors
    assert _codes(result) == ["TIME_SIGNATURE_CHANGE_MID_MEASURE"]  # no cascade of other issues


def test_mid_measure_time_in_the_first_measure_leaves_the_meter_unknown(tmp_path: Path) -> None:
    body = quarters(("C", 4)) + _time_xml(4, 4) + quarters(("D", 4))
    result = _parse(tmp_path, measure(1, body, attrs=attributes(time=None)))
    assert "TIME_SIGNATURE_CHANGE_MID_MEASURE" in _codes(result)
    assert "TIME_SIGNATURE_MISSING" in _codes(result)  # the unapplied meter is not used


def test_time_signature_change_changes_the_expected_length(tmp_path: Path) -> None:
    m1 = measure(1, quarters(("C", 4), ("D", 4), ("E", 4), ("F", 4)), attrs=attributes())
    m2_attrs = "<attributes><time><beats>3</beats><beat-type>4</beat-type></time></attributes>"
    m2 = measure(2, quarters(("G", 4), ("A", 4), ("B", 4)), attrs=m2_attrs)
    m3 = measure(3, quarters(("C", 5)))
    result = _parse(tmp_path, m1 + m2 + m3)
    line = _line(result, "P1/s1/v1")
    assert line.events[-1].start == 7  # 4 + 3
    assert [i.code for i in result.issues] == ["MEASURE_INCOMPLETE"]  # only m3 is short


def test_six_eight_measure_length(tmp_path: Path) -> None:
    eighths = "".join(note("C", 4, 1) for _ in range(6))
    m1 = measure(1, eighths, attrs=attributes(time=(6, 8)))
    m2 = measure(2, note("D", 4, 1))
    line = _line(_parse(tmp_path, m1 + m2), "P1/s1/v1")
    assert line.events[-1].start == 3  # 6/8 = 3 quarter notes


# --- unplaceable elements are reported, never guessed ---------------------------------


def test_missing_voice_is_an_error_but_time_still_advances(tmp_path: Path) -> None:
    body = quarters(("C", 4)) + note("D", 4, 2, voice=None) + quarters(("E", 4), ("F", 4))
    result = _parse(tmp_path, measure(1, body, attrs=attributes()))
    issue = next(i for i in result.issues if i.code == "VOICE_MISSING")
    assert issue.severity is Severity.ERROR
    assert issue.measure == 1
    assert issue.beat == 2
    assert _starts(_line(result, "P1/s1/v1")) == [0, 2, 3]  # voice 1 is not assumed


def test_note_without_duration_is_an_error(tmp_path: Path) -> None:
    body = (
        quarters(("C", 4))
        + "<note><pitch><step>D</step><octave>4</octave></pitch><voice>1</voice></note>"
    )
    assert "NOTE_DURATION_MISSING" in _codes(_parse(tmp_path, measure(1, body, attrs=attributes())))


@pytest.mark.parametrize("duration", ["0", "-2", "abc", "1/2", "1e1"])
def test_invalid_durations_are_errors(tmp_path: Path, duration: str) -> None:
    body = note("C", 4, duration)
    assert "NOTE_DURATION_INVALID" in _codes(_parse(tmp_path, measure(1, body, attrs=attributes())))


def test_missing_divisions_is_reported_once(tmp_path: Path) -> None:
    body = quarters(("C", 4), ("D", 4))
    result = _parse(tmp_path, measure(1, body, attrs=attributes(divisions=None)))
    assert _codes(result).count("DIVISIONS_MISSING") == 1
    assert _line_ids(result) == []


@pytest.mark.parametrize("divisions", ["0", "-1", "x"])
def test_invalid_divisions_are_errors(tmp_path: Path, divisions: str) -> None:
    result = _parse(tmp_path, measure(1, quarters(("C", 4)), attrs=attributes(divisions=divisions)))
    assert "DIVISIONS_INVALID" in _codes(result)


def test_backup_and_forward_need_valid_durations(tmp_path: Path) -> None:
    body = quarters(("C", 4)) + "<backup/>" + "<forward><duration>0</duration></forward>"
    result = _parse(tmp_path, measure(1, body, attrs=attributes()))
    assert _codes(result).count("MOVE_DURATION_INVALID") == 2


def _line_ids(result: ParseResult) -> list[str]:
    return [] if result.song is None else [p.part_id for p in result.song.parts]


def test_events_in_each_line_are_ordered_by_start(tmp_path: Path) -> None:
    body = (
        quarters(("C", 4), ("D", 4))
        + backup(4)
        + quarters(("E", 4), ("F", 4))
        + quarters(("G", 4), ("A", 4))
    )
    result = _parse(tmp_path, measure(1, body, attrs=attributes()))
    line = _line(result, "P1/s1/v1")
    assert _starts(line) == sorted(_starts(line))
    assert isinstance(line.events[0], Note)
