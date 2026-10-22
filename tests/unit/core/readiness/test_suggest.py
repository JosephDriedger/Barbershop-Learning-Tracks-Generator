"""Role suggestions: deterministic, unconfirmed, never applied."""

from dataclasses import replace
from fractions import Fraction
from pathlib import Path

from barbershop_tracks.core.readiness.lines import describe_lines
from barbershop_tracks.core.readiness.suggest import (
    SuggestionBasis,
    shared_staff_positions,
    suggest_roles,
)
from barbershop_tracks.models import Note, Part, Pitch, SourceLine, Step, VoiceRole
from xml_builders import attributes, backup, measure, note, parse_text, score


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


# --- the shared-staff layout: Tenor/Lead on the first staff, Baritone/Bass on the second ------


def _line(part: str, voice: str, notes: int, name: str = "LEAD") -> Part:
    events = tuple(
        Note(
            start=Fraction(i),
            duration=Fraction(1),
            measure=1,
            beat=Fraction(1),
            written_pitch=Pitch(Step.C, 4),
        )
        for i in range(notes)
    )
    return Part(
        part_id=f"{part}/s1/v{voice}",
        name=name,
        events=events,
        source_line=SourceLine(part_id=part, staff=1, voice=voice),
        source_name=name,
    )


def _layout(*, p1: tuple[int, ...] = (150, 171), p2: tuple[int, ...] = (165, 136)) -> list[Part]:
    return [
        *(_line("P1", str(v), n, "LEAD") for v, n in enumerate(p1, start=1)),
        *(_line("P2", str(v), n, "BASS") for v, n in enumerate(p2, start=1)),
    ]


def test_the_upper_voice_is_tenor_and_baritone_and_the_lower_is_lead_and_bass() -> None:
    source = _layout()
    by_line = {s.line_id: s for s in suggest_roles(source)}
    assert by_line["P1/s1/v1"].role is VoiceRole.TENOR
    assert by_line["P1/s1/v2"].role is VoiceRole.LEAD
    assert by_line["P2/s1/v1"].role is VoiceRole.BARITONE
    assert by_line["P2/s1/v2"].role is VoiceRole.BASS
    assert {s.basis for s in by_line.values()} == {SuggestionBasis.LAYOUT}
    assert not any(s.confirmed for s in by_line.values())
    assert "unconfirmed" in by_line["P1/s1/v1"].note


def test_the_voice_not_the_pitch_or_the_note_count_decides_which_is_upper() -> None:
    # the lower voice has more notes here, and crossing makes pitch useless: voice 1 is still upper
    by_line = {s.line_id: s.role for s in suggest_roles(_layout(p1=(90, 200), p2=(10, 10)))}
    assert by_line["P1/s1/v1"] is VoiceRole.TENOR
    assert by_line["P2/s1/v1"] is VoiceRole.BARITONE


def test_stray_fragments_are_left_without_a_suggestion() -> None:
    source = _layout(p1=(150, 171, 11, 3), p2=(165, 136, 13, 4))
    by_line = {s.line_id: s.role for s in suggest_roles(source)}
    assert by_line["P1/s1/v3"] is None
    assert by_line["P1/s1/v4"] is None
    assert by_line["P2/s1/v3"] is None
    assert by_line["P1/s1/v1"] is VoiceRole.TENOR
    assert by_line["P2/s1/v2"] is VoiceRole.BASS


def test_a_third_real_voice_is_not_guessed_about() -> None:
    assert {s.role for s in suggest_roles(_layout(p1=(100, 100, 90)))} == {None}


def test_the_layout_is_not_used_when_a_part_name_speaks() -> None:
    source = _layout()
    named = [
        replace(p, name="Tenor", source_name="Tenor") if p.part_id == "P1/s1/v1" else p
        for p in source
    ]
    by_line = {s.line_id: s for s in suggest_roles(named)}
    assert by_line["P1/s1/v1"].role is VoiceRole.TENOR
    assert by_line["P1/s1/v2"].role is VoiceRole.LEAD  # its own name says Lead
    assert {by_line[line].basis for line in ("P1/s1/v1", "P1/s1/v2")} == {SuggestionBasis.NAME}
    assert by_line["P2/s1/v1"].role is None  # names speak, so the layout stays out of it
    assert by_line["P2/s1/v2"].role is None


def test_one_staff_or_three_staves_are_not_the_layout() -> None:
    one = [_line("P1", "1", 20), _line("P1", "2", 20)]
    assert {s.role for s in suggest_roles(one)} == {None}
    three = [_line(p, v, 20) for p in ("P1", "P2", "P3") for v in ("1", "2")]
    assert {s.role for s in suggest_roles(three)} == {None}


def test_describe_lines_labels_each_line_by_its_place_on_the_staff(tmp_path: Path) -> None:
    def staff(*voices: tuple[str, str]) -> str:
        body = ""
        for index, (voice, step) in enumerate(voices):
            body += (backup(4) if index else "") + note(step, 4, 4, voice=voice)
        return measure(1, body, attrs=attributes(divisions="1"))

    xml = score(
        staff(("1", "E"), ("2", "C")),
        staff(("1", "G"), ("2", "D")),
        names=["LEAD", "BASS"],  # all a recognised PDF leaves of "TENOR/LEAD" and "BARI/BASS"
    )
    lines = describe_lines(parse_text(tmp_path, xml))
    assert [line.display_name for line in lines] == [
        "Tenor/Lead staff, upper voice",
        "Tenor/Lead staff, lower voice",
        "Baritone/Bass staff, upper voice",
        "Baritone/Bass staff, lower voice",
    ]
    assert [line.suggestion.role for line in lines] == list(VoiceRole)
    assert lines[0].part_name == "LEAD"  # the name in the file is kept, only not shown first


def test_a_line_outside_the_layout_is_shown_by_its_file_name() -> None:
    # two lines of one part are not the two-staff layout: nothing to label by position
    assert shared_staff_positions([_line("P1", "1", 20), _line("P1", "2", 20)]) == {}
