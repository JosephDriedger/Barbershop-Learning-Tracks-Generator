"""Reading repeat signs from MusicXML and expanding them (M3d1), on hand-written scores."""

from fractions import Fraction
from pathlib import Path

import pytest

from barbershop_tracks.core.musicxml import ParseResult
from barbershop_tracks.models import RepeatKind, TransitionKind
from xml_builders import attributes, measure, note, parse_text, score

pytestmark = pytest.mark.usefixtures("no_network")

WHOLE = note("C", 4, 8)  # one whole note at divisions=2


def bar(inner: str, location: str | None = "right") -> str:
    where = f' location="{location}"' if location is not None else ""
    return f"<barline{where}>{inner}</barline>"


def forward(location: str | None = "left") -> str:
    return bar('<repeat direction="forward"/>', location)


def backward(times: str | None = None, location: str | None = "right", extra: str = "") -> str:
    t = f' times="{times}"' if times is not None else ""
    return bar(f'<repeat direction="backward"{t}{extra}/>', location)


def m(number: int | str, *, pre: str = "", post: str = "", first: bool = False, **kw: bool) -> str:
    return measure(number, pre + WHOLE + post, attrs=attributes() if first else "", **kw)


def parse(tmp_path: Path, *parts: str) -> ParseResult:
    return parse_text(tmp_path, score(*parts))


def codes(result: ParseResult) -> list[str]:
    return [i.code for i in result.issues]


def order(result: ParseResult) -> list[int]:
    assert result.performed is not None
    return [p.source_index for p in result.performed.plan.played]


def simple(*, times: str | None = None) -> str:
    return m(1, pre=forward(), first=True) + m(2, post=backward(times)) + m(3)


# --- accepted structures ---------------------------------------------------------------------


def test_forward_and_backward_expand_to_two_passes(tmp_path: Path) -> None:
    result = parse(tmp_path, simple())
    assert not result.issues, [str(i) for i in result.issues]
    assert order(result) == [0, 1, 0, 1, 2]
    assert result.song is not None
    assert [(k.kind, k.measure_index, k.times) for k in result.song.repeat_marks] == [
        (RepeatKind.FORWARD, 0, None),
        (RepeatKind.BACKWARD, 1, None),
    ]


def test_the_source_song_stays_literal(tmp_path: Path) -> None:
    result = parse(tmp_path, simple(times="3"))
    assert result.song is not None
    assert [e.start for e in result.song.parts[0].events] == [0, 4, 8]
    assert result.performed is not None
    assert result.performed.song is result.song
    assert [e.start for e in result.performed.lines[0].part.events] == [0, 4, 8, 12, 16, 20, 24]


@pytest.mark.parametrize("times", ["2", "3", "4", "9", "16"])
def test_times_is_the_total_number_of_passes(tmp_path: Path, times: str) -> None:
    result = parse(tmp_path, simple(times=times))
    assert order(result) == [0, 1] * int(times) + [2]
    assert not result.issues


def test_absent_times_is_two_passes_and_equals_an_explicit_two(tmp_path: Path) -> None:
    assert order(parse(tmp_path, simple())) == order(parse(tmp_path, simple(times="2")))


def test_times_one_is_one_pass_with_a_warning(tmp_path: Path) -> None:
    result = parse(tmp_path, simple(times="1"))
    assert order(result) == [0, 1, 2]
    assert codes(result) == ["REPEAT_TIMES_ONE"]
    assert not result.issues.has_errors


def test_a_backward_repeat_without_a_forward_returns_to_the_score_start(tmp_path: Path) -> None:
    body = m(1, first=True) + m(2) + m(3, post=backward()) + m(4)
    result = parse(tmp_path, body)
    assert order(result) == [0, 1, 2, 0, 1, 2, 3]
    assert not result.issues


def test_a_pickup_returns_to_the_pickup_with_exact_positions(tmp_path: Path) -> None:
    pickup = measure(0, note("C", 4, 2), attrs=attributes(), implicit=True)  # one quarter note
    body = (
        pickup
        + m(1)
        + measure(2, note("C", 4, 6) + backward(), implicit=True)  # the 3-beat remainder
        + m(3)
    )
    result = parse(tmp_path, body)
    assert not result.issues.has_errors, [str(i) for i in result.issues]
    assert order(result) == [0, 1, 2, 0, 1, 2, 3]
    assert result.performed is not None
    plan = result.performed.plan
    assert [p.performed_start for p in plan.played] == [0, 1, 5, 8, 9, 13, 16]
    assert plan.played[3].arrival is TransitionKind.REPEAT_JUMP
    assert plan.end == 20
    assert result.song is not None
    assert [s.length for s in result.song.measures] == [1, 4, 3, 4]
    assert [s.implicit for s in result.song.measures] == [True, False, True, False]
    assert result.song.measures[0].number == 0


def test_an_unused_forward_plays_through_with_one_warning(tmp_path: Path) -> None:
    result = parse(tmp_path, m(1, first=True) + m(2, pre=forward()) + m(3))
    assert order(result) == [0, 1, 2]
    assert codes(result) == ["REPEAT_FORWARD_UNUSED"]
    assert not result.issues.has_errors


def test_consecutive_repeats(tmp_path: Path) -> None:
    body = (
        m(1, pre=forward(), post=backward(), first=True)
        + m(2, pre=forward(), post=backward("3"))
        + m(3)
    )
    assert order(parse(tmp_path, body)) == [0, 0, 1, 1, 1, 2]


def test_the_measure_table_keeps_raw_numbers_and_never_uses_them_as_identity(
    tmp_path: Path,
) -> None:
    body = (
        measure("X1", WHOLE + backward(), attrs=attributes())
        + measure("X1", WHOLE)  # the same label twice
        + measure("0", WHOLE)
    )
    result = parse(tmp_path, body)
    assert result.song is not None
    assert [s.raw_number for s in result.song.measures] == ["X1", "X1", "0"]
    assert [s.index for s in result.song.measures] == [0, 1, 2]
    assert order(result) == [0, 0, 1, 2]
    assert "MEASURE_NUMBER_NONNUMERIC" in codes(result)


# --- invalid and unsupported signs -------------------------------------------------------------


@pytest.mark.parametrize("times", ["0", "-1", "1.5", "x", "", " ", "2e1"])
def test_invalid_times_is_an_error_and_never_coerced(tmp_path: Path, times: str) -> None:
    result = parse(tmp_path, simple(times=times))
    assert "REPEAT_TIMES_INVALID" in codes(result)
    assert result.issues.has_errors
    assert result.performed is not None
    assert result.performed.plan.is_identity  # not silently turned into a repeat


def test_excessive_times_is_an_error(tmp_path: Path) -> None:
    assert "REPEAT_TIMES_EXCESSIVE" in codes(parse(tmp_path, simple(times="17")))


def test_times_on_a_forward_is_ignored_with_a_warning(tmp_path: Path) -> None:
    sign = bar('<repeat direction="forward" times="5"/>', "left")
    result = parse(tmp_path, m(1, pre=sign, first=True) + m(2, post=backward()))
    assert "REPEAT_TIMES_IGNORED" in codes(result)
    assert order(result) == [0, 1, 0, 1]


@pytest.mark.parametrize(
    ("sign", "code"),
    [
        (forward("right"), "REPEAT_BARLINE_PLACEMENT"),
        (forward(None), "REPEAT_BARLINE_PLACEMENT"),  # location defaults to right
        (backward(location="left"), "REPEAT_BARLINE_PLACEMENT"),
        (forward("middle"), "REPEAT_MID_MEASURE"),
        (backward(location="middle"), "REPEAT_MID_MEASURE"),
        (bar('<repeat direction="sideways"/>'), "REPEAT_DIRECTION_INVALID"),
        (bar("<repeat/>"), "REPEAT_DIRECTION_INVALID"),
        (backward(extra=' after-jump="yes"'), "REPEAT_AFTER_JUMP_UNSUPPORTED"),
    ],
)
def test_signs_outside_the_supported_subset_are_errors(
    tmp_path: Path, sign: str, code: str
) -> None:
    result = parse(tmp_path, m(1, post=sign, first=True) + m(2))
    assert code in codes(result)
    assert result.issues.has_errors
    assert result.performed is not None
    assert result.performed.plan.is_identity  # never reinterpreted onto the containing measure


def test_a_forward_after_the_notes_is_mid_measure(tmp_path: Path) -> None:
    result = parse(tmp_path, m(1, post=forward("left"), first=True) + m(2, post=backward()))
    assert "REPEAT_MID_MEASURE" in codes(result)


def test_a_backward_followed_by_more_notes_is_mid_measure(tmp_path: Path) -> None:
    body = measure(1, WHOLE + backward() + note("D", 4, 8), attrs=attributes(time=(8, 4)))
    result = parse(tmp_path, body)
    assert "REPEAT_MID_MEASURE" in codes(result)


def test_nested_repeats_are_an_error(tmp_path: Path) -> None:
    body = (
        m(1, pre=forward(), first=True)
        + m(2, pre=forward())
        + m(3, post=backward())
        + m(4, post=backward())
    )
    result = parse(tmp_path, body)
    assert "REPEAT_NESTED_UNSUPPORTED" in codes(result)
    assert result.issues.has_errors


def test_a_second_bare_backward_is_ambiguous(tmp_path: Path) -> None:
    body = m(1, first=True) + m(2, post=backward()) + m(3) + m(4, post=backward())
    result = parse(tmp_path, body)
    assert "REPEAT_START_AMBIGUOUS" in codes(result)
    assert result.issues.has_errors


def test_a_bad_ending_beside_a_repeat_leaves_the_whole_structure_unexpanded(
    tmp_path: Path,
) -> None:
    ending = bar('<ending number="x" type="stop"/><repeat direction="backward"/>')
    result = parse(tmp_path, m(1, pre=forward(), first=True) + m(2, post=ending) + m(3))
    assert "ENDING_NUMBER_INVALID" in codes(result)
    assert result.song is not None
    assert result.song.repeat_marks == ()  # no partial reading of a structure with a bad ending
    assert result.song.ending_spans == ()
    assert result.performed is not None
    assert result.performed.plan.is_identity


def test_jump_markers_are_still_unsupported(tmp_path: Path) -> None:
    direction = (
        "<direction><direction-type><words>D.C.</words></direction-type>"
        '<sound dacapo="yes"/></direction>'
    )
    result = parse(tmp_path, measure(1, WHOLE + direction, attrs=attributes()))
    assert "UNSUPPORTED_JUMP" in codes(result)


# --- several parts ---------------------------------------------------------------------------


def test_parts_with_the_same_structure_share_one_plan(tmp_path: Path) -> None:
    result = parse(tmp_path, simple(), simple(times="2"))  # absent times equals an explicit 2
    assert not result.issues, [str(i) for i in result.issues]
    assert order(result) == [0, 1, 0, 1, 2]
    assert result.performed is not None
    a, b = result.performed.lines
    assert [e.start for e in a.part.events] == [e.start for e in b.part.events]


@pytest.mark.parametrize(
    "other",
    [
        m(1, first=True) + m(2) + m(3),  # no marks at all
        simple(times="3"),  # different pass count
        m(1, first=True) + m(2, pre=forward()) + m(3, post=backward()),  # different range
        m(1, pre=forward(), first=True) + m(2) + m(3, post=backward()),
    ],
)
def test_parts_with_different_structures_conflict(tmp_path: Path, other: str) -> None:
    result = parse(tmp_path, simple(), other)
    assert "REPEAT_STRUCTURE_CONFLICT" in codes(result)
    assert result.issues.has_errors
    assert result.song is not None
    assert result.song.repeat_marks == ()
    assert result.performed is not None
    assert result.performed.plan.is_identity  # never expanded onto incompatible timelines


def test_equal_measure_counts_do_not_make_structures_equal(tmp_path: Path) -> None:
    only_second = m(1, first=True) + m(2, pre=forward(), post=backward()) + m(3)
    result = parse(tmp_path, simple(), only_second)
    assert "REPEAT_STRUCTURE_CONFLICT" in codes(result)


def test_marks_on_mismatched_part_lengths_are_not_guessed_at(tmp_path: Path) -> None:
    result = parse(tmp_path, simple(), m(1, pre=forward(), first=True) + m(2, post=backward()))
    assert "PART_MEASURE_COUNT_MISMATCH" in codes(result)
    assert result.song is not None
    assert result.song.repeat_marks == ()


def test_a_score_without_repeats_is_unchanged(tmp_path: Path) -> None:
    result = parse(tmp_path, m(1, first=True) + m(2))
    assert not result.issues
    assert result.performed is not None
    assert result.performed.plan.is_identity
    assert result.song is not None
    assert result.performed.lines[0].part.events == result.song.parts[0].events
    assert Fraction(0) == result.performed.plan.played[0].performed_start


# --- invariants worth pinning ------------------------------------------------------------------


def test_a_failed_repeat_structure_is_never_a_clean_repeat_free_score(tmp_path: Path) -> None:
    broken = parse(tmp_path, m(1, post=forward("right"), first=True) + m(2, post=backward()))
    clean = parse(tmp_path, m(1, first=True) + m(2))
    assert broken.performed is not None
    assert clean.performed is not None
    assert broken.performed.plan.is_identity
    assert clean.performed.plan.is_identity  # the plans look alike ...
    assert broken.issues.has_errors  # ... but the ERROR stays reachable through the result
    assert not clean.issues
    assert "REPEAT_BARLINE_PLACEMENT" in codes(broken)


def test_the_expansion_cap_is_an_error_not_a_shortened_song(tmp_path: Path) -> None:
    body = m(1, pre=forward(), first=True)
    body += "".join(m(n) for n in range(2, 700)) + m(700, post=backward("16"))
    result = parse(tmp_path, body)
    assert "REPEAT_EXPANSION_TOO_LARGE" in codes(result)
    assert result.performed is not None
    assert result.performed.plan.is_identity
    assert len(result.performed.plan.played) == 700  # the written song, not a truncation


def test_a_repeated_source_note_maps_each_copy_to_its_own_occurrence(tmp_path: Path) -> None:
    result = parse(tmp_path, simple(times="3"))
    assert result.performed is not None
    line = result.performed.lines[0]
    first_measure = [
        (e, line.occurrence_of(e))
        for e in line.part.events
        if line.occurrence_of(e).measure_index == 0
    ]
    assert [o.visit for _, o in first_measure] == [1, 2, 3]
    assert [o.source_event_index for _, o in first_measure] == [0, 0, 0]  # one source note
    assert [o.performed_start for _, o in first_measure] == [0, 8, 16]
    assert len({id(e) for e, _ in first_measure}) == 3
