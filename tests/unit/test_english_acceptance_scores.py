"""The English acceptance scores: written by their generator, ready quartets, as described."""

import sys
from pathlib import Path

import pytest
import yaml

from barbershop_tracks.core.musicxml import parse_musicxml
from barbershop_tracks.core.pipeline.preparation import prepare
from barbershop_tracks.core.synthesis import SourceIdentity, VoiceEngineRef
from barbershop_tracks.core.synthesis.openutau import write_ustx
from barbershop_tracks.models import VoiceRole
from readiness_builders import quartet_assignments

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "docs" / "acceptance" / "fixtures"
sys.path.insert(0, str(REPO / "scripts"))

import build_english_acceptance_fixture as generator  # noqa: E402

ARPASING = "OpenUtau.Plugin.Builtin.ArpasingPhonemizer"
ROLES = (VoiceRole.TENOR, VoiceRole.LEAD, VoiceRole.BARITONE, VoiceRole.BASS)


def ustx_lyrics(version: str, phonemizer: str) -> dict[str, list[str]]:
    parsed = parse_musicxml(FIXTURES / f"english-quartet-{version}-words.musicxml")
    ref = VoiceEngineRef(singer="s", phonemizer=phonemizer, renderer="WORLDLINE-R")
    prepared = prepare(
        parsed,
        quartet_assignments(),
        identity=SourceIdentity(display_name=f"{version}.musicxml"),
        engine_refs=dict.fromkeys(ROLES, ref),
        follow_lead=True,
    )
    assert prepared.generatable, prepared.review
    assert prepared.plan is not None
    document = yaml.safe_load(write_ustx(prepared.plan).text)
    return {p["name"]: [n["lyric"] for n in p["notes"]] for p in document["voice_parts"]}


def test_the_committed_scores_are_what_the_generator_writes() -> None:
    for name, content in generator.render().items():
        committed = (FIXTURES / name).read_text(encoding="utf-8").replace("\r\n", "\n")
        assert committed == content, (
            f"{name} is out of date: python scripts/{generator.__name__}.py"
        )


@pytest.mark.parametrize("version", ["known", "unknown", "respelled"])
def test_every_version_is_a_ready_quartet_that_is_not_waiting_for_lyrics(version: str) -> None:
    lyrics = ustx_lyrics(
        version, ARPASING
    )  # asserts that the plan is ready: nothing left to review
    assert set(lyrics) == {"Tenor", "Lead", "Baritone", "Bass"}
    assert generator.TEMPO == "88"


def test_the_known_score_sends_whole_words_with_extenders_to_a_dictionary_phonemizer() -> None:
    lyrics = ustx_lyrics("known", ARPASING)
    lead = lyrics["Lead"]
    assert lead[:4] == ["Love", "is", "a", "song"]
    assert lead[4:8] == ["we", "sing", "+", "+"]  # the melisma
    assert lead[8:11] == ["together", "+", "+"]  # three syllables, then the sustained last note
    assert "always" in lead
    assert "don't" in lead
    assert "'cause" in lead
    assert lead[-1] == "home"  # the whole note
    assert lyrics["Bass"][4:8] == ["dum", "dum", "dum", "dum"]  # the Bass's own words
    assert lyrics["Tenor"][:4] == ["Love", "is", "a", "song"]  # the parts follow the Lead


def test_the_unknown_score_has_the_words_the_dictionary_lacks_and_whole() -> None:
    lead = ustx_lyrics("unknown", ARPASING)["Lead"]
    for word in ("lov'd", "ev'ryone", "'neath", "o'er"):
        assert word in lead
    assert ustx_lyrics("unknown", ARPASING)["Bass"][4:8][-1] == "mammy"


def test_the_respelled_score_replaces_exactly_the_unknown_words() -> None:
    lead = ustx_lyrics("respelled", ARPASING)["Lead"]
    for word in ("loved", "everyone", "beneath", "over"):
        assert word in lead
    assert not {"lov'd", "ev'ryone", "'neath", "o'er"} & set(lead)
    assert ustx_lyrics("respelled", ARPASING)["Bass"][4:8][-1] == "mommy"


def test_the_manifest_lists_every_word_with_a_place_and_an_expectation() -> None:
    manifest = generator.words_manifest()
    for version in ("known", "unknown", "respelled"):
        words = manifest["versions"][version]["words"]  # type: ignore[index]
        assert all({"word", "sung_by", "where", "in_dictionary"} <= set(w) for w in words)
    unknown = manifest["versions"]["unknown"]["words"]  # type: ignore[index]
    assert {
        w["word"] for w in unknown if not w["in_dictionary"]
    } == generator.OUTSIDE_THE_DICTIONARY
    bass = next(w for w in unknown if w["word"] == "mammy")
    assert bass["where"] == "bar 2, beat 4"
