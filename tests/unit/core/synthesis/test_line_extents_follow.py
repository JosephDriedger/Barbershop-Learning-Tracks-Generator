"""A part with a held "Oo" of known length keeps holding it, and follows the Lead after it."""

from fractions import Fraction

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


def bay_blues(line: int | None) -> SynthesisPlan:
    """The Baritone writes "Oo" with a line, then moves note for note with the Lead's words."""
    return plan_of_parts(
        lead=[
            sung(LEAD, 4, 0.5, "Well"),
            sung(LEAD, 4.5, 0.5, "I"),
            sung(LEAD, 5, 1, "ain't"),
        ],
        baritone=[
            sung(
                BARITONE,
                0,
                4,
                "Oo",
                melisma=Melisma.UNTYPED,
                extend_length=None if line is None else Fraction(line),
            ),
            sung(BARITONE, 4, 0.5),
            sung(BARITONE, 4.5, 0.5),
            sung(BARITONE, 5, 1),
        ],
    )


def test_a_line_drawn_over_the_leads_rhythm_is_held_to_its_end_not_read_as_ended() -> None:
    plan = bay_blues(line=8)  # the line runs to the end of all three notes and beyond
    assert [lyric(plan, BARITONE, i).state for i in (1, 2, 3)] == [
        LyricState.SCORE_CONTINUATION
    ] * 3
    assert written(plan, "Baritone") == ["Oo", "+", "+", "+"]
    assert "read as ended" not in lyric(plan, BARITONE, 1).provenance.detail


def test_a_line_that_stops_where_the_leads_words_begin_gives_way_to_them() -> None:
    plan = bay_blues(line=4)  # drawn to the end of the first note only
    assert [lyric(plan, BARITONE, i).state for i in (1, 2, 3)] == [LyricState.LEAD_SYLLABLE] * 3
    assert written(plan, "Baritone") == ["Oo", "Well", "I", "ain't"]


def test_without_a_known_length_the_old_reading_of_the_rhythm_stays() -> None:
    plan = bay_blues(line=None)
    assert [lyric(plan, BARITONE, i).state for i in (1, 2, 3)] == [LyricState.LEAD_SYLLABLE] * 3
    assert "extender line" in lyric(plan, BARITONE, 1).provenance.detail
