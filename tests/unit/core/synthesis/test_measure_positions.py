"""Places are named with the measure numbers the SCORE uses, so a person can find them in it."""

from fractions import Fraction
from pathlib import Path

from barbershop_tracks.core.pipeline import prepare
from barbershop_tracks.core.readiness import RoleAssignments
from barbershop_tracks.core.synthesis import MeasureMark, MeterPoint, SourceIdentity, VoiceEngineRef
from barbershop_tracks.core.synthesis.positions import position_label
from barbershop_tracks.models import VoiceRole
from xml_builders import (
    attributes,
    lyric_xml,
    measure,
    note,
    parse_text,
    score,
    syl,
    tempo_direction,
    text,
)

ROLES = (VoiceRole.TENOR, VoiceRole.LEAD, VoiceRole.BARITONE, VoiceRole.BASS)
FOUR_FOUR = (MeterPoint(position=Fraction(0), beats=4, beat_type=4),)


def marks(*spec: tuple[int, int, int]) -> tuple[MeasureMark, ...]:
    """(number, length in quarters, visit) in performed order, laid end to end."""
    out: list[MeasureMark] = []
    cursor = Fraction(0)
    for number, length, visit in spec:
        out.append(MeasureMark(start=cursor, length=Fraction(length), number=number, visit=visit))
        cursor += length
    return tuple(out)


def test_without_measures_the_bars_are_counted_from_the_start() -> None:
    assert position_label(Fraction(5), FOUR_FOUR) == "bar 2, beat 2"


def test_a_score_whose_numbers_are_the_counted_ones_is_labelled_the_same() -> None:
    plain = marks((1, 4, 1), (2, 4, 1), (3, 4, 1))
    for quarters in (0, 1, 5, 9, 11):
        assert position_label(Fraction(quarters), FOUR_FOUR, plain) == position_label(
            Fraction(quarters), FOUR_FOUR
        )


def test_a_pickup_bar_is_bar_zero_and_the_first_full_bar_is_bar_one() -> None:
    # two quarters of pickup, then full bars: counted from the start the first full bar is "bar 2"
    score = marks((0, 2, 1), (1, 4, 1), (2, 4, 1))
    assert (
        position_label(Fraction(0), FOUR_FOUR, score) == "bar 0, beat 3"
    )  # the pickup sounds on beats 3-4
    assert position_label(Fraction(1), FOUR_FOUR, score) == "bar 0, beat 4"
    assert position_label(Fraction(2), FOUR_FOUR, score) == "bar 1, beat 1"
    assert position_label(Fraction(2) + Fraction(5, 2), FOUR_FOUR, score) == "bar 1, beat 3½"
    assert position_label(Fraction(6), FOUR_FOUR, score) == "bar 2, beat 1"
    # the same place counted from the start is one bar late: the bug this fixes
    assert position_label(Fraction(6), FOUR_FOUR) == "bar 2, beat 3"


def test_a_repeated_measure_says_which_time_it_is_played() -> None:
    score = marks((1, 4, 1), (2, 4, 1), (1, 4, 2), (2, 4, 2))
    assert position_label(Fraction(4), FOUR_FOUR, score) == "bar 2, beat 1"
    assert position_label(Fraction(8), FOUR_FOUR, score) == "bar 1, beat 1 (time 2)"
    assert position_label(Fraction(13), FOUR_FOUR, score) == "bar 2, beat 2 (time 2)"


def test_the_beat_follows_the_meter_of_the_measure() -> None:
    six_eight = (MeterPoint(position=Fraction(0), beats=6, beat_type=8),)
    score = marks((1, 3, 1), (2, 3, 1))
    assert position_label(Fraction(0), six_eight, score) == "bar 1, beat 1"
    assert position_label(Fraction(1, 2), six_eight, score) == "bar 1, beat 2"
    assert position_label(Fraction(3), six_eight, score) == "bar 2, beat 1"


def test_a_position_outside_every_measure_falls_back_to_counting() -> None:
    assert position_label(Fraction(40), FOUR_FOUR, marks((1, 4, 1))) == "bar 11, beat 1"


def test_a_plan_built_from_a_score_carries_the_scores_own_measure_numbers(tmp_path: Path) -> None:
    names = ["Tenor", "Lead", "Baritone", "Bass"]

    def part(index: int) -> str:
        lyric = lyric_xml(syl("single"), text("la"))
        pickup = measure(
            0,
            (tempo_direction("90") if index == 0 else "")
            + note("C", 4, 2, lyrics=lyric)
            + note("D", 4, 2, lyrics=lyric),
            attrs=attributes(),
            implicit=True,
        )
        full = measure(1, "".join(note("E", 4, 2, lyrics=lyric) for _ in range(4)))
        return pickup + full

    parsed = parse_text(tmp_path, score(*(part(i) for i in range(4)), names=names))
    assignments = RoleAssignments(
        entries=tuple((role, f"P{i}/s1/v1") for i, role in enumerate(ROLES, start=1))
    )
    refs = {
        role: VoiceEngineRef(singer="s", phonemizer="OpenUtau.Core.DefaultPhonemizer", renderer="R")
        for role in ROLES
    }
    plan = prepare(
        parsed,
        assignments,
        identity=SourceIdentity(display_name="p.musicxml"),
        engine_refs=refs,
        follow_lead=False,
    ).plan
    assert plan is not None
    assert [m.number for m in plan.measures] == [0, 1]
    assert plan.measures[0].length < plan.measures[1].length  # the pickup is short
    first_full_bar = plan.measures[1].start
    assert position_label(first_full_bar, plan.meter, plan.measures) == "bar 1, beat 1"
    assert position_label(Fraction(0), plan.meter, plan.measures) == "bar 0, beat 3"
