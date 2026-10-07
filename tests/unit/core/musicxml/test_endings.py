"""Reading endings (voltas) from MusicXML and planning them (M3e1), on hand-written scores."""

import copy
from pathlib import Path

import pytest

from barbershop_tracks.core.musicxml import ParseResult
from barbershop_tracks.models import EndingClose, TransitionKind
from xml_builders import attributes, measure, note, parse_text, score

pytestmark = pytest.mark.usefixtures("no_network")

WHOLE = note("C", 4, 8)  # one whole note at divisions=2


def bar(inner: str, location: str = "right") -> str:
    return f'<barline location="{location}">{inner}</barline>'


def start(number: str = "1", location: str = "left", text: str = "") -> str:
    return bar(f'<ending number="{number}" type="start">{text}</ending>', location)


def close(
    number: str = "1",
    kind: str = "stop",
    *,
    repeat: bool = False,
    times: str | None = None,
    location: str = "right",
) -> str:
    rep = ""
    if repeat:
        t = f' times="{times}"' if times is not None else ""
        rep = f'<repeat direction="backward"{t}/>'
    return bar(f'<ending number="{number}" type="{kind}"/>{rep}', location)


def fwd() -> str:
    return bar('<repeat direction="forward"/>', "left")


def m(number: int, *, pre: str = "", post: str = "", first: bool = False, step: str = "C") -> str:
    return measure(number, pre + note(step, 4, 8) + post, attrs=attributes() if first else "")


def run(tmp_path: Path, *parts: str) -> ParseResult:
    return parse_text(tmp_path, score(*parts))


def codes(result: ParseResult) -> list[str]:
    return [i.code for i in result.issues]


def order(result: ParseResult) -> list[int]:
    assert result.performed is not None
    return [p.source_index for p in result.performed.plan.played]


def standard(second: str = "2", kind: str = "discontinue") -> str:
    # |: 1 2 [1. 3 :| [2. 4 | 5
    return (
        m(1, pre=fwd(), first=True)
        + m(2)
        + m(3, pre=start("1"), post=close("1", "stop", repeat=True))
        + m(4, pre=start(second), post=close(second, kind))
        + m(5)
    )


# --- the accepted layouts --------------------------------------------------------------------


def test_a_first_and_second_ending(tmp_path: Path) -> None:
    result = run(tmp_path, standard())
    assert not result.issues, [str(i) for i in result.issues]
    assert order(result) == [0, 1, 2, 0, 1, 3, 4]


def test_the_literal_spans_are_source_facts_with_the_closing_kind(tmp_path: Path) -> None:
    result = run(tmp_path, standard())
    assert result.song is not None
    spans = result.song.ending_spans
    assert [(s.start_index, s.end_index, s.numbers, s.raw_number) for s in spans] == [
        (2, 2, (1,), "1"),
        (3, 3, (2,), "2"),
    ]
    assert [s.closing for s in spans] == [EndingClose.STOP, EndingClose.DISCONTINUE]


@pytest.mark.parametrize("kind", ["stop", "discontinue"])
def test_stop_and_discontinue_play_alike(tmp_path: Path, kind: str) -> None:
    result = run(tmp_path, standard(kind=kind))
    assert order(result) == [0, 1, 2, 0, 1, 3, 4]
    assert result.song is not None
    assert result.song.ending_spans[1].closing is EndingClose(kind)


def test_the_musescore_export_form_with_text_content_is_read(tmp_path: Path) -> None:
    body = (
        m(1, pre=fwd(), first=True)
        + m(2, pre=start("1", text="1."), post=close("1", repeat=True))
        + m(3, pre=start("2", text="2."), post=close("2", "discontinue"))
        + m(4)
    )
    result = run(tmp_path, body)
    assert not result.issues
    assert order(result) == [0, 1, 0, 2, 3]


def test_one_two_then_three_with_matching_times(tmp_path: Path) -> None:
    body = (
        m(1, pre=fwd(), first=True)
        + m(2)
        + m(3, pre=start("1, 2"), post=close("1, 2", repeat=True, times="3"))
        + m(4, pre=start("3"), post=close("3", "discontinue"))
        + m(5)
    )
    result = run(tmp_path, body)
    assert not result.issues, [str(i) for i in result.issues]
    assert order(result) == [0, 1, 2, 0, 1, 2, 0, 1, 3, 4]
    assert result.song is not None
    assert result.song.ending_spans[0].numbers == (1, 2)
    assert result.song.ending_spans[0].raw_number == "1, 2"


def test_three_endings_without_times(tmp_path: Path) -> None:
    body = (
        m(1, pre=fwd(), first=True)
        + m(2)
        + m(3, pre=start("1"), post=close("1", repeat=True))
        + m(4, pre=start("2"), post=close("2", repeat=True))
        + m(5, pre=start("3"), post=close("3", "discontinue"))
        + m(6)
    )
    assert order(run(tmp_path, body)) == [0, 1, 2, 0, 1, 3, 0, 1, 4, 5]


def test_a_multi_measure_ending(tmp_path: Path) -> None:
    body = (
        m(1, pre=fwd(), first=True)
        + m(2, pre=start("1"))
        + m(3, post=close("1", repeat=True))
        + m(4, pre=start("2"))
        + m(5, post=close("2", "discontinue"))
        + m(6)
    )
    result = run(tmp_path, body)
    assert not result.issues
    assert order(result) == [0, 1, 2, 0, 3, 4, 5]


def test_ending_context_is_recorded_on_the_played_measures(tmp_path: Path) -> None:
    result = run(tmp_path, standard())
    assert result.performed is not None
    played = result.performed.plan.played
    assert [m.endings for m in played] == [(), (), (1,), (), (), (2,), ()]
    assert [m.repeat_pass for m in played] == [1, 1, 1, 2, 2, 2, None]
    assert played[5].arrival is TransitionKind.ENDING_SKIP
    assert played[6].arrival is TransitionKind.REPEAT_EXIT


def test_the_source_song_is_not_changed_by_planning(tmp_path: Path) -> None:
    result = run(tmp_path, standard())
    assert result.song is not None
    before = copy.deepcopy(result.song)
    assert result.performed is not None
    assert result.performed.song is result.song
    assert result.song == before
    assert [e.start for e in result.song.parts[0].events] == [0, 4, 8, 12, 16]
    performed = [e.start for e in result.performed.lines[0].part.events]
    assert performed == [0, 4, 8, 12, 16, 20, 24]


def test_exact_pickup_timing_with_endings(tmp_path: Path) -> None:
    pickup = measure(0, note("C", 4, 2), attrs=attributes(), implicit=True)  # one quarter note
    body = (
        pickup
        + m(1)
        + measure(
            2,
            start("1") + note("C", 4, 6) + close("1", repeat=True),
            implicit=True,
        )
        + measure(3, start("2") + note("C", 4, 6) + close("2", "discontinue"), implicit=True)
        + m(4)
    )
    result = run(tmp_path, body)
    assert not result.issues.has_errors, [str(i) for i in result.issues]
    assert order(result) == [0, 1, 2, 0, 1, 3, 4]  # no forward repeat: back to the pickup
    assert result.performed is not None
    starts = [p.performed_start for p in result.performed.plan.played]
    assert [int(s) for s in starts] == [0, 1, 5, 8, 9, 13, 16]


# --- number errors ------------------------------


def with_number(number: str | None) -> str:
    if number is None:
        first = bar('<ending type="start"/>', "left")
        last = bar('<ending type="stop"/><repeat direction="backward"/>')
    else:
        first, last = start(number), close(number, repeat=True)
    return (
        m(1, pre=fwd(), first=True)
        + m(2)
        + m(3, pre=first, post=last)
        + m(4, pre=start("2"), post=close("2", "discontinue"))
    )


@pytest.mark.parametrize(
    "number", ["x", "0", "-1", "1-2", "01", "1,1", "1 ,2", "1.5", "1,,2", "2,"]
)
def test_invalid_numbers_are_errors_and_never_repaired(tmp_path: Path, number: str) -> None:
    result = run(tmp_path, with_number(number))
    assert "ENDING_NUMBER_INVALID" in codes(result)
    assert result.issues.has_errors
    assert result.performed is not None
    assert result.performed.plan.is_identity
    assert result.song is not None
    assert result.song.ending_spans == ()  # never turned into a span


def test_a_missing_number_is_an_error(tmp_path: Path) -> None:
    assert "ENDING_NUMBER_INVALID" in codes(run(tmp_path, with_number(None)))


def test_a_spaces_only_number_is_unusable(tmp_path: Path) -> None:
    result = run(tmp_path, with_number("  "))
    assert "ENDING_NUMBER_UNSPECIFIED" in codes(result)
    assert result.issues.has_errors


@pytest.mark.parametrize("number", ["1,2", "1, 2", " 1 "])
def test_valid_number_spellings_are_read(tmp_path: Path, number: str) -> None:
    result = run(tmp_path, with_number(number))
    assert "ENDING_NUMBER_INVALID" not in codes(result)


def test_an_unknown_type_is_an_error(tmp_path: Path) -> None:
    bad = bar('<ending number="1" type="sideways"/>', "left")
    result = run(tmp_path, m(1, pre=bad, first=True) + m(2))
    assert "ENDING_TYPE_INVALID" in codes(result)


# --- placement and pairing ---------------------------------------------------------------------


def test_a_start_at_the_right_barline_is_refused_not_moved(tmp_path: Path) -> None:
    body = (
        m(1, pre=fwd(), first=True)
        + m(2, post=bar('<ending number="1" type="start"/>'))
        + m(3, post=close("1", repeat=True))
        + m(4, pre=start("2"), post=close("2", "discontinue"))
    )
    result = run(tmp_path, body)
    assert "ENDING_BARLINE_PLACEMENT" in codes(result)
    assert result.performed is not None
    assert result.performed.plan.is_identity


def test_a_stop_at_the_left_barline_is_refused(tmp_path: Path) -> None:
    body = m(1, pre=start("1"), first=True) + m(2, pre=close("1", location="left"))
    assert "ENDING_BARLINE_PLACEMENT" in codes(run(tmp_path, body))


def test_an_ending_marker_in_the_middle_of_a_measure_is_refused(tmp_path: Path) -> None:
    middle = bar('<ending number="1" type="stop"/>', "middle")
    assert "ENDING_MID_MEASURE" in codes(run(tmp_path, m(1, post=middle, first=True)))
    more = measure(1, WHOLE + close("1") + note("D", 4, 8), attrs=attributes(time=(8, 4)))
    result = run(tmp_path, more)
    assert "ENDING_MID_MEASURE" in codes(result)


def test_a_start_after_the_notes_is_mid_measure(tmp_path: Path) -> None:
    body = m(1, post=start("1"), first=True) + m(2, post=close("1"))
    assert "ENDING_MID_MEASURE" in codes(run(tmp_path, body))


def test_a_start_that_is_never_closed(tmp_path: Path) -> None:
    body = m(1, pre=fwd(), first=True) + m(2, pre=start("1")) + m(3)
    result = run(tmp_path, body)
    assert "ENDING_UNCLOSED" in codes(result)
    assert result.performed is not None
    assert result.performed.plan.is_identity


def test_a_stop_without_a_start(tmp_path: Path) -> None:
    body = m(1, first=True) + m(2, post=close("1", repeat=True))
    assert "ENDING_STOP_WITHOUT_START" in codes(run(tmp_path, body))


def test_a_discontinue_without_a_start(tmp_path: Path) -> None:
    body = m(1, first=True) + m(2, post=close("2", "discontinue"))
    assert "ENDING_STOP_WITHOUT_START" in codes(run(tmp_path, body))


def test_overlapping_spans(tmp_path: Path) -> None:
    body = m(1, pre=start("1"), first=True) + m(2, pre=start("2")) + m(3, post=close("2"))
    assert "ENDING_OVERLAP" in codes(run(tmp_path, body))


def test_a_closing_number_that_differs_from_the_opening_one(tmp_path: Path) -> None:
    body = m(1, pre=start("1"), first=True) + m(2, post=close("2"))
    assert "ENDING_NUMBER_MISMATCH" in codes(run(tmp_path, body))


# --- structure errors surfaced through the parser -------------------------------------------------


def volta(first: str, second: str, *, repeat_on_first: bool = True) -> str:
    return (
        m(1, pre=fwd(), first=True)
        + m(2)
        + m(3, pre=start(first), post=close(first, repeat=repeat_on_first))
        + m(4, pre=start(second), post=close(second, "discontinue"))
    )


def test_a_duplicate_pass(tmp_path: Path) -> None:
    assert "ENDING_PASS_DUPLICATE" in codes(run(tmp_path, volta("1", "1, 2")))


def test_a_missing_pass(tmp_path: Path) -> None:
    result = run(tmp_path, volta("1", "3"))
    assert "ENDING_PASS_MISSING" in codes(result)
    assert result.performed is not None
    assert result.performed.plan.is_identity


def test_an_ending_with_no_valid_repeat_path(tmp_path: Path) -> None:
    result = run(tmp_path, volta("1", "2", repeat_on_first=False))
    assert "ENDING_WITHOUT_REPEAT" in codes(result)
    assert result.performed is not None
    assert result.performed.plan.is_identity  # never A B C and then silently dropping the rest


def test_a_lone_ending_with_its_own_backward_repeat(tmp_path: Path) -> None:
    body = (
        m(1, pre=fwd(), first=True)
        + m(2, pre=start("1, 2"), post=close("1, 2", repeat=True))
        + m(3)
    )
    result = run(tmp_path, body)
    assert "ENDING_STRUCTURE_UNSUPPORTED" in codes(result)
    assert result.performed is not None
    assert result.performed.plan.is_identity  # not looped as a plain repeat


def test_times_that_contradicts_the_endings(tmp_path: Path) -> None:
    body = (
        m(1, pre=fwd(), first=True)
        + m(2)
        + m(3, pre=start("1"), post=close("1", repeat=True, times="3"))
        + m(4, pre=start("2"), post=close("2", "discontinue"))
    )
    assert "REPEAT_TIMES_ENDINGS_CONFLICT" in codes(run(tmp_path, body))


def test_the_expansion_cap_with_endings_is_an_error_not_a_truncation(tmp_path: Path) -> None:
    numbers = ",".join(str(n) for n in range(1, 16))
    body = m(1, pre=fwd(), first=True) + "".join(m(n) for n in range(2, 700))
    body += m(700, pre=start(numbers), post=close(numbers, repeat=True))
    body += m(701, pre=start("16"), post=close("16", "discontinue"))
    result = run(tmp_path, body)
    assert "REPEAT_EXPANSION_TOO_LARGE" in codes(result)
    assert result.performed is not None
    assert len(result.performed.plan.played) == 701  # the written song


def test_jump_markers_are_still_unsupported_next_to_endings(tmp_path: Path) -> None:
    direction = (
        "<direction><direction-type><words>D.S.</words></direction-type>"
        '<sound dalsegno="x"/></direction>'
    )
    body = m(1, pre=fwd(), post=direction, first=True) + m(2)
    assert "UNSUPPORTED_JUMP" in codes(run(tmp_path, body))


# --- several parts ------------------------------


def test_parts_with_the_same_endings_share_one_plan(tmp_path: Path) -> None:
    result = run(tmp_path, standard(), standard(kind="stop"))  # only the engraving differs
    assert not result.issues, [str(i) for i in result.issues]
    assert order(result) == [0, 1, 2, 0, 1, 3, 4]


def test_parts_that_disagree_about_endings_conflict(tmp_path: Path) -> None:
    other = (
        m(1, pre=fwd(), first=True)
        + m(2)
        + m(3, pre=start("1"), post=close("1", repeat=True))
        + m(4, pre=start("2"), post=close("2", "discontinue"))
        + m(5)
    )
    different = other.replace('number="2"', 'number="2, 3"')  # a different pass set
    result = run(tmp_path, standard(), different)
    assert "REPEAT_STRUCTURE_CONFLICT" in codes(result)
    assert result.performed is not None
    assert result.performed.plan.is_identity


def test_a_part_without_endings_conflicts_with_one_that_has_them(tmp_path: Path) -> None:
    plain = (
        m(1, pre=fwd(), first=True)
        + m(2)
        + m(3, post=bar('<repeat direction="backward"/>'))
        + m(4)
        + m(5)
    )
    result = run(tmp_path, standard(), plain)
    assert "REPEAT_STRUCTURE_CONFLICT" in codes(result)
    assert result.song is not None
    assert result.song.ending_spans == ()  # no part is authoritative


def test_a_broken_ending_in_one_part_blocks_the_structure_of_all(tmp_path: Path) -> None:
    broken = standard().replace('number="2" type="discontinue"', 'number="x" type="discontinue"')
    result = run(tmp_path, standard(), broken)
    assert "ENDING_NUMBER_INVALID" in codes(result)
    assert result.song is not None
    assert result.song.repeat_marks == ()
    assert result.song.ending_spans == ()


def test_planning_leaves_every_literal_fact_of_the_song_unchanged(tmp_path: Path) -> None:
    tempo = (
        "<direction><direction-type><words>t</words></direction-type>"
        '<sound tempo="90"/></direction>'
    )
    body = (
        m(1, pre=fwd(), first=True, post=tempo)
        + m(2)
        + m(3, pre=start("1"), post=close("1", repeat=True))
        + measure(
            4,
            start("2")
            + "<attributes><time><beats>3</beats><beat-type>4</beat-type></time></attributes>"
            + note("C", 4, 6)
            + close("2", "discontinue"),
        )
        + m(5)
    )
    result = run(tmp_path, body)
    assert result.song is not None
    song = result.song
    before = copy.deepcopy(song)
    assert result.performed is not None
    assert result.performed.song is song
    assert song == before
    assert song.measures == before.measures
    assert song.repeat_marks == before.repeat_marks
    assert song.ending_spans == before.ending_spans
    assert song.tempo_map == before.tempo_map
    assert song.time_signatures == before.time_signatures
    assert song.parts == before.parts
    assert len(song.ending_spans) == 2
    assert len(song.time_signatures) == 2
