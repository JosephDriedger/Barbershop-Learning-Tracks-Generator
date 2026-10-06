from fractions import Fraction
from pathlib import Path

import pytest

from barbershop_tracks.core.errors import ScoreFileError, UnsupportedScoreFormatError
from barbershop_tracks.core.musicxml import ParseResult, parse_musicxml
from barbershop_tracks.models import Part, Severity, SourceLine
from xml_builders import (
    BASS,
    attributes,
    backup,
    measure,
    note,
    parse_text,
    quarters,
    score,
)

pytestmark = pytest.mark.usefixtures("no_network")

FOUR = quarters(("C", 4), ("D", 4), ("E", 4), ("F", 4))


def _ids(result: ParseResult) -> list[str]:
    return [] if result.song is None else [p.part_id for p in result.song.parts]


def _codes(result: ParseResult) -> list[str]:
    return [issue.code for issue in result.issues]


def _line(result: ParseResult, line_id: str) -> Part:
    assert result.song is not None
    return next(p for p in result.song.parts if p.part_id == line_id)


# --- parts, staves, voice lines -------------------------------------------------------


def test_two_voices_on_an_implied_staff_become_two_lines(tmp_path: Path) -> None:
    body = FOUR + backup(8) + quarters(("A", 3), ("B", 3), ("C", 4), ("D", 4), voice="2")
    result = parse_text(tmp_path, score(measure(1, body, attrs=attributes())))
    assert _ids(result) == ["P1/s1/v1", "P1/s1/v2"]
    line = _line(result, "P1/s1/v2")
    assert line.source_line == SourceLine(part_id="P1", staff=1, voice="2")
    assert line.part_id == str(line.source_line)


def test_voice_ids_are_not_renumbered_or_assumed_contiguous(tmp_path: Path) -> None:
    clefs = (
        '<clef number="1"><sign>G</sign><line>2</line></clef>'
        '<clef number="2"><sign>F</sign><line>4</line></clef>'
    )
    attrs = attributes(staves=2, clefs=clefs)
    body = (
        note("E", 5, 8, voice="1", staff=1)
        + backup(8)
        + note("C", 5, 8, voice="2", staff=1)
        + backup(8)
        + note("G", 3, 8, voice="5", staff=2)
        + backup(8)
        + note("C", 3, 8, voice="6", staff=2)
    )
    result = parse_text(tmp_path, score(measure(1, body, attrs=attrs)))
    assert not result.issues
    assert _ids(result) == ["P1/s1/v1", "P1/s1/v2", "P1/s2/v5", "P1/s2/v6"]
    assert _line(result, "P1/s2/v5").source_line == SourceLine(part_id="P1", staff=2, voice="5")


def test_the_same_voice_id_on_two_staves_is_two_lines(tmp_path: Path) -> None:
    attrs = attributes(staves=2)
    body = note("C", 5, 8, voice="1", staff=1) + backup(8) + note("C", 3, 8, voice="1", staff=2)
    result = parse_text(tmp_path, score(measure(1, body, attrs=attrs)))
    assert _ids(result) == ["P1/s1/v1", "P1/s2/v1"]
    assert _line(result, "P1/s1/v1").events[0].midi_note == 72
    assert _line(result, "P1/s2/v1").events[0].midi_note == 48


def test_four_separate_parts(tmp_path: Path) -> None:
    parts = [measure(1, FOUR, attrs=attributes()) for _ in range(4)]
    result = parse_text(tmp_path, score(*parts))
    assert _ids(result) == ["P1/s1/v1", "P2/s1/v1", "P3/s1/v1", "P4/s1/v1"]


def _ttbb_two_part_layout(tmp_path: Path) -> ParseResult:
    """Two parts, each one staff with two voices, pickup, divisions 12: a common layout."""
    attrs_p1 = (
        "<attributes><divisions>12</divisions><key><fifths>0</fifths></key>"
        "<time><beats>4</beats><beat-type>4</beat-type></time>"
        "<clef><sign>G</sign><line>2</line><clef-octave-change>-1</clef-octave-change></clef></attributes>"
    )
    attrs_p2 = attrs_p1.replace(
        "<clef><sign>G</sign><line>2</line><clef-octave-change>-1</clef-octave-change></clef>",
        f"<clef>{BASS}</clef>",
    )

    def two_voices(upper: str, lower: str, steps: int) -> str:
        return (
            "".join(note(upper, 4, 12, voice="1") for _ in range(steps))
            + backup(12 * steps)
            + "".join(note(lower, 3, 12, voice="2") for _ in range(steps))
        )

    p1 = measure(0, two_voices("E", "C", 1), attrs=attrs_p1, implicit=True) + measure(
        1, two_voices("E", "C", 4)
    )
    p2 = measure(0, two_voices("G", "C", 1), attrs=attrs_p2, implicit=True) + measure(
        1, two_voices("G", "C", 4)
    )
    names = ["TENOR\n LEAD", "BARI\nBASS"]
    return parse_text(tmp_path, score(p1, p2, names=names))


def test_two_part_four_singer_layout_gives_four_lines_without_roles(tmp_path: Path) -> None:
    result = _ttbb_two_part_layout(tmp_path)
    assert not result.issues
    assert _ids(result) == ["P1/s1/v1", "P1/s1/v2", "P2/s1/v1", "P2/s1/v2"]
    assert result.song is not None
    assert all(part.role is None for part in result.song.parts)  # never inferred from names
    first = _line(result, "P1/s1/v1").events[0]
    assert first.measure == 0
    assert first.start == 0
    assert first.beat == 1
    assert _line(result, "P1/s1/v1").events[1].start == 1  # full measure follows the pickup


def test_part_names_are_collapsed_for_display_and_preserved_raw(tmp_path: Path) -> None:
    result = _ttbb_two_part_layout(tmp_path)
    part = _line(result, "P1/s1/v1")
    assert part.name == "TENOR LEAD"
    assert part.source_name == "TENOR\n LEAD"
    assert _line(result, "P2/s1/v2").name == "BARI BASS"


def test_events_of_different_lines_are_independent(tmp_path: Path) -> None:
    result = _ttbb_two_part_layout(tmp_path)
    upper, lower = _line(result, "P1/s1/v1"), _line(result, "P1/s1/v2")
    assert [e.start for e in upper.events] == [e.start for e in lower.events]
    assert upper.events[0].midi_note != lower.events[0].midi_note


# --- metadata -------------------------------------------------------------------------


def _head(work: str = "", movement: str = "", ident: str = "") -> str:
    parts = ""
    if work:
        parts += f"<work><work-title>{work}</work-title></work>"
    if movement:
        parts += f"<movement-title>{movement}</movement-title>"
    if ident:
        parts += f"<identification>{ident}</identification>"
    return parts


def test_title_prefers_work_then_movement_then_empty(tmp_path: Path) -> None:
    body = measure(1, FOUR, attrs=attributes())
    both = parse_text(tmp_path, score(body, head=_head("Work", "Movement")), "a.musicxml")
    movement = parse_text(tmp_path, score(body, head=_head(movement="Movement")), "b.musicxml")
    neither = parse_text(tmp_path, score(body), "c.musicxml")
    assert both.song is not None
    assert movement.song is not None
    assert neither.song is not None
    assert both.song.title == "Work"
    assert movement.song.title == "Movement"
    assert neither.song.title == ""  # never taken from the file name


def test_composer_arranger_software_and_version(tmp_path: Path) -> None:
    ident = (
        '<creator type="composer">A. Composer</creator>'
        '<creator type="arranger">B. Arranger</creator>'
        "<encoding><software>MuseScore Studio 4.7.4</software></encoding>"
    )
    path = tmp_path / "s.musicxml"
    path.write_text(
        score(measure(1, FOUR, attrs=attributes()), head=_head(ident=ident), version="3.1")
    )
    song = parse_musicxml(path).song
    assert song is not None
    assert song.composer == "A. Composer"
    assert song.arranger == "B. Arranger"
    assert song.source.software == "MuseScore Studio 4.7.4"
    assert song.source.format_version == "3.1"
    assert song.source.format_name == "MusicXML"
    assert song.source.path == path


def test_missing_metadata_is_none_not_invented(tmp_path: Path) -> None:
    song = parse_text(tmp_path, score(measure(1, FOUR, attrs=attributes()))).song
    assert song is not None
    assert (song.composer, song.arranger, song.source.software) == (None, None, None)


def test_score_without_a_tempo_has_an_empty_tempo_map(tmp_path: Path) -> None:
    song = parse_text(tmp_path, score(measure(1, FOUR, attrs=attributes()))).song
    assert song is not None
    assert song.tempo_map == ()  # never a default such as 120
    assert [(t.beats, t.beat_type) for t in song.time_signatures] == [(4, 4)]


# --- clef notation data ---------------------------------------------------------------


def test_clefs_are_recorded_with_staff_position_and_octave_change(tmp_path: Path) -> None:
    clefs = (
        '<clef number="1"><sign>G</sign><line>2</line>'
        "<clef-octave-change>-1</clef-octave-change></clef>"
        '<clef number="2"><sign>F</sign><line>4</line></clef>'
    )
    result = parse_text(tmp_path, score(measure(1, FOUR, attrs=attributes(staves=2, clefs=clefs))))
    assert result.song is not None
    one, two = result.song.clef_changes
    assert (one.part_id, one.staff, one.sign, one.line, one.octave_change) == ("P1", 1, "G", 2, -1)
    assert (two.staff, two.sign, two.line, two.octave_change) == (2, "F", 4, 0)
    assert one.measure == 1
    assert one.position == 0


def test_a_clef_change_inside_a_measure_has_an_exact_position(tmp_path: Path) -> None:
    mid_clef = f"<attributes><clef>{BASS}</clef></attributes>"
    body = quarters(("C", 4), ("D", 4)) + mid_clef + quarters(("E", 3), ("F", 3))
    result = parse_text(tmp_path, score(measure(1, body, attrs=attributes())))
    assert result.song is not None
    first, second = result.song.clef_changes
    assert first.position == 0
    assert second.position == Fraction(2)
    assert second.sign == "F"


def test_clef_in_a_later_measure_has_a_global_position(tmp_path: Path) -> None:
    m2 = measure(2, FOUR, attrs=f"<attributes><clef>{BASS}</clef></attributes>")
    result = parse_text(tmp_path, score(measure(1, FOUR, attrs=attributes()) + m2))
    assert result.song is not None
    positions = [(c.measure, c.position) for c in result.song.clef_changes]
    assert positions == [(1, Fraction(0)), (2, Fraction(4))]


def test_unreadable_clef_is_a_warning_only(tmp_path: Path) -> None:
    attrs = attributes(clefs="<clef><line>2</line></clef>")
    result = parse_text(tmp_path, score(measure(1, FOUR, attrs=attrs)))
    assert _codes(result) == ["CLEF_INVALID"]
    assert not result.issues.has_errors


# --- repeats and jumps are detected, never silently read once -------------------------


def _barline(inner: str, location: str = "right") -> str:
    return f'<barline location="{location}">{inner}</barline>'


@pytest.mark.parametrize(
    "inner",
    [
        '<ending number="1" type="start"/>',
        '<ending number="1, 2" type="stop"/><repeat direction="backward"/>',
    ],
)
def test_endings_block_generation(tmp_path: Path, inner: str) -> None:
    m1 = measure(1, FOUR + _barline(inner), attrs=attributes())
    result = parse_text(tmp_path, score(m1 + measure(2, FOUR)))
    issue = next(i for i in result.issues if i.code == "ENDING_NOT_SUPPORTED_YET")
    assert issue.severity is Severity.ERROR
    assert issue.measure == 1
    assert issue.part_id == "P1"
    assert "REPEAT_NOT_SUPPORTED_YET" not in _codes(result)  # the temporary code is retired


def test_barline_without_repeat_is_fine(tmp_path: Path) -> None:
    final = _barline("<bar-style>light-heavy</bar-style>")
    result = parse_text(tmp_path, score(measure(1, FOUR + final, attrs=attributes())))
    assert not result.issues


@pytest.mark.parametrize("attribute", ["dacapo", "dalsegno", "segno", "coda", "tocoda", "fine"])
def test_jump_markers_are_errors(tmp_path: Path, attribute: str) -> None:
    direction = (
        "<direction><direction-type><words>x</words></direction-type>"
        f'<sound {attribute}="yes"/></direction>'
    )
    result = parse_text(tmp_path, score(measure(1, FOUR + direction, attrs=attributes())))
    issue = next(i for i in result.issues if i.code == "UNSUPPORTED_JUMP")
    assert attribute in issue.message
    assert result.issues.has_errors


def test_sound_directly_in_a_measure_is_checked_too(tmp_path: Path) -> None:
    result = parse_text(
        tmp_path, score(measure(1, FOUR + '<sound dacapo="yes"/>', attrs=attributes()))
    )
    assert "UNSUPPORTED_JUMP" in _codes(result)


def test_tempo_sound_without_jump_is_not_flagged_in_m3b1(tmp_path: Path) -> None:
    direction = (
        "<direction><direction-type><words>x</words></direction-type>"
        '<sound tempo="96"/></direction>'
    )
    result = parse_text(tmp_path, score(measure(1, FOUR + direction, attrs=attributes())))
    assert not result.issues


# --- special note kinds are deferred, not misread -------------------------------------


# --- measure numbers ------------------------------------------------------------------


def test_non_numeric_measure_number_falls_back_to_position_with_a_warning(tmp_path: Path) -> None:
    result = parse_text(tmp_path, score(measure("X1", FOUR, attrs=attributes())))
    assert _codes(result) == ["MEASURE_NUMBER_NONNUMERIC"]
    assert _line(result, "P1/s1/v1").events[0].measure == 1
    assert not result.issues.has_errors


def test_source_measure_numbers_are_preserved(tmp_path: Path) -> None:
    result = parse_text(tmp_path, score(measure(5, FOUR, attrs=attributes()) + measure(6, FOUR)))
    assert [e.measure for e in _line(result, "P1/s1/v1").events] == [5] * 4 + [6] * 4


# --- cross-part consistency -----------------------------------------------------------


def test_parts_with_different_measure_counts_are_an_error(tmp_path: Path) -> None:
    one = measure(1, FOUR, attrs=attributes())
    two = measure(1, FOUR, attrs=attributes()) + measure(2, FOUR)
    result = parse_text(tmp_path, score(one, two))
    assert "PART_MEASURE_COUNT_MISMATCH" in _codes(result)


def test_parts_with_different_measure_lengths_are_an_error(tmp_path: Path) -> None:
    one = measure(1, FOUR, attrs=attributes()) + measure(2, FOUR)
    three = quarters(("C", 4), ("D", 4), ("E", 4))
    two = measure(1, three, attrs=attributes(time=(3, 4))) + measure(2, three)
    result = parse_text(tmp_path, score(one, two))
    issue = next(i for i in result.issues if i.code == "MEASURE_LENGTH_MISMATCH_ACROSS_PARTS")
    assert issue.part_id == "P2"


# --- structure problems ---------------------------------------------------------------


def test_score_without_parts(tmp_path: Path) -> None:
    result = parse_text(tmp_path, score())
    assert result.song is None
    assert _codes(result) == ["NO_PARTS"]


def test_part_missing_from_part_list(tmp_path: Path) -> None:
    xml = (
        '<score-partwise version="4.0"><part-list/>'
        f'<part id="P9">{measure(1, FOUR, attrs=attributes())}</part></score-partwise>'
    )
    result = parse_text(tmp_path, xml)
    assert "PART_NOT_IN_PART_LIST" in _codes(result)
    assert _ids(result) == ["P9/s1/v1"]  # still parsed, but the error blocks generation


def test_part_id_with_a_slash_is_rejected(tmp_path: Path) -> None:
    xml = (
        '<score-partwise version="4.0"><part-list><score-part id="a/b"/></part-list>'
        f'<part id="a/b">{measure(1, FOUR, attrs=attributes())}</part></score-partwise>'
    )
    result = parse_text(tmp_path, xml)
    assert "PART_ID_INVALID" in _codes(result)
    assert result.song is None


def test_loader_errors_still_raise(tmp_path: Path) -> None:
    with pytest.raises(ScoreFileError):
        parse_musicxml(tmp_path / "missing.musicxml")
    timewise = tmp_path / "t.musicxml"
    timewise.write_text("<score-timewise/>")
    with pytest.raises(UnsupportedScoreFormatError):
        parse_musicxml(timewise)


def test_note_issues_carry_the_line_id_and_position(tmp_path: Path) -> None:
    body = quarters(("C", 4)) + note("C", 12, 2, voice="2")
    result = parse_text(tmp_path, score(measure(1, body, attrs=attributes())))
    issue = next(i for i in result.issues if i.code == "PITCH_OUT_OF_RANGE")
    assert issue.part_id == "P1/s1/v2"
    assert issue.measure == 1
    assert issue.beat == 2


def test_a_lyric_is_attached_to_its_note_literally(tmp_path: Path) -> None:
    lyric = "<lyric><syllabic>single</syllabic><text>la</text></lyric>"
    body = note("C", 4, 8, extra="").replace("</note>", lyric + "</note>")
    result = parse_text(tmp_path, score(measure(1, body, attrs=attributes())))
    (attached,) = _line(result, "P1/s1/v1").events[0].lyrics
    assert (attached.text, attached.verse) == ("la", None)  # no number in the source
    assert not result.issues
