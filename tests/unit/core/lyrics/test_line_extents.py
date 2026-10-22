"""A held syllable whose line length is known lasts exactly that long (MuseScore project)."""

from dataclasses import replace
from fractions import Fraction

from barbershop_tracks.core.lyrics import analyze_line
from barbershop_tracks.models import (
    AttackRole,
    LineLyricAnalysis,
    Lyric,
    Melisma,
    MelismaBasis,
    Note,
)
from lyric_builders import LINE, L, n, performed, r

R = AttackRole


def held(text: str, length: float | int | None) -> Lyric:
    lyric = L(text, melisma=Melisma.UNTYPED)
    return lyric if length is None else replace(lyric, extend_length=Fraction(str(length)))


def run(*notes: Note) -> LineLyricAnalysis:
    return analyze_line(performed(*notes), part_id=LINE)


def test_the_line_holds_at_least_as_far_as_it_was_drawn() -> None:
    result = run(n(0, held("doo", 2)), n(1), n(2), n(3, L("so")))
    assert [a.role for a in result.attacks] == [
        R.SYLLABLE,
        R.MELISMA_CONTINUATION,
        R.MELISMA_CONTINUATION,  # past the line, which MuseScore leaves out where it is implied
        R.SYLLABLE,
    ]
    assert result.attacks[1].melisma_basis is MelismaBasis.LINE
    assert result.attacks[2].melisma_basis is MelismaBasis.UNTYPED
    assert result.attacks[2].melisma_origin == 0


def test_a_note_that_starts_inside_the_line_holds_even_if_it_ends_after_it() -> None:
    result = run(n(0, held("doo", 1.5)), n(1, dur=2), n(3, L("so")))
    assert result.attacks[1].role is R.MELISMA_CONTINUATION


def test_a_long_line_goes_on_where_the_old_guess_would_have_stopped() -> None:
    notes = [n(0, held("ooh", 8))] + [n(i) for i in range(1, 8)] + [n(8, L("so"))]
    result = run(*notes)
    assert [a.role for a in result.attacks[1:8]] == [R.MELISMA_CONTINUATION] * 7
    assert result.attacks[8].role is R.SYLLABLE


def test_a_rest_still_ends_the_line() -> None:
    result = run(n(0, held("doo", 8)), r(1), n(2))
    assert [a.role for a in result.attacks] == [R.SYLLABLE, R.REST, R.MISSING]


def test_a_new_lyric_ends_the_line_early() -> None:
    result = run(n(0, held("doo", 8)), n(1), n(2, L("so")), n(3))
    assert [a.role for a in result.attacks] == [
        R.SYLLABLE,
        R.MELISMA_CONTINUATION,
        R.SYLLABLE,
        R.MISSING,
    ]


def test_without_a_known_length_the_line_runs_to_the_next_lyric_or_rest_as_before() -> None:
    result = run(n(0, held("doo", None)), n(1), n(2), n(3, L("so")))
    assert [a.role for a in result.attacks] == [
        R.SYLLABLE,
        R.MELISMA_CONTINUATION,
        R.MELISMA_CONTINUATION,
        R.SYLLABLE,
    ]
    assert result.attacks[1].melisma_basis is MelismaBasis.UNTYPED


def test_a_line_that_ended_is_held_on_until_the_next_lyric() -> None:
    result = run(n(0, held("doo", 1)), n(1), n(2), n(3, L("so")), n(4))
    assert [a.role for a in result.attacks] == [
        R.SYLLABLE,
        R.MELISMA_CONTINUATION,
        R.MELISMA_CONTINUATION,
        R.SYLLABLE,
        R.MISSING,  # the next lyric ended it: a note after that is missing its lyric
    ]
