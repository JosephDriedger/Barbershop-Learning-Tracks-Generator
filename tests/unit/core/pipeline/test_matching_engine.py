"""When nobody chose a pronunciation engine, the one the voices were made for is used, and said."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from barbershop_tracks.core.pipeline.coordinator import (
    EngineChoice,
    GenerateRequest,
    _matching_engine,
)
from barbershop_tracks.core.readiness import RoleAssignments
from barbershop_tracks.core.rendering.engine_detect import ENGLISH_XSAMPA
from barbershop_tracks.models import VoiceRole

DEFAULT = "OpenUtau.Core.DefaultPhonemizer"
ARPASING = "OpenUtau.Plugin.Builtin.ArpasingPhonemizer"
XSAMPA_NAMES = [
    "@ p",
    "@ b",
    "S@",
    "tS@",
    "@ N",
    "p@",
    "t@",
    "k@",
    "m@",
    "n@",
    "l@",
    "r@",
    "s@",
] * 3
SYLLABLES = [c + v for c in "kstnhmyrw" for v in "aiueo"]


def bank(root: Path, name: str, aliases: list[str]) -> None:
    folder = root / name
    folder.mkdir(parents=True)
    lines = [f"s{i}.wav={alias},0,100,-200,10,10" for i, alias in enumerate(aliases)]
    (folder / "oto.ini").write_text("\n".join(lines) + "\n", encoding="utf-8")


def request(
    singer: str | None, *, automatic: bool, phonemizer: str = DEFAULT, per_voice: Any = None
) -> GenerateRequest:
    engine = EngineChoice(singer, phonemizer, "WORLDLINE-R", per_voice or {}, automatic=automatic)
    return GenerateRequest(
        score=Path("score.musicxml"),
        output=Path("out"),
        assignments=RoleAssignments(entries=()),
        engine=engine,
    )


def config(root: Path) -> Any:
    return SimpleNamespace(singers_dir=root)


def test_an_x_sampa_voice_gets_the_x_sampa_engine_and_a_notice(tmp_path: Path) -> None:
    bank(tmp_path, "english", XSAMPA_NAMES)
    changed, notice = _matching_engine(request("english", automatic=True), config(tmp_path))
    assert changed.engine.phonemizer == ENGLISH_XSAMPA
    assert notice is not None
    assert "EnXSampaPhonemizer" in notice
    assert "Advanced" in notice


def test_a_choice_made_by_the_person_is_never_changed(tmp_path: Path) -> None:
    bank(tmp_path, "english", XSAMPA_NAMES)
    same, notice = _matching_engine(request("english", automatic=False), config(tmp_path))
    assert same.engine.phonemizer == DEFAULT
    assert notice is None


def test_a_plain_syllable_voice_keeps_the_default(tmp_path: Path) -> None:
    bank(tmp_path, "romaji", SYLLABLES)
    same, notice = _matching_engine(request("romaji", automatic=True), config(tmp_path))
    assert same.engine.phonemizer == DEFAULT
    assert notice is None


def test_voices_that_point_to_different_engines_keep_the_default(tmp_path: Path) -> None:
    bank(tmp_path, "english", XSAMPA_NAMES)
    bank(tmp_path, "romaji", SYLLABLES)
    mixed = {VoiceRole.TENOR: "english", VoiceRole.LEAD: "romaji"}
    same, notice = _matching_engine(
        request("english", automatic=True, per_voice=mixed), config(tmp_path)
    )
    assert same.engine.phonemizer == DEFAULT
    assert notice is None


def test_no_voices_folder_changes_nothing() -> None:
    nowhere: Any = SimpleNamespace(singers_dir=None)
    same, notice = _matching_engine(request("english", automatic=True), nowhere)
    assert same.engine.phonemizer == DEFAULT
    assert notice is None
