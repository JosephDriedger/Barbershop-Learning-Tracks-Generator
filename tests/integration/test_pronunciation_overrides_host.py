"""A person's pronunciation through the real render host: accepted, refused, scoped.

The synthetic voicebank cannot sing English phonemes, so what is shown here is what the engine does
with the pronunciation before and while it phonemizes: the word stops being "unknown", the symbols
are checked by the engine itself (not by a copy of its symbol list), a refusal stops the run
before any stem is rendered, and one decision touches one voice at one note.
"""

from pathlib import Path

import pytest

from barbershop_tracks.core.rendering import (
    OpenUtauRenderBackend,
    PronunciationError,
    RenderSettings,
)
from barbershop_tracks.core.runtime import RuntimeLayout
from barbershop_tracks.core.synthesis import VoiceEngineRef
from barbershop_tracks.core.synthesis.openutau import (
    PronunciationOverride,
    parse_symbols,
    resolve_overrides,
)
from barbershop_tracks.models import VoiceRole
from host_support import host_environment, require_host
from synth_builders import ROLES, SOURCE, full_lyrics, plan_of
from synthetic_voicebank import SINGER_ID, build_voicebank

pytestmark = pytest.mark.integration

ARPASING = "OpenUtau.Plugin.Builtin.ArpasingPhonemizer"
VCCV = "OpenUtau.Plugin.Builtin.EnglishVCCVPhonemizer"
XSAMPA = "OpenUtau.Plugin.Builtin.EnXSampaPhonemizer"
SHA = SOURCE.sha256 or ""
WORD = "blorptastic"  # a made-up word: the dictionary does not have it and a model would only guess
ARPABET = (
    "b l ao r p t ae s t ih k"  # accepted by all three engines (the syllable ones translate it)
)
NATIVE = {
    ARPASING: ARPABET,
    VCCV: "b l 9 r p t & s t I k",
    XSAMPA: "b l O r p t { s t I k",
}


class Rig:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.singers = root / "singers"
        build_voicebank(self.singers)
        self.layout = RuntimeLayout.under(root / "bin", root / "data")

    def backend(self, **options: object) -> OpenUtauRenderBackend:
        return OpenUtauRenderBackend(
            RenderSettings(
                layout=self.layout,
                singers_dir=self.singers,
                host_binaries=require_host(),
                extra_env={k: v for k, v in host_environment().items() if k == "DOTNET_ROOT"},
                **options,  # type: ignore[arg-type]
            )
        )


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    require_host()
    return Rig(tmp_path)


def model_in_host() -> bool:
    import json

    record = require_host() / "blt-host-build.json"
    return bool(json.loads(record.read_text(encoding="utf-8")).get("g2p_model") == "included")


def plan_with(phonemizer: str, words: tuple[str, ...] = ("la", WORD, "la", "la")):  # type: ignore[no-untyped-def]
    engine = VoiceEngineRef(singer=SINGER_ID, phonemizer=phonemizer, renderer="WORLDLINE-R")
    return plan_of(voices=full_lyrics(words), engine_refs=dict.fromkeys(ROLES, engine))


def decide(
    phonemizer: str,
    symbols: str,
    *,
    role: VoiceRole = VoiceRole.LEAD,
    word: str = WORD,
    start: int = 1,
) -> PronunciationOverride:
    return PronunciationOverride(
        role=role,
        start=start,  # type: ignore[arg-type]
        word=word,
        phonemizer=phonemizer,
        symbols=parse_symbols(symbols),
        approved_by="A. Singer",
        source_sha256=SHA,
    )


@pytest.mark.parametrize("phonemizer", [ARPASING, VCCV, XSAMPA])
def test_a_word_the_dictionary_lacks_stops_every_voice_until_it_is_decided(
    rig: Rig, phonemizer: str
) -> None:
    if model_in_host():
        pytest.skip("the research host guesses instead of stopping")
    plan = plan_with(phonemizer)
    with pytest.raises(PronunciationError) as error:
        rig.backend(compose_unknown_words=False).check_pronunciations(plan)
    assert error.value.code == "PRONUNCIATION_UNKNOWN"
    assert sorted(u["voice"] for u in error.value.details["unknown_words"]) == [
        "Baritone",
        "Bass",
        "Lead",
        "Tenor",
    ]


@pytest.mark.parametrize("phonemizer", [ARPASING, VCCV, XSAMPA])
def test_one_decision_unblocks_one_voice_only(rig: Rig, phonemizer: str) -> None:
    if model_in_host():
        pytest.skip("the research host guesses instead of stopping")
    plan = plan_with(phonemizer)
    resolved = resolve_overrides(plan, [decide(phonemizer, ARPABET)], source_sha256=SHA)
    with pytest.raises(PronunciationError) as error:
        rig.backend(compose_unknown_words=False).check_pronunciations(plan, resolved)
    named = {u["voice"] for u in error.value.details["unknown_words"]}
    assert named == {"Tenor", "Baritone", "Bass"}  # the Lead was decided; nobody else was touched
    assert "Lead" not in named


@pytest.mark.parametrize("phonemizer", [ARPASING, VCCV, XSAMPA])
def test_a_decision_for_every_voice_clears_the_block_and_the_engine_reports_its_sounds(
    rig: Rig, phonemizer: str
) -> None:
    plan = plan_with(phonemizer)
    resolved = resolve_overrides(
        plan, [decide(phonemizer, ARPABET, role=role) for role in ROLES], source_sha256=SHA
    )
    result = rig.backend().check_pronunciations(plan, resolved)
    assert result["unknown_word_count"] == 0
    reported = {p["track"]: p for p in result["pronunciations"]}
    assert set(reported) == {"Tenor", "Lead", "Baritone", "Bass"}
    for item in reported.values():
        assert item["lyric"] == WORD  # the word as the score gives it, without the brackets
        assert item["hint"] == ARPABET
        assert item["phonemes"]
        assert "error" not in item["phonemes"]


@pytest.mark.parametrize("phonemizer", [VCCV, XSAMPA])
def test_the_native_notation_of_a_syllable_phonemizer_is_accepted_too(
    rig: Rig, phonemizer: str
) -> None:
    plan = plan_with(phonemizer)
    resolved = resolve_overrides(
        plan,
        [decide(phonemizer, NATIVE[phonemizer], role=role) for role in ROLES],
        source_sha256=SHA,
    )
    result = rig.backend().check_pronunciations(plan, resolved)
    assert all(p["phonemes"] for p in result["pronunciations"])


@pytest.mark.parametrize("phonemizer", [ARPASING, VCCV, XSAMPA])
def test_a_symbol_the_engine_does_not_know_is_refused_before_anything_renders(
    rig: Rig, phonemizer: str
) -> None:
    plan = plan_with(phonemizer)
    resolved = resolve_overrides(
        plan,
        [decide(phonemizer, "b l zzz r", role=role) for role in ROLES],
        source_sha256=SHA,
    )
    with pytest.raises(PronunciationError) as error:
        rig.backend().check_pronunciations(plan, resolved)
    assert error.value.code == "PRONUNCIATION_INVALID"
    found = error.value.details["invalid_hints"]
    assert {h["voice"] for h in found} == {"Tenor", "Lead", "Baritone", "Bass"}
    assert {h["symbol"] for h in found} == {"zzz"}
    assert {h["where"] for h in found} == {"bar 1, beat 2"}
    assert "zzz" in error.value.message
    assert "nothing was rendered" in error.value.message


def test_arpasing_would_drop_a_wrong_symbol_silently_so_it_is_named_instead(rig: Rig) -> None:
    # with the stress digits of the CMU dictionary: Arpasing alone would have sung "eh v r"
    plan = plan_with(ARPASING, words=("la", "ev'ry", "la", "la"))
    resolved = resolve_overrides(
        plan,
        [decide(ARPASING, "eh1 v r iy0", word="ev'ry", role=role) for role in ROLES],
        source_sha256=SHA,
    )
    with pytest.raises(PronunciationError) as error:
        rig.backend().check_pronunciations(plan, resolved)
    assert {h["symbol"] for h in error.value.details["invalid_hints"]} == {"eh1", "iy0"}


def test_a_refused_pronunciation_renders_nothing_and_publishes_nothing(
    rig: Rig, tmp_path: Path
) -> None:
    plan = plan_with(ARPASING)
    resolved = resolve_overrides(
        plan, [decide(ARPASING, "b l zzz", role=role) for role in ROLES], source_sha256=SHA
    )
    destination = tmp_path / "stems"
    with pytest.raises(PronunciationError) as error:
        rig.backend().render(plan, destination, overrides=resolved)
    assert error.value.code == "PRONUNCIATION_INVALID"
    assert not destination.exists()
    staging = rig.layout.staging
    assert not staging.is_dir() or list(staging.iterdir()) == []  # no half-finished job left behind
