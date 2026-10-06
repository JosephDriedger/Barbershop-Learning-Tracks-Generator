"""Attack roles, verse selection, coverage aggregation and text hazards."""

from fractions import Fraction

import pytest

from barbershop_tracks.core.lyrics import analyze_line, choose_verse, logical_verses
from barbershop_tracks.models import (
    AttackRole,
    LineLyricAnalysis,
    Lyric,
    Melisma,
    Severity,
    Syllabic,
)
from lyric_builders import LINE, L, codes, n, performed, r

R = AttackRole
S = Syllabic


def run(*notes, verse: str | None = None) -> LineLyricAnalysis:  # type: ignore[no-untyped-def]
    return analyze_line(performed(*notes), part_id=LINE, verse=verse)


# --- basic roles -----------------------------------------------------------------------------


def test_normal_single_syllables() -> None:
    result = run(n(0, L("la")), n(1, L("ni")), n(2, L("na")))
    assert [a.role for a in result.attacks] == [R.SYLLABLE] * 3
    assert [a.lyric.text for a in result.attacks if a.lyric] == ["la", "ni", "na"]
    assert result.verse == "1"
    assert result.coverage.syllable_attacks == 3
    assert not result.issues


def test_rests_are_rests() -> None:
    result = run(n(0, L("la")), r(1), n(2, L("ni")))
    assert [a.role for a in result.attacks] == [R.SYLLABLE, R.REST, R.SYLLABLE]
    assert result.coverage.sung_attacks == 2


def test_empty_line() -> None:
    result = analyze_line([], part_id=LINE)
    assert result.attacks == ()
    assert result.verse is None
    assert not result.issues  # nothing sung, nothing to report


def test_a_line_of_only_rests_is_not_reported() -> None:
    assert not run(r(0), r(1)).issues


def test_attack_refers_to_its_performance_note() -> None:
    notes = performed(n(0, L("la")), n(1, L("ni")))
    result = analyze_line(notes, part_id=LINE)
    assert [a.performed for a in result.attacks] == notes
    assert [a.index for a in result.attacks] == [0, 1]


def test_simultaneous_attacks_are_reported() -> None:
    result = run(n(0, L("la")), n(0, L("ni"), pitch=n(0).written_pitch))
    assert "LYRIC_SIMULTANEOUS_ATTACKS" in codes(result)


def test_duplicate_lyrics_for_the_verse_are_a_conflict_and_nothing_is_chosen() -> None:
    result = run(n(0, L("la"), L("ni")))
    assert result.attacks[0].role is R.CONFLICT
    assert result.attacks[0].lyric is None
    assert result.coverage.conflict_attacks == 1


# --- coverage aggregation ------------------------------------------------------------------


def test_a_lyricless_line_gives_one_issue_not_hundreds() -> None:
    result = run(*[n(i) for i in range(300)])
    assert codes(result) == ["LYRIC_LINE_EMPTY"]
    assert result.issues.issues[0].severity is Severity.WARNING
    assert result.coverage.missing_attacks == 300
    assert not result.coverage.has_any_lyric


def test_a_mostly_lyricless_line_gives_one_summary_with_structured_runs() -> None:
    notes = []
    for i in range(0, 200, 20):
        notes += [n(i, L("la"))] + [n(i + k) for k in range(1, 20)]
    result = run(*notes)
    assert codes(result) == ["LYRIC_MISSING_SUMMARY"]
    assert result.coverage.missing_attacks == 190
    assert len(result.coverage.missing_runs) == 10
    assert all(run_.count == 19 for run_ in result.coverage.missing_runs)
    assert (
        "190 performed attacks lack resolved lyrics across 10 runs"
        in result.issues.issues[0].message
    )


def test_runs_have_exact_locations() -> None:
    result = run(n(0, L("la")), n(1), n(2), n(3, L("ni")), n(7), n(8, L("na")))
    first, second = result.coverage.missing_runs
    assert (first.first_index, first.last_index, first.count) == (1, 2, 2)
    assert (first.first_measure, first.first_beat) == (1, Fraction(2))
    assert (first.last_measure, first.last_beat) == (1, Fraction(3))
    assert (second.count, second.first_measure, second.first_beat) == (1, 2, Fraction(4))
    summary = result.issues.issues[0]
    assert (summary.measure, summary.beat) == (1, Fraction(2))  # located at the first run


def test_rests_do_not_split_a_missing_run() -> None:
    result = run(n(0, L("la")), n(1), r(2), n(3), n(4, L("ni")))
    (only,) = result.coverage.missing_runs
    assert only.count == 2


def test_melisma_attacks_are_never_reported_as_missing() -> None:
    result = run(n(0, L("la", melisma=Melisma.UNTYPED)), *[n(i) for i in range(1, 30)])
    assert not result.issues
    assert result.coverage.missing_attacks == 0


def test_isolated_missing_attack_is_still_one_summary() -> None:
    result = run(n(0, L("la")), n(1), n(2, L("ni")))
    assert codes(result) == ["LYRIC_MISSING_SUMMARY"]
    assert "1 performed attacks lack" in result.issues.issues[0].message
    assert "1 run " in result.issues.issues[0].message


def test_humming_counts_as_a_lyric_for_coverage() -> None:
    result = run(n(0, Lyric.humming()), n(1))
    assert result.coverage.has_any_lyric
    assert codes(result) == ["LYRIC_MISSING_SUMMARY"]


# --- verse selection -------------------------------------------------------------------------


def test_choose_verse_prefers_logical_one() -> None:
    assert choose_verse(["2", "1"]).selected == "1"
    assert choose_verse(["3", "2"]).selected == "3"  # first in document order
    assert choose_verse([]).selected is None


def test_requested_verse_overrides_and_reports_whether_it_exists() -> None:
    assert choose_verse(["1", "2"], "2").selected == "2"
    missing = choose_verse(["1"], "7")
    assert (missing.selected, missing.found) == ("7", False)


def test_only_explicit_verse_one() -> None:
    result = run(n(0, L("la", verse="1")))
    assert result.verse == "1"
    assert not result.issues


def test_only_unnumbered_lyrics() -> None:
    result = run(n(0, L("la")), n(1, L("ni")))
    assert result.verse == "1"
    assert result.verses == ("1",)
    assert result.coverage.syllable_attacks == 2


def test_mixed_numbered_and_unnumbered_are_one_stream_with_one_warning() -> None:
    result = run(n(0, L("la", verse="1")), n(1, L("ni")), n(2, L("na", verse="1")), n(3, L("ma")))
    assert result.coverage.syllable_attacks == 4  # analyzed together
    assert codes(result) == ["LYRIC_VERSE_MIXED_NUMBERING"]  # once, not once per note


def test_mixed_numbering_warning_only_applies_to_verse_one() -> None:
    result = run(n(0, L("la", verse="2")), n(1, L("ni", verse="2")))
    assert "LYRIC_VERSE_MIXED_NUMBERING" not in codes(result)


def test_only_verse_two_is_analyzed_without_renumbering_or_warning() -> None:
    result = run(n(0, L("la", verse="2")), n(1, L("ni", verse="2")))
    assert result.verse == "2"
    assert not result.issues
    assert result.attacks[0].lyric is not None
    assert result.attacks[0].lyric.verse == "2"  # the source number is untouched


def test_several_verses_select_one_and_warn_once() -> None:
    result = run(
        n(0, L("la", verse="1"), L("ni", verse="2")), n(1, L("na", verse="1"), L("ma", verse="2"))
    )
    assert result.verse == "1"
    assert result.verses == ("1", "2")
    assert codes(result) == ["LYRIC_MULTIPLE_VERSES"]
    assert [a.lyric.text for a in result.attacks if a.lyric] == ["la", "na"]


def test_several_verses_without_one_fall_back_and_explain() -> None:
    result = run(n(0, L("la", verse="3"), L("ni", verse="2")))
    assert result.verse == "3"  # first in document order
    issue = next(i for i in result.issues if i.code == "LYRIC_MULTIPLE_VERSES")
    assert "no verse '1'" in issue.message
    assert "3" in issue.message


def test_requested_verse_selects_that_stream() -> None:
    result = run(n(0, L("la", verse="1"), L("ni", verse="2")), verse="2")
    assert result.verse == "2"
    assert result.attacks[0].lyric is not None
    assert result.attacks[0].lyric.text == "ni"
    assert "LYRIC_MULTIPLE_VERSES" not in codes(result)  # the choice was explicit


def test_requested_verse_one_matches_unnumbered_lyrics() -> None:
    result = run(n(0, L("la")), verse="1")
    assert result.attacks[0].role is R.SYLLABLE


def test_a_requested_verse_the_line_lacks_is_an_error() -> None:
    result = run(n(0, L("la")), verse="5")
    issue = next(i for i in result.issues if i.code == "LYRIC_VERSE_NOT_FOUND")
    assert issue.severity is Severity.ERROR
    assert result.attacks[0].role is R.MISSING


def test_logical_verses_are_in_document_order() -> None:
    notes = performed(n(0, L("a", verse="2")), n(1, L("b", verse="1")), n(2, L("c")))
    assert logical_verses(notes) == ("2", "1")


# --- text hazards (reported, never rewritten) -------------------------------------------------


@pytest.mark.parametrize(
    ("text", "code"),
    [
        (" la", "LYRIC_TEXT_WHITESPACE"),
        ("la ", "LYRIC_TEXT_WHITESPACE"),
        ("la ni", "LYRIC_TEXT_INNER_SPACE"),
        ("ba-", "LYRIC_TEXT_TRAILING_HYPHEN"),
        ("-", "LYRIC_TEXT_RESERVED_CHARACTERS"),
        ("+", "LYRIC_TEXT_RESERVED_CHARACTERS"),
        ("+la", "LYRIC_TEXT_RESERVED_CHARACTERS"),
        ("[la]", "LYRIC_TEXT_RESERVED_CHARACTERS"),
        ("la~", "LYRIC_TEXT_RESERVED_CHARACTERS"),
    ],
)
def test_each_hazard_is_reported_as_a_warning(text: str, code: str) -> None:
    result = run(n(0, L(text)))
    issue = next(i for i in result.issues if i.code == code)
    assert issue.severity is Severity.WARNING
    assert result.attacks[0].lyric is not None
    assert result.attacks[0].lyric.text == text  # the text is exactly as written


def test_ordinary_text_has_no_hazard() -> None:
    assert not run(n(0, L("la")), n(1, L("ni-ni"))).issues


def test_a_lone_hyphen_is_reserved_but_not_a_trailing_hyphen() -> None:
    assert codes(run(n(0, L("-")))) == ["LYRIC_TEXT_RESERVED_CHARACTERS"]


def test_hazards_are_aggregated_one_issue_per_kind_per_line() -> None:
    result = run(*[n(i, L(f"la{' ' * 1}")) for i in range(50)])
    assert codes(result).count("LYRIC_TEXT_WHITESPACE") == 1
    message = next(i.message for i in result.issues if i.code == "LYRIC_TEXT_WHITESPACE")
    assert message.startswith("50 syllable")


def test_hazards_ignore_other_verses() -> None:
    result = run(n(0, L("la", verse="1"), L("+", verse="2")))
    assert "LYRIC_TEXT_RESERVED_CHARACTERS" not in codes(result)


def test_an_elided_hazard_in_a_later_segment_is_found() -> None:
    from barbershop_tracks.models import LyricSegment

    lyric = L("la", elided=(LyricSegment(text="ni ", joiner="_"),))
    assert "LYRIC_TEXT_WHITESPACE" in codes(run(n(0, lyric)))


def test_syllabic_values_are_kept_on_the_attack_lyrics() -> None:
    result = run(n(0, L("a", S.BEGIN)), n(1, L("way", S.END)))
    assert [a.lyric.syllabic for a in result.attacks if a.lyric] == [S.BEGIN, S.END]
