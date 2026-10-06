"""The typed and untyped melisma state machines, through ``analyze_line``."""

import pytest

from barbershop_tracks.core.lyrics import analyze_line
from barbershop_tracks.models import (
    AttackRole,
    LineLyricAnalysis,
    Melisma,
    MelismaBasis,
    Severity,
    Syllabic,
)
from lyric_builders import LINE, L, codes, ext, n, performed, r

R = AttackRole


def run(*notes) -> LineLyricAnalysis:  # type: ignore[no-untyped-def]
    return analyze_line(performed(*notes), part_id=LINE)


def roles(analysis: LineLyricAnalysis) -> list[AttackRole]:
    return [a.role for a in analysis.attacks]


# --- untyped (MuseScore style, inferred) -----------------------------------------------


@pytest.mark.parametrize("length", [1, 2, 6, 23])
def test_untyped_extender_followed_by_lyricless_attacks_of_any_length(length: int) -> None:
    # The 23-note case reflects a structure observed in a real score (no content committed).
    notes = [n(0, L("la", melisma=Melisma.UNTYPED))]
    notes += [n(i) for i in range(1, length + 1)]
    notes += [n(length + 1, L("ni"))]
    result = run(*notes)
    assert roles(result) == [R.SYLLABLE] + [R.MELISMA_CONTINUATION] * length + [R.SYLLABLE]
    assert result.coverage.longest_melisma == length
    assert result.coverage.continuation_attacks == length
    assert result.coverage.missing_attacks == 0
    assert not result.issues


def test_continuations_know_their_origin_position_and_basis() -> None:
    result = run(n(0, L("la", melisma=Melisma.UNTYPED)), n(1), n(2), n(3, L("ni")))
    one, two = result.attacks[1], result.attacks[2]
    assert (one.melisma_origin, one.melisma_position) == (0, 1)
    assert (two.melisma_origin, two.melisma_position) == (0, 2)
    assert one.melisma_basis is MelismaBasis.UNTYPED
    assert result.attacks[3].melisma_origin is None


def test_untyped_is_never_treated_as_a_typed_start() -> None:
    result = run(n(0, L("la", melisma=Melisma.UNTYPED)), n(1), n(2, ext(Melisma.CONTINUE)))
    assert "LYRIC_EXTEND_WITHOUT_START" in codes(result)  # no explicit START was ever invented


def test_without_an_extender_lyricless_attacks_are_missing_not_a_melisma() -> None:
    result = run(n(0, L("la")), n(1), n(2))
    assert roles(result) == [R.SYLLABLE, R.MISSING, R.MISSING]


def test_a_new_lyric_ends_an_untyped_extender() -> None:
    result = run(n(0, L("la", melisma=Melisma.UNTYPED)), n(1), n(2, L("ni")), n(3))
    assert roles(result) == [R.SYLLABLE, R.MELISMA_CONTINUATION, R.SYLLABLE, R.MISSING]


def test_a_new_lyric_with_its_own_extender_opens_a_new_melisma() -> None:
    result = run(
        n(0, L("la", melisma=Melisma.UNTYPED)),
        n(1),
        n(2, L("ni", melisma=Melisma.UNTYPED)),
        n(3),
    )
    assert roles(result) == [R.SYLLABLE, R.MELISMA_CONTINUATION, R.SYLLABLE, R.MELISMA_CONTINUATION]
    assert result.attacks[3].melisma_origin == 2


def test_untyped_extender_open_at_the_end_of_the_line_is_not_flagged() -> None:
    result = run(n(0, L("la", melisma=Melisma.UNTYPED)), n(1), n(2))
    assert roles(result)[1:] == [R.MELISMA_CONTINUATION] * 2
    assert not result.issues


def test_untyped_extender_on_the_last_attack_is_fine() -> None:
    assert not run(n(0, L("la")), n(1, L("ni", melisma=Melisma.UNTYPED))).issues


# --- rests and untyped extenders ---------------------------------------------------------


def test_untyped_extender_then_rest_then_lyricless_note_is_missing() -> None:
    result = run(n(0, L("la", melisma=Melisma.UNTYPED)), n(1), r(2), n(3), n(4, L("ni")))
    assert roles(result) == [R.SYLLABLE, R.MELISMA_CONTINUATION, R.REST, R.MISSING, R.SYLLABLE]
    interrupted = [i for i in result.issues if i.code == "LYRIC_MELISMA_INTERRUPTED"]
    assert len(interrupted) == 1  # one line-level warning, not one per note
    assert interrupted[0].severity is Severity.WARNING
    assert "MusicXML does not say" in interrupted[0].message  # named as our interpretation


def test_interruption_warning_is_aggregated_for_several_rests() -> None:
    notes = []
    for i in range(0, 12, 4):
        notes += [n(i, L("la", melisma=Melisma.UNTYPED)), r(i + 1), n(i + 2)]
    result = run(*notes)
    assert codes(result).count("LYRIC_MELISMA_INTERRUPTED") == 1
    assert "3 untyped extender" in next(
        i.message for i in result.issues if i.code == "LYRIC_MELISMA_INTERRUPTED"
    )


def test_untyped_extender_then_rest_then_a_new_lyric_is_not_interrupted() -> None:
    result = run(n(0, L("la", melisma=Melisma.UNTYPED)), r(1), n(2, L("ni")))
    assert "LYRIC_MELISMA_INTERRUPTED" not in codes(result)


def test_untyped_extender_ending_at_a_rest_that_ends_the_line_is_not_interrupted() -> None:
    result = run(n(0, L("la", melisma=Melisma.UNTYPED)), n(1), r(2))
    assert not result.issues


def test_rest_with_no_active_extender_changes_nothing() -> None:
    result = run(n(0, L("la")), r(1), n(2))
    assert roles(result) == [R.SYLLABLE, R.REST, R.MISSING]
    assert "LYRIC_MELISMA_INTERRUPTED" not in codes(result)


def test_rest_gets_the_rest_role_never_a_continuation() -> None:
    result = run(n(0, L("la", melisma=Melisma.UNTYPED)), r(1))
    assert result.attacks[1].role is R.REST


# --- typed explicit state ----------------------------------------------------------------


def typed_start(text: str = "la"):  # type: ignore[no-untyped-def]
    return L(text, melisma=Melisma.START)


def test_typed_start_continue_stop() -> None:
    result = run(
        n(0, typed_start()),
        n(1, ext(Melisma.CONTINUE)),
        n(2),
        n(3, ext(Melisma.STOP)),
        n(4),
    )
    assert roles(result) == [
        R.SYLLABLE,
        R.MELISMA_CONTINUATION,
        R.MELISMA_CONTINUATION,
        R.MELISMA_CONTINUATION,
        R.MISSING,
    ]
    assert result.attacks[1].melisma_basis is MelismaBasis.TYPED
    assert codes(result) == ["LYRIC_MISSING_SUMMARY"]  # only the trailing attack after STOP


def test_typed_start_then_rest_then_continue_and_stop_is_one_extension() -> None:
    result = run(n(0, typed_start()), r(1), n(2, ext(Melisma.CONTINUE)), n(3, ext(Melisma.STOP)))
    assert roles(result) == [R.SYLLABLE, R.REST, R.MELISMA_CONTINUATION, R.MELISMA_CONTINUATION]
    assert not result.issues  # the explicit state is stronger evidence than the rest


def test_typed_start_then_rest_then_lyricless_note_then_stop() -> None:
    result = run(n(0, typed_start()), r(1), n(2), n(3, ext(Melisma.STOP)), n(4))
    assert roles(result) == [
        R.SYLLABLE,
        R.REST,
        R.MELISMA_CONTINUATION,
        R.MELISMA_CONTINUATION,
        R.MISSING,
    ]
    assert codes(result) == ["LYRIC_MISSING_SUMMARY"]  # nothing about the typed extension


def test_typed_extension_survives_a_rest_and_is_unclosed_at_the_end_of_the_line() -> None:
    result = run(n(0, typed_start()), r(1), n(2))
    assert roles(result) == [R.SYLLABLE, R.REST, R.MELISMA_CONTINUATION]
    issue = next(i for i in result.issues if i.code == "LYRIC_MELISMA_UNCLOSED")
    assert issue.severity is Severity.WARNING
    assert issue.measure == 1
    assert issue.beat == 1  # located at the START


def test_unclosed_typed_start_keeps_the_analysis() -> None:
    result = run(n(0, typed_start()), n(1), n(2))
    assert roles(result) == [R.SYLLABLE, R.MELISMA_CONTINUATION, R.MELISMA_CONTINUATION]
    assert not result.issues.has_errors


def test_typed_start_ended_by_a_new_lyric_is_unclosed() -> None:
    result = run(n(0, typed_start()), n(1), n(2, L("ni")))
    assert "LYRIC_MELISMA_UNCLOSED" in codes(result)
    assert roles(result)[2] is R.SYLLABLE


def test_continue_without_a_typed_extension_is_an_error() -> None:
    result = run(n(0, L("la")), n(1, ext(Melisma.CONTINUE)))
    issue = next(i for i in result.issues if i.code == "LYRIC_EXTEND_WITHOUT_START")
    assert issue.severity is Severity.ERROR
    assert result.attacks[1].role is R.CONFLICT


def test_stop_without_a_typed_extension_is_an_error() -> None:
    result = run(n(0, ext(Melisma.STOP)))
    assert "LYRIC_EXTEND_WITHOUT_START" in codes(result)


def test_stop_closes_the_extension() -> None:
    result = run(n(0, typed_start()), n(1, ext(Melisma.STOP)), n(2, ext(Melisma.CONTINUE)))
    assert codes(result) == ["LYRIC_EXTEND_WITHOUT_START"]  # nothing is open any more


@pytest.mark.parametrize("form", [Melisma.UNTYPED, Melisma.START])
def test_extension_only_start_or_untyped_starts_nothing(form: Melisma) -> None:
    result = run(n(0, L("la")), n(1, ext(form)))
    issue = next(i for i in result.issues if i.code == "LYRIC_EXTEND_SEQUENCE_INVALID")
    assert issue.severity is Severity.ERROR
    assert result.attacks[1].role is R.CONFLICT


@pytest.mark.parametrize("form", [Melisma.CONTINUE, Melisma.STOP])
def test_text_that_claims_to_continue_or_stop_is_an_analysis_error(form: Melisma) -> None:
    result = run(n(0, typed_start()), n(1, L("ni", melisma=form)))
    issue = next(i for i in result.issues if i.code == "LYRIC_EXTEND_SEQUENCE_INVALID")
    assert issue.severity is Severity.ERROR
    assert result.attacks[1].role is R.CONFLICT
    # the source is untouched: the lyric still says what it said
    assert result.attacks[1].performed.source[0].lyrics[0].melisma is form


def test_a_typed_extension_ended_by_a_conflict_is_unclosed() -> None:
    result = run(n(0, typed_start()), n(1, L("ni", melisma=Melisma.STOP)))
    assert "LYRIC_MELISMA_UNCLOSED" in codes(result)


def test_typed_and_untyped_states_do_not_mix() -> None:
    # A typed CONTINUE cannot continue an inferred (untyped) extension.
    result = run(n(0, L("la", melisma=Melisma.UNTYPED)), n(1, ext(Melisma.CONTINUE)))
    assert "LYRIC_EXTEND_WITHOUT_START" in codes(result)


def test_no_maximum_length_for_a_typed_extension() -> None:
    notes = [n(0, typed_start())] + [n(i) for i in range(1, 40)] + [n(40, ext(Melisma.STOP))]
    result = run(*notes)
    assert result.coverage.longest_melisma == 40
    assert not result.issues


# --- humming and laughing ------------------------------------------------------------------


def test_humming_and_laughing_are_explicit_events_and_end_an_inferred_melisma() -> None:
    from barbershop_tracks.models import Lyric

    result = run(
        n(0, L("la", melisma=Melisma.UNTYPED)),
        n(1),
        n(2, Lyric.humming()),
        n(3),
        n(4, Lyric.laughing()),
        n(5),
    )
    assert roles(result) == [
        R.SYLLABLE,
        R.MELISMA_CONTINUATION,
        R.HUMMING,
        R.MISSING,
        R.LAUGHING,
        R.MISSING,
    ]
    assert not result.issues.has_errors  # they are legitimate; the backend decides later


def test_humming_inside_a_typed_extension_conflicts() -> None:
    from barbershop_tracks.models import Lyric

    result = run(n(0, typed_start()), n(1, Lyric.humming()), n(2))
    issue = next(i for i in result.issues if i.code == "LYRIC_EXTEND_SEQUENCE_INVALID")
    assert issue.severity is Severity.ERROR
    assert result.attacks[1].role is R.HUMMING  # still an explicit vocal event
    assert result.attacks[2].role is R.MISSING  # the explicit extension was ended by the conflict


def test_a_lyric_inside_an_elided_syllable_chain_opens_one_melisma() -> None:
    result = run(n(0, L("la", Syllabic.SINGLE, melisma=Melisma.UNTYPED)), n(1), n(2))
    assert result.coverage.longest_melisma == 2
