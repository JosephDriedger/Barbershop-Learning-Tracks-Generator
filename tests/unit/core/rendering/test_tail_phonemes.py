"""The backend asks the host's dictionary only for the words whose closing consonants may move."""

from fractions import Fraction
from typing import Any

from barbershop_tracks.core.rendering import CancelToken, OpenUtauRenderBackend
from barbershop_tracks.core.synthesis import VoiceEngineRef
from barbershop_tracks.models import Lyric, Melisma, VoiceRole
from readiness_builders import PITCHES, note
from synth_builders import ROLES, plan_of

ARPASING = "OpenUtau.Plugin.Builtin.ArpasingPhonemizer"
LEAD = PITCHES[VoiceRole.LEAD]


def plan() -> Any:
    lead = [
        note(0, Fraction(3, 4), LEAD, lyrics=(Lyric(text="babe", melisma=Melisma.UNTYPED),)),
        note(Fraction(3, 4), Fraction(1, 4), LEAD),
        note(1, 1, LEAD, lyrics=(Lyric(text="now"),)),
    ]
    voices = {r.value: [note(0, 1, PITCHES[r], lyrics=(Lyric(text="la"),))] for r in ROLES}
    voices["lead"] = lead
    ref = VoiceEngineRef(singer="s", phonemizer=ARPASING, renderer="WORLDLINE-R")
    return plan_of(voices=voices, engine_refs=dict.fromkeys(ROLES, ref))


def backend_with(answer: dict[str, str | None], asked: list[list[str]]) -> OpenUtauRenderBackend:
    backend = OpenUtauRenderBackend.__new__(OpenUtauRenderBackend)

    def lookup(pieces: list[str], *_rest: object) -> dict[str, str | None]:
        asked.append(list(pieces))
        return answer

    backend._lookup = lookup  # type: ignore[method-assign, assignment]
    return backend


def test_the_held_word_is_looked_up_and_its_phonemes_are_split() -> None:
    asked: list[list[str]] = []
    backend = backend_with({"babe": "b ey b"}, asked)
    found = backend._tail_phonemes(plan(), _none(), ["host"], {}, CancelToken())
    assert asked == [["babe"]]
    assert found == {"babe": ("b", "ey", "b")}


def test_a_word_the_dictionary_lacks_is_simply_not_adjusted() -> None:
    backend = backend_with({"babe": None}, [])
    assert backend._tail_phonemes(plan(), _none(), ["host"], {}, CancelToken()) == {}


def test_no_lookup_is_made_when_no_word_needs_it() -> None:
    asked: list[list[str]] = []
    backend = backend_with({}, asked)
    voices = {
        r.value: [note(0, 1, PITCHES[r], lyrics=(Lyric(text="la"),)) for _ in range(1)]
        for r in ROLES
    }
    ref = VoiceEngineRef(singer="s", phonemizer=ARPASING, renderer="WORLDLINE-R")
    quiet = plan_of(voices=voices, engine_refs=dict.fromkeys(ROLES, ref))
    assert backend._tail_phonemes(quiet, _none(), ["host"], {}, CancelToken()) == {}
    assert asked == []


def _none() -> Any:
    from barbershop_tracks.core.synthesis.openutau import NO_OVERRIDES

    return NO_OVERRIDES
