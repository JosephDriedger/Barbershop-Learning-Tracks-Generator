"""Words that span notes are sent whole to the dictionary phonemizers, and only to them."""

import pytest
import yaml

from barbershop_tracks.core.synthesis import VoiceEngineRef
from barbershop_tracks.core.synthesis.openutau import write_ustx
from barbershop_tracks.core.synthesis.openutau.words import DICTIONARY_PHONEMIZERS
from barbershop_tracks.models import Lyric, Melisma, Note, Syllabic, VoiceRole
from readiness_builders import PITCHES, note
from synth_builders import ROLES, plan_of

ARPASING = "OpenUtau.Plugin.Builtin.ArpasingPhonemizer"
DEFAULT = "OpenUtau.Core.DefaultPhonemizer"
BEGIN, MIDDLE, END, SINGLE = Syllabic.BEGIN, Syllabic.MIDDLE, Syllabic.END, Syllabic.SINGLE


def syllable(start: int, text: str, kind: Syllabic, *, held: bool = False, dur: int = 1) -> Note:
    melisma = Melisma.UNTYPED if held else Melisma.NONE
    lyric = Lyric(text=text, syllabic=kind, melisma=melisma)
    return note(start, dur, PITCHES[VoiceRole.LEAD], lyrics=(lyric,))


def held_note(start: int) -> Note:
    """A note without a lyric of its own, under the melisma of the one before."""
    return note(start, 1, PITCHES[VoiceRole.LEAD])


def refs(phonemizer: str) -> dict[VoiceRole, VoiceEngineRef]:
    ref = VoiceEngineRef(singer="s", phonemizer=phonemizer, renderer="WORLDLINE-R")
    return dict.fromkeys(ROLES, ref)


def voice_lyrics(
    voice: str, plan_voices: dict[str, list[Note]], phonemizer: str = ARPASING, follow: bool = False
) -> list[str]:
    plan = plan_of(voices=plan_voices, engine_refs=refs(phonemizer), follow_lead=follow)
    document = yaml.safe_load(write_ustx(plan).text)
    part = next(p for p in document["voice_parts"] if p["name"] == voice)
    return [n["lyric"] for n in part["notes"]]


def quartet(lead: list[Note], **others: list[Note]) -> dict[str, list[Note]]:
    voices = {r.value: [note(0, 1, PITCHES[r], lyrics=(Lyric(text="la"),))] for r in ROLES}
    voices["lead"] = lead
    voices.update(others)
    return voices


def lead_lyrics(lead: list[Note], phonemizer: str = ARPASING) -> list[str]:
    return voice_lyrics("Lead", quartet(lead), phonemizer)


def test_the_phonemizers_that_look_words_up_are_the_ones_named_in_the_config() -> None:
    from barbershop_tracks.core.pipeline.config import ENGLISH_PHONEMIZERS

    assert tuple(ENGLISH_PHONEMIZERS) == DICTIONARY_PHONEMIZERS


def test_a_word_on_three_notes_is_sent_whole_with_extenders() -> None:
    lead = [
        syllable(0, "to", BEGIN),
        syllable(1, "geth", MIDDLE),
        syllable(2, "er", END),
        syllable(3, "now", SINGLE),
    ]
    assert lead_lyrics(lead) == ["together", "+", "+", "now"]


@pytest.mark.parametrize("phonemizer", DICTIONARY_PHONEMIZERS)
def test_every_dictionary_phonemizer_gets_the_whole_word(phonemizer: str) -> None:
    lead = [syllable(0, "to", BEGIN), syllable(1, "geth", MIDDLE), syllable(2, "er", END)]
    assert lead_lyrics(lead, phonemizer) == ["together", "+", "+"]


def test_the_default_phonemizer_still_gets_the_syllables() -> None:
    lead = [syllable(0, "to", BEGIN), syllable(1, "geth", MIDDLE), syllable(2, "er", END)]
    assert lead_lyrics(lead, DEFAULT) == ["to", "geth", "er"]


def test_a_melisma_inside_a_word_keeps_its_extenders() -> None:
    lead = [
        syllable(0, "to", BEGIN),
        syllable(1, "geth", MIDDLE, held=True),
        held_note(2),
        syllable(3, "er", END),
    ]
    assert lead_lyrics(lead) == ["together", "+", "+", "+"]


def test_apostrophes_and_single_syllable_words_are_left_alone() -> None:
    lead = [
        syllable(0, "ev'", BEGIN),
        syllable(1, "ry", END),
        syllable(2, "don't", SINGLE),
        syllable(3, "'cause", SINGLE),
    ]
    assert lead_lyrics(lead) == ["ev'ry", "+", "don't", "'cause"]


def test_a_word_without_syllable_marks_is_one_word_per_note() -> None:
    lead = [
        note(0, 1, PITCHES[VoiceRole.LEAD], lyrics=(Lyric(text="to"),)),
        note(1, 1, PITCHES[VoiceRole.LEAD], lyrics=(Lyric(text="geth"),)),
    ]
    assert lead_lyrics(lead) == ["to", "geth"]


@pytest.mark.parametrize(
    "notes",
    [
        [syllable(0, "to", BEGIN), syllable(2, "geth", END)],  # a rest inside the word
        [syllable(0, "to", BEGIN)],  # the score ends first
        [syllable(0, "geth", MIDDLE), syllable(1, "er", END)],  # starts in the middle of a word
        [syllable(0, "to", BEGIN), syllable(1, "now", SINGLE)],  # the next note is another word
    ],
)
def test_a_word_that_is_not_complete_on_touching_notes_is_left_as_the_score_writes_it(
    notes: list[Note],
) -> None:
    written = [n.lyrics[0].text for n in notes]
    assert lead_lyrics(notes) == written  # nothing is joined, nothing is invented


def test_a_part_that_follows_the_lead_takes_the_whole_word_too() -> None:
    lead = [syllable(0, "to", BEGIN), syllable(1, "geth", MIDDLE), syllable(2, "er", END)]
    tenor = [note(i, 1, PITCHES[VoiceRole.TENOR]) for i in range(3)]
    voices = quartet(lead, tenor=tenor)
    assert voice_lyrics("Tenor", voices, follow=True) == ["together", "+", "+"]


def test_a_part_that_holds_one_note_under_the_leads_word_keeps_the_first_syllable_only() -> None:
    lead = [syllable(0, "to", BEGIN), syllable(1, "geth", MIDDLE), syllable(2, "er", END)]
    voices = quartet(lead, tenor=[note(0, 3, PITCHES[VoiceRole.TENOR])])
    assert voice_lyrics("Tenor", voices, follow=True) == ["to"]


def test_a_part_that_sings_only_some_syllables_of_the_leads_word_is_not_joined() -> None:
    lead = [syllable(0, "to", BEGIN), syllable(1, "geth", MIDDLE), syllable(2, "er", END)]
    skipping = [note(0, 1, PITCHES[VoiceRole.TENOR]), note(2, 1, PITCHES[VoiceRole.TENOR])]
    voices = quartet(lead, tenor=skipping)
    assert voice_lyrics("Tenor", voices, follow=True) == ["to", "er"]
