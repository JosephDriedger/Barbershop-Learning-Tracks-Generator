"""The end of a fermata note at full tempo: the closing of a syllable takes its usual time."""

import random
from collections.abc import Sequence
from fractions import Fraction

import pytest

from barbershop_tracks.core.musicxml.fermata_tails import (
    CONSONANT,
    TAIL,
    tail_for,
    tempo_changes_heard,
    with_fermata_tails,
)
from barbershop_tracks.models import TempoChange

HALF = Fraction(1, 2)
EIGHTH_TAIL = Fraction(3, 8)  # what an eighth note can spare: 180 ticks of its 240


def change(position: Fraction | int, bpm: Fraction | float) -> TempoChange:
    return TempoChange(position=Fraction(position), bpm=Fraction(bpm))


def seconds_at(
    changes: list[TempoChange] | tuple[TempoChange, ...], position: Fraction
) -> Fraction:
    total = Fraction(0)
    for index, current in enumerate(changes):
        end = changes[index + 1].position if index + 1 < len(changes) else None
        if end is None or end >= position:
            return total + (position - current.position) * 60 / current.bpm
        total += (end - current.position) * 60 / current.bpm
    raise AssertionError("unreachable")


def bpm_at(changes: Sequence[TempoChange], position: Fraction) -> Fraction:
    return [c for c in changes if c.position <= position][-1].bpm


# Ebb Tide opens with two eighth notes that each have a fermata, as MuseScore exports them: half
# the tempo for the note, and in its last tick the return to the tempo before.
PICKUP = [
    change(0, 30),
    change(Fraction(239, 480), 60),
    change(HALF, 30),
    change(Fraction(479, 480), 60),
]


def test_each_fermata_note_ends_at_the_full_tempo_for_its_last_three_consonants() -> None:
    shaped = with_fermata_tails(PICKUP)
    assert [c.position for c in shaped] == [0, HALF - EIGHTH_TAIL, HALF, 1 - EIGHTH_TAIL]
    assert bpm_at(shaped, HALF - EIGHTH_TAIL) == 60
    assert bpm_at(shaped, 1 - EIGHTH_TAIL) == 60
    assert bpm_at(shaped, Fraction(1, 16)) < 30  # what the tail took is given back before it
    assert TAIL == 5 * CONSONANT == Fraction(5, 8)  # 300 ticks


def test_the_notes_end_at_the_same_time_in_seconds() -> None:
    shaped = with_fermata_tails(PICKUP)
    for end in (HALF, Fraction(1), Fraction(3)):
        assert abs(seconds_at(shaped, end) - seconds_at(PICKUP, end)) < Fraction(1, 10_000)


def test_every_tempo_it_writes_is_exact_as_a_double() -> None:
    assert all((c.bpm * (1 << 20)).denominator == 1 for c in with_fermata_tails(PICKUP))


def test_a_fermata_after_a_ritardando_gets_its_tail_too() -> None:
    steps = [change(0, 60), change(8, 58), change(Fraction(33, 4), 56), change(9, 45)]
    fermata = [*steps, change(12, 30), change(Fraction(6239, 480), 60)]
    shaped = with_fermata_tails(fermata)
    assert shaped[:4] == tuple(steps)  # the ritardando is as it was
    assert bpm_at(shaped, Fraction(13) - tail_for(Fraction(1))) == 60


def test_a_ritardando_and_a_return_to_tempo_are_left_as_they_were() -> None:
    rit = [change(0, 63), change(Fraction(3, 2), 59), change(Fraction(5, 2), 47), change(3, 63)]
    assert with_fermata_tails(rit) == tuple(rit)


def test_a_plain_change_of_tempo_is_left_as_it_was() -> None:
    faster = [change(0, 60), change(8, 90), change(16, 60)]
    assert with_fermata_tails(faster) == tuple(faster)


def test_a_section_at_a_slower_tempo_is_not_a_held_note() -> None:
    slower = [change(0, 60), change(8, 30), change(16, 60)]
    assert with_fermata_tails(slower) == tuple(slower)


def test_a_note_too_short_for_a_slow_part_and_a_consonant_is_left_as_it_was() -> None:
    short = [change(0, 60), change(1, 30), change(Fraction(529, 480), 60)]  # 50 ticks
    assert with_fermata_tails(short) == tuple(short)


def test_an_end_that_is_not_on_the_grid_of_the_notes_is_left_as_it_was() -> None:
    off_grid = [change(0, 60), change(1, 30), change(Fraction(15, 7), 60)]
    assert with_fermata_tails(off_grid) == tuple(off_grid)


def test_a_score_with_one_tempo_is_left_as_it_was() -> None:
    assert with_fermata_tails([change(0, 63)]) == (change(0, 63),)
    assert with_fermata_tails([]) == ()


def test_the_one_tick_returns_between_two_fermatas_are_not_counted_as_tempo_changes() -> None:
    assert tempo_changes_heard(PICKUP) == 1
    assert tempo_changes_heard([change(0, 63)]) == 0


def test_a_stretch_of_one_and_a_half_times_is_shaped_and_a_milder_one_is_not() -> None:
    held = [change(0, 60), change(1, 40), change(Fraction(959, 480), 60)]  # two thirds
    assert with_fermata_tails(held) != tuple(held)
    mild = [change(0, 60), change(1, 45), change(Fraction(959, 480), 60)]  # three quarters
    assert with_fermata_tails(mild) == tuple(mild)
    milder = [change(0, 60), change(1, 50), change(Fraction(959, 480), 60)]
    assert with_fermata_tails(milder) == tuple(milder)


def test_a_stretch_as_long_as_a_whole_note_is_shaped_and_a_longer_one_is_not() -> None:
    whole = [change(0, 60), change(1, 30), change(Fraction(2399, 480), 60)]
    assert with_fermata_tails(whole) != tuple(whole)
    longer = [change(0, 60), change(1, 30), change(Fraction(2459, 480), 60)]
    assert with_fermata_tails(longer) == tuple(longer)


def test_a_one_tick_return_to_a_different_tempo_is_not_the_end_of_a_fermata_note() -> None:
    odd = [change(0, 30), change(Fraction(239, 480), 60), change(HALF, 45)]
    assert with_fermata_tails(odd) == tuple(odd)


def test_a_stretch_that_never_ends_is_left_as_it_was() -> None:
    final = [change(0, 60), change(8, 30)]  # the last fermata of a song: nothing comes after it
    assert with_fermata_tails(final) == tuple(final)


def test_a_stretch_at_the_start_that_never_returns_is_left_as_it_was() -> None:
    assert with_fermata_tails([change(0, 30)]) == (change(0, 30),)


def test_a_third_fermata_note_in_a_row_is_shaped_as_well() -> None:
    notes = [
        change(0, 30),
        change(Fraction(239, 480), 60),
        change(HALF, 30),
        change(Fraction(479, 480), 60),
        change(1, 30),
        change(Fraction(3, 2) - Fraction(1, 480), 60),
    ]
    shaped = with_fermata_tails(notes)
    for end in (HALF, Fraction(1), Fraction(3, 2)):
        assert bpm_at(shaped, end - EIGHTH_TAIL) == 60
        assert abs(seconds_at(shaped, end) - seconds_at(notes, end)) < Fraction(1, 10_000)


def test_the_tempo_that_follows_the_stretch_is_not_touched() -> None:
    notes = [*PICKUP, change(Fraction(177, 8), 58), change(Fraction(89, 4), 45)]
    shaped = with_fermata_tails(notes)
    assert shaped[-2:] == tuple(notes[-2:])
    assert bpm_at(shaped, Fraction(10)) == 60


def test_shaping_twice_gives_a_valid_tempo_map_that_keeps_the_times() -> None:
    once = with_fermata_tails(PICKUP)
    twice = with_fermata_tails(once)
    assert [c.position for c in twice] == sorted({c.position for c in twice})
    assert abs(seconds_at(twice, HALF) - seconds_at(PICKUP, HALF)) < Fraction(1, 1000)


def test_the_input_is_not_changed() -> None:
    before = list(PICKUP)
    with_fermata_tails(PICKUP)
    assert list(PICKUP) == before


def test_random_stretches_keep_their_times_their_grid_and_their_order() -> None:
    generator = random.Random(2026)
    for _ in range(300):
        fast = Fraction(generator.choice([60, 63, 72, 84, 96]))
        slow = fast * Fraction(generator.choice([40, 50, 60, 66, 70]), 100)
        count = generator.randint(1, 3)
        cursor = Fraction(generator.choice([0, 0, generator.randint(1, 40)]))
        changes = [change(0, fast)] if cursor else []
        ends: list[Fraction] = []
        lengths: list[Fraction] = []
        for _note in range(count):
            length = Fraction(generator.randint(2, 8), 4)  # half a quarter to two quarters
            end = cursor + length
            changes += [change(cursor, slow), change(end - Fraction(1, 480), fast)]
            ends.append(end)
            lengths.append(length)
            cursor = end
        shaped = with_fermata_tails(changes)
        positions = [c.position for c in shaped]
        assert positions == sorted(set(positions)), changes
        assert all((p * 480).denominator == 1 for p in positions)
        assert all(Fraction(float(c.bpm)) == c.bpm and c.bpm > 0 for c in shaped)
        for end, length in zip(ends, lengths, strict=True):
            assert abs(seconds_at(shaped, end) - seconds_at(changes, end)) < Fraction(1, 100_000)
            assert bpm_at(shaped, end - tail_for(length)) == fast
            assert bpm_at(shaped, end - tail_for(length) - Fraction(1, 16)) < fast


def test_the_tail_is_300_ticks_and_less_for_a_shorter_note() -> None:
    assert tail_for(Fraction(4)) == Fraction(5, 8)
    assert tail_for(Fraction(1)) == Fraction(5, 8)  # a quarter note: 480 ticks
    assert tail_for(Fraction(3, 4)) == Fraction(
        5, 8
    )  # 360 ticks: 330 can be spared, 300 is the most
    assert tail_for(Fraction(5, 8)) == Fraction(1, 2)  # 300 ticks: 240 of them
    assert tail_for(Fraction(1, 2)) == Fraction(3, 8)  # an eighth note: 240 ticks
    assert tail_for(Fraction(5, 16)) == Fraction(1, 4)  # 150 ticks: two consonants
    assert tail_for(Fraction(1, 4)) == Fraction(1, 8)  # a sixteenth: 120 ticks
    assert tail_for(Fraction(3, 16)) == Fraction(1, 8)  # 90 ticks: one consonant, 30 ticks slow
    assert tail_for(Fraction(1, 8)) == 0  # 60 ticks: no room for both
    assert tail_for(Fraction(0)) == 0


def test_a_sixteenth_note_fermata_gets_a_one_consonant_tail_and_keeps_its_time() -> None:
    sixteenth = [change(0, 30), change(Fraction(119, 480), 60)]
    shaped = with_fermata_tails(sixteenth)
    assert bpm_at(shaped, Fraction(1, 4) - CONSONANT) == 60
    assert bpm_at(shaped, Fraction(1, 16)) < 30
    assert abs(
        seconds_at(shaped, Fraction(1, 4)) - seconds_at(sixteenth, Fraction(1, 4))
    ) < Fraction(1, 10_000)


def test_a_very_slow_stretch_gets_a_very_slow_first_part_but_keeps_its_time() -> None:
    triple = [change(0, 20), change(Fraction(239, 480), 60), change(HALF, 20)]  # three times
    shaped = with_fermata_tails(triple)
    assert 0 < shaped[0].bpm < 10
    assert abs(seconds_at(shaped, HALF) - seconds_at(triple, HALF)) < Fraction(1, 100_000)


def test_a_stretch_that_would_need_a_tempo_midi_cannot_hold_is_left_as_it_was() -> None:
    extreme = [change(0, 0.5), change(Fraction(239, 480), 60), change(HALF, 0.5)]
    assert with_fermata_tails(extreme) == tuple(extreme)


def test_a_tail_gives_way_to_a_shorter_one_rather_than_need_a_tempo_midi_cannot_hold() -> None:
    # five times as slow: the tail of 180 ticks would need 3.5 bpm for the first 60 ticks
    five_times = [change(0, 12), change(Fraction(239, 480), 60), change(HALF, 12)]
    shaped = with_fermata_tails(five_times)
    assert shaped != tuple(five_times)
    assert all(c.bpm >= 4 for c in shaped)
    assert bpm_at(shaped, HALF - CONSONANT) == 60  # at least the closing consonant
    assert abs(seconds_at(shaped, HALF) - seconds_at(five_times, HALF)) < Fraction(1, 100_000)


# What MuseScore 4 exports for Ebb Tide, as (tick at 480 per quarter, bpm): three pairs of fermata
# eighths, each pair after the opening, after a ritardando (at 22) and again at 87, and the
# ritardando steps themselves.
EBB_TIDE_EXPORT = [
    (0, 30), (239, 60), (240, 30), (479, 60),
    (10590, 58.125), (10620, 56.25), (10650, 54.375), (10680, 52.5), (10710, 50.625),
    (10740, 48.75), (10770, 46.875), (10800, 45),
    (11520, 30), (11759, 60), (11760, 30), (11999, 60),
    (41760, 30), (41999, 60), (42000, 30), (42239, 60),
    (48030, 58.125), (48060, 56.25), (48090, 54.375), (48120, 52.5), (48150, 50.625),
    (48180, 48.75), (48210, 46.875), (48240, 45),
]  # fmt: skip


def exported(events: list[tuple[int, float]]) -> list[TempoChange]:
    return [change(Fraction(tick, 480), Fraction(bpm)) for tick, bpm in events]


def test_the_real_export_of_ebb_tide_is_shaped_at_every_fermata_and_nowhere_else() -> None:
    export = exported(EBB_TIDE_EXPORT)
    shaped = with_fermata_tails(export)
    assert len(shaped) == len(export)
    different = [i for i, (a, b) in enumerate(zip(export, shaped, strict=True)) if a != b]
    assert different == [0, 1, 2, 3, 12, 13, 14, 15, 16, 17, 18, 19]  # not the ritardandos
    assert shaped[4:12] == tuple(export[4:12])
    assert shaped[20:] == tuple(export[20:])
    for change_ in export:
        assert abs(
            seconds_at(shaped, change_.position) - seconds_at(export, change_.position)
        ) < Fraction(1, 20_000)
    for end in (HALF, 1, Fraction(24) + HALF, 25, Fraction(87) + HALF, 88):
        assert bpm_at(shaped, Fraction(end) - EIGHTH_TAIL) == 60


def test_a_fermata_after_a_ritardando_that_had_already_slowed_is_shaped() -> None:
    # the last chord of Ebb Tide with a fermata: the ritardando has reached 33.75 and the
    # fermata plays at 30 (a drop of a tenth), then MuseScore returns to 60 a tick before the end
    rit = [
        (48090, 40.78125),
        (48120, 39.375),
        (48150, 37.96875),
        (48180, 36.5625),
        (48210, 35.15625),
    ]
    export = exported([(0, 60), *rit, (48240, 33.75), (49920, 30), (50879, 60)])
    shaped = with_fermata_tails(export)
    assert shaped[-2].bpm < 30  # the first part of the note
    assert bpm_at(shaped, Fraction(50880, 480) - tail_for(Fraction(2))) == 60
    assert abs(
        seconds_at(shaped, Fraction(50880, 480)) - seconds_at(export, Fraction(50880, 480))
    ) < Fraction(1, 20_000)
    assert shaped[:7] == tuple(export[:7])  # the ritardando is as it was


def test_a_return_that_is_on_a_note_boundary_is_not_a_fermata() -> None:
    # "a tempo" comes on the beat; the return from a fermata is a tick before the note end
    on_the_beat = [change(0, 60), change(1, 30), change(2, 60)]
    assert with_fermata_tails(on_the_beat) == tuple(on_the_beat)
    one_tick_early = [change(0, 60), change(1, 30), change(Fraction(959, 480), 60)]
    assert with_fermata_tails(one_tick_early) != tuple(one_tick_early)


def test_a_triplet_fermata_note_is_shaped() -> None:
    # an eighth-note triplet is 160 ticks: its end is not a multiple of 30 ticks
    triplet = [change(0, 30), change(Fraction(159, 480), 60)]
    shaped = with_fermata_tails(triplet)
    assert shaped != tuple(triplet)
    assert abs(seconds_at(shaped, Fraction(1, 3)) - seconds_at(triplet, Fraction(1, 3))) < Fraction(
        1, 100_000
    )


# More real MuseScore 4 exports of Ebb Tide with the fermatas changed, as (tick, bpm): each case is
# the events, then the (start, end) of every fermata note in ticks and the tempo it returns to.
EXPORTS = {
    "a stretch of three": (
        [(0, 20), (239, 60), (240, 20), (479, 60)],
        [(0, 240, 60), (240, 480, 60)],
    ),
    "a stretch of one and a half": (
        [(0, 40), (239, 60), (240, 40), (479, 60)],
        [(0, 240, 60), (240, 480, 60)],
    ),
    "a fermata on a half note": (
        [(0, 60), (480, 30), (1439, 60)],
        [(480, 1440, 60)],
    ),
    "a tempo mark on a fermata": (
        [(0, 60), (1920, 36), (2879, 72)],
        [(1920, 2880, 72)],
    ),
}


@pytest.mark.parametrize("name", list(EXPORTS))
def test_other_real_exports_are_shaped_and_keep_their_times(name: str) -> None:
    events, notes = EXPORTS[name]
    export = exported([(tick, float(bpm)) for tick, bpm in events])
    shaped = with_fermata_tails(export)
    assert shaped != tuple(export)
    for start, end, fast in notes:
        length = Fraction(end - start, 480)
        tail = tail_for(length)
        assert bpm_at(shaped, Fraction(end, 480) - tail) == fast
        assert bpm_at(shaped, Fraction(start, 480)) < bpm_at(export, Fraction(start, 480)) + 1
        assert abs(
            seconds_at(shaped, Fraction(end, 480)) - seconds_at(export, Fraction(end, 480))
        ) < Fraction(1, 100_000)
    # whatever comes before the first fermata is as it was
    assert shaped[0].position == 0
