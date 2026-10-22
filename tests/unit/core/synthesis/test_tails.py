"""A short last note of a held word must be able to sound its own pitch (the "babe" dotted pair)."""

from collections.abc import Mapping, Sequence
from fractions import Fraction
from typing import Any

import pytest
import yaml

from barbershop_tracks.core.synthesis import VoiceEngineRef
from barbershop_tracks.core.synthesis.openutau import short_tail_words, write_ustx
from barbershop_tracks.core.synthesis.openutau.tails import (
    SHIFT_TICKS,
    glide_ms,
    needs_shift,
    overrides_for,
    trailing_consonants,
)
from barbershop_tracks.models import Lyric, Melisma, Note, VoiceRole
from readiness_builders import PITCHES, note
from synth_builders import ROLES, plan_of

ARPASING = "OpenUtau.Plugin.Builtin.ArpasingPhonemizer"
VCCV = "OpenUtau.Plugin.Builtin.EnglishVCCVPhonemizer"
DEFAULT = "OpenUtau.Core.DefaultPhonemizer"
LEAD = PITCHES[VoiceRole.LEAD]
DOTTED, SIXTEENTH = Fraction(3, 4), Fraction(1, 4)
BABE = ("b", "ey", "b")


def refs(phonemizer: str) -> dict[VoiceRole, VoiceEngineRef]:
    ref = VoiceEngineRef(singer="s", phonemizer=phonemizer, renderer="WORLDLINE-R")
    return dict.fromkeys(ROLES, ref)


def sing(start: Fraction | int, text: str, dur: Fraction | int, *, held: bool = False) -> Note:
    melisma = Melisma.UNTYPED if held else Melisma.NONE
    return note(start, dur, LEAD, lyrics=(Lyric(text=text, melisma=melisma),))


def lyric_less(start: Fraction | int, dur: Fraction | int) -> Note:
    return note(start, dur, LEAD)


def voices(lead: list[Note]) -> dict[str, list[Note]]:
    others = {r.value: [note(0, 1, PITCHES[r], lyrics=(Lyric(text="la"),))] for r in ROLES}
    others["lead"] = lead
    return others


def lead_notes(
    phonemizer: str, lead: list[Note], phonemes: Mapping[str, Sequence[str]] | None
) -> list[dict[str, Any]]:
    plan = plan_of(voices=voices(lead), engine_refs=refs(phonemizer))
    document = yaml.safe_load(write_ustx(plan, phonemes=phonemes).text)
    notes: list[dict[str, Any]] = next(p for p in document["voice_parts"] if p["name"] == "Lead")[
        "notes"
    ]
    return notes


def babe_then_now() -> list[Note]:
    """ "babe" on a dotted eighth and a sixteenth (a held syllable), then another word."""
    return [
        sing(0, "babe", DOTTED, held=True),
        lyric_less(DOTTED, SIXTEENTH),
        sing(1, "now", 1),
    ]


# --- the pure rules ---------------------------------------------------------------------------


def test_the_consonants_after_the_last_vowel_are_found() -> None:
    assert trailing_consonants(BABE) == (2,)
    assert trailing_consonants(("s", "aw", "n", "d", "z")) == (2, 3, 4)
    assert trailing_consonants(("l", "ah", "v")) == (2,)
    assert trailing_consonants(("n", "aw")) == ()  # ends on a vowel
    assert trailing_consonants(("s", "t")) == ()  # no vowel: the engine spreads it differently
    assert trailing_consonants(("B", "EY", "B")) == (2,)  # case does not matter


def test_only_a_short_last_note_of_a_word_held_over_several_needs_it() -> None:
    assert needs_shift(120, 2, True)  # a sixteenth
    assert needs_shift(180, 3, True)
    assert not needs_shift(240, 2, True)  # an eighth has room for the consonant
    assert not needs_shift(120, 1, True)  # one note: the engine's own placing is fine
    assert not needs_shift(120, 2, False)  # nothing follows: the engine adds its own tail


def test_the_offset_is_in_ticks_and_follows_the_resolution() -> None:
    assert overrides_for(BABE, 480) == [{"index": 2, "offset": SHIFT_TICKS}]
    assert overrides_for(BABE, 960) == [{"index": 2, "offset": 2 * SHIFT_TICKS}]
    assert overrides_for(("n", "aw"), 480) == []


def test_a_short_held_note_changes_pitch_quicker() -> None:
    assert glide_ms(True, 120, 480) == 15
    assert glide_ms(True, 240, 480) == 40  # an eighth glides as every note does
    assert glide_ms(False, 120, 480) == 40  # a note with a syllable of its own too


# --- in the project file -------------------------------------------------------------------------


def test_babe_on_a_dotted_eighth_and_a_sixteenth_has_its_closing_b_moved() -> None:
    notes = lead_notes(ARPASING, babe_then_now(), {"babe": BABE})
    assert [n["lyric"] for n in notes] == ["babe", "+", "now"]
    assert notes[0]["phoneme_overrides"] == [{"index": 2, "offset": SHIFT_TICKS}]
    assert notes[1]["phoneme_overrides"] == []  # the held note carries none
    assert notes[2]["phoneme_overrides"] == []


def test_the_sixteenth_changes_pitch_quickly_and_the_others_as_ever() -> None:
    notes = lead_notes(ARPASING, babe_then_now(), {"babe": BABE})
    xs = [[point["x"] for point in n["pitch"]["data"]] for n in notes]
    assert xs == [[-40, 40], [-15, 15], [-40, 40]]


def test_without_the_dictionarys_phonemes_nothing_is_moved() -> None:
    for phonemes in (None, {}, {"other": BABE}):
        notes = lead_notes(ARPASING, babe_then_now(), phonemes)
        assert all(n["phoneme_overrides"] == [] for n in notes)


def test_a_word_that_ends_on_a_vowel_is_left_alone() -> None:
    lead = [sing(0, "go", DOTTED, held=True), lyric_less(DOTTED, SIXTEENTH), sing(1, "now", 1)]
    notes = lead_notes(ARPASING, lead, {"go": ("g", "ow")})
    assert all(n["phoneme_overrides"] == [] for n in notes)


def test_a_long_last_note_is_left_alone() -> None:
    lead = [sing(0, "babe", 1, held=True), lyric_less(1, 2), sing(3, "now", 1)]
    notes = lead_notes(ARPASING, lead, {"babe": BABE})
    assert all(n["phoneme_overrides"] == [] for n in notes)


def test_a_word_on_one_note_is_left_alone() -> None:
    lead = [sing(0, "babe", SIXTEENTH), sing(SIXTEENTH, "now", 1)]
    notes = lead_notes(ARPASING, lead, {"babe": BABE})
    assert all(n["phoneme_overrides"] == [] for n in notes)


def test_the_last_word_of_a_voice_is_left_alone() -> None:
    lead = [sing(0, "babe", DOTTED, held=True), lyric_less(DOTTED, SIXTEENTH)]
    notes = lead_notes(ARPASING, lead, {"babe": BABE})
    assert all(n["phoneme_overrides"] == [] for n in notes)


@pytest.mark.parametrize("phonemizer", [VCCV, DEFAULT])
def test_only_arpasing_places_phonemes_this_way(phonemizer: str) -> None:
    notes = lead_notes(phonemizer, babe_then_now(), {"babe": BABE})
    assert all(n["phoneme_overrides"] == [] for n in notes)


def test_the_words_to_look_up_are_the_short_tailed_held_ones() -> None:
    plan = plan_of(voices=voices(babe_then_now()), engine_refs=refs(ARPASING))
    assert short_tail_words(plan) == ("babe",)
    other = plan_of(voices=voices(babe_then_now()), engine_refs=refs(VCCV))
    assert short_tail_words(other) == ()
    single = plan_of(
        voices=voices([sing(0, "babe", SIXTEENTH), sing(SIXTEENTH, "now", 1)]),
        engine_refs=refs(ARPASING),
    )
    assert short_tail_words(single) == ()
