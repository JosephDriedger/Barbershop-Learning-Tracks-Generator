"""A slur over a note with no lyric of its own holds the syllable before it (one syllable, many).

MuseScore writes no extender for this unless the lyric has one, so the slur is the only sign. An
extender (typed or untyped) always decides first; a slur never invents a syllable that was not sung.
"""

from dataclasses import replace

import pytest

from barbershop_tracks.core.lyrics import analyze_line
from barbershop_tracks.models import AttackRole, LineLyricAnalysis, Melisma, MelismaBasis, Note
from lyric_builders import LINE, L, n, performed, r

R = AttackRole


def slurred(note: Note, *, opens: int = 0, closes: int = 0) -> Note:
    return replace(note, slurs_opened=opens, slurs_closed=closes)


def run(*notes: Note) -> LineLyricAnalysis:
    return analyze_line(performed(*notes), part_id=LINE)


def test_a_slur_over_a_lyric_less_note_holds_the_syllable() -> None:
    result = run(slurred(n(0, L("cis")), opens=1), slurred(n(1), closes=1), n(2, L("co")))
    assert [a.role for a in result.attacks] == [R.SYLLABLE, R.MELISMA_CONTINUATION, R.SYLLABLE]
    held = result.attacks[1]
    assert held.melisma_origin == 0
    assert held.melisma_position == 1
    assert held.melisma_basis is MelismaBasis.SLUR


def test_without_a_slur_the_same_notes_are_missing_a_lyric() -> None:
    result = run(n(0, L("cis")), n(1), n(2, L("co")))
    assert [a.role for a in result.attacks] == [R.SYLLABLE, R.MISSING, R.SYLLABLE]


def test_a_longer_slur_holds_every_note_under_it() -> None:
    result = run(slurred(n(0, L("Bay")), opens=1), n(1), n(2), slurred(n(3), closes=1), n(4))
    assert [a.role for a in result.attacks] == [
        R.SYLLABLE,
        R.MELISMA_CONTINUATION,
        R.MELISMA_CONTINUATION,
        R.MELISMA_CONTINUATION,
        R.MISSING,  # after the slur ended
    ]
    assert [a.melisma_position for a in result.attacks[1:4]] == [1, 2, 3]


def test_a_note_with_its_own_lyric_under_a_slur_is_sung_as_written() -> None:
    result = run(slurred(n(0, L("Fran")), opens=1), slurred(n(1, L("cis")), closes=1))
    assert [a.role for a in result.attacks] == [R.SYLLABLE, R.SYLLABLE]


def test_a_slur_that_starts_on_a_note_without_a_syllable_invents_none() -> None:
    result = run(slurred(n(0), opens=1), slurred(n(1), closes=1))
    assert [a.role for a in result.attacks] == [R.MISSING, R.MISSING]


def test_a_rest_ends_the_hold() -> None:
    result = run(slurred(n(0, L("la")), opens=1), r(1), slurred(n(2), closes=1))
    assert [a.role for a in result.attacks] == [R.SYLLABLE, R.REST, R.MISSING]


def test_an_extender_decides_before_a_slur() -> None:
    result = run(slurred(n(0, L("la", melisma=Melisma.UNTYPED)), opens=1), slurred(n(1), closes=1))
    assert result.attacks[1].melisma_basis is MelismaBasis.UNTYPED


def test_a_slur_opened_on_the_syllable_and_a_second_one_nested_inside() -> None:
    result = run(
        slurred(n(0, L("la")), opens=1),
        slurred(n(1), opens=1),
        slurred(n(2), closes=1),
        slurred(n(3), closes=1),
        n(4),
    )
    assert [a.role for a in result.attacks] == [
        R.SYLLABLE,
        R.MELISMA_CONTINUATION,
        R.MELISMA_CONTINUATION,
        R.MELISMA_CONTINUATION,
        R.MISSING,
    ]


def test_slur_marks_are_stored_on_the_note_and_a_rest_has_none() -> None:
    note = slurred(n(0, L("la")), opens=2, closes=1)
    assert (note.slurs_opened, note.slurs_closed) == (2, 1)
    with pytest.raises(ValueError, match="rest cannot have slurs"):
        replace(r(0), slurs_opened=1)
