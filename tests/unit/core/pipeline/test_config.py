import json
from pathlib import Path

import pytest

from barbershop_tracks.core.mixing import DEFAULT_PROFILE, PRESETS
from barbershop_tracks.core.pipeline import (
    DEFAULT_PHONEMIZER,
    DEFAULT_RENDERER,
    ErrorCategory,
    PipelineError,
    config_path,
    discover_singers,
    load_config_file,
    resolve_config,
)


def code_of(call: object) -> str:
    assert callable(call)
    with pytest.raises(PipelineError) as info:
        call()
    assert info.value.category is ErrorCategory.CONFIGURATION
    return info.value.code


def test_a_missing_config_file_is_simply_empty(tmp_path: Path) -> None:
    assert load_config_file(tmp_path / "none.json") == {}


def test_a_config_file_is_read_and_validated(tmp_path: Path) -> None:
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"singers_dir": "D:/v", "singer": "abc"}), encoding="utf-8")
    assert load_config_file(path) == {"singers_dir": "D:/v", "singer": "abc"}


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("{not json", "CONFIG_INVALID"),
        ("[1]", "CONFIG_INVALID"),
        ('{"singer": 3}', "CONFIG_INVALID"),
        ('{"singer": " "}', "CONFIG_INVALID"),
        ('{"colour": "red"}', "CONFIG_UNKNOWN_KEY"),
    ],
)
def test_a_bad_config_file_is_a_configuration_error(tmp_path: Path, text: str, code: str) -> None:
    path = tmp_path / "c.json"
    path.write_text(text, encoding="utf-8")
    assert code_of(lambda: load_config_file(path)) == code


def test_the_config_file_location_can_be_chosen_by_environment(tmp_path: Path) -> None:
    assert config_path({"BLT_CONFIG": str(tmp_path / "x.json")}) == tmp_path / "x.json"
    assert config_path({}).name == "config.json"


def test_precedence_is_command_line_then_environment_then_file(tmp_path: Path) -> None:
    file = {"singers_dir": "from-file", "ffmpeg": "file-ffmpeg", "singer": "file-singer"}
    env = {"BLT_SINGERS_DIR": "from-env", "BLT_FFMPEG": "env-ffmpeg"}
    resolved = resolve_config(file, overrides={"singers_dir": "from-cli"}, environ=env)
    assert resolved.singers_dir == Path("from-cli")
    assert resolved.sources["singers_dir"] == "command line"
    assert resolved.ffmpeg == Path("env-ffmpeg")
    assert resolved.sources["ffmpeg"] == "environment BLT_FFMPEG"
    assert resolved.singer == "file-singer"
    assert resolved.sources["singer"] == "config file"


def test_defaults_are_only_where_they_cannot_change_the_music(tmp_path: Path) -> None:
    resolved = resolve_config({}, environ={"BLT_DATA_DIR": str(tmp_path / "d")})
    assert resolved.singer is None  # the voicebank is never chosen for the user
    assert resolved.phonemizer == DEFAULT_PHONEMIZER
    assert resolved.renderer == DEFAULT_RENDERER
    assert resolved.gain_profile == DEFAULT_PROFILE
    assert resolved.layout.data == tmp_path / "d"
    assert resolved.layout.singers != resolved.singers_dir or resolved.singers_dir is None


def test_dotnet_root_is_passed_to_the_host_environment(tmp_path: Path) -> None:
    resolved = resolve_config({}, overrides={"dotnet_root": str(tmp_path)}, environ={})
    assert resolved.host_environment() == {"DOTNET_ROOT": str(tmp_path)}
    assert resolve_config({}, environ={}).host_environment() == {}


def test_gain_profiles_by_preset_and_by_file(tmp_path: Path) -> None:
    named = resolve_config({"gain_profile": "strong-focus"}, environ={})
    assert named.gain_profile == PRESETS["strong-focus"]
    assert code_of(lambda: resolve_config({"gain_profile": "loud"}, environ={})) == (
        "GAIN_PROFILE_UNKNOWN"
    )
    file = tmp_path / "p.json"
    file.write_text(json.dumps({"name": "mine", "predominant_focus": 0.7}), encoding="utf-8")
    custom = resolve_config({}, environ={}, profile_file=file).gain_profile
    assert (custom.name, custom.predominant_focus) == ("mine", 0.7)
    file.write_text(json.dumps({"predominant_focus": 0.05}), encoding="utf-8")
    assert code_of(lambda: resolve_config({}, environ={}, profile_file=file)) == (
        "MIX_PREDOMINANT_ORDER"
    )
    file.write_text(json.dumps({"loudness": 3}), encoding="utf-8")
    assert code_of(lambda: resolve_config({}, environ={}, profile_file=file)) == "MIX_PROFILE_FILE"
    assert code_of(lambda: resolve_config({}, environ={}, profile_file=tmp_path / "no.json")) == (
        "GAIN_PROFILE_FILE"
    )


def test_singers_are_found_by_their_folders_not_by_guessing(tmp_path: Path) -> None:
    (tmp_path / "A" / "character.txt").parent.mkdir()
    (tmp_path / "A" / "character.txt").write_text("name=a", encoding="utf-8")
    (tmp_path / "pack" / "B").mkdir(parents=True)
    (tmp_path / "pack" / "B" / "oto.ini").write_text("", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "readme.txt").write_text("not a voicebank", encoding="utf-8")
    assert discover_singers(tmp_path) == {"A", "B"}
    assert discover_singers(tmp_path / "missing") == set()
