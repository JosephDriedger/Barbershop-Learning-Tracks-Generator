"""Lyrics as real scores type them (curly apostrophes, quotes, !, parentheses) reach the engine as words."""

from fractions import Fraction

import pytest
import yaml

from barbershop_tracks.core.synthesis import LyricState, VoiceEngineRef
from barbershop_tracks.core.synthesis.openutau import (
    PronunciationOverride,
    UstxError,
    parse_symbols,
    resolve_overrides,
    validate_lyric_text,
    write_ustx,
)
from barbershop_tracks.core.synthesis.openutau.words import engine_text
from barbershop_tracks.models import Lyric, Syllabic, VoiceRole
from readiness_builders import PITCHES, note
from synth_builders import ROLES, SOURCE, plan_of

ARPASING = "OpenUtau.Plugin.Builtin.ArpasingPhonemizer"


@pytest.mark.parametrize(
    ("written", "sent"),
    [
        ("she’s", "she's"),
        ("ain’t", "ain't"),
        ("in’", "in'"),
        ("‘cause", "'cause"),
        ("wond’rin", "wond'rin"),
        ("“good", "good"),
        ("bye”", "bye"),
        ("Bay!", "Bay"),
        ("(With", "With"),
        ("by)", "by"),
        ("Why?", "Why"),
        ("baby,", "baby"),
        ("end.”", "end"),
        ("don't", "don't"),  # a plain apostrophe is left alone
        ("o'er", "o'er"),
        ("'neath", "'neath"),  # an apostrophe at the start is part of the word
        ("a-b", "a-b"),  # nothing inside a word is touched
        ("—", "—"),  # only punctuation: left as it is (and refused later, naming it)
        ("...", "..."),
    ],
)
def test_the_engine_gets_the_word_the_score_means(written: str, sent: str) -> None:
    assert engine_text(written) == sent


def plan_with(words: list[tuple[str, Syllabic]], phonemizer: str = ARPASING):  # type: ignore[no-untyped-def]
    lead = [
        note(i, 1, PITCHES[VoiceRole.LEAD], lyrics=(Lyric(text=t, syllabic=k),))
        for i, (t, k) in enumerate(words)
    ]
    voices = {r.value: [note(0, 1, PITCHES[r], lyrics=(Lyric(text="la"),))] for r in ROLES}
    voices["lead"] = lead
    engine = VoiceEngineRef(singer="s", phonemizer=phonemizer, renderer="WORLDLINE-R")
    return plan_of(voices=voices, engine_refs=dict.fromkeys(ROLES, engine))


def lead_lyrics(plan) -> list[str]:  # type: ignore[no-untyped-def]
    document = yaml.safe_load(write_ustx(plan).text)
    part = next(p for p in document["voice_parts"] if p["name"] == "Lead")
    return [n["lyric"] for n in part["notes"]]


def test_a_score_typed_the_way_musescore_types_it_is_written_for_the_engine() -> None:
    single = Syllabic.SINGLE
    plan = plan_with(
        [("she’s", single), ("ain’t", single), ("Bay!", single), ("(With", single), ("by)", single)]
    )
    assert lead_lyrics(plan) == ["she's", "ain't", "Bay", "With", "by"]


def test_a_word_in_quotes_over_two_notes_is_one_clean_word() -> None:
    plan = plan_with([("“good", Syllabic.BEGIN), ("bye”", Syllabic.END)])
    assert lead_lyrics(plan) == ["goodbye", "+"]


def test_the_default_phonemizer_gets_the_same_clean_text() -> None:
    plan = plan_with([("ain’t", Syllabic.SINGLE)], phonemizer="OpenUtau.Core.DefaultPhonemizer")
    assert lead_lyrics(plan) == ["ain't"]


def test_the_scores_own_text_is_not_changed() -> None:
    plan = plan_with(
        [("she’s", Syllabic.SINGLE), ("“good", Syllabic.BEGIN), ("bye”", Syllabic.END)]
    )
    notes = plan.voice(VoiceRole.LEAD).notes
    assert [n.lyric.text for n in notes] == ["she’s", "“good", "bye”"]
    assert notes[0].lyric.provenance.source_text == "she’s"
    assert notes[0].lyric.state is LyricState.SCORE_LYRIC


def test_a_pronunciation_decided_for_the_word_matches_the_note_that_spells_it_curly() -> None:
    plan = plan_with([("o’er", Syllabic.SINGLE), ("la", Syllabic.SINGLE)])
    decision = PronunciationOverride(
        role=VoiceRole.LEAD,
        start=Fraction(0),
        word="o'er",  # as the engine and the host name it
        phonemizer=ARPASING,
        symbols=parse_symbols("ow er"),
        approved_by="A. Singer",
        source_sha256=SOURCE.sha256 or "",
    )
    resolved = resolve_overrides(plan, [decision], source_sha256=SOURCE.sha256)
    assert lead_lyrics_with(plan, resolved)[0] == "o'er[ow er]"


def lead_lyrics_with(plan, resolved) -> list[str]:  # type: ignore[no-untyped-def]
    document = yaml.safe_load(write_ustx(plan, overrides=resolved).text)
    part = next(p for p in document["voice_parts"] if p["name"] == "Lead")
    return [n["lyric"] for n in part["notes"]]


def test_a_character_the_engine_cannot_take_is_named_in_the_refusal() -> None:
    with pytest.raises(UstxError) as error:
        validate_lyric_text("café")
    assert "U+00E9" in error.value.message
    assert "write it with plain letters" in error.value.message


def test_the_lyric_review_accepts_what_the_engine_will_receive() -> None:
    from barbershop_tracks.ui.lyric_review import check_text

    assert check_text("she’s") == ""
    assert check_text("“goodbye”") == ""
    assert "U+00E9" in check_text("café")
