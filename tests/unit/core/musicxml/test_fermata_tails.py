"""The end of a fermata note at full tempo: the closing of a syllable takes its usual time."""

import random
from fractions import Fraction

from barbershop_tracks.core.musicxml.fermata_tails import (
    CONSONANT,
    TAIL,
    tail_for,
    tempo_changes_heard,
    with_fermata_tails,
)
from barbershop_tracks.models import TempoChange

HALF = Fraction(1, 2)


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


def bpm_at(changes: tuple[TempoChange, ...], position: Fraction) -> Fraction:
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
    assert [c.position for c in shaped] == [0, HALF - TAIL, HALF, 1 - TAIL]
    assert bpm_at(shaped, HALF - TAIL) == 60
    assert bpm_at(shaped, 1 - TAIL) == 60
    assert bpm_at(shaped, Fraction(1, 16)) < 30  # what the tail took is given back before it
    assert TAIL == 3 * CONSONANT == Fraction(3, 8)  # 180 ticks


def test_the_notes_end_at_the_same_time_in_seconds() -> None:
    shaped = with_fermata_tails(PICKUP)
    for end in (HALF, Fraction(1), Fraction(3)):
        assert abs(seconds_at(shaped, end) - seconds_at(PICKUP, end)) < Fraction(1, 10_000)


def test_every_tempo_it_writes_is_a_multiple_of_a_1024th() -> None:
    assert all((c.bpm * 1024).denominator == 1 for c in with_fermata_tails(PICKUP))


def test_a_fermata_after_a_ritardando_gets_its_tail_too() -> None:
    steps = [change(0, 60), change(8, 58), change(Fraction(33, 4), 56), change(9, 45)]
    fermata = [*steps, change(12, 30), change(Fraction(5759, 480) + 1, 60)]
    shaped = with_fermata_tails(fermata)
    assert shaped[:4] == tuple(steps)  # the ritardando is as it was
    assert bpm_at(shaped, Fraction(12) + Fraction(5759, 480) - TAIL) == 60


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
    short = [change(0, 60), change(1, 30), change(Fraction(11, 10), 60)]  # 49 ticks
    assert with_fermata_tails(short) == tuple(short)


def test_an_end_that_is_not_on_the_engine_grid_is_left_as_it_was() -> None:
    off_grid = [change(0, 60), change(1, 30), change(Fraction(15, 7), 60)]
    assert with_fermata_tails(off_grid) == tuple(off_grid)


def test_a_score_with_one_tempo_is_left_as_it_was() -> None:
    assert with_fermata_tails([change(0, 63)]) == (change(0, 63),)
    assert with_fermata_tails([]) == ()


def test_the_one_tick_returns_between_two_fermatas_are_not_counted_as_tempo_changes() -> None:
    assert tempo_changes_heard(PICKUP) == 1
    assert tempo_changes_heard([change(0, 63)]) == 0


def test_a_stretch_of_one_and_a_half_times_is_shaped_and_a_milder_one_is_not() -> None:
    held = [change(0, 60), change(1, 40), change(2, 60)]  # two thirds of the tempo
    assert with_fermata_tails(held) != tuple(held)
    mild = [change(0, 60), change(1, 45), change(2, 60)]  # three quarters: not clearly a fermata
    assert with_fermata_tails(mild) == tuple(mild)
    milder = [change(0, 60), change(1, 50), change(2, 60)]
    assert with_fermata_tails(milder) == tuple(milder)


def test_a_stretch_as_long_as_a_whole_note_is_shaped_and_a_longer_one_is_not() -> None:
    whole = [change(0, 60), change(1, 30), change(5, 60)]
    assert with_fermata_tails(whole) != tuple(whole)
    longer = [change(0, 60), change(1, 30), change(Fraction(51, 10), 60)]
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
        assert bpm_at(shaped, end - TAIL) == 60
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
        for _note in range(count):
            end = cursor + Fraction(generator.randint(2, 8), 4)  # a quarter to two quarters
            changes += [change(cursor, slow), change(end - Fraction(1, 480), fast)]
            ends.append(end)
            cursor = end
        shaped = with_fermata_tails(changes)
        positions = [c.position for c in shaped]
        assert positions == sorted(set(positions)), changes
        assert all((p * 480).denominator == 1 for p in positions)
        assert all((c.bpm * 1024).denominator == 1 and c.bpm > 0 for c in shaped)
        for end in ends:
            assert abs(seconds_at(shaped, end) - seconds_at(changes, end)) < Fraction(1, 2_000)
            assert bpm_at(shaped, end - TAIL) == fast


def test_the_tail_is_three_consonants_and_less_for_a_shorter_note() -> None:
    assert tail_for(Fraction(1, 2)) == Fraction(3, 8)  # an eighth note: 240 ticks
    assert tail_for(Fraction(4)) == Fraction(3, 8)
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
    assert abs(seconds_at(shaped, HALF) - seconds_at(triple, HALF)) < Fraction(1, 1_000)


def test_a_stretch_that_would_need_less_than_a_beat_per_minute_is_left_as_it_was() -> None:
    extreme = [change(0, 0.5), change(Fraction(239, 480), 60), change(HALF, 0.5)]
    assert with_fermata_tails(extreme) == tuple(extreme)
