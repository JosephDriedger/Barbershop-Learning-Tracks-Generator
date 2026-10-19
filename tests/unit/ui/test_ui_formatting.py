from fractions import Fraction

import pytest

from barbershop_tracks.core.synthesis import MeterPoint
from barbershop_tracks.ui.formatting import (
    clock,
    duration_label,
    note_name,
    position_label,
    sentence,
)

FOUR_FOUR = [MeterPoint(position=Fraction(0), beats=4, beat_type=4)]


@pytest.mark.parametrize(
    ("midi", "name"), [(60, "C4"), (64, "E4"), (61, "C#4"), (48, "C3"), (127, "G9"), (0, "C-1")]
)
def test_note_names(midi: int, name: str) -> None:
    assert note_name(midi) == name


@pytest.mark.parametrize(
    ("start", "label"),
    [
        (Fraction(0), "bar 1, beat 1"),
        (Fraction(1), "bar 1, beat 2"),
        (Fraction(3, 2), "bar 1, beat 2½"),
        (Fraction(4), "bar 2, beat 1"),
        (Fraction(9), "bar 3, beat 2"),
        (Fraction(1, 3), "bar 1, beat 1.33"),
    ],
)
def test_positions_in_common_time(start: Fraction, label: str) -> None:
    assert position_label(start, FOUR_FOUR) == label


def test_positions_follow_meter_changes() -> None:
    meters = [
        MeterPoint(position=Fraction(0), beats=4, beat_type=4),
        MeterPoint(position=Fraction(8), beats=3, beat_type=4),  # two 4/4 bars, then 3/4
    ]
    assert position_label(Fraction(8), meters) == "bar 3, beat 1"
    assert position_label(Fraction(11), meters) == "bar 4, beat 1"
    assert position_label(Fraction(12), meters) == "bar 4, beat 2"
    six_eight = [MeterPoint(position=Fraction(0), beats=6, beat_type=8)]
    assert position_label(Fraction(3), six_eight) == "bar 2, beat 1"
    assert position_label(Fraction(1), six_eight) == "bar 1, beat 3"


def test_without_a_meter_only_beats_are_shown() -> None:
    assert position_label(Fraction(2), []) == "beat 3"


def test_durations_and_clock() -> None:
    assert duration_label(Fraction(1)) == "1 beat"
    assert duration_label(Fraction(2)) == "2 beats"
    assert duration_label(Fraction(1, 2)) == "0.5 beats" or duration_label(Fraction(1, 2)).endswith(
        "beats"
    )
    assert duration_label(Fraction(1, 3)) == "0.33 beats"
    assert clock(0) == "0:00"
    assert clock(75.9) == "1:15"
    assert clock(3600) == "60:00"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "the score has no tempo, and none is assumed.",
            "The score has no tempo, and none is assumed.",
        ),
        ("3 notes lie outside the usual range", "3 notes lie outside the usual range"),
        ("Already a sentence.", "Already a sentence."),
        ("", ""),
        ("'Oo' is read as 'ooh'", "'Oo' is read as 'ooh'"),
    ],
)
def test_a_message_starts_with_a_capital_letter(text: str, expected: str) -> None:
    assert sentence(text) == expected
