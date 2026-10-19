"""An untyped extender line (MuseScore) ends where a part keeps the Lead's rhythm."""

import yaml
from test_same_note_rule import lyric, plan_of_parts, sung

from barbershop_tracks.core.synthesis import LyricState, SynthesisPlan
from barbershop_tracks.core.synthesis.openutau import write_ustx
from barbershop_tracks.models import Melisma, VoiceRole

BARITONE, LEAD = VoiceRole.BARITONE, VoiceRole.LEAD


def written(plan: SynthesisPlan, name: str) -> list[str]:
    document = yaml.safe_load(write_ustx(plan).text)
    part = next(p for p in document["voice_parts"] if p["name"] == name)
    return [n["lyric"] for n in part["notes"]]


def bay_blues(melisma: Melisma = Melisma.UNTYPED) -> SynthesisPlan:
    """The Baritone writes "Oo" with a line, then moves note for note with the Lead's words."""
    return plan_of_parts(
        lead=[
            sung(LEAD, 4, 0.5, "Well"),
            sung(LEAD, 4.5, 0.5, "I"),
            sung(LEAD, 5, 1, "ain't"),
        ],
        baritone=[
            sung(BARITONE, 0, 4, "Oo", melisma=melisma),
            sung(BARITONE, 4, 0.5),
            sung(BARITONE, 4.5, 0.5),
            sung(BARITONE, 5, 1),
        ],
    )


def test_a_part_that_keeps_the_leads_rhythm_after_its_extender_sings_the_leads_words() -> None:
    plan = bay_blues()
    assert lyric(plan, BARITONE, 0).text == "Oo"
    assert [lyric(plan, BARITONE, i).state for i in (1, 2, 3)] == [LyricState.LEAD_SYLLABLE] * 3
    assert [lyric(plan, BARITONE, i).text for i in (1, 2, 3)] == ["Well", "I", "ain't"]
    assert "extender line" in lyric(plan, BARITONE, 1).provenance.detail
    assert plan.is_ready
    assert written(plan, "Baritone") == ["Oo", "Well", "I", "ain't"]


def test_a_typed_extender_is_left_alone() -> None:
    plan = bay_blues(Melisma.START)
    states = [lyric(plan, BARITONE, i).state for i in (1, 2, 3)]
    assert states == [LyricState.SCORE_CONTINUATION] * 3
    assert written(plan, "Baritone") == ["Oo", "+", "+", "+"]


def test_a_note_longer_than_the_leads_keeps_holding() -> None:
    # the real "Oo" held under quick words: the Baritone's second note outlasts the Lead's word
    plan = plan_of_parts(
        lead=[sung(LEAD, 0.5, 0.5, "Guess"), sung(LEAD, 4, 0.5, "freight")],
        baritone=[
            sung(BARITONE, 0, 4, "Oo", melisma=Melisma.UNTYPED),
            sung(BARITONE, 4, 4),
        ],
    )
    assert lyric(plan, BARITONE, 1).state is LyricState.SCORE_CONTINUATION
    assert written(plan, "Baritone") == ["Oo", "+"]


def test_a_note_that_starts_elsewhere_keeps_holding() -> None:
    plan = plan_of_parts(
        lead=[sung(LEAD, 4.25, 0.5, "Well")],
        baritone=[
            sung(BARITONE, 0, 4, "Oo", melisma=Melisma.UNTYPED),
            sung(BARITONE, 4, 0.5),
        ],
    )
    assert lyric(plan, BARITONE, 1).state is LyricState.SCORE_CONTINUATION


def test_once_the_line_has_ended_a_note_in_the_leads_rhythm_holds_what_the_lead_holds() -> None:
    plan = plan_of_parts(
        lead=[
            sung(LEAD, 4, 0.5, "Well", melisma=Melisma.UNTYPED),
            sung(LEAD, 4.5, 0.5),  # under the Lead's own extender: the Lead holds "Well"
            sung(LEAD, 5, 1, "ain't"),
        ],
        baritone=[
            sung(BARITONE, 0, 4, "Oo", melisma=Melisma.UNTYPED),
            sung(BARITONE, 4, 0.5),
            sung(BARITONE, 4.5, 0.5),
            sung(BARITONE, 5, 1),
        ],
    )
    assert [lyric(plan, BARITONE, i).state for i in (1, 2, 3)] == [
        LyricState.LEAD_SYLLABLE,
        LyricState.LEAD_SUSTAIN,
        LyricState.LEAD_SYLLABLE,
    ]
    assert written(plan, "Baritone") == ["Oo", "Well", "+", "ain't"]
