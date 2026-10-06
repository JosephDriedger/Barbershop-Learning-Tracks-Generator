"""<tie> (sound) versus <tied> (notation) parsing, and tie diagnostics through the parser."""

from fractions import Fraction
from pathlib import Path

import pytest

from barbershop_tracks.core.musicxml import ParseResult
from barbershop_tracks.core.timeline import merge_tied_notes
from barbershop_tracks.models import Note, PerformanceNote, Severity
from xml_builders import (
    attributes,
    backup,
    measure,
    note,
    parse_text,
    quarters,
    rest,
    score,
    tie_xml,
    tied_xml,
)

pytestmark = pytest.mark.usefixtures("no_network")


def _parse(tmp_path: Path, *parts: str) -> ParseResult:
    return parse_text(tmp_path, score(*parts))


def _events(result: ParseResult, line: str = "P1/s1/v1") -> tuple[Note, ...]:
    assert result.song is not None
    return next(p for p in result.song.parts if p.part_id == line).events


def _codes(result: ParseResult) -> list[str]:
    return [issue.code for issue in result.issues]


def _tied_pair(tie_first: str, tied_first: str, tie_second: str, tied_second: str) -> str:
    first = note(
        "C",
        4,
        2,
        tie=tie_first,
        notations=tied_first,
        extra="",
    )
    second = note("C", 4, 2, tie=tie_second, notations=tied_second)
    return measure(1, first + second + quarters(("E", 4), ("F", 4)), attrs=attributes())


# --- reading <tie> -------------------------------------------------------------------


def test_tie_start_and_stop_set_the_flags(tmp_path: Path) -> None:
    body = _tied_pair(tie_xml("start"), tied_xml("start"), tie_xml("stop"), tied_xml("stop"))
    result = _parse(tmp_path, body)
    first, second = _events(result)[:2]
    assert (first.tied_to_next, first.tied_from_previous) == (True, False)
    assert (second.tied_to_next, second.tied_from_previous) == (False, True)
    assert not result.issues


def test_a_chain_member_has_both_flags(tmp_path: Path) -> None:
    body = measure(
        1,
        note("C", 4, 2, tie=tie_xml("start"), notations=tied_xml("start"))
        + note("C", 4, 2, tie=tie_xml("stop", "start"), notations=tied_xml("stop", "start"))
        + note("C", 4, 2, tie=tie_xml("stop"), notations=tied_xml("stop"))
        + quarters(("F", 4)),
        attrs=attributes(),
    )
    result = _parse(tmp_path, body)
    middle = _events(result)[1]
    assert middle.tied_to_next
    assert middle.tied_from_previous
    assert not result.issues


def test_untied_notes_have_no_flags(tmp_path: Path) -> None:
    result = _parse(tmp_path, measure(1, quarters(("C", 4)) * 4, attrs=attributes()))
    assert not any(e.tied_to_next or e.tied_from_previous for e in _events(result))


@pytest.mark.parametrize("kind", ["continue", "let-ring", "bogus", ""])
def test_invalid_tie_type_is_an_error(tmp_path: Path, kind: str) -> None:
    body = measure(1, note("C", 4, 8, tie=f'<tie type="{kind}"/>'), attrs=attributes())
    result = _parse(tmp_path, body)
    issue = next(i for i in result.issues if i.code == "TIE_TYPE_INVALID")
    assert issue.severity is Severity.ERROR
    assert issue.part_id == "P1/s1/v1"


def test_tie_without_a_type_is_an_error(tmp_path: Path) -> None:
    body = measure(1, note("C", 4, 8, tie="<tie/>"), attrs=attributes())
    assert "TIE_TYPE_INVALID" in _codes(_parse(tmp_path, body))


# --- <tie> versus <tied> -------------------------------------------------------------


def test_tie_without_tied_is_a_warning_and_the_sound_tie_is_used(tmp_path: Path) -> None:
    body = _tied_pair(tie_xml("start"), "", tie_xml("stop"), "")
    result = _parse(tmp_path, body)
    assert _codes(result).count("TIE_WITHOUT_TIED") == 2
    assert all(
        i.severity is Severity.WARNING for i in result.issues if i.code == "TIE_WITHOUT_TIED"
    )
    first, second = _events(result)[:2]
    assert first.tied_to_next
    assert second.tied_from_previous
    assert not result.issues.has_errors


def test_tied_without_tie_is_an_error_and_is_not_converted_to_a_sound_tie(tmp_path: Path) -> None:
    body = _tied_pair("", tied_xml("start"), "", tied_xml("stop"))
    result = _parse(tmp_path, body)
    errors = [i for i in result.issues if i.code == "TIED_WITHOUT_TIE"]
    assert len(errors) == 2
    assert all(e.severity is Severity.ERROR for e in errors)
    first, second = _events(result)[:2]
    assert not first.tied_to_next  # <tie> is authoritative; <tied> alone does not tie
    assert not second.tied_from_previous
    assert result.issues.has_errors


def test_tied_without_tie_diagnostic_carries_what_a_repair_would_need(tmp_path: Path) -> None:
    body = _tied_pair("", tied_xml("start"), "", tied_xml("stop"))
    issue = next(i for i in _parse(tmp_path, body).issues if i.code == "TIED_WITHOUT_TIE")
    assert issue.part_id == "P1/s1/v1"  # the source line
    assert issue.measure == 1
    assert issue.beat == 1
    assert "C4" in issue.message  # which pitch
    assert "start" in issue.message  # which notated tie type was found
    assert "NOT treated as tied" in issue.message


def test_tied_without_tie_does_not_merge_the_notes(tmp_path: Path) -> None:
    result = _parse(tmp_path, _tied_pair("", tied_xml("start"), "", tied_xml("stop")))
    merged = merge_tied_notes(_events(result), part_id="P1/s1/v1")
    assert not merged.issues  # no tie flags, so nothing for the merge to complain about
    assert [len(p.source) for p in merged.notes] == [1, 1, 1, 1]


def test_contradicting_types_are_an_error(tmp_path: Path) -> None:
    body = _tied_pair(tie_xml("start"), tied_xml("stop"), tie_xml("stop"), tied_xml("start"))
    result = _parse(tmp_path, body)
    assert _codes(result).count("TIE_TIED_MISMATCH") == 2
    assert result.issues.has_errors


def test_contradicting_counts_are_an_error(tmp_path: Path) -> None:
    body = measure(
        1,
        note("C", 4, 2, tie=tie_xml("start"), notations=tied_xml("start"))
        + note("C", 4, 2, tie=tie_xml("stop", "start"), notations=tied_xml("stop"))
        + note("C", 4, 2, tie=tie_xml("stop"), notations=tied_xml("stop"))
        + quarters(("F", 4)),
        attrs=attributes(),
    )
    result = _parse(tmp_path, body)
    issue = next(i for i in result.issues if i.code == "TIE_TIED_MISMATCH")
    assert issue.beat == 2  # the chain member whose <tied> lacks the 'start'


@pytest.mark.parametrize("notation_only", ["continue", "let-ring"])
def test_tied_continue_and_let_ring_are_notation_only(tmp_path: Path, notation_only: str) -> None:
    body = measure(
        1,
        note("C", 4, 8, notations=f'<tied type="{notation_only}"/>'),
        attrs=attributes(),
    )
    result = _parse(tmp_path, body)
    assert not result.issues  # neither a tie nor a disagreement
    assert not _events(result)[0].tied_to_next


def test_agreement_in_a_different_element_order_is_not_a_mismatch(tmp_path: Path) -> None:
    body = measure(
        1,
        note("C", 4, 2, tie=tie_xml("start"), notations=tied_xml("start"))
        + note("C", 4, 2, tie=tie_xml("stop", "start"), notations=tied_xml("start", "stop"))
        + note("C", 4, 2, tie=tie_xml("stop"), notations=tied_xml("stop"))
        + quarters(("F", 4)),
        attrs=attributes(),
    )
    assert not _parse(tmp_path, body).issues


def test_multiple_notations_elements_are_all_read(tmp_path: Path) -> None:
    first = (
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>2</duration>"
        '<tie type="start"/><voice>1</voice>'
        '<notations><tied type="start"/></notations><notations><slur type="start"/></notations>'
        "</note>"
    )
    second = note("C", 4, 2, tie=tie_xml("stop"), notations=tied_xml("stop"))
    result = _parse(
        tmp_path, measure(1, first + second + quarters(("E", 4), ("F", 4)), attrs=attributes())
    )
    assert not result.issues


def test_rests_ignore_tie_elements(tmp_path: Path) -> None:
    body = measure(1, rest(8), attrs=attributes())
    assert not _parse(tmp_path, body).issues


# --- ties through the parser: merging happens only in the helper --------------------


def test_song_keeps_both_source_notes(tmp_path: Path) -> None:
    body = _tied_pair(tie_xml("start"), tied_xml("start"), tie_xml("stop"), tied_xml("stop"))
    events = _events(_parse(tmp_path, body))
    assert len(events) == 4  # nothing was merged or removed


def test_tie_across_a_barline_through_the_parser(tmp_path: Path) -> None:
    m1 = measure(
        1,
        quarters(("C", 4), ("D", 4), ("E", 4))
        + note("G", 4, 2, tie=tie_xml("start"), notations=tied_xml("start")),
        attrs=attributes(),
    )
    m2 = measure(
        2,
        note("G", 4, 4, tie=tie_xml("stop"), notations=tied_xml("stop"))
        + quarters(("A", 4), ("B", 4)),
    )
    result = _parse(tmp_path, m1 + m2)
    assert not result.issues
    merged = merge_tied_notes(_events(result), part_id="P1/s1/v1")
    group = next(p for p in merged.notes if p.is_tied_group)
    assert (group.start, group.duration, group.measure) == (Fraction(3), Fraction(3), 1)


def test_tie_across_a_divisions_change_through_the_parser(tmp_path: Path) -> None:
    m1 = measure(
        1,
        quarters(("C", 4), ("D", 4), ("E", 4))
        + note("G", 4, 2, tie=tie_xml("start"), notations=tied_xml("start")),
        attrs=attributes(),
    )
    # divisions 4: a duration of 6 is 3/2 quarter notes
    m2 = measure(
        2,
        note("G", 4, 6, tie=tie_xml("stop"), notations=tied_xml("stop"))
        + "".join(note("A", 4, 4) for _ in range(2))
        + note("B", 4, 2),
        attrs=attributes(divisions="4", time=None, clefs=None),
    )
    result = _parse(tmp_path, m1 + m2)
    merged = merge_tied_notes(_events(result), part_id="P1/s1/v1")
    group = next(p for p in merged.notes if p.is_tied_group)
    assert group.duration == 1 + 3 / 2 or group.duration == 2.5
    assert not merged.issues


def test_enharmonic_tie_through_the_parser(tmp_path: Path) -> None:
    first = note("C", 4, 2, alter="1", tie=tie_xml("start"), notations=tied_xml("start"))
    second = note("D", 4, 2, alter="-1", tie=tie_xml("stop"), notations=tied_xml("stop"))
    result = _parse(
        tmp_path, measure(1, first + second + quarters(("E", 4), ("F", 4)), attrs=attributes())
    )
    assert not result.issues
    group = next(p for p in merge_tied_notes(_events(result), part_id="x").notes if p.is_tied_group)
    assert isinstance(group, PerformanceNote)
    assert [str(s.written_pitch) for s in group.source] == ["C#4", "Db4"]


def test_tie_between_chord_members_through_the_parser(tmp_path: Path) -> None:
    def chord(tie_c: str, tied_c: str, tie_e: str, tied_e: str) -> str:
        return note("C", 4, 4, tie=tie_c, notations=tied_c) + note(
            "E", 4, 4, extra="<chord/>", tie=tie_e, notations=tied_e
        )

    body = chord(tie_xml("start"), tied_xml("start"), "", "") + chord(
        tie_xml("stop"), tied_xml("stop"), "", ""
    )
    result = _parse(tmp_path, measure(1, body, attrs=attributes()))
    assert not result.issues
    merged = merge_tied_notes(_events(result), part_id="P1/s1/v1")
    assert sorted((str(p.pitch), len(p.source)) for p in merged.notes) == [
        ("C4", 2),
        ("E4", 1),
        ("E4", 1),
    ]


def test_tie_problems_are_reported_by_the_parser_with_the_line(tmp_path: Path) -> None:
    body = measure(
        1,
        note("C", 4, 2, tie=tie_xml("start"), notations=tied_xml("start"))
        + quarters(("D", 4), ("E", 4), ("F", 4)),
        attrs=attributes(),
    )
    result = _parse(tmp_path, body)
    issue = next(i for i in result.issues if i.code == "TIE_UNMATCHED_START")
    assert (issue.part_id, issue.measure) == ("P1/s1/v1", 1)
    assert result.issues.has_errors


def test_ties_do_not_pair_across_voices(tmp_path: Path) -> None:
    body = (
        note("C", 4, 2, voice="1", tie=tie_xml("start"), notations=tied_xml("start"))
        + quarters(("D", 4), ("E", 4), ("F", 4))
        + backup(8)
        + note("C", 4, 2, voice="2")
        + note("C", 4, 2, voice="2", tie=tie_xml("stop"), notations=tied_xml("stop"))
        + quarters(("A", 3), ("B", 3), voice="2")
    )
    result = _parse(tmp_path, measure(1, body, attrs=attributes()))
    assert set(_codes(result)) >= {"TIE_UNMATCHED_START", "TIE_UNMATCHED_STOP"}
