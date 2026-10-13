"""The barbershop convention: parts without lyrics of their own sing what the Lead sings."""

from fractions import Fraction

import pytest
import yaml

from barbershop_tracks.core.pipeline import default_follow_lead
from barbershop_tracks.core.synthesis import (
    LyricApproval,
    LyricState,
    ReviewReason,
    SynthesisPlan,
)
from barbershop_tracks.core.synthesis.openutau import write_ustx
from barbershop_tracks.models import Melisma, VoiceRole
from readiness_builders import PITCHES, note, rest
from synth_builders import ROLES, full_lyrics, performed, plan_of, sung, text

LEAD, TENOR = VoiceRole.LEAD, VoiceRole.TENOR


def follow(**voices: list) -> SynthesisPlan:  # type: ignore[type-arg]
    return plan_of(performed(**voices), follow_lead=True)


def states(plan: SynthesisPlan, role: VoiceRole) -> list[LyricState]:
    return [n.lyric.state for n in plan.voice(role).notes]


def texts(plan: SynthesisPlan, role: VoiceRole) -> list[str | None]:
    return [n.lyric.text for n in plan.voice(role).notes]


def lead_only(words: list[str | None]) -> dict[str, list]:  # type: ignore[type-arg]
    voices = {role.value: sung(role, [None] * len(words)) for role in ROLES}
    voices["lead"] = sung(LEAD, words)
    return voices


def test_parts_sing_the_leads_words_where_the_score_gives_them_none() -> None:
    plan = follow(**lead_only(["one", "two", "three", "four"]))
    for role in (VoiceRole.TENOR, VoiceRole.BARITONE, VoiceRole.BASS):
        assert states(plan, role) == [LyricState.LEAD_SYLLABLE] * 4
        assert texts(plan, role) == ["one", "two", "three", "four"]
    assert states(plan, LEAD) == [LyricState.SCORE_LYRIC] * 4
    assert plan.is_ready
    assert plan.review_items == ()


def test_the_provenance_names_the_lead_note_that_was_followed() -> None:
    plan = follow(**lead_only(["one", "two", "three", "four"]))
    second = plan.voice(VoiceRole.BASS).notes[1].lyric.provenance
    assert second.follows_start == Fraction(1)
    assert "follows the Lead" in second.detail
    assert "'two'" in second.detail


def test_without_the_rule_the_same_notes_still_need_review() -> None:
    plan = plan_of(performed(**lead_only(["one", "two", "three", "four"])), follow_lead=False)
    assert states(plan, TENOR) == [LyricState.ABSENT] * 4
    assert not plan.is_ready


def test_a_lyric_the_score_gives_a_part_is_never_replaced() -> None:
    voices = lead_only(["one", "two", "three", "four"])
    voices["tenor"] = sung(TENOR, ["la", None, "la", None])
    plan = follow(**voices)
    assert states(plan, TENOR) == [
        LyricState.SCORE_LYRIC,
        LyricState.LEAD_SYLLABLE,
        LyricState.SCORE_LYRIC,
        LyricState.LEAD_SYLLABLE,
    ]
    assert texts(plan, TENOR) == ["la", "two", "la", "four"]


def test_a_part_moving_under_a_held_word_sustains_the_vowel() -> None:
    voices = lead_only(["love", "you", "so", "much"])
    voices["lead"] = sung(LEAD, ["love", "you"], duration=2) + sung(
        LEAD, ["so", "much"], duration=2, start=4
    )
    voices["tenor"] = sung(TENOR, [None] * 8)
    plan = follow(**voices)
    kinds = states(plan, TENOR)
    assert kinds[:4] == [
        LyricState.LEAD_SYLLABLE,
        LyricState.LEAD_SUSTAIN,
        LyricState.LEAD_SYLLABLE,
        LyricState.LEAD_SUSTAIN,
    ]
    assert texts(plan, TENOR)[:2] == ["love", None]
    assert plan.is_ready


def test_after_a_gap_the_syllable_is_sung_again_because_a_vowel_cannot_cross_it() -> None:
    voices = lead_only(["love", None, None, None])
    voices["lead"] = [note(0, 4, PITCHES[LEAD], lyrics=text("love"))]
    voices["tenor"] = [
        note(0, 1, PITCHES[TENOR]),
        rest(1, 1),
        note(2, 1, PITCHES[TENOR]),
        note(3, 1, PITCHES[TENOR]),
    ]
    plan = follow(**voices)
    notes = plan.voice(TENOR).notes
    assert [n.lyric.state for n in notes] == [
        LyricState.LEAD_SYLLABLE,
        LyricState.LEAD_SYLLABLE,  # after the rest: sung again
        LyricState.LEAD_SUSTAIN,  # touches the note before it
    ]
    assert [n.lyric.text for n in notes] == ["love", "love", None]


def test_a_part_that_sings_while_the_lead_rests_goes_to_review() -> None:
    voices = lead_only(["one", None, "three", "four"])
    voices["lead"] = [
        note(0, 1, PITCHES[LEAD], lyrics=text("one")),
        rest(1, 1),
        note(2, 1, PITCHES[LEAD], lyrics=text("three")),
        note(3, 1, PITCHES[LEAD], lyrics=text("four")),
    ]
    plan = follow(**voices)
    tenor = plan.voice(TENOR).notes
    assert tenor[1].lyric.state is LyricState.ABSENT
    assert tenor[1].lyric.review_reason is ReviewReason.LYRIC_ABSENT
    assert not plan.is_ready
    assert {(i.role, i.start) for i in plan.review_items if i.role is TENOR} == {
        (TENOR, Fraction(1))
    }


def test_a_leads_melisma_is_held_by_the_part_that_moves_under_it() -> None:
    voices = lead_only([None, None, None, None])
    voices["lead"] = [
        note(0, 1, PITCHES[LEAD], lyrics=text("ah", melisma=Melisma.UNTYPED)),
        note(1, 1, PITCHES[LEAD], frm=True),
        note(2, 1, PITCHES[LEAD], lyrics=text("men")),
        note(3, 1, PITCHES[LEAD], lyrics=text("now")),
    ]
    plan = follow(**voices)
    assert states(plan, LEAD)[:2] == [LyricState.SCORE_LYRIC, LyricState.SCORE_CONTINUATION]
    assert states(plan, TENOR) == [
        LyricState.LEAD_SYLLABLE,
        LyricState.LEAD_SUSTAIN,
        LyricState.LEAD_SYLLABLE,
        LyricState.LEAD_SYLLABLE,
    ]
    assert texts(plan, TENOR) == ["ah", None, "men", "now"]


def test_an_undecided_lead_gives_the_parts_nothing_to_follow() -> None:
    plan = follow(**lead_only(["one", None, "three", "four"]))
    assert plan.voice(LEAD).notes[1].lyric.state is LyricState.ABSENT
    assert plan.voice(TENOR).notes[1].lyric.state is LyricState.ABSENT
    assert plan.voice(TENOR).notes[0].lyric.state is LyricState.LEAD_SYLLABLE


def test_an_explicit_approval_overrides_the_rule() -> None:
    song = performed(**lead_only(["one", "two", "three", "four"]))
    approval = LyricApproval(role=TENOR, start=Fraction(1), text="oo", approved_by="tester")
    plan = plan_of(song, approvals=[approval], follow_lead=True)
    note_two = plan.voice(TENOR).notes[1].lyric
    assert (note_two.state, note_two.text) == (LyricState.USER_APPROVED, "oo")
    assert plan.voice(TENOR).notes[2].lyric.state is LyricState.LEAD_SYLLABLE


def test_the_written_project_holds_the_vowel_with_an_extender() -> None:
    voices = lead_only([None] * 4)
    voices["lead"] = sung(LEAD, ["love", "you"], duration=2)
    voices["tenor"] = sung(TENOR, [None] * 4)
    for role in (VoiceRole.BARITONE, VoiceRole.BASS):
        voices[role.value] = sung(role, [None] * 4)
    plan = follow(**voices)
    project = yaml.safe_load(write_ustx(plan).text)
    track_notes = project["voice_parts"]
    lyrics_by_part = [[n["lyric"] for n in part["notes"]] for part in track_notes]
    assert ["love", "+", "you", "+"] in lyrics_by_part


def test_the_environment_can_switch_the_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BLT_FOLLOW_LEAD", raising=False)
    assert default_follow_lead() is True
    monkeypatch.setenv("BLT_FOLLOW_LEAD", "0")
    assert default_follow_lead() is False
    monkeypatch.setenv("BLT_FOLLOW_LEAD", "1")
    assert default_follow_lead() is True


def test_a_score_with_every_lyric_is_unchanged_by_the_rule() -> None:
    with_rule = follow(**full_lyrics())
    without = plan_of(performed(**full_lyrics()), follow_lead=False)
    assert with_rule.voices == without.voices
