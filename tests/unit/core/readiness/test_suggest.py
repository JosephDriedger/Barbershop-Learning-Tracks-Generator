"""Role suggestions: deterministic, unconfirmed, never applied."""

from barbershop_tracks.core.readiness.suggest import SuggestionBasis, suggest_roles
from barbershop_tracks.models import Part, VoiceRole


def parts(*names: str | None) -> list[Part]:
    return [
        Part(part_id=f"P{i}/s1/v1", name=name or f"P{i}", source_name=name)
        for i, name in enumerate(names, start=1)
    ]


def test_part_names_give_name_based_suggestions() -> None:
    suggestions = suggest_roles(parts("Tenor", "Lead", "Baritone", "Bass"))
    assert [s.role for s in suggestions] == list(VoiceRole)
    assert {s.basis for s in suggestions} == {SuggestionBasis.NAME}
    assert not any(s.confirmed for s in suggestions)


def test_common_abbreviations_and_extra_words_are_understood() -> None:
    suggestions = suggest_roles(parts("Tenor 1 (T)", "Lead voice", "Bari", "Bass line"))
    assert [s.role for s in suggestions] == list(VoiceRole)


def test_the_name_wins_over_the_order() -> None:
    suggestions = suggest_roles(parts("Bass", "Baritone", "Lead", "Tenor"))
    assert [s.role for s in suggestions] == [
        VoiceRole.BASS,
        VoiceRole.BARITONE,
        VoiceRole.LEAD,
        VoiceRole.TENOR,
    ]


def test_four_unnamed_lines_get_an_order_guess_flagged_unconfirmed() -> None:
    suggestions = suggest_roles(parts(None, None, None, None))
    assert [s.role for s in suggestions] == [
        VoiceRole.TENOR,
        VoiceRole.LEAD,
        VoiceRole.BARITONE,
        VoiceRole.BASS,
    ]
    assert {s.basis for s in suggestions} == {SuggestionBasis.ORDER}
    assert not any(s.confirmed for s in suggestions)
    assert "unconfirmed" in suggestions[0].note


def test_no_order_guess_for_other_than_four_lines() -> None:
    assert {s.role for s in suggest_roles(parts(None, None, None))} == {None}
    assert {s.role for s in suggest_roles(parts(None, None, None, None, None))} == {None}


def test_no_order_guess_when_some_names_already_speak() -> None:
    suggestions = suggest_roles(parts("Tenor", None, None, None))
    assert [s.role for s in suggestions] == [VoiceRole.TENOR, None, None, None]


def test_a_name_with_two_voice_words_or_a_repeated_role_gets_no_suggestion() -> None:
    both = suggest_roles(parts("Tenor/Lead", None))
    assert both[0].role is None
    twice = suggest_roles(parts("Lead", "Lead 2", "Bass"))
    assert [s.role for s in twice] == [None, None, VoiceRole.BASS]
    assert "no suggestion" in twice[0].note
    assert "no suggestion" in twice[1].note  # both are reported, neither is preferred


def test_suggestions_are_deterministic_and_never_touch_the_parts() -> None:
    source = parts("Tenor", "Lead", "Baritone", "Bass")
    assert suggest_roles(source) == suggest_roles(source)
    assert all(part.role is None for part in source)
