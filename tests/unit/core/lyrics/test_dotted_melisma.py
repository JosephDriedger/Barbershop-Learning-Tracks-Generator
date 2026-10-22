"""A lyric-less sixteenth straight after a dotted eighth holds that eighth's syllable.

MuseScore draws no extender line for so short a note, so the file says nothing, and without this
reading the sixteenth would be a note "missing a lyric". It is our reading, labelled as such
(``MelismaBasis.DOTTED_RHYTHM``), for that one note; a slur or an extender decides first.
"""

from dataclasses import replace
from fractions import Fraction

from barbershop_tracks.core.lyrics import analyze_line
from barbershop_tracks.models import AttackRole, LineLyricAnalysis, Melisma, MelismaBasis, Note
from lyric_builders import LINE, L, n, performed, r

R = AttackRole
DOTTED = Fraction(3, 4)
SIXTEENTH = Fraction(1, 4)
EIGHTH = Fraction(1, 2)


def run(*notes: Note) -> LineLyricAnalysis:
    return analyze_line(performed(*notes), part_id=LINE)


def test_a_lyric_less_sixteenth_after_a_dotted_eighth_holds_the_syllable() -> None:
    result = run(
        n(0, L("babe"), dur=DOTTED),
        n(DOTTED, dur=SIXTEENTH),
        n(1, L("the"), dur=EIGHTH),
    )
    assert [a.role for a in result.attacks] == [R.SYLLABLE, R.MELISMA_CONTINUATION, R.SYLLABLE]
    held = result.attacks[1]
    assert held.melisma_origin == 0
    assert held.melisma_basis is MelismaBasis.DOTTED_RHYTHM


def test_it_holds_that_one_note_only() -> None:
    result = run(
        n(0, L("babe"), dur=DOTTED),
        n(DOTTED, dur=SIXTEENTH),
        n(1, dur=EIGHTH),  # a second lyric-less note is still missing its lyric
    )
    assert [a.role for a in result.attacks] == [R.SYLLABLE, R.MELISMA_CONTINUATION, R.MISSING]


def test_a_sixteenth_with_its_own_lyric_is_sung_as_written() -> None:
    result = run(n(0, L("Ma"), dur=DOTTED), n(DOTTED, L("ry"), dur=SIXTEENTH))
    assert [a.role for a in result.attacks] == [R.SYLLABLE, R.SYLLABLE]


def test_other_lengths_are_not_a_dotted_figure() -> None:
    eighth_then_sixteenth = run(n(0, L("la"), dur=EIGHTH), n(EIGHTH, dur=SIXTEENTH))
    assert eighth_then_sixteenth.attacks[1].role is R.MISSING
    dotted_then_eighth = run(n(0, L("la"), dur=DOTTED), n(DOTTED, dur=EIGHTH))
    assert dotted_then_eighth.attacks[1].role is R.MISSING
    dotted_then_longer = run(n(0, L("la"), dur=DOTTED), n(DOTTED, dur=Fraction(3, 8)))
    assert dotted_then_longer.attacks[1].role is R.MISSING


def test_a_rest_between_them_breaks_the_figure() -> None:
    result = run(n(0, L("la"), dur=DOTTED), r(DOTTED, EIGHTH), n(DOTTED + EIGHTH, dur=SIXTEENTH))
    assert [a.role for a in result.attacks] == [R.SYLLABLE, R.REST, R.MISSING]


def test_a_dotted_eighth_that_has_no_syllable_invents_none() -> None:
    result = run(n(0, dur=DOTTED), n(DOTTED, dur=SIXTEENTH))
    assert [a.role for a in result.attacks] == [R.MISSING, R.MISSING]


def test_an_extender_decides_before_the_dotted_figure() -> None:
    result = run(n(0, L("la", melisma=Melisma.UNTYPED), dur=DOTTED), n(DOTTED, dur=SIXTEENTH))
    assert result.attacks[1].melisma_basis is MelismaBasis.UNTYPED


def test_a_slur_decides_before_the_dotted_figure() -> None:
    result = run(
        replace(n(0, L("la"), dur=DOTTED), slurs_opened=1),
        replace(n(DOTTED, dur=SIXTEENTH), slurs_closed=1),
    )
    assert result.attacks[1].melisma_basis is MelismaBasis.SLUR
