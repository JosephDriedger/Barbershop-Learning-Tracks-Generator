"""The repeat planner: pure rules on hand-built measure tables."""

from fractions import Fraction

import pytest

from barbershop_tracks.core.timeline import plan_performance
from barbershop_tracks.core.timeline.repeats import MAX_PERFORMED_MEASURES
from barbershop_tracks.models import (
    MeasureSpan,
    PerformancePlan,
    RepeatKind,
    RepeatMark,
    Severity,
    TransitionKind,
)

T = TransitionKind


def table(count: int, length: int = 4, *, numbers: list[int] | None = None) -> list[MeasureSpan]:
    spans = []
    for index in range(count):
        spans.append(
            MeasureSpan(
                index=index,
                number=numbers[index] if numbers else index + 1,
                start=Fraction(index * length),
                length=Fraction(length),
            )
        )
    return spans


def fwd(index: int) -> RepeatMark:
    return RepeatMark(kind=RepeatKind.FORWARD, measure_index=index)


def back(index: int, times: int | None = None) -> RepeatMark:
    return RepeatMark(kind=RepeatKind.BACKWARD, measure_index=index, times=times)


def order(plan: PerformancePlan) -> list[int]:
    return [m.source_index for m in plan.played]


def codes(result) -> list[str]:  # type: ignore[no-untyped-def]
    return [issue.code for issue in result.issues]


# --- the plain cases ----------------------------------------------------------------------


def test_no_marks_is_the_identity() -> None:
    result = plan_performance(table(3), [])
    assert order(result.plan) == [0, 1, 2]
    assert result.plan.is_identity
    assert [m.arrival for m in result.plan.played] == [T.START, T.SEQUENTIAL, T.SEQUENTIAL]
    assert not result.issues


def test_an_empty_table_is_an_empty_plan() -> None:
    result = plan_performance([], [])
    assert result.plan.played == ()
    assert result.plan.end == 0
    assert result.plan.is_identity


def test_forward_and_backward_play_twice_by_default() -> None:
    result = plan_performance(table(4), [fwd(0), back(1)])
    assert order(result.plan) == [0, 1, 0, 1, 2, 3]
    assert not result.issues


def test_arrivals_distinguish_jumps_from_exits_and_adjacency() -> None:
    plan = plan_performance(table(4), [fwd(0), back(1)]).plan
    assert [m.arrival for m in plan.played] == [
        T.START,
        T.SEQUENTIAL,
        T.REPEAT_JUMP,
        T.SEQUENTIAL,
        T.REPEAT_EXIT,
        T.SEQUENTIAL,
    ]
    assert plan.jump_positions == {Fraction(8)}


def test_visits_count_the_times_each_written_measure_is_played() -> None:
    plan = plan_performance(table(3), [fwd(0), back(1, 3)]).plan
    assert [(m.source_index, m.visit) for m in plan.played] == [
        (0, 1),
        (1, 1),
        (0, 2),
        (1, 2),
        (0, 3),
        (1, 3),
        (2, 1),
    ]
    assert [m.performed_index for m in plan.played] == list(range(7))


def test_times_is_the_total_number_of_passes() -> None:
    for times in (2, 3, 4, 9, 16):
        plan = plan_performance(table(3), [fwd(0), back(1, times)]).plan
        assert order(plan) == [0, 1] * times + [2]


def test_times_one_is_a_single_pass_without_a_jump() -> None:
    result = plan_performance(table(3), [fwd(0), back(1, 1)])
    assert order(result.plan) == [0, 1, 2]
    assert result.plan.jump_positions == frozenset()


def test_a_repeat_in_the_middle_and_at_the_end() -> None:
    assert order(plan_performance(table(5), [fwd(2), back(3)]).plan) == [0, 1, 2, 3, 2, 3, 4]
    assert order(plan_performance(table(3), [fwd(1), back(2)]).plan) == [0, 1, 2, 1, 2]


def test_a_one_measure_repeat() -> None:
    plan = plan_performance(table(3), [fwd(1), back(1, 3)]).plan
    assert order(plan) == [0, 1, 1, 1, 2]


def test_consecutive_repeats_in_one_barline_and_apart() -> None:
    same_bar = plan_performance(table(3), [fwd(0), back(0), fwd(1), back(1)]).plan
    assert order(same_bar) == [0, 0, 1, 1, 2]
    apart = plan_performance(table(5), [fwd(0), back(1), fwd(2), back(3, 3)]).plan
    assert order(apart) == [0, 1, 0, 1, 2, 3, 2, 3, 2, 3, 4]
    assert [m.arrival for m in apart.played][4] is T.REPEAT_EXIT
    assert [m.arrival for m in apart.played][5] is T.SEQUENTIAL  # inside the second section
    assert [m.arrival for m in apart.played][6] is T.REPEAT_JUMP


# --- backward repeat without a forward -------------------------------------------------------


def test_a_first_backward_without_a_forward_repeats_from_the_beginning() -> None:
    result = plan_performance(table(4), [back(2)])
    assert order(result.plan) == [0, 1, 2, 0, 1, 2, 3]
    assert not result.issues


def test_a_backward_at_the_first_measure_repeats_that_measure() -> None:
    assert order(plan_performance(table(2), [back(0)]).plan) == [0, 0, 1]


def test_a_second_bare_backward_is_ambiguous() -> None:
    result = plan_performance(table(5), [back(1), back(3)])
    assert codes(result) == ["REPEAT_START_AMBIGUOUS"]
    assert next(iter(result.issues)).severity is Severity.ERROR
    assert next(iter(result.issues)).measure == 4
    assert result.plan.is_identity  # the output stays defined


def test_a_bare_backward_after_a_forward_marked_repeat_is_ambiguous() -> None:
    result = plan_performance(table(6), [fwd(1), back(2), back(4)])
    assert codes(result) == ["REPEAT_START_AMBIGUOUS"]


def test_a_bare_backward_before_a_later_forward_repeat_is_fine() -> None:
    result = plan_performance(table(5), [back(1), fwd(2), back(3)])
    assert order(result.plan) == [0, 1, 0, 1, 2, 3, 2, 3, 4]
    assert not result.issues


# --- nesting and unused forwards -------------------------------------------------------------


def test_nested_repeats_are_unsupported() -> None:
    result = plan_performance(table(5), [fwd(0), fwd(1), back(2), back(3)])
    assert codes(result) == ["REPEAT_NESTED_UNSUPPORTED"]
    assert result.plan.is_identity


def test_two_forwards_and_one_backward_are_not_reinterpreted() -> None:
    result = plan_performance(table(4), [fwd(0), fwd(1), back(2)])
    assert codes(result) == ["REPEAT_NESTED_UNSUPPORTED"]
    assert order(result.plan) == [0, 1, 2, 3]


def test_a_forward_that_is_never_closed_plays_straight_through_with_a_warning() -> None:
    result = plan_performance(table(3), [fwd(1)])
    assert order(result.plan) == [0, 1, 2]
    assert codes(result) == ["REPEAT_FORWARD_UNUSED"]
    assert next(iter(result.issues)).severity is Severity.WARNING
    assert not result.issues.has_errors


# --- identity of measures and exact positions ---------------------------------------------------


def test_display_numbers_are_never_identity() -> None:
    numbers = [0, 1, 1, 2]  # a pickup labelled 0 and a repeated label
    plan = plan_performance(table(4, numbers=numbers), [fwd(1), back(2)]).plan
    assert [(m.source_index, m.number) for m in plan.played] == [
        (0, 0),
        (1, 1),
        (2, 1),
        (1, 1),
        (2, 1),
        (3, 2),
    ]
    assert plan.played[1].source_index != plan.played[2].source_index


def test_pickup_keeps_its_true_length_and_positions_are_exact() -> None:
    spans = [
        MeasureSpan(index=0, number=0, start=Fraction(0), length=Fraction(1), implicit=True),
        MeasureSpan(index=1, number=1, start=Fraction(1), length=Fraction(4)),
        MeasureSpan(index=2, number=2, start=Fraction(5), length=Fraction(3), implicit=True),
    ]
    plan = plan_performance(spans, [back(2)]).plan  # back to the pickup, no forward
    assert [m.source_index for m in plan.played] == [0, 1, 2, 0, 1, 2]
    assert [m.performed_start for m in plan.played] == [0, 1, 5, 8, 9, 13]
    assert plan.end == 16
    assert plan.played[3].arrival is T.REPEAT_JUMP


def test_exact_fraction_lengths_survive_expansion() -> None:
    third = Fraction(10, 3)
    spans = [
        MeasureSpan(index=0, number=1, start=Fraction(0), length=third),
        MeasureSpan(index=1, number=2, start=third, length=third),
    ]
    plan = plan_performance(spans, [fwd(0), back(1, 3)]).plan
    assert plan.end == 6 * third
    assert plan.played[-1].performed_start == 5 * third


def test_locate_finds_the_performed_measure() -> None:
    plan = plan_performance(table(2), [fwd(0), back(1)]).plan
    found = plan.locate(Fraction(9))
    assert found is not None
    assert (found.source_index, found.visit, found.performed_index) == (0, 2, 2)
    assert plan.locate(Fraction(0)) is not None
    assert plan.locate(Fraction(100)) is None
    assert plan.locate(Fraction(-1)) is None


# --- limits ------------------------------------------------------------------------------------


def test_expansion_size_is_limited() -> None:
    spans = table(MAX_PERFORMED_MEASURES // 10 + 1)
    marks = [fwd(0), back(len(spans) - 1, 16)]
    result = plan_performance(spans, marks)
    assert codes(result) == ["REPEAT_EXPANSION_TOO_LARGE"]
    assert result.plan.is_identity


def test_a_plan_that_fits_the_limit_is_accepted() -> None:
    result = plan_performance(table(100), [fwd(0), back(99, 16)])
    assert len(result.plan.played) == 1600
    assert not result.issues


@pytest.mark.parametrize("marks", [[fwd(0), back(1)], [back(2)], [fwd(1), back(2, 3)]])
def test_planning_is_deterministic(marks: list[RepeatMark]) -> None:
    first = plan_performance(table(4), marks)
    assert plan_performance(table(4), list(reversed(marks))).plan == first.plan
