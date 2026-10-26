"""A measure MuseScore exports shorter than the time signature is shorter: a pickup, not padding.

MuseScore writes every rest, so an under-filled measure in its export is an irregular measure (the
first of Ebb Tide is one beat in 3/4 and is not marked ``implicit``). Padding it to the time
signature put every later note, and every tempo change MuseScore plays, two beats later than in
MuseScore. A program that leaves trailing rests out (most hand-written files) is still padded.
"""

from fractions import Fraction
from pathlib import Path

import pytest

from barbershop_tracks.core.musicxml import ParseResult
from barbershop_tracks.models import Part
from xml_builders import attributes, measure, parse_text, quarters, score

pytestmark = pytest.mark.usefixtures("no_network")

MUSESCORE = (
    "<identification><encoding><software>MuseScore 4.2.1</software></encoding></identification>"
)
OTHER = "<identification><encoding><software>Finale 27</software></encoding></identification>"
THREE_FOUR = attributes(time=(3, 4))


def three_four(tmp_path: Path, bars: str, software: str = MUSESCORE) -> ParseResult:
    return parse_text(tmp_path, score(bars, head=software))


def starts(result: ParseResult) -> list[Fraction]:
    assert result.song is not None
    part: Part = result.song.parts[0]
    return [event.start for event in part.events]


def pickup_then_bar() -> str:
    return measure(1, quarters(("G", 4)), attrs=THREE_FOUR) + measure(
        2, quarters(("C", 5), ("D", 5), ("E", 5))
    )


def test_a_short_first_measure_of_a_musescore_export_is_a_pickup_of_its_own_length(
    tmp_path: Path,
) -> None:
    result = three_four(tmp_path, pickup_then_bar())
    assert starts(result) == [0, 1, 2, 3]  # the bar begins one beat in, not three
    assert [i.code for i in result.issues] == []
    assert result.song is not None
    assert [(m.start, m.length) for m in result.song.measures] == [
        (Fraction(0), Fraction(1)),
        (Fraction(1), Fraction(3)),
    ]
    assert result.performed is not None
    assert result.song.duration == 4


def test_the_same_file_from_another_program_is_padded_to_the_time_signature(tmp_path: Path) -> None:
    result = three_four(tmp_path, pickup_then_bar(), OTHER)
    assert starts(result) == [0, 3, 4, 5]
    assert [i.code for i in result.issues] == ["MEASURE_INCOMPLETE"]


def test_a_file_that_says_nothing_about_its_program_is_padded(tmp_path: Path) -> None:
    result = parse_text(tmp_path, score(pickup_then_bar()))
    assert starts(result) == [0, 3, 4, 5]


def test_a_short_measure_in_the_middle_of_a_musescore_export_keeps_its_length(
    tmp_path: Path,
) -> None:
    bars = (
        measure(1, quarters(("C", 4), ("D", 4), ("E", 4)), attrs=THREE_FOUR)
        + measure(2, quarters(("F", 4), ("G", 4)))  # a measure told to be two beats
        + measure(3, quarters(("A", 4), ("B", 4), ("C", 5)))
    )
    result = three_four(tmp_path, bars)
    assert starts(result) == [0, 1, 2, 3, 4, 5, 6, 7]
    assert [i.code for i in result.issues] == []


def test_a_full_measure_and_an_overfull_one_are_as_before(tmp_path: Path) -> None:
    full = three_four(
        tmp_path, measure(1, quarters(("C", 4), ("D", 4), ("E", 4)), attrs=THREE_FOUR)
    )
    assert [i.code for i in full.issues] == []
    over = three_four(
        tmp_path, measure(1, quarters(("C", 4), ("D", 4), ("E", 4), ("F", 4)), attrs=THREE_FOUR)
    )
    assert [i.code for i in over.issues] == ["MEASURE_DURATION_MISMATCH"]


def test_two_parts_that_both_open_with_the_pickup_stay_aligned(tmp_path: Path) -> None:
    first = pickup_then_bar()
    second = measure(1, quarters(("C", 3)), attrs=THREE_FOUR) + measure(
        2, quarters(("F", 3), ("G", 3), ("A", 3))
    )
    result = parse_text(tmp_path, score(first, second, head=MUSESCORE))
    assert [i.code for i in result.issues] == []
    assert result.song is not None
    assert [p.events[1].start for p in result.song.parts] == [1, 1]


def test_an_implicit_pickup_is_as_before(tmp_path: Path) -> None:
    bars = measure(0, quarters(("G", 4)), attrs=THREE_FOUR, implicit=True) + measure(
        1, quarters(("C", 5), ("D", 5), ("E", 5))
    )
    result = three_four(tmp_path, bars)
    assert starts(result) == [0, 1, 2, 3]
    assert [i.code for i in result.issues] == []
