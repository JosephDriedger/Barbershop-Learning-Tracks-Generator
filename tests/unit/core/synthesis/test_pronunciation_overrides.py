"""A person's pronunciation for one word of one score: scoped, checked, written as a hint."""

from dataclasses import replace
from fractions import Fraction
from typing import Any

import pytest
import yaml

from barbershop_tracks.core.synthesis import LyricState, SynthesisPlan, VoiceEngineRef
from barbershop_tracks.core.synthesis.openutau import (
    ALPHABETS,
    NO_OVERRIDES,
    OverrideError,
    PronunciationOverride,
    UstxError,
    parse_symbols,
    resolve_overrides,
    write_ustx,
)
from barbershop_tracks.models import Lyric, Melisma, Note, Syllabic, VoiceRole
from readiness_builders import PITCHES, note
from synth_builders import ROLES, SOURCE, plan_of

ARPASING = "OpenUtau.Plugin.Builtin.ArpasingPhonemizer"
VCCV = "OpenUtau.Plugin.Builtin.EnglishVCCVPhonemizer"
XSAMPA = "OpenUtau.Plugin.Builtin.EnXSampaPhonemizer"
DEFAULT = "OpenUtau.Core.DefaultPhonemizer"
SHA = SOURCE.sha256 or ""
BEGIN, MIDDLE, END, SINGLE = Syllabic.BEGIN, Syllabic.MIDDLE, Syllabic.END, Syllabic.SINGLE


def syllable(start: int, text: str, kind: Syllabic = SINGLE) -> Note:
    return note(start, 1, PITCHES[VoiceRole.LEAD], lyrics=(Lyric(text=text, syllabic=kind),))


def held(start: int) -> Note:
    return note(start, 1, PITCHES[VoiceRole.LEAD], lyrics=(Lyric(text="la", melisma=Melisma.NONE),))


def refs(phonemizer: str, special: dict[str, str]) -> dict[VoiceRole, VoiceEngineRef]:
    out: dict[VoiceRole, VoiceEngineRef] = {}
    for role in ROLES:
        out[role] = VoiceEngineRef(
            singer="s", phonemizer=special.get(role.value, phonemizer), renderer="WORLDLINE-R"
        )
    return out


def plan_for(
    lead: list[Note],
    *,
    phonemizer: str = ARPASING,
    tenor: list[Note] | None = None,
    follow: bool = False,
    engines: dict[str, str] | None = None,
) -> SynthesisPlan:
    voices = {r.value: [note(0, 1, PITCHES[r], lyrics=(Lyric(text="la"),))] for r in ROLES}
    voices["lead"] = lead
    if tenor is not None:
        voices["tenor"] = tenor
    return plan_of(voices=voices, engine_refs=refs(phonemizer, engines or {}), follow_lead=follow)


def decision(
    word: str,
    start: int | Fraction,
    *,
    role: VoiceRole = VoiceRole.LEAD,
    phonemizer: str = ARPASING,
    symbols: str = "ow er",
    sha: str = SHA,
    by: str = "A. Singer",
) -> PronunciationOverride:
    return PronunciationOverride(
        role=role,
        start=Fraction(start),
        word=word,
        phonemizer=phonemizer,
        symbols=parse_symbols(symbols),
        approved_by=by,
        source_sha256=sha,
    )


def lyrics_written(plan: SynthesisPlan, voice: str, overrides: Any = NO_OVERRIDES) -> list[str]:
    document = yaml.safe_load(write_ustx(plan, overrides=overrides).text)
    part = next(p for p in document["voice_parts"] if p["name"] == voice)
    return [n["lyric"] for n in part["notes"]]


# --- the form of what a person types -----------------------------------------------------------


def test_symbols_are_split_on_spaces() -> None:
    assert parse_symbols("  eh  v r iy ") == ("eh", "v", "r", "iy")


@pytest.mark.parametrize("bad", ["", "   ", "eh [v] r", "eh v]", "a\x01b"])
def test_a_pronunciation_of_the_wrong_form_is_refused(bad: str) -> None:
    with pytest.raises(OverrideError):
        parse_symbols(bad)


def test_a_pronunciation_has_a_limited_length() -> None:
    with pytest.raises(OverrideError) as error:
        parse_symbols(" ".join(["ah"] * 65))
    assert error.value.code == "OVERRIDE_TOO_LONG"


def test_x_sampa_symbols_with_backslash_and_braces_are_accepted() -> None:
    assert parse_symbols("I\\ {~ @` t_}") == ("I\\", "{~", "@`", "t_}")


def test_an_override_needs_a_phonemizer_that_takes_pronunciations() -> None:
    with pytest.raises(OverrideError) as error:
        decision("o'er", 0, phonemizer=DEFAULT)
    assert error.value.code == "OVERRIDE_PHONEMIZER_UNSUPPORTED"


def test_an_override_names_who_decided_it_and_for_which_score() -> None:
    with pytest.raises(OverrideError, match="who decided"):
        decision("o'er", 0, by="  ")
    with pytest.raises(OverrideError, match="SHA-256"):
        decision("o'er", 0, sha="not-a-hash")


def test_every_dictionary_phonemizer_has_its_own_notation() -> None:
    assert ALPHABETS[ARPASING] == "arpabet"
    assert ALPHABETS[VCCV] == "vccv"
    assert ALPHABETS[XSAMPA] == "xsampa"
    assert decision("o'er", 0, phonemizer=XSAMPA, symbols="oU 3").alphabet == "xsampa"


# --- scoping: one voice, one note, one word, one score, one engine ------------------------------


def test_a_contraction_is_written_with_its_hint_and_the_score_keeps_its_own_text() -> None:
    plan = plan_for([syllable(0, "o'er"), syllable(1, "la")])
    resolved = resolve_overrides(plan, [decision("o'er", 0)], source_sha256=SHA)
    assert lyrics_written(plan, "Lead", resolved) == ["o'er[ow er]", "la"]
    # the plan, which the review screens and the package read, still has the score's own words
    note0 = plan.voice(VoiceRole.LEAD).notes[0].lyric
    assert note0.text == "o'er"
    assert note0.provenance.source_text == "o'er"
    assert note0.state is LyricState.SCORE_LYRIC


@pytest.mark.parametrize("word", ["'neath", "lov'd", "o'er", "mammy"])
def test_each_kind_of_unusual_word_can_be_given_a_pronunciation(word: str) -> None:
    plan = plan_for([syllable(0, word), syllable(1, "la")])
    resolved = resolve_overrides(plan, [decision(word, 0, symbols="n iy th")], source_sha256=SHA)
    assert lyrics_written(plan, "Lead", resolved)[0] == f"{word}[n iy th]"


def test_a_word_over_several_notes_is_decided_on_its_first_note_as_the_whole_word() -> None:
    plan = plan_for([syllable(0, "ev'", BEGIN), syllable(1, "ry", MIDDLE), syllable(2, "one", END)])
    resolved = resolve_overrides(
        plan, [decision("ev'ryone", 0, symbols="eh v r iy w ah n")], source_sha256=SHA
    )
    assert lyrics_written(plan, "Lead", resolved) == ["ev'ryone[eh v r iy w ah n]", "+", "+"]
    (found,) = resolved.all()
    assert found.score_lyrics == (
        "ev'",
        "ry",
        "one",
    )  # the syllables, exactly as the score has them
    assert plan.voice(VoiceRole.LEAD).notes[1].lyric.text == "ry"


def test_the_same_word_in_another_bar_is_not_affected() -> None:
    plan = plan_for(
        [syllable(0, "o'er"), syllable(1, "la"), syllable(8, "o'er"), syllable(9, "la")]
    )
    resolved = resolve_overrides(plan, [decision("o'er", 8)], source_sha256=SHA)
    assert lyrics_written(plan, "Lead", resolved) == ["o'er", "la", "o'er[ow er]", "la"]


def test_both_occurrences_need_a_decision_each() -> None:
    plan = plan_for([syllable(0, "o'er"), syllable(1, "la"), syllable(8, "o'er")])
    resolved = resolve_overrides(
        plan, [decision("o'er", 0), decision("o'er", 8, symbols="ao r")], source_sha256=SHA
    )
    assert lyrics_written(plan, "Lead", resolved) == ["o'er[ow er]", "la", "o'er[ao r]"]


def test_another_voice_with_the_same_word_at_the_same_place_is_not_affected() -> None:
    tenor = [syllable(0, "o'er"), syllable(1, "la")]
    plan = plan_for([syllable(0, "o'er"), syllable(1, "la")], tenor=tenor)
    resolved = resolve_overrides(plan, [decision("o'er", 0)], source_sha256=SHA)  # the Lead's only
    assert lyrics_written(plan, "Lead", resolved)[0] == "o'er[ow er]"
    assert lyrics_written(plan, "Tenor", resolved)[0] == "o'er"
    both = resolve_overrides(
        plan, [decision("o'er", 0), decision("o'er", 0, role=VoiceRole.TENOR)], source_sha256=SHA
    )
    assert lyrics_written(plan, "Tenor", both)[0] == "o'er[ow er]"


def test_a_voice_that_follows_the_lead_is_decided_for_itself() -> None:
    plan = plan_for(
        [syllable(0, "o'er"), syllable(1, "la")],
        tenor=[note(0, 1, PITCHES[VoiceRole.TENOR])],
        follow=True,
    )
    assert plan.voice(VoiceRole.TENOR).notes[0].lyric.state is LyricState.LEAD_SYLLABLE
    resolved = resolve_overrides(
        plan, [decision("o'er", 0, role=VoiceRole.TENOR)], source_sha256=SHA
    )
    assert lyrics_written(plan, "Tenor", resolved)[0] == "o'er[ow er]"
    assert lyrics_written(plan, "Lead", resolved)[0] == "o'er"


@pytest.mark.parametrize(
    ("phonemizer", "symbols"),
    [(ARPASING, "ow er"), (VCCV, "o 3"), (XSAMPA, "oU 3")],
)
def test_each_dictionary_phonemizer_writes_the_symbols_it_was_given(
    phonemizer: str, symbols: str
) -> None:
    plan = plan_for([syllable(0, "o'er"), syllable(1, "la")], phonemizer=phonemizer)
    resolved = resolve_overrides(
        plan, [decision("o'er", 0, phonemizer=phonemizer, symbols=symbols)], source_sha256=SHA
    )
    assert lyrics_written(plan, "Lead", resolved)[0] == f"o'er[{symbols}]"


def test_the_notation_of_one_phonemizer_is_refused_for_another() -> None:
    plan = plan_for([syllable(0, "o'er"), syllable(1, "la")], phonemizer=XSAMPA)
    with pytest.raises(OverrideError) as error:
        resolve_overrides(plan, [decision("o'er", 0, phonemizer=ARPASING)], source_sha256=SHA)
    assert error.value.code == "OVERRIDE_PHONEMIZER_MISMATCH"
    assert "ArpasingPhonemizer" in error.value.message
    assert "EnXSampaPhonemizer" in error.value.message


def test_a_voice_that_uses_the_default_phonemizer_takes_no_pronunciation() -> None:
    plan = plan_for([syllable(0, "o'er"), syllable(1, "la")], phonemizer=DEFAULT)
    # the override object itself cannot be made for the default phonemizer ...
    with pytest.raises(OverrideError):
        decision("o'er", 0, phonemizer=DEFAULT)
    # ... and one made for an English engine does not fit a voice that uses the default one
    with pytest.raises(OverrideError) as error:
        resolve_overrides(plan, [decision("o'er", 0)], source_sha256=SHA)
    assert error.value.code == "OVERRIDE_PHONEMIZER_MISMATCH"


def test_two_voices_may_use_different_phonemizers_each_with_its_own_decision() -> None:
    plan = plan_for(
        [syllable(0, "o'er"), syllable(1, "la")],
        tenor=[syllable(0, "o'er"), syllable(1, "la")],
        engines={"lead": XSAMPA},  # the Lead's engine differs from the others' (Arpasing)
    )
    resolved = resolve_overrides(
        plan,
        [
            decision("o'er", 0, phonemizer=XSAMPA, symbols="oU 3"),
            decision("o'er", 0, role=VoiceRole.TENOR, symbols="ow er"),
        ],
        source_sha256=SHA,
    )
    assert lyrics_written(plan, "Lead", resolved)[0] == "o'er[oU 3]"
    assert lyrics_written(plan, "Tenor", resolved)[0] == "o'er[ow er]"
    with pytest.raises(OverrideError) as error:  # the Tenor's notation is not the Lead's
        resolve_overrides(plan, [decision("o'er", 0, phonemizer=ARPASING)], source_sha256=SHA)
    assert error.value.code == "OVERRIDE_PHONEMIZER_MISMATCH"


# --- stale and mismatched decisions are refused, not skipped --------------------------------------


def test_a_decision_for_another_version_of_the_score_is_refused() -> None:
    plan = plan_for([syllable(0, "o'er"), syllable(1, "la")])
    other = "cd" * 32
    with pytest.raises(OverrideError) as error:
        resolve_overrides(plan, [decision("o'er", 0, sha=other)], source_sha256=SHA)
    assert error.value.code == "OVERRIDE_WRONG_SCORE"
    assert "decide it again" in error.value.message


def test_a_decision_for_a_note_that_is_not_there_is_refused() -> None:
    plan = plan_for([syllable(0, "o'er"), syllable(1, "la")])
    with pytest.raises(OverrideError) as error:
        resolve_overrides(plan, [decision("o'er", 5)], source_sha256=SHA)
    assert error.value.code == "OVERRIDE_NO_NOTE"


def test_a_decision_for_a_word_the_score_no_longer_has_there_is_refused() -> None:
    plan = plan_for([syllable(0, "'neath"), syllable(1, "la")])
    with pytest.raises(OverrideError) as error:
        resolve_overrides(plan, [decision("o'er", 0)], source_sha256=SHA)
    assert error.value.code == "OVERRIDE_WORD_MISMATCH"
    assert "'neath" in error.value.message
    assert "o'er" in error.value.message


def test_a_decision_made_for_a_syllable_is_stale_once_the_word_is_whole() -> None:
    plan = plan_for([syllable(0, "ev'", BEGIN), syllable(1, "ry", MIDDLE), syllable(2, "one", END)])
    with pytest.raises(OverrideError) as error:
        resolve_overrides(plan, [decision("ev'", 0)], source_sha256=SHA)
    assert error.value.code == "OVERRIDE_WORD_MISMATCH"


def test_a_decision_on_the_second_syllable_of_a_word_is_refused() -> None:
    plan = plan_for([syllable(0, "ev'", BEGIN), syllable(1, "ry", MIDDLE), syllable(2, "one", END)])
    with pytest.raises(OverrideError) as error:
        resolve_overrides(plan, [decision("ry", 1)], source_sha256=SHA)
    assert error.value.code == "OVERRIDE_NOT_WORD_START"


def test_a_decision_on_a_held_note_is_refused() -> None:
    lead = [
        note(0, 1, PITCHES[VoiceRole.LEAD], lyrics=(Lyric(text="o'er", melisma=Melisma.UNTYPED),)),
        note(1, 1, PITCHES[VoiceRole.LEAD]),
    ]
    plan = plan_for(lead)
    with pytest.raises(OverrideError) as error:
        resolve_overrides(plan, [decision("o'er", 1)], source_sha256=SHA)
    assert error.value.code in ("OVERRIDE_NO_WORD", "OVERRIDE_NO_NOTE")


def test_two_decisions_for_one_note_are_refused() -> None:
    plan = plan_for([syllable(0, "o'er"), syllable(1, "la")])
    with pytest.raises(OverrideError) as error:
        resolve_overrides(
            plan, [decision("o'er", 0), decision("o'er", 0, symbols="ao r")], source_sha256=SHA
        )
    assert error.value.code == "OVERRIDE_DUPLICATE"


def test_nothing_is_resolved_when_there_is_nothing_to_resolve() -> None:
    plan = plan_for([syllable(0, "o'er"), syllable(1, "la")])
    assert resolve_overrides(plan, [], source_sha256=SHA) is NO_OVERRIDES
    assert lyrics_written(plan, "Lead") == ["o'er", "la"]


def test_overrides_of_another_plan_cannot_be_written() -> None:
    plan = plan_for([syllable(0, "o'er"), syllable(1, "la")])
    other = plan_for([syllable(0, "'neath"), syllable(1, "la")])
    resolved = resolve_overrides(plan, [decision("o'er", 0)], source_sha256=SHA)
    with pytest.raises(UstxError) as error:
        write_ustx(other, overrides=resolved)
    assert error.value.code in ("USTX_OVERRIDE_WORD", "USTX_OVERRIDE_UNUSED")


def test_a_bracket_in_a_score_lyric_is_still_refused_whatever_the_overrides() -> None:
    plan = plan_for([syllable(0, "o'er[ow er]"), syllable(1, "la")])
    with pytest.raises(UstxError) as error:
        write_ustx(plan)
    assert error.value.code == "USTX_LYRIC_TEXT"


def test_x_sampa_backslash_survives_the_project_file() -> None:
    plan = plan_for([syllable(0, "o'er"), syllable(1, "la")], phonemizer=XSAMPA)
    resolved = resolve_overrides(
        plan, [decision("o'er", 0, phonemizer=XSAMPA, symbols="I\\ {~ @`")], source_sha256=SHA
    )
    assert lyrics_written(plan, "Lead", resolved)[0] == "o'er[I\\ {~ @`]"


def test_overrides_do_not_change_anything_else_in_the_project() -> None:
    plan = plan_for([syllable(0, "o'er"), syllable(1, "la")])
    resolved = resolve_overrides(plan, [decision("o'er", 0)], source_sha256=SHA)
    plain = write_ustx(plan).text
    hinted = write_ustx(plan, overrides=resolved).text
    assert hinted != plain
    assert hinted.replace("o'er[ow er]", "o'er") == plain
    assert replace(plan).source.sha256 == SHA
