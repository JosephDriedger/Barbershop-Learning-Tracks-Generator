"""Volta groups and ending-aware planning, on hand-built measure tables (M3e1)."""

from fractions import Fraction

import pytest

from barbershop_tracks.core.timeline import plan_performance
from barbershop_tracks.core.timeline.repeats import MAX_PERFORMED_MEASURES
from barbershop_tracks.models import (
    EndingClose,
    EndingSpan,
    MeasureSpan,
    PerformancePlan,
    RepeatKind,
    RepeatMark,
    Severity,
    TransitionKind,
)

T = TransitionKind


def table(count: int, length: int = 4) -> list[MeasureSpan]:
    return [
        MeasureSpan(index=i, number=i + 1, start=Fraction(i * length), length=Fraction(length))
        for i in range(count)
    ]


def fwd(index: int) -> RepeatMark:
    return RepeatMark(kind=RepeatKind.FORWARD, measure_index=index)


def back(index: int, times: int | None = None) -> RepeatMark:
    return RepeatMark(kind=RepeatKind.BACKWARD, measure_index=index, times=times)


def ending(
    start: int, end: int, *numbers: int, closing: EndingClose = EndingClose.STOP
) -> EndingSpan:
    return EndingSpan(start_index=start, end_index=end, numbers=numbers, closing=closing)


def order(plan: PerformancePlan) -> list[int]:
    return [m.source_index for m in plan.played]


def codes(result) -> list[str]:  # type: ignore[no-untyped-def]
    return [i.code for i in result.issues]


# |: 0 1 [1. 2 :| [2. 3 | 4
STANDARD = ([fwd(0), back(2)], [ending(2, 2, 1), ending(3, 3, 2, closing=EndingClose.DISCONTINUE)])


def test_a_first_and_second_ending() -> None:
    marks, spans = STANDARD
    result = plan_performance(table(5), marks, spans)
    assert order(result.plan) == [0, 1, 2, 0, 1, 3, 4]
    assert not result.issues


def test_transitions_and_contexts_of_the_standard_layout() -> None:
    marks, spans = STANDARD
    played = plan_performance(table(5), marks, spans).plan.played
    assert [m.arrival for m in played] == [
        T.START,
        T.SEQUENTIAL,
        T.SEQUENTIAL,  # the first ending is written right after the body
        T.REPEAT_JUMP,
        T.SEQUENTIAL,
        T.ENDING_SKIP,  # the second ending: the first one was skipped
        T.REPEAT_EXIT,  # leaving the last ending keeps written adjacency
    ]
    assert [m.repeat_pass for m in played] == [1, 1, 1, 2, 2, 2, None]
    assert [m.endings for m in played] == [(), (), (1,), (), (), (2,), ()]


def test_the_closing_kind_does_not_change_the_route_but_is_preserved() -> None:
    stop = plan_performance(table(5), [fwd(0), back(2)], [ending(2, 2, 1), ending(3, 3, 2)])
    disc = plan_performance(
        table(5),
        [fwd(0), back(2)],
        [ending(2, 2, 1, closing=EndingClose.DISCONTINUE), ending(3, 3, 2)],
    )
    assert order(stop.plan) == order(disc.plan)
    assert ending(2, 2, 1, closing=EndingClose.DISCONTINUE).closing is EndingClose.DISCONTINUE


def test_a_multi_measure_first_ending() -> None:
    # |: 0 1 [1. 2 3 :| [2. 4 | 5
    result = plan_performance(table(6), [fwd(0), back(3)], [ending(2, 3, 1), ending(4, 4, 2)])
    assert order(result.plan) == [0, 1, 2, 3, 0, 1, 4, 5]
    assert not result.issues


def test_a_multi_measure_second_ending() -> None:
    # |: 0 1 [1. 2 :| [2. 3 4 | 5
    result = plan_performance(table(6), [fwd(0), back(2)], [ending(2, 2, 1), ending(3, 4, 2)])
    assert order(result.plan) == [0, 1, 2, 0, 1, 3, 4, 5]
    assert not result.issues


def test_endings_one_two_then_three() -> None:
    # |: 0 1 [1,2. 2 :| [3. 3 | 4  (the pass set {1,2} then {3}); times=3 agrees
    result = plan_performance(table(5), [fwd(0), back(2, 3)], [ending(2, 2, 1, 2), ending(3, 3, 3)])
    assert order(result.plan) == [0, 1, 2, 0, 1, 2, 0, 1, 3, 4]
    played = result.plan.played
    assert [m.repeat_pass for m in played][:9] == [1, 1, 1, 2, 2, 2, 3, 3, 3]
    assert [m.endings for m in played if m.source_index == 2] == [(1, 2), (1, 2)]


def test_three_separate_endings() -> None:
    # |: 0 1 [1. 2 :| [2. 3 :| [3. 4 | 5
    marks = [fwd(0), back(2), back(3)]
    spans = [ending(2, 2, 1), ending(3, 3, 2), ending(4, 4, 3)]
    result = plan_performance(table(6), marks, spans)
    assert order(result.plan) == [0, 1, 2, 0, 1, 3, 0, 1, 4, 5]
    assert [m.arrival for m in result.plan.played][5] is T.ENDING_SKIP
    assert [m.arrival for m in result.plan.played][8] is T.ENDING_SKIP


def test_four_and_sixteen_passes_are_supported() -> None:
    n = 4
    spans = [ending(2 + k, 2 + k, k + 1) for k in range(n)]
    marks = [fwd(0)] + [back(2 + k) for k in range(n - 1)]
    result = plan_performance(table(2 + n + 1), marks, spans)
    assert not result.issues
    assert [m.repeat_pass for m in result.plan.played if m.source_index < 2] == [
        1,
        1,
        2,
        2,
        3,
        3,
        4,
        4,
    ]
    first = ending(2, 2, *range(1, 16))
    last = ending(3, 3, 16)
    sixteen = plan_performance(table(5), [fwd(0), back(2)], [first, last])
    assert not sixteen.issues
    assert len(sixteen.plan.played) == 2 * 16 + 15 + 1 + 1


def test_the_route_is_deterministic_when_numbers_are_not_in_source_order() -> None:
    # [2. 2 :| [1,3?]: endings written {2} then {1}? not allowed: the last must be {N}
    ok = plan_performance(
        table(6),
        [fwd(0), back(2), back(3)],
        [ending(2, 2, 2), ending(3, 3, 1), ending(4, 4, 3)],
    )
    assert not ok.issues
    assert order(ok.plan) == [0, 1, 3, 0, 1, 2, 0, 1, 4, 5]  # pass 1 skips the written-first ending
    assert [m.arrival for m in ok.plan.played][2] is T.ENDING_SKIP


def test_a_bare_backward_start_is_the_score_start() -> None:
    result = plan_performance(table(4), [back(1)], [ending(1, 1, 1), ending(2, 2, 2)])
    assert not result.issues
    assert order(result.plan) == [0, 1, 0, 2, 3]


def test_two_volta_groups_in_sequence() -> None:
    # |: 0 [1. 1 :| [2. 2 | |: 3 [1. 4 :| [2. 5 | 6
    marks = [fwd(0), back(1), fwd(3), back(4)]
    spans = [ending(1, 1, 1), ending(2, 2, 2), ending(4, 4, 1), ending(5, 5, 2)]
    result = plan_performance(table(7), marks, spans)
    assert not result.issues
    assert order(result.plan) == [0, 1, 0, 2, 3, 4, 3, 5, 6]
    assert [m.arrival for m in result.plan.played][4] is T.REPEAT_EXIT  # group two starts after


def test_a_plain_repeat_and_a_group_can_follow_each_other() -> None:
    marks = [fwd(0), back(0), fwd(2), back(3)]
    spans = [ending(3, 3, 1), ending(4, 4, 2)]
    result = plan_performance(table(6), marks, spans)
    assert not result.issues
    assert order(result.plan) == [0, 0, 1, 2, 3, 2, 4, 5]


def test_pickup_timing_is_exact_with_endings() -> None:
    spans = [
        MeasureSpan(index=0, number=0, start=Fraction(0), length=Fraction(1), implicit=True),
        MeasureSpan(index=1, number=1, start=Fraction(1), length=Fraction(4)),
        MeasureSpan(index=2, number=2, start=Fraction(5), length=Fraction(3), implicit=True),
        MeasureSpan(index=3, number=3, start=Fraction(8), length=Fraction(3), implicit=True),
        MeasureSpan(index=4, number=4, start=Fraction(11), length=Fraction(4)),
    ]
    result = plan_performance(
        spans, [back(2)], [ending(2, 2, 1), ending(3, 3, 2)]
    )  # bare repeat: back to the pickup
    assert not result.issues
    plan = result.plan
    assert order(plan) == [0, 1, 2, 0, 1, 3, 4]
    assert [m.performed_start for m in plan.played] == [0, 1, 5, 8, 9, 13, 16]
    assert plan.end == 20


def test_visit_and_repeat_pass_are_different_things() -> None:
    marks, spans = [fwd(0), back(2, 3)], [ending(2, 2, 1, 2), ending(3, 3, 3)]
    played = plan_performance(table(5), marks, spans).plan.played
    ending_one_two = [m for m in played if m.source_index == 2]
    assert [(m.visit, m.repeat_pass) for m in ending_one_two] == [(1, 1), (2, 2)]
    last = next(m for m in played if m.source_index == 3)
    assert (last.visit, last.repeat_pass, last.endings) == (1, 3, (3,))  # played once, on pass 3
    after = played[-1]
    assert (after.source_index, after.repeat_pass, after.endings) == (4, None, ())


def test_discontinuities_include_ending_skips_but_not_exits() -> None:
    marks, spans = STANDARD
    plan = plan_performance(table(5), marks, spans).plan
    assert plan.jump_positions == {Fraction(12)}  # the repeat jump only
    assert plan.discontinuity_positions == {Fraction(12), Fraction(20)}  # plus the ending skip


# --- rejected structures ------------------------------------------------------------------------


def rejected(marks: list[RepeatMark], spans: list[EndingSpan], count: int = 6):  # type: ignore[no-untyped-def]
    result = plan_performance(table(count), marks, spans)
    assert result.plan.is_identity  # the written order, never a partial expansion
    assert result.issues.has_errors
    assert all(i.severity is Severity.ERROR for i in result.issues)
    return codes(result)


def test_a_duplicated_pass_is_rejected() -> None:
    assert rejected([fwd(0), back(2)], [ending(2, 2, 1), ending(3, 3, 1, 2)]) == [
        "ENDING_PASS_DUPLICATE"
    ]


def test_a_missing_pass_is_rejected_and_nothing_is_renumbered() -> None:
    assert rejected([fwd(0), back(2)], [ending(2, 2, 1), ending(3, 3, 3)]) == [
        "ENDING_PASS_MISSING"
    ]
    assert rejected([fwd(0), back(2)], [ending(2, 2, 2), ending(3, 3, 3)]) == [
        "ENDING_PASS_MISSING"
    ]


def test_a_non_last_ending_without_a_backward_repeat_is_rejected() -> None:
    assert rejected([fwd(0)], [ending(2, 2, 1), ending(3, 3, 2)]) == ["ENDING_WITHOUT_REPEAT"]


def test_a_lone_ending_without_a_repeat_has_no_route() -> None:
    assert rejected([fwd(0)], [ending(2, 2, 1)]) == ["ENDING_WITHOUT_REPEAT"]


def test_a_lone_ending_with_its_own_backward_repeat_is_unsupported() -> None:
    codes_ = rejected([fwd(0), back(2)], [ending(2, 2, 1, 2)])
    assert codes_ == ["ENDING_STRUCTURE_UNSUPPORTED"]


def test_a_last_ending_with_a_backward_repeat_is_unsupported() -> None:
    marks = [fwd(0), back(2), back(3)]
    assert rejected(marks, [ending(2, 2, 1), ending(3, 3, 2)]) == ["ENDING_STRUCTURE_UNSUPPORTED"]


def test_a_last_ending_must_be_exactly_the_final_pass() -> None:
    marks = [fwd(0), back(2)]
    assert rejected(marks, [ending(2, 2, 1), ending(3, 3, 2, 3)]) == [
        "ENDING_STRUCTURE_UNSUPPORTED"
    ]


def test_a_repeat_sign_inside_the_endings_is_unsupported() -> None:
    marks = [fwd(0), back(2), back(3)]
    spans = [ending(2, 3, 1), ending(4, 4, 2)]  # a backward repeat in the middle of ending 1
    assert rejected(marks, spans, 7) == ["ENDING_STRUCTURE_UNSUPPORTED"]
    assert rejected([fwd(0), fwd(3), back(2)], [ending(2, 3, 1), ending(4, 4, 2)], 7) == [
        "ENDING_STRUCTURE_UNSUPPORTED"
    ]


def test_times_that_contradicts_the_endings_is_an_error_not_a_choice() -> None:
    marks = [fwd(0), back(2, 3)]
    assert rejected(marks, [ending(2, 2, 1), ending(3, 3, 2)]) == ["REPEAT_TIMES_ENDINGS_CONFLICT"]
    agree = plan_performance(table(5), [fwd(0), back(2, 2)], [ending(2, 2, 1), ending(3, 3, 2)])
    assert not agree.issues


def test_too_many_passes_is_an_error() -> None:
    marks = [fwd(0), back(2)]
    spans = [ending(2, 2, *range(1, 17)), ending(3, 3, 17)]
    assert rejected(marks, spans) == ["REPEAT_TIMES_EXCESSIVE"]


def test_endings_with_no_body_are_unsupported() -> None:
    marks = [back(0)]
    assert rejected(marks, [ending(0, 0, 1), ending(1, 1, 2)]) == ["ENDING_STRUCTURE_UNSUPPORTED"]


def test_a_group_after_an_earlier_repeat_with_no_start_of_its_own_is_ambiguous() -> None:
    marks = [back(0), back(2)]
    assert rejected(marks, [ending(2, 2, 1), ending(3, 3, 2)]) == ["REPEAT_START_AMBIGUOUS"]


def test_endings_that_do_not_tile_are_separate_groups_and_each_must_stand_alone() -> None:
    # a gap measure between the endings: they are not one group, so the first is a lone ending
    # that carries its own backward repeat
    marks = [fwd(0), back(2)]
    assert rejected(marks, [ending(2, 2, 1), ending(4, 4, 2)], 6) == [
        "ENDING_STRUCTURE_UNSUPPORTED"
    ]


def test_the_expansion_cap_applies_to_endings() -> None:
    body = MAX_PERFORMED_MEASURES // 15
    count = body + 3
    spans = [ending(body, body, *range(1, 16)), ending(body + 1, body + 1, 16)]
    result = plan_performance(table(count), [fwd(0), back(body)], spans)
    assert codes(result) == ["REPEAT_EXPANSION_TOO_LARGE"]
    assert result.plan.is_identity  # the written song, never a truncation


def test_a_valid_plan_just_under_the_cap_is_accepted() -> None:
    spans = [ending(100, 100, *range(1, 16)), ending(101, 101, 16)]
    result = plan_performance(table(103), [fwd(0), back(100)], spans)
    assert not result.issues
    assert len(result.plan.played) == 100 * 16 + 15 + 1 + 1


@pytest.mark.parametrize("bad", [(), (0,), (2, 1), (1, 1)])
def test_an_ending_span_needs_positive_sorted_unique_numbers(bad: tuple[int, ...]) -> None:
    with pytest.raises(ValueError, match="ending numbers"):
        EndingSpan(start_index=0, end_index=0, numbers=bad, closing=EndingClose.STOP)


def test_an_ending_span_must_span_measures_in_order() -> None:
    with pytest.raises(ValueError, match="at least one measure"):
        EndingSpan(start_index=3, end_index=2, numbers=(1,), closing=EndingClose.STOP)


def test_discontinuity_positions_is_the_one_authoritative_boundary_api() -> None:
    marks, spans = STANDARD
    plan = plan_performance(table(5), marks, spans).plan
    kinds = {m.arrival for m in plan.played}
    assert {T.REPEAT_JUMP, T.ENDING_SKIP} <= kinds  # the plan has both kinds
    jump = [m.performed_start for m in plan.played if m.arrival is T.REPEAT_JUMP]
    skip = [m.performed_start for m in plan.played if m.arrival is T.ENDING_SKIP]
    assert plan.jump_positions == set(jump)  # the narrower, repeat-jump-only API
    assert plan.discontinuity_positions == set(jump) | set(skip)  # downstream needs only this
    # exits and ordinary adjacency are never discontinuities
    adjacent = {
        m.performed_start
        for m in plan.played
        if m.arrival in (T.START, T.SEQUENTIAL, T.REPEAT_EXIT)
    }
    assert not adjacent & plan.discontinuity_positions
