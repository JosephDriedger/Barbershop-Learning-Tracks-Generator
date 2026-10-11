from fractions import Fraction

from barbershop_tracks.core.readiness.lines import LineInfo
from barbershop_tracks.core.readiness.suggest import RoleSuggestion, SuggestionBasis
from barbershop_tracks.models import VoiceRole
from barbershop_tracks.ui.assignments import AssignmentState, Ignore


def info(line: str, name: str, suggested: VoiceRole | None = None, attacks: int = 8) -> LineInfo:
    return LineInfo(
        line_id=line,
        part_name=name,
        source_name=name,
        staff=1,
        voice="1",
        sounding_attacks=attacks,
        has_lyrics=False,
        first_measure=1,
        last_measure=2,
        first_start=Fraction(0),
        suggestion=RoleSuggestion(
            line, suggested, SuggestionBasis.NAME if suggested else SuggestionBasis.NONE, ""
        ),
    )


def four() -> AssignmentState:
    return AssignmentState(
        (
            info("P1", "Tenor", VoiceRole.TENOR),
            info("P2", "Lead", VoiceRole.LEAD),
            info("P3", "Baritone", VoiceRole.BARITONE),
            info("P4", "Bass", VoiceRole.BASS),
        )
    )


def test_nothing_is_decided_at_the_start() -> None:
    state = four()
    assert all(choice is None for choice in state.choices.values())
    assert not state.complete
    assert state.missing_roles() == [
        VoiceRole.TENOR,
        VoiceRole.LEAD,
        VoiceRole.BARITONE,
        VoiceRole.BASS,
    ]
    assert "Choose a part for: Tenor, Lead, Baritone, Bass." in state.problems()


def test_one_voice_cannot_be_given_to_two_lines() -> None:
    state = four()
    assert state.set_choice("P1", VoiceRole.LEAD)
    assert not state.set_choice("P2", VoiceRole.LEAD)
    assert state.choices["P2"] is None
    assert not state.can_choose("P2", VoiceRole.LEAD)
    assert state.set_choice("P1", VoiceRole.LEAD)  # choosing the same thing again is fine
    assert state.set_choice("P1", VoiceRole.TENOR)  # changing frees the voice
    assert state.set_choice("P2", VoiceRole.LEAD)


def test_unknown_lines_are_refused() -> None:
    assert not four().set_choice("P9", VoiceRole.BASS)


def test_a_complete_mapping_builds_role_assignments() -> None:
    state = four()
    for line, role in zip(
        ("P1", "P2", "P3", "P4"),
        (VoiceRole.TENOR, VoiceRole.LEAD, VoiceRole.BARITONE, VoiceRole.BASS),
        strict=True,
    ):
        state.set_choice(line, role)
    assert state.complete
    assignments = state.to_role_assignments()
    assert assignments.entries == (
        (VoiceRole.TENOR, "P1"),
        (VoiceRole.LEAD, "P2"),
        (VoiceRole.BARITONE, "P3"),
        (VoiceRole.BASS, "P4"),
    )
    assert assignments.ignored == ()


def test_extra_musical_lines_must_be_decided_or_ignored() -> None:
    state = AssignmentState((*four().lines, info("P5", "Piano")))
    for line, role in zip(
        ("P1", "P2", "P3", "P4"),
        (VoiceRole.TENOR, VoiceRole.LEAD, VoiceRole.BARITONE, VoiceRole.BASS),
        strict=True,
    ):
        state.set_choice(line, role)
    assert state.problems() != []
    assert "Piano" in state.problems()[0]
    state.set_choice("P5", Ignore.IGNORE)
    assert state.problems() == []
    assert state.to_role_assignments().ignored == ("P5",)


def test_an_empty_line_does_not_need_a_decision() -> None:
    state = AssignmentState((*four().lines, info("P5", "Empty staff", attacks=0)))
    for line, role in zip(
        ("P1", "P2", "P3", "P4"),
        (VoiceRole.TENOR, VoiceRole.LEAD, VoiceRole.BARITONE, VoiceRole.BASS),
        strict=True,
    ):
        state.set_choice(line, role)
    assert state.complete


def test_suggestions_are_marked_and_block_until_confirmed() -> None:
    state = four()
    assert state.suggest() == 4
    assert state.suggested == {"P1", "P2", "P3", "P4"}
    assert not state.complete
    assert "confirm" in state.problems()[0].lower()
    state.confirm_suggestions()
    assert state.complete


def test_touching_a_suggested_row_confirms_only_that_row() -> None:
    state = four()
    state.suggest()
    state.set_choice("P2", VoiceRole.LEAD)
    assert state.suggested == {"P1", "P3", "P4"}


def test_suggestions_never_override_a_choice_or_take_a_taken_voice() -> None:
    state = four()
    state.set_choice("P1", VoiceRole.BASS)  # the user put the first line on Bass
    state.suggest()
    assert state.choices["P1"] is VoiceRole.BASS
    assert state.choices["P4"] is None  # Bass is taken, so no suggestion for P4
    assert state.suggested == {"P2", "P3"}


def test_choices_are_remembered_for_the_same_lines() -> None:
    state = four()
    state.set_choice("P1", VoiceRole.TENOR)
    state.set_choice("P2", Ignore.IGNORE)
    saved = state.snapshot()
    fresh = four()
    fresh.restore(saved, ["P1", "P2", "P3", "P4"])
    assert fresh.choices["P1"] is VoiceRole.TENOR
    assert fresh.choices["P2"] is Ignore.IGNORE
    other = AssignmentState((info("X1", "Other"),))
    other.restore(saved, ["X1"])
    assert other.choices == {"X1": None}


def test_clear_resets_everything() -> None:
    state = four()
    state.suggest()
    state.clear()
    assert all(choice is None for choice in state.choices.values())
    assert not state.suggested
