"""Source structure facts and the derived performance objects."""

from fractions import Fraction

import pytest

from barbershop_tracks.models import (
    MeasureSpan,
    Note,
    NoteOccurrence,
    Part,
    PerformancePlan,
    PerformedLine,
    PlayedMeasure,
    RepeatKind,
    RepeatMark,
    Song,
    TransitionKind,
)


def span(index: int, start: int, length: int = 4) -> MeasureSpan:
    return MeasureSpan(
        index=index, number=index + 1, start=Fraction(start), length=Fraction(length)
    )


def test_measure_span_end_and_defaults() -> None:
    measure = span(0, 0)
    assert measure.end == 4
    assert measure.raw_number is None
    assert not measure.implicit


@pytest.mark.parametrize("bad", [{"index": -1}, {"start": -1}, {"length": -1}])
def test_measure_span_rejects_negative_values(bad: dict[str, int]) -> None:
    values = {"index": 0, "number": 1, "start": 0, "length": 4} | bad
    with pytest.raises(ValueError, match="negative"):
        MeasureSpan(**values)  # type: ignore[arg-type]


def test_a_display_number_may_be_zero_or_repeat() -> None:
    MeasureSpan(index=0, number=0, start=Fraction(0), length=Fraction(1), raw_number="0")
    MeasureSpan(index=5, number=1, start=Fraction(0), length=Fraction(1), raw_number="X1")


def test_repeat_mark_rules() -> None:
    assert RepeatMark(kind=RepeatKind.BACKWARD, measure_index=2, times=3).times == 3
    with pytest.raises(ValueError, match="times must be at least 1"):
        RepeatMark(kind=RepeatKind.BACKWARD, measure_index=0, times=0)
    with pytest.raises(ValueError, match="forward"):
        RepeatMark(kind=RepeatKind.FORWARD, measure_index=0, times=2)
    with pytest.raises(ValueError, match="negative"):
        RepeatMark(kind=RepeatKind.FORWARD, measure_index=-1)


def test_song_checks_its_structure() -> None:
    Song(title="t", measures=(span(0, 0), span(1, 4)))
    with pytest.raises(ValueError, match="indices"):
        Song(title="t", measures=(span(1, 0),))
    with pytest.raises(ValueError, match="contiguous"):
        Song(title="t", measures=(span(0, 0), span(1, 5)))
    with pytest.raises(ValueError, match="does not exist"):
        Song(
            title="t",
            measures=(span(0, 0),),
            repeat_marks=(RepeatMark(kind=RepeatKind.BACKWARD, measure_index=1),),
        )


def played(
    index: int, source: int, start: int, arrival: TransitionKind, visit: int = 1
) -> PlayedMeasure:
    return PlayedMeasure(
        source_index=source,
        number=source + 1,
        visit=visit,
        performed_index=index,
        performed_start=Fraction(start),
        length=Fraction(4),
        arrival=arrival,
    )


def test_a_plan_must_be_contiguous_and_start_with_start() -> None:
    first = played(0, 0, 0, TransitionKind.START)
    PerformancePlan(played=(first, played(1, 1, 4, TransitionKind.SEQUENTIAL)))
    with pytest.raises(ValueError, match="contiguous"):
        PerformancePlan(played=(first, played(1, 1, 5, TransitionKind.SEQUENTIAL)))
    with pytest.raises(ValueError, match="START"):
        PerformancePlan(played=(played(0, 0, 0, TransitionKind.SEQUENTIAL),))
    with pytest.raises(ValueError, match="START"):
        PerformancePlan(played=(first, played(1, 1, 4, TransitionKind.START)))
    with pytest.raises(ValueError, match="performed_index"):
        PerformancePlan(played=(played(1, 0, 0, TransitionKind.START),))


def test_visits_of_collects_every_time_a_measure_is_played() -> None:
    plan = PerformancePlan(
        played=(
            played(0, 0, 0, TransitionKind.START),
            played(1, 0, 4, TransitionKind.REPEAT_JUMP, visit=2),
        )
    )
    assert [m.visit for m in plan.visits_of(0)] == [1, 2]
    assert plan.visits_of(7) == ()
    assert not plan.is_identity


def test_a_line_needs_one_occurrence_per_event() -> None:
    note = Note(start=Fraction(0), duration=Fraction(1), measure=1, beat=Fraction(1))
    part = Part(part_id="p", name="p", events=(note,))
    with pytest.raises(ValueError, match="one occurrence per event"):
        PerformedLine(part=part, occurrences=())
    occurrence = NoteOccurrence(
        part_id="p", source_event_index=0, measure_index=0, visit=1, performed_start=Fraction(0)
    )
    assert PerformedLine(part=part, occurrences=(occurrence,)).occurrence_of(note) is occurrence


def test_visit_must_be_positive() -> None:
    with pytest.raises(ValueError, match="visit"):
        NoteOccurrence(
            part_id="p", source_event_index=0, measure_index=0, visit=0, performed_start=Fraction(0)
        )
    with pytest.raises(ValueError, match="visit"):
        played(0, 0, 0, TransitionKind.START, visit=0)


def test_source_models_have_no_performance_fields() -> None:
    from dataclasses import fields

    from barbershop_tracks.models import ValidationIssue

    assert "visit" not in {f.name for f in fields(Note)}
    assert "visit" not in {f.name for f in fields(ValidationIssue)}


def test_played_measure_carries_pass_and_ending_context() -> None:
    measure = PlayedMeasure(
        source_index=3,
        number=4,
        visit=1,
        performed_index=5,
        performed_start=Fraction(20),
        length=Fraction(4),
        arrival=TransitionKind.ENDING_SKIP,
        repeat_pass=3,
        endings=(3,),
    )
    assert (measure.visit, measure.repeat_pass, measure.endings) == (1, 3, (3,))
    with pytest.raises(ValueError, match="repeat_pass"):
        PlayedMeasure(
            source_index=0,
            number=1,
            visit=1,
            performed_index=0,
            performed_start=Fraction(0),
            length=Fraction(4),
            arrival=TransitionKind.START,
            repeat_pass=0,
        )


def test_performance_location_keeps_structured_context_and_formats_it_separately() -> None:
    from barbershop_tracks.models import PerformanceLocation

    location = PerformanceLocation(
        measure_index=7,
        number=8,
        visit=2,
        performed_position=Fraction(30),
        performed_measure_index=9,
        repeat_pass=2,
        endings=(2,),
    )
    assert (location.measure_index, location.number, location.visit) == (7, 8, 2)
    assert (location.repeat_pass, location.endings) == (2, (2,))
    assert location.describe() == "measure 8, second visit, pass 2, ending 2"
    plain = PerformanceLocation(
        measure_index=0,
        number=1,
        visit=1,
        performed_position=Fraction(0),
        performed_measure_index=0,
    )
    assert plain.describe() == "measure 1, first visit"


def test_the_song_checks_ending_spans() -> None:
    from barbershop_tracks.models import EndingClose, EndingSpan

    def ending(a: int, b: int, n: int) -> EndingSpan:
        return EndingSpan(start_index=a, end_index=b, numbers=(n,), closing=EndingClose.STOP)

    measures = (span(0, 0), span(1, 4), span(2, 8))
    assert Song(title="t", measures=measures, ending_spans=(ending(1, 1, 1),))
    with pytest.raises(ValueError, match="does not exist"):
        Song(title="t", measures=measures, ending_spans=(ending(2, 3, 1),))
    with pytest.raises(ValueError, match="overlap"):
        Song(title="t", measures=measures, ending_spans=(ending(0, 1, 1), ending(1, 2, 2)))
