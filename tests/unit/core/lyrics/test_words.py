"""The syllabic word state machine (independent of melismas), through ``analyze_line``."""

from barbershop_tracks.core.lyrics import analyze_line
from barbershop_tracks.models import (
    AttackRole,
    LineLyricAnalysis,
    LyricSegment,
    Melisma,
    Severity,
    Syllabic,
)
from lyric_builders import LINE, L, codes, n, performed, r

S = Syllabic


def run(*notes) -> LineLyricAnalysis:  # type: ignore[no-untyped-def]
    return analyze_line(performed(*notes), part_id=LINE)


def texts(analysis: LineLyricAnalysis) -> list[str]:
    return [word.text for word in analysis.words]


# --- well-formed words -------------------------------------------------------------------


def test_single_syllables_are_words() -> None:
    result = run(n(0, L("day", S.SINGLE)), n(1, L("by", S.SINGLE)))
    assert texts(result) == ["day", "by"]
    assert not result.issues


def test_begin_end() -> None:
    result = run(n(0, L("a", S.BEGIN)), n(1, L("way", S.END)))
    assert texts(result) == ["away"]
    assert result.words[0].closed
    assert not result.issues


def test_begin_middle_end() -> None:
    result = run(n(0, L("ba", S.BEGIN)), n(1, L("na", S.MIDDLE)), n(2, L("na", S.END)))
    assert texts(result) == ["banana"]
    assert [s.syllabic for s in result.words[0].syllables] == [S.BEGIN, S.MIDDLE, S.END]
    assert not result.issues


def test_begin_middle_middle_end() -> None:
    notes = [
        n(0, L("a", S.BEGIN)),
        n(1, L("b", S.MIDDLE)),
        n(2, L("c", S.MIDDLE)),
        n(3, L("d", S.END)),
    ]
    assert texts(run(*notes)) == ["abcd"]


def test_attacks_know_their_word() -> None:
    result = run(n(0, L("a", S.BEGIN)), n(1, L("way", S.END)), n(2, L("we", S.SINGLE)))
    assert [a.word_indices for a in result.attacks] == [(0,), (0,), (1,)]


def test_a_word_spans_a_rest_without_error_and_the_rest_is_recorded() -> None:
    result = run(n(0, L("ba", S.BEGIN)), r(1), n(2, L("na", S.END)))
    assert texts(result) == ["bana"]
    assert result.words[0].interrupted_by_rest
    assert not result.issues  # no "words cannot cross rests" rule


def test_a_word_spans_missing_and_continuation_attacks() -> None:
    result = run(n(0, L("ba", S.BEGIN, melisma=Melisma.UNTYPED)), n(1), n(2, L("na", S.END)))
    assert texts(result) == ["bana"]


def test_the_word_text_is_the_literal_join_nothing_is_rewritten() -> None:
    result = run(n(0, L("ba-", S.BEGIN)), n(1, L("na", S.END)))
    assert texts(result) == ["ba-na"]  # the written hyphen is kept (and reported as a hazard)


def test_extend_does_not_substitute_for_syllabic() -> None:
    result = run(n(0, L("day", S.SINGLE, melisma=Melisma.UNTYPED)), n(1), n(2))
    assert texts(result) == ["day"]
    assert [a.role for a in result.attacks][1:] == [AttackRole.MELISMA_CONTINUATION] * 2
    assert result.words[0].syllables[0].attack_index == 0


def test_extend_on_begin_does_not_close_the_word() -> None:
    result = run(n(0, L("a", S.BEGIN, melisma=Melisma.UNTYPED)), n(1), n(2, L("way", S.END)))
    assert texts(result) == ["away"]
    assert not result.issues


# --- malformed chains ---------------------------------------------------------------------


def test_orphan_end() -> None:
    result = run(n(0, L("way", S.END)))
    issue = next(i for i in result.issues if i.code == "LYRIC_WORD_UNOPENED")
    assert issue.severity is Severity.ERROR


def test_orphan_middle_then_end_gives_one_error() -> None:
    result = run(n(0, L("na", S.MIDDLE)), n(1, L("na", S.END)))
    assert codes(result) == ["LYRIC_WORD_UNOPENED"]  # one mistake, one diagnostic
    assert texts(result) == ["nana"]


def test_unfinished_begin_at_the_end_of_the_line() -> None:
    result = run(n(0, L("a", S.BEGIN)))
    issue = next(i for i in result.issues if i.code == "LYRIC_WORD_UNCLOSED")
    assert issue.severity is Severity.ERROR
    assert not result.words[0].closed


def test_begin_followed_by_single_is_unclosed() -> None:
    result = run(n(0, L("a", S.BEGIN)), n(1, L("day", S.SINGLE)))
    assert codes(result) == ["LYRIC_WORD_UNCLOSED"]
    assert texts(result) == ["a", "day"]


def test_begin_followed_by_begin_is_unclosed() -> None:
    result = run(n(0, L("a", S.BEGIN)), n(1, L("b", S.BEGIN)), n(2, L("c", S.END)))
    assert codes(result) == ["LYRIC_WORD_UNCLOSED"]
    assert texts(result) == ["a", "bc"]


def test_middle_never_ended_is_unclosed() -> None:
    result = run(n(0, L("a", S.BEGIN)), n(1, L("b", S.MIDDLE)))
    assert codes(result) == ["LYRIC_WORD_UNCLOSED"]


# --- UNSPECIFIED -----------------------------------------------------------------------------


def test_unspecified_outside_a_word_is_a_complete_syllable_not_an_error() -> None:
    result = run(n(0, L("la", S.UNSPECIFIED)), n(1, L("ni", S.SINGLE)))
    assert texts(result) == ["la", "ni"]
    assert codes(result) == ["LYRIC_SYLLABIC_MISSING"]  # a warning only
    assert not result.issues.has_errors


def test_unspecified_inside_an_open_word_is_ambiguous_and_never_read_as_end() -> None:
    result = run(n(0, L("hel", S.BEGIN)), n(1, L("lo", S.UNSPECIFIED)))
    assert "LYRIC_WORD_AMBIGUOUS" in codes(result)
    ambiguous = next(i for i in result.issues if i.code == "LYRIC_WORD_AMBIGUOUS")
    assert ambiguous.severity is Severity.ERROR
    assert "hel" in ambiguous.message
    assert "hello" not in texts(result)  # not joined
    assert "LYRIC_WORD_UNCLOSED" in codes(result)  # the open BEGIN is still unfinished


def test_unspecified_inside_an_open_word_can_still_be_closed_by_a_real_end() -> None:
    result = run(n(0, L("a", S.BEGIN)), n(1, L("b", S.UNSPECIFIED)), n(2, L("c", S.END)))
    assert codes(result).count("LYRIC_WORD_AMBIGUOUS") == 1
    assert "LYRIC_WORD_UNCLOSED" not in codes(result)
    assert texts(result) == ["ac", "b"]


def test_every_unspecified_in_a_line_is_one_aggregated_warning() -> None:
    notes = [n(i, L("la", S.UNSPECIFIED)) for i in range(10)]
    result = run(*notes)
    assert codes(result).count("LYRIC_SYLLABIC_MISSING") == 1
    assert "10 syllable" in next(
        i.message for i in result.issues if i.code == "LYRIC_SYLLABIC_MISSING"
    )


# --- elided lyrics ---------------------------------------------------------------------------


def test_elided_segments_are_separate_syllables_in_the_chain() -> None:
    lyric = L("the", S.SINGLE, elided=(LyricSegment(text="ir", syllabic=S.SINGLE, joiner="‿"),))
    result = run(n(0, lyric), n(1, L("day", S.SINGLE)))
    assert texts(result) == ["the", "ir", "day"]
    assert result.attacks[0].word_indices == (0, 1)
    assert result.attacks[0].syllable_count == 2
    assert "LYRIC_ELIDED" in codes(result)


def test_an_elided_word_can_begin_in_one_attack_and_end_in_the_next() -> None:
    lyric = L("to", S.SINGLE, elided=(LyricSegment(text="a", syllabic=S.BEGIN),))
    result = run(n(0, lyric), n(1, L("way", S.END)))
    assert texts(result) == ["to", "away"]
    assert not result.issues.has_errors
