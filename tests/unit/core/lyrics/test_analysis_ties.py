"""Lyrics on tied notes: OUR performed-interpretation policy (MusicXML is silent on this).

MusicXML 4.0 says nothing about lyrics on tied notes. MuseScore keeps every lyric where it was
written and plays one attack per tie group. Our policy: the first source note supplies the
attack's lyric; an identical repeat on a continuation is a WARNING; anything else is an ERROR
because merging the tie would swallow it. Nothing is moved, mutated or discarded.
"""

from pathlib import Path

import pytest

from barbershop_tracks.core.lyrics import analyze_line, analyze_song_lyrics
from barbershop_tracks.core.musicxml import parse_musicxml
from barbershop_tracks.models import (
    AttackRole,
    LineLyricAnalysis,
    Lyric,
    LyricSegment,
    Melisma,
    Note,
    Severity,
    Syllabic,
)
from lyric_builders import LINE, L, codes, ext, n, performed

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "musicxml" / "lyrics_ties"
R = AttackRole


def run(*notes, verse: str | None = None) -> LineLyricAnalysis:  # type: ignore[no-untyped-def]
    return analyze_line(performed(*notes), part_id=LINE, verse=verse)


def tie(*lyrics_per_note: tuple[Lyric, ...]) -> list[Note]:
    """A tie group on one pitch: one tuple of lyrics per source note."""
    count = len(lyrics_per_note)
    notes = []
    for i, lyrics in enumerate(lyrics_per_note):
        notes.append(n(i, *lyrics, to=i < count - 1, frm=i > 0))
    return notes


# --- the cases from the research ------------------------------------------------------------


def test_lyric_on_the_start_only_is_the_normal_case() -> None:
    result = run(*tie((L("la"),), ()), n(2, L("ni")))
    assert [a.role for a in result.attacks] == [R.SYLLABLE, R.SYLLABLE]  # one attack per group
    assert not result.issues


def test_three_note_tie_with_the_lyric_on_the_first_only() -> None:
    result = run(*tie((L("la"),), (), ()))
    assert len(result.attacks) == 1
    assert not result.issues


def test_identical_lyric_repeated_on_the_continuation_is_a_warning() -> None:
    result = run(*tie((L("la"),), (L("la"),)))
    issue = next(i for i in result.issues if i.code == "LYRIC_TIE_REPEATED")
    assert issue.severity is Severity.WARNING
    assert issue.measure == 1
    assert issue.beat == 2  # located at the continuation note
    assert "MusicXML does not say" in issue.message  # presented as our policy, not a MusicXML rule
    assert not result.issues.has_errors
    assert len(result.attacks) == 1


def test_different_lyric_on_the_continuation_is_an_error() -> None:
    result = run(*tie((L("la"),), (L("ni"),)))
    issue = next(i for i in result.issues if i.code == "LYRIC_TIE_CONFLICT")
    assert issue.severity is Severity.ERROR
    assert "'ni'" in issue.message
    assert "MusicXML does not say" in issue.message
    assert result.attacks[0].lyric is not None
    assert result.attacks[0].lyric.text == "la"  # the first note's lyric is the attack's


def test_continuation_lyric_with_none_on_the_start_is_an_error_and_not_moved() -> None:
    result = run(*tie((), (L("ni"),)))
    assert "LYRIC_TIE_CONFLICT" in codes(result)
    assert result.attacks[0].role is R.MISSING  # we do not move "ni" onto the attack
    assert result.attacks[0].lyric is None


def test_three_note_tie_with_lyrics_on_later_members() -> None:
    result = run(*tie((L("la"),), (L("ni"),), (L("na"),)))
    assert codes(result) == ["LYRIC_TIE_CONFLICT", "LYRIC_TIE_CONFLICT"]  # each is located
    assert [i.beat for i in result.issues] == [2, 3]


def test_a_repeat_and_a_conflict_on_one_tie_group_are_reported_separately() -> None:
    result = run(*tie((L("la"),), (L("la"),), (L("ni"),)))
    assert codes(result) == ["LYRIC_TIE_REPEATED", "LYRIC_TIE_CONFLICT"]


# --- "identical" means the meaningful literal content, not flattened text ---------------------


@pytest.mark.parametrize(
    "continuation",
    [
        L("la", Syllabic.BEGIN),  # same text, different syllabic
        L("la", Syllabic.UNSPECIFIED),
        L("la", melisma=Melisma.UNTYPED),  # same text, an extender the attack lacks
        L("la", elided=(LyricSegment(text="x"),)),  # same first text, extra elided syllable
    ],
)
def test_same_text_with_different_semantics_is_not_harmless_repetition(continuation) -> None:  # type: ignore[no-untyped-def]
    result = run(*tie((L("la", Syllabic.SINGLE),), (continuation,)))
    assert codes(result) == ["LYRIC_TIE_CONFLICT"]


def test_a_different_lyric_kind_is_a_conflict() -> None:
    from barbershop_tracks.models import Lyric

    assert codes(run(*tie((L("la"),), (Lyric.humming(),)))) == ["LYRIC_TIE_CONFLICT"]


def test_identical_content_ignores_verse_spelling_name_and_time_only() -> None:
    from barbershop_tracks.models import Lyric

    start = Lyric(text="la", syllabic=Syllabic.SINGLE, verse=None)
    cont = Lyric(text="la", syllabic=Syllabic.SINGLE, verse="1", name="verse")
    assert codes(run(*tie((start,), (cont,)))) == [
        "LYRIC_TIE_REPEATED",
        "LYRIC_VERSE_MIXED_NUMBERING",  # unnumbered and "1" are mixed in the stream
    ]


def test_identical_extender_on_both_notes_is_a_repeat_and_opens_one_melisma() -> None:
    result = run(
        *tie((L("la", melisma=Melisma.UNTYPED),), (L("la", melisma=Melisma.UNTYPED),)), n(2)
    )
    assert codes(result) == ["LYRIC_TIE_REPEATED"]
    assert [a.role for a in result.attacks] == [R.SYLLABLE, R.MELISMA_CONTINUATION]


# --- extension-only continuation events -------------------------------------------------------


def test_extension_only_continue_on_a_continuation_feeds_the_typed_state() -> None:
    notes = [
        n(0, L("la", melisma=Melisma.START), to=True),
        n(1, ext(Melisma.CONTINUE), frm=True),
        n(2),
    ]
    result = run(*notes)
    assert [a.role for a in result.attacks] == [R.SYLLABLE, R.MELISMA_CONTINUATION]
    assert "LYRIC_TIE_CONFLICT" not in codes(result)
    assert result.coverage.longest_melisma == 1


def test_longest_melisma_counts_performed_continuation_attacks_only() -> None:
    # attack + 23 continuation attacks, where some attacks are tie groups carrying extra
    # source notes, typed CONTINUE markers and a STOP on swallowed (tie-continuation) notes
    notes = [n(0, L("la", melisma=Melisma.START), to=True), n(1, ext(Melisma.CONTINUE), frm=True)]
    notes += [n(i) for i in range(2, 24)]  # 22 more lyric-less attacks
    notes += [n(24, to=True), n(25, ext(Melisma.STOP), frm=True)]  # 1 attack, 2 source notes
    result = run(*notes)
    continuations = [a for a in result.attacks if a.role is R.MELISMA_CONTINUATION]
    assert len(continuations) == 23
    assert result.coverage.longest_melisma == 23
    assert len(result.attacks) == 24  # source notes (26) are not attacks


def test_extension_only_stop_on_a_continuation_closes_the_extension() -> None:
    notes = [n(0, L("la", melisma=Melisma.START), to=True), n(1, ext(Melisma.STOP), frm=True), n(2)]
    result = run(*notes)
    assert "LYRIC_MELISMA_UNCLOSED" not in codes(result)
    assert result.attacks[1].role is R.MISSING  # the extension was closed by the STOP


def test_extension_only_event_on_a_continuation_without_an_open_extension_is_an_error() -> None:
    result = run(*tie((L("la"),), (ext(Melisma.STOP),)))
    assert "LYRIC_EXTEND_WITHOUT_START" in codes(result)


def test_extension_only_untyped_on_a_continuation_is_invalid() -> None:
    result = run(*tie((L("la"),), (ext(Melisma.UNTYPED),)))
    assert "LYRIC_EXTEND_SEQUENCE_INVALID" in codes(result)


def test_a_tie_group_can_be_a_melisma_continuation() -> None:
    notes = [n(0, L("la", melisma=Melisma.UNTYPED)), *tie_at(1, 2)]
    result = run(*notes, n(3, L("ni")))
    assert [a.role for a in result.attacks] == [R.SYLLABLE, R.MELISMA_CONTINUATION, R.SYLLABLE]
    assert not result.issues


def tie_at(first: int, count: int) -> list[Note]:
    return [n(first + i, to=i < count - 1, frm=i > 0) for i in range(count)]


# --- verses on continuations ---------------------------------------------------------------


def test_a_continuation_lyric_in_another_verse_is_ignored_for_the_selected_verse() -> None:
    result = run(*tie((L("la", verse="1"),), (L("ni", verse="2"),)))
    assert "LYRIC_TIE_CONFLICT" not in codes(result)
    assert "LYRIC_MULTIPLE_VERSES" in codes(result)


def test_the_continuation_lyric_conflicts_when_that_verse_is_selected() -> None:
    result = run(*tie((L("la", verse="1"),), (L("ni", verse="2"),)), verse="2")
    assert "LYRIC_TIE_CONFLICT" in codes(result)  # verse 2 has no lyric on the attack
    assert result.attacks[0].role is R.MISSING


# --- source untouched, tie diagnostics of the parser stay with the parser ----------------------


def test_source_notes_inside_the_group_are_never_modified() -> None:
    first, second = n(0, L("la"), to=True), n(1, L("ni"), frm=True)
    snapshot = (first.lyrics, second.lyrics)
    result = run(first, second)
    assert (first.lyrics, second.lyrics) == snapshot
    assert result.attacks[0].performed.source == (first, second)


# --- the MuseScore research fixtures (parsed, merged, analyzed) --------------------------------


def analyze_fixture(name: str, variant: str = "inputs") -> LineLyricAnalysis:
    parsed = parse_musicxml(FIXTURES / variant / f"{name}.musicxml")
    assert parsed.song is not None
    return analyze_song_lyrics(parsed.song).lines[0]


@pytest.mark.parametrize("variant", ["inputs", "musescore_roundtrip"])
def test_fixture_t1_lyric_on_start_only(variant: str) -> None:
    assert not analyze_fixture("t1_lyric_on_start_only", variant).issues.has_errors


@pytest.mark.parametrize("variant", ["inputs", "musescore_roundtrip"])
def test_fixture_t2_repeated_lyric_is_a_warning(variant: str) -> None:
    assert "LYRIC_TIE_REPEATED" in codes(analyze_fixture("t2_same_lyric_repeated", variant))


@pytest.mark.parametrize("variant", ["inputs", "musescore_roundtrip"])
def test_fixture_t3_different_lyric_is_an_error(variant: str) -> None:
    assert "LYRIC_TIE_CONFLICT" in codes(
        analyze_fixture("t3_different_lyric_on_continuation", variant)
    )


@pytest.mark.parametrize("variant", ["inputs", "musescore_roundtrip"])
def test_fixture_t4_continuation_lyric_only(variant: str) -> None:
    result = analyze_fixture("t4_continuation_lyric_only", variant)
    assert "LYRIC_TIE_CONFLICT" in codes(result)
    assert result.attacks[0].role is R.MISSING


@pytest.mark.parametrize("variant", ["inputs", "musescore_roundtrip"])
def test_fixture_t5_three_note_tie_first_only(variant: str) -> None:
    result = analyze_fixture("t5_three_note_tie_first_only", variant)
    assert not result.issues.has_errors
    assert len(result.attacks[0].performed.source) == 3


@pytest.mark.parametrize("variant", ["inputs", "musescore_roundtrip"])
def test_fixture_t6_later_members_conflict_twice(variant: str) -> None:
    result = analyze_fixture("t6_three_note_tie_later_members", variant)
    assert codes(result).count("LYRIC_TIE_CONFLICT") == 2


@pytest.mark.parametrize("variant", ["inputs", "musescore_roundtrip"])
def test_fixture_t7a_extender_on_the_tie_start(variant: str) -> None:
    result = analyze_fixture("t7a_extend_on_tie_start", variant)
    assert not result.issues.has_errors
    assert result.attacks[0].role is R.SYLLABLE


@pytest.mark.parametrize("variant", ["inputs", "musescore_roundtrip"])
def test_fixture_t7b_extender_on_the_continuation_conflicts(variant: str) -> None:
    assert "LYRIC_TIE_CONFLICT" in codes(analyze_fixture("t7b_extend_on_continuation", variant))


def test_fixture_t7c_extension_only_continuation_is_invalid_where_it_survives() -> None:
    # MuseScore drops this lyric on export, so only the hand-written input still has it.
    assert "LYRIC_EXTEND_SEQUENCE_INVALID" in codes(
        analyze_fixture("t7c_extend_only_on_continuation")
    )
    assert "LYRIC_EXTEND_SEQUENCE_INVALID" not in codes(
        analyze_fixture("t7c_extend_only_on_continuation", "musescore_roundtrip")
    )


@pytest.mark.parametrize("variant", ["inputs", "musescore_roundtrip"])
def test_fixture_t8_a_tie_group_inside_a_melisma(variant: str) -> None:
    result = analyze_fixture("t8_tie_then_next_note_lyric_less_after_melisma", variant)
    assert [a.role for a in result.attacks] == [R.SYLLABLE, R.MELISMA_CONTINUATION, R.SYLLABLE]
    assert not result.issues.has_errors


@pytest.mark.parametrize("variant", ["inputs", "musescore_roundtrip"])
def test_fixture_t9_verse_two_on_the_continuation_only(variant: str) -> None:
    result = analyze_fixture("t9_verse2_only_on_continuation", variant)
    assert result.verse == "1"
    assert "LYRIC_TIE_CONFLICT" not in codes(result)  # it belongs to verse 2, not the analyzed one
