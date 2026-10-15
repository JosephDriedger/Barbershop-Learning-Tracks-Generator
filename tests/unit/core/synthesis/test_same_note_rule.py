"""A lyric written once under one part is sung by the parts that hold the very same note."""

from fractions import Fraction

import pytest
import yaml

from barbershop_tracks.core.synthesis import LyricState, SynthesisPlan, VoiceEngineRef
from barbershop_tracks.core.synthesis.openutau import write_ustx
from barbershop_tracks.models import Lyric, Melisma, Note, Syllabic, VoiceRole
from readiness_builders import PITCHES, note
from synth_builders import ROLES, plan_of

ARPASING = "OpenUtau.Plugin.Builtin.ArpasingPhonemizer"


def sung(
    role: VoiceRole, start: float, length: float, text: str | None = None, **kw: object
) -> Note:
    lyrics = () if text is None else (Lyric(text=text, **kw),)  # type: ignore[arg-type]
    return note(Fraction(str(start)), Fraction(str(length)), PITCHES[role], lyrics=lyrics)


def plan_of_parts(
    *,
    lead: list[Note] | None = None,
    tenor: list[Note] | None = None,
    baritone: list[Note] | None = None,
    bass: list[Note] | None = None,
    follow: bool = True,
) -> SynthesisPlan:
    given = {"lead": lead, "tenor": tenor, "baritone": baritone, "bass": bass}
    voices = {r.value: given[r.value] or [sung(r, 0, 1, "la")] for r in ROLES}
    engine = VoiceEngineRef(singer="s", phonemizer=ARPASING, renderer="WORLDLINE-R")
    return plan_of(voices=voices, engine_refs=dict.fromkeys(ROLES, engine), follow_lead=follow)


def lyric(plan: SynthesisPlan, role: VoiceRole, index: int):  # type: ignore[no-untyped-def]
    return plan.voice(role).notes[index].lyric


def written(plan: SynthesisPlan, name: str) -> list[str]:
    document = yaml.safe_load(write_ustx(plan).text)
    part = next(p for p in document["voice_parts"] if p["name"] == name)
    return [n["lyric"] for n in part["notes"]]


def oo_under_the_baritone(follow: bool = True) -> SynthesisPlan:
    """The Lead sings quick words; the Baritone's "Oo" is written once; the others hold it."""
    lead = [
        sung(VoiceRole.LEAD, 0.5, 0.5, "Just"),
        sung(VoiceRole.LEAD, 1, 1, "gon"),
    ]
    return plan_of_parts(
        lead=lead,
        tenor=[sung(VoiceRole.TENOR, 0, 4)],
        baritone=[sung(VoiceRole.BARITONE, 0, 4, "Oo")],
        bass=[sung(VoiceRole.BASS, 0, 4)],
        follow=follow,
    )


def test_a_lyric_written_only_under_the_baritone_is_sung_by_tenor_and_bass() -> None:
    plan = oo_under_the_baritone()
    for role in (VoiceRole.TENOR, VoiceRole.BASS):
        sung_here = lyric(plan, role, 0)
        assert sung_here.state is LyricState.LEAD_SYLLABLE  # a rule decision, never a review item
        assert sung_here.text == "Oo"
        assert sung_here.provenance.follows_role == "baritone"
        assert "Baritone" in sung_here.provenance.detail
        assert "writes it once" in sung_here.provenance.detail
    assert plan.is_ready
    assert written(plan, "Tenor") == ["Oo"]
    assert written(plan, "Bass") == ["Oo"]


def test_the_leads_words_are_not_given_to_a_part_that_holds_the_baritones_note() -> None:
    plan = oo_under_the_baritone()
    # before this rule the Tenor would have sung the Lead's first word
    assert lyric(plan, VoiceRole.TENOR, 0).text != "Just"
    assert lyric(plan, VoiceRole.LEAD, 0).text == "Just"  # the Lead keeps its own words


def test_the_parts_that_have_a_lyric_of_their_own_are_never_changed() -> None:
    plan = oo_under_the_baritone()
    assert lyric(plan, VoiceRole.BARITONE, 0).state is LyricState.SCORE_LYRIC
    assert lyric(plan, VoiceRole.BARITONE, 0).text == "Oo"
    assert {n.lyric.state for n in plan.voice(VoiceRole.LEAD).notes} == {LyricState.SCORE_LYRIC}


def test_when_the_lead_has_the_very_same_note_the_leads_words_are_the_convention() -> None:
    plan = plan_of_parts(
        lead=[sung(VoiceRole.LEAD, 0, 1, "la")],
        tenor=[sung(VoiceRole.TENOR, 0, 1)],
        baritone=[
            sung(VoiceRole.BARITONE, 0, 1, "doo")
        ],  # another part's own word on the same note
        bass=[sung(VoiceRole.BASS, 0, 1)],
    )
    assert lyric(plan, VoiceRole.TENOR, 0).text == "la"
    assert lyric(plan, VoiceRole.TENOR, 0).provenance.follows_role == "lead"
    assert lyric(plan, VoiceRole.BASS, 0).text == "la"


def test_parts_that_disagree_about_the_same_note_leave_it_to_a_person() -> None:
    lead = [sung(VoiceRole.LEAD, 0.5, 0.5, "Just")]
    plan = plan_of_parts(
        lead=lead,
        tenor=[sung(VoiceRole.TENOR, 0, 4)],
        baritone=[sung(VoiceRole.BARITONE, 0, 4, "Oo")],
        bass=[sung(VoiceRole.BASS, 0, 4, "doo")],
    )
    held = lyric(plan, VoiceRole.TENOR, 0)
    assert held.state is LyricState.ABSENT  # not "Oo", not "doo", and not the Lead's "Just"
    assert not plan.is_ready
    assert [(i.role, i.note_index) for i in plan.review_items if i.role is VoiceRole.TENOR] == [
        (VoiceRole.TENOR, 0)
    ]


def test_a_part_that_holds_the_chord_for_a_different_time_sings_the_same_word() -> None:
    plan = plan_of_parts(
        lead=[sung(VoiceRole.LEAD, 0.5, 0.5, "Just")],
        tenor=[sung(VoiceRole.TENOR, 0, 7)],  # longer than the Baritone's note
        baritone=[sung(VoiceRole.BARITONE, 0, 3, "Oo")],
        bass=[sung(VoiceRole.BASS, 0, 2)],  # shorter than the Baritone's note
    )
    for role in (VoiceRole.TENOR, VoiceRole.BASS):
        assert lyric(plan, role, 0).text == "Oo"
        assert lyric(plan, role, 0).provenance.follows_role == "baritone"
    assert written(plan, "Bass") == ["Oo"]


def test_the_part_with_the_same_length_is_the_match_when_the_lead_moves_faster() -> None:
    # the Lead starts a short word with the held "Oo": the parts holding what the Baritone holds
    # sing the Baritone's word, not the Lead's
    plan = plan_of_parts(
        lead=[sung(VoiceRole.LEAD, 0, 0.5, "Guess"), sung(VoiceRole.LEAD, 0.5, 1, "I'll")],
        tenor=[sung(VoiceRole.TENOR, 0, 4)],
        baritone=[sung(VoiceRole.BARITONE, 0, 4, "Oo")],
        bass=[sung(VoiceRole.BASS, 0, 4)],
    )
    for role in (VoiceRole.TENOR, VoiceRole.BASS):
        assert lyric(plan, role, 0).text == "Oo"


def test_the_lead_wins_when_it_starts_together_and_no_part_is_as_long() -> None:
    plan = plan_of_parts(
        lead=[sung(VoiceRole.LEAD, 0, 0.5, "Guess")],
        tenor=[sung(VoiceRole.TENOR, 0, 4)],
        baritone=[sung(VoiceRole.BARITONE, 0, 3, "Oo")],
        bass=[sung(VoiceRole.BASS, 0, 3, "Oo")],
    )
    assert lyric(plan, VoiceRole.TENOR, 0).text == "Guess"


def test_a_note_that_starts_elsewhere_is_not_a_twin() -> None:
    plan = plan_of_parts(
        lead=[sung(VoiceRole.LEAD, 0, 4, "la")],
        tenor=[sung(VoiceRole.TENOR, 1, 1)],  # starts inside the Baritone's note, not with it
        baritone=[sung(VoiceRole.BARITONE, 0, 4, "doo")],
        bass=[sung(VoiceRole.BASS, 0, 4, "doo")],
    )
    assert lyric(plan, VoiceRole.TENOR, 0).text == "la"  # the Lead rule, as before


def test_a_part_whose_note_starts_with_a_continuation_holds_though_it_is_shorter() -> None:
    plan = plan_of_parts(
        lead=[
            sung(VoiceRole.LEAD, 0.5, 1.5, "now"),
            sung(VoiceRole.LEAD, 3.5, 0.5, "so"),
        ],
        tenor=[sung(VoiceRole.TENOR, 0, 2), sung(VoiceRole.TENOR, 2, 5)],
        baritone=[
            sung(VoiceRole.BARITONE, 0, 2, "Oo", melisma=Melisma.UNTYPED),
            sung(VoiceRole.BARITONE, 2, 5),
        ],
        bass=[
            sung(VoiceRole.BASS, 0, 2),
            sung(VoiceRole.BASS, 2, 3),
        ],  # shorter than the Baritone's
    )
    assert lyric(plan, VoiceRole.BASS, 1).state is LyricState.LEAD_SUSTAIN
    assert written(plan, "Bass") == ["Oo", "+"]


def test_a_held_note_that_continues_the_baritones_syllable_holds_its_vowel() -> None:
    baritone = [
        sung(VoiceRole.BARITONE, 0, 2, "Oo", melisma=Melisma.UNTYPED),
        sung(VoiceRole.BARITONE, 2, 2),  # under the extender: a continuation, no text of its own
    ]
    plan = plan_of_parts(
        lead=[
            sung(VoiceRole.LEAD, 0.5, 1.5, "now"),
            sung(VoiceRole.LEAD, 2.5, 1, "gon"),
        ],
        tenor=[sung(VoiceRole.TENOR, 0, 2), sung(VoiceRole.TENOR, 2, 2)],
        baritone=baritone,
        bass=[sung(VoiceRole.BASS, 0, 2), sung(VoiceRole.BASS, 2, 2)],
    )
    assert lyric(plan, VoiceRole.BARITONE, 1).state is LyricState.SCORE_CONTINUATION
    assert lyric(plan, VoiceRole.TENOR, 0).text == "Oo"
    assert (
        lyric(plan, VoiceRole.TENOR, 1).state is LyricState.LEAD_SUSTAIN
    )  # holds, does not repeat "Oo"
    assert written(plan, "Tenor") == ["Oo", "+"]
    assert written(plan, "Bass") == ["Oo", "+"]


def test_the_rule_is_part_of_following_and_goes_off_with_it() -> None:
    plan = oo_under_the_baritone(follow=False)
    assert lyric(plan, VoiceRole.TENOR, 0).state is LyricState.ABSENT
    assert not plan.is_ready


def test_a_word_of_several_syllables_written_once_is_sung_whole() -> None:
    syllables = [("to", Syllabic.BEGIN), ("geth", Syllabic.MIDDLE), ("er", Syllabic.END)]
    baritone = [sung(VoiceRole.BARITONE, i, 1, t, syllabic=k) for i, (t, k) in enumerate(syllables)]
    plan = plan_of_parts(
        lead=[sung(VoiceRole.LEAD, 0.5, 2.5, "now")],
        tenor=[sung(VoiceRole.TENOR, i, 1) for i in range(3)],
        baritone=baritone,
        bass=[sung(VoiceRole.BASS, i, 1) for i in range(3)],
    )
    assert [n.lyric.text for n in plan.voice(VoiceRole.TENOR).notes] == ["to", "geth", "er"]
    assert written(plan, "Tenor") == ["together", "+", "+"]
    assert written(plan, "Bass") == ["together", "+", "+"]


@pytest.mark.parametrize("role", [VoiceRole.TENOR, VoiceRole.BASS])
def test_the_review_says_whose_words_a_part_sings(role: VoiceRole) -> None:
    from barbershop_tracks.ui.lyric_review import LyricReviewState

    state = LyricReviewState(oo_under_the_baritone())
    rows = [r for r in state.rows if r.role is role and r.inherited]
    assert [r.reason for r in rows] == ["Follows the Baritone (the same note, written once)"]
