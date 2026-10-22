"""Who has the melody: read from the words, then overridden by marked bars."""

from collections.abc import Sequence
from dataclasses import replace
from fractions import Fraction

import pytest

from barbershop_tracks.core.melody import (
    MelodyError,
    MelodyMark,
    beats_in_bar,
    detect_melody,
    is_vocable,
    melody_of,
)
from barbershop_tracks.core.synthesis import MeasureMark, MeterPoint, SynthesisPlan
from barbershop_tracks.models import VoiceRole
from synth_builders import ROLES, plan_of, sung

LEAD, TENOR, BARI, BASS = VoiceRole.LEAD, VoiceRole.TENOR, VoiceRole.BARITONE, VoiceRole.BASS


def plan(**by_role: Sequence[str | None]) -> SynthesisPlan:
    """Eight quarter notes per voice (bars of four): words given per role, "la" for the rest."""
    voices = {r.value: sung(r, by_role.get(r.value, ["la"] * 8)) for r in ROLES}
    return plan_of(voices=voices)


def with_bars(source: SynthesisPlan) -> SynthesisPlan:
    marks = (
        MeasureMark(start=Fraction(0), length=Fraction(4), number=1),
        MeasureMark(start=Fraction(4), length=Fraction(4), number=2),
        MeasureMark(start=Fraction(8), length=Fraction(8), number=3),
    )
    return replace(source, measures=marks)


@pytest.mark.parametrize(
    "text", ["oo", "Oo", "ooh", "Ooo", "OOH!", "mm", "hmm", "hm", "doo", "bum"]
)
def test_these_are_sounds_not_words(text: str) -> None:
    assert is_vocable(text)


@pytest.mark.parametrize("text", ["oh", "O", "la", "love", "Oh!", "a", "ah", "do", "moon", "home"])
def test_these_can_be_words(text: str) -> None:
    assert not is_vocable(text)


def test_the_lead_has_the_melody_while_it_sings_words() -> None:
    sections = detect_melody(plan())
    assert [(s.role, int(s.start), int(s.end)) for s in sections] == [(LEAD, 0, 16)]
    assert not sections[0].marked
    assert sections[0].note == ""


def test_when_everyone_is_on_oo_the_lead_keeps_it() -> None:
    oos = {r.value: ["oo"] * 8 for r in ROLES}
    assert [s.role for s in detect_melody(plan(**oos))] == [LEAD]


def test_another_part_has_the_melody_when_it_alone_sings_the_words() -> None:
    sections = detect_melody(
        plan(
            lead=["la"] * 4 + ["oo"] * 4,
            tenor=["la"] * 4 + ["love", "is", "born", "now"],
            baritone=["la"] * 4 + ["oo"] * 4,
            bass=["la"] * 4 + ["oo"] * 4,
        )
    )
    assert [(s.role, int(s.start), int(s.end)) for s in sections] == [
        (LEAD, 0, 4),
        (TENOR, 4, 8),
        (LEAD, 8, 16),
    ]
    assert sections[1].note == "sings the words while the Lead does not"


def test_a_rest_in_the_lead_passes_the_melody_to_the_one_part_that_sings() -> None:
    voices = {
        "lead": sung(LEAD, ["la"] * 4),  # then rests
        "tenor": sung(TENOR, ["la"] * 4 + ["come", "sing", "with", "me"]),
        "baritone": sung(BARI, ["la"] * 4 + ["oo"] * 4),
        "bass": sung(BASS, ["la"] * 4 + ["oo"] * 4),
    }
    sections = detect_melody(plan_of(voices=voices))
    assert [(s.role, int(s.start), int(s.end)) for s in sections] == [
        (LEAD, 0, 4),
        (TENOR, 4, 8),
        (LEAD, 8, 16),
    ]


def test_several_parts_singing_words_over_a_lead_oo_is_not_guessed() -> None:
    sections = detect_melody(
        plan(
            lead=["la"] * 4 + ["oo"] * 4,
            tenor=["la"] * 4 + ["a", "b", "c", "d"],
            baritone=["la"] * 4 + ["a", "b", "c", "d"],
        )
    )
    unclear = next(s for s in sections if s.note)
    assert unclear.role is LEAD  # the usual is kept
    assert (int(unclear.start), int(unclear.end)) == (4, 8)
    assert "Tenor and Baritone" in unclear.note


def test_a_lead_that_merely_rests_while_the_others_move_still_has_it() -> None:
    voices = {
        "lead": sung(LEAD, ["la"] * 4),
        "tenor": sung(TENOR, ["la"] * 8),
        "baritone": sung(BARI, ["la"] * 8),
        "bass": sung(BASS, ["la"] * 8),
    }
    sections = detect_melody(plan_of(voices=voices))
    assert [s.role for s in sections] == [LEAD]
    assert sections[0].note == ""


def test_marked_bars_win_over_the_words() -> None:
    marked = melody_of(with_bars(plan()), [MelodyMark(BASS, 2, 2)])
    assert [(s.role, int(s.start), int(s.end), s.marked) for s in marked] == [
        (LEAD, 0, 4, False),
        (BASS, 4, 8, True),
        (LEAD, 8, 16, False),
    ]
    assert marked[1].bars == "bar 2"


def test_a_later_mark_wins_over_an_earlier_one() -> None:
    marked = melody_of(with_bars(plan()), [MelodyMark(BASS, 1, 2), MelodyMark(TENOR, 2, 2)])
    assert [(s.role, int(s.start), int(s.end)) for s in marked] == [
        (BASS, 0, 4),
        (TENOR, 4, 8),
        (LEAD, 8, 16),
    ]


def test_a_mark_that_names_a_bar_the_score_lacks_is_refused() -> None:
    with pytest.raises(MelodyError) as error:
        melody_of(with_bars(plan()), [MelodyMark(TENOR, 2, 9)])
    assert error.value.code == "MELODY_MARK_BAR"


def test_marks_need_the_bars_of_the_score() -> None:
    with pytest.raises(MelodyError) as error:
        melody_of(replace(plan(), measures=()), [MelodyMark(TENOR, 1, 1)])
    assert error.value.code == "MELODY_NO_BARS"


def test_a_range_that_runs_backwards_is_refused() -> None:
    with pytest.raises(MelodyError) as error:
        MelodyMark(TENOR, 5, 2)
    assert error.value.code == "MELODY_MARK_RANGE"


def test_no_marks_leave_the_detection_unchanged() -> None:
    source = plan()
    assert melody_of(source) == detect_melody(source)


def test_the_record_says_where_each_section_came_from() -> None:
    marked = melody_of(with_bars(plan()), [MelodyMark(BASS, 2, 2)])
    assert [s.as_record()["basis"] for s in marked] == ["lyrics", "marked", "lyrics"]
    assert marked[1].as_record()["role"] == "bass"


def test_a_mark_can_start_and_end_on_a_beat() -> None:
    marked = melody_of(with_bars(plan()), [MelodyMark(BASS, 2, 3, first_beat=3, last_beat=2)])
    assert [(s.role, int(s.start), int(s.end), s.marked) for s in marked] == [
        (LEAD, 0, 6, False),
        (BASS, 6, 10, True),  # beats 3 and 4 of bar 2, then beats 1 and 2 of bar 3
        (LEAD, 10, 16, False),
    ]
    assert marked[1].bars == "bar 2 beat 3 to bar 3 beat 2"


def test_a_mark_inside_one_bar_names_its_beats() -> None:
    marked = melody_of(with_bars(plan()), [MelodyMark(TENOR, 2, 2, first_beat=2, last_beat=3)])
    assert [(s.role, int(s.start), int(s.end)) for s in marked] == [
        (LEAD, 0, 5),
        (TENOR, 5, 7),
        (LEAD, 7, 16),
    ]
    assert marked[1].bars == "bar 2 beats 2 to 3"


def test_a_mark_from_a_beat_to_the_end_of_the_bar() -> None:
    marked = melody_of(with_bars(plan()), [MelodyMark(TENOR, 2, 2, first_beat=4)])
    assert [(s.role, int(s.start), int(s.end)) for s in marked] == [
        (LEAD, 0, 7),
        (TENOR, 7, 8),
        (LEAD, 8, 16),
    ]
    assert marked[1].bars == "bar 2 beat 4 to the end"


def test_a_mark_without_beats_is_still_the_whole_bars() -> None:
    assert MelodyMark(TENOR, 2, 3) == MelodyMark(TENOR, 2, 3, 1, None)


def test_a_beat_the_bar_lacks_is_refused() -> None:
    with pytest.raises(MelodyError) as error:
        melody_of(with_bars(plan()), [MelodyMark(TENOR, 2, 2, first_beat=5)])
    assert error.value.code == "MELODY_MARK_BEAT"
    assert "4 beats" in error.value.message
    with pytest.raises(MelodyError) as error:
        melody_of(with_bars(plan()), [MelodyMark(TENOR, 1, 2, last_beat=6)])
    assert error.value.code == "MELODY_MARK_BEAT"


@pytest.mark.parametrize("beats", [(0, None), (1, 0), (3, 2)])
def test_beats_must_be_counted_from_one_and_go_forward(beats: tuple[int, int | None]) -> None:
    with pytest.raises(MelodyError):
        MelodyMark(TENOR, 2, 2, first_beat=beats[0], last_beat=beats[1])


def test_a_bar_has_as_many_beats_as_its_time_signature_says() -> None:
    six_eight = replace(
        with_bars(plan()),
        meter=(MeterPoint(position=Fraction(0), beats=6, beat_type=8),),
        measures=(
            MeasureMark(start=Fraction(0), length=Fraction(3), number=1),
            MeasureMark(start=Fraction(3), length=Fraction(3), number=2),
            MeasureMark(start=Fraction(6), length=Fraction(10), number=3),
        ),
    )
    marked = melody_of(six_eight, [MelodyMark(BASS, 2, 2, first_beat=2)])
    assert [(s.role, s.start, s.end) for s in marked] == [
        (LEAD, Fraction(0), Fraction(7, 2)),
        (BASS, Fraction(7, 2), Fraction(6)),  # the second beat of 6/8 is an eighth note in
        (LEAD, Fraction(6), Fraction(16)),
    ]
    assert beats_in_bar(six_eight, 2) == 6
    assert beats_in_bar(with_bars(plan()), 2) == 4
    melody_of(six_eight, [MelodyMark(BASS, 2, 2, first_beat=6)])
    with pytest.raises(MelodyError):
        melody_of(six_eight, [MelodyMark(BASS, 2, 2, first_beat=7)])  # 6/8 has six beats


def test_a_simple_meter_in_eighths_counts_each_eighth() -> None:
    three_eight = replace(
        with_bars(plan()),
        meter=(MeterPoint(position=Fraction(0), beats=3, beat_type=8),),
        measures=(
            MeasureMark(start=Fraction(0), length=Fraction(3, 2), number=1),
            MeasureMark(start=Fraction(3, 2), length=Fraction(3, 2), number=2),
            MeasureMark(start=Fraction(3), length=Fraction(13), number=3),
        ),
    )
    marked = melody_of(three_eight, [MelodyMark(BASS, 2, 2, first_beat=3)])
    assert [(s.start, s.end) for s in marked if s.marked] == [(Fraction(5, 2), Fraction(3))]


def test_a_section_the_words_start_mid_bar_says_which_beat() -> None:
    sections = detect_melody(
        with_bars(
            plan(
                lead=["la"] * 6 + ["oo"] * 2,
                tenor=["la"] * 6 + ["love", "is"],
                baritone=["la"] * 6 + ["oo"] * 2,
                bass=["la"] * 6 + ["oo"] * 2,
            )
        )
    )
    tenor = next(s for s in sections if s.role is TENOR)
    assert tenor.bars == "bar 2 beat 3 to the end"


def test_the_record_keeps_the_beats() -> None:
    marked = melody_of(with_bars(plan()), [MelodyMark(BASS, 2, 2, first_beat=3)])
    record = marked[1].as_record()
    assert record["first_beat"] == "3"
    assert record["last_beat"] is None
