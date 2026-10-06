import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _load_script() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts" / "check_no_audio_in_repo.py"
    spec = importlib.util.spec_from_file_location("check_no_audio_in_repo", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_flags_audio_projects_and_ffmpeg() -> None:
    script = _load_script()
    paths = [
        "src/app.py",
        "out/Tenor.WAV",
        "a/b/Full Quartet.mp3",
        "song.ustx",
        "bin/ffmpeg.exe",
        "examples/song.musicxml",
    ]
    assert script.find_forbidden(paths) == [
        "out/Tenor.WAV",
        "a/b/Full Quartet.mp3",
        "song.ustx",
        "bin/ffmpeg.exe",
    ]


def test_clean_list_passes() -> None:
    script = _load_script()
    assert script.find_forbidden(["README.md", "src/x.py"]) == []
