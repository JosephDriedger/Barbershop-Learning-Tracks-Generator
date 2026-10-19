"""MusicXML to the 13-track package through the real CLI, real render host, generated voicebank.

No user voicebank and no redistributed voicebank is involved: the singer is a few sine waves
generated into a temporary folder. These tests run wherever the host has been built, CI included.
"""

import array
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest
import yaml

from barbershop_tracks.cli import main
from barbershop_tracks.core.rendering.wav import read_raw
from barbershop_tracks.core.singer_names import SINGER_SEPARATOR as SEP
from cli_scores import LINES, quartet_xml
from host_support import host_environment, host_processes, require_host
from shims import write_shim
from synthetic_voicebank import SINGER_ID, build_voicebank

pytestmark = pytest.mark.integration

FAKE_FFMPEG = Path(__file__).resolve().parents[1] / "fake_ffmpeg.py"


class Rig:
    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.root = root
        self.out = root / "out"
        self.singers = root / "singers"
        build_voicebank(self.singers)
        self.score = root / "song.musicxml"
        self.write_score()
        host = require_host()
        monkeypatch.setenv("BLT_CONFIG", str(root / "no-config.json"))
        monkeypatch.setenv("BLT_DATA_DIR", str(root / "data"))
        monkeypatch.setenv("BLT_HOST_DIR", str(host))
        for key, value in host_environment().items():
            if key == "DOTNET_ROOT":
                monkeypatch.setenv(key, value)

    def write_score(self, **options: Any) -> None:
        options.setdefault("all_lyrics", True)
        options.setdefault("word", "la")
        self.score.write_text(quartet_xml(**options), encoding="utf-8")

    def args(self, *extra: str, assign: dict[str, str] | None = None) -> list[str]:
        mapping = assign or {r: LINES[r] for r in ("tenor", "lead", "baritone", "bass")}
        out = [
            "generate",
            str(self.score),
            "--out",
            str(self.out),
            "--singers-dir",
            str(self.singers),
            "--singer",
            SINGER_ID,
        ]
        for role, line in mapping.items():
            out += ["--assign", f"{role.upper()}={line}"]
        return [*out, *extra]

    @property
    def package(self) -> Path:
        return self.out / "song_learning_tracks"

    def staging(self) -> list[str]:
        root = self.root / "data" / "staging"
        return sorted(p.name for p in root.iterdir()) if root.is_dir() else []

    def hosts(self) -> int:
        return host_processes(self.root)


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Rig:
    return Rig(tmp_path, monkeypatch)


def events_of(capsys: pytest.CaptureFixture[str]) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")
    ]


# --- success ---


def test_musicxml_to_the_thirteen_track_package(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(rig.args("--progress", "json")) == 0
    events = events_of(capsys)

    names = sorted(p.name for p in rig.package.iterdir())
    assert len([n for n in names if n.endswith(".wav")]) == 13
    assert len(names) == 14  # the 13 tracks and the manifest: no stems, no project, no temp files
    manifest = json.loads((rig.package / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source"]["sha256"] == hashlib.sha256(rig.score.read_bytes()).hexdigest()
    assert manifest["source"]["display_name"] == "song.musicxml"
    frames = manifest["audio"]["frames"]
    assert frames == 8 * 60 * 44100 // 100 + (0 if (8 * 60 * 44100) % 100 == 0 else 1)
    for wav in rig.package.glob("*.wav"):
        info, _ = read_raw(wav)
        assert info.frames == frames

    stages = [e["stage"] for e in events if e["event"] == "stage" and e["status"] == "started"]
    assert stages == [
        "source_loading",
        "score_analysis",
        "readiness_validation",
        "ustx_preparation",
        "voicebank_discovery",
        "stem_rendering",
        "stem_validation",
        "mixing",
        "package_publication",
    ]
    assert events[-1]["event"] == "result"
    assert events[-1]["tracks"] == 13
    assert sum(1 for e in events if e["event"] == "progress") == 13
    assert any(e["event"] == "host" for e in events)
    assert rig.staging() == []


@pytest.mark.parametrize(
    "folder",
    [f"pack{SEP}bank", "My Voice Bank (v2)", "テスト ボイス é"],
    ids=["inside-a-pack-folder", "spaces-and-brackets", "non-ascii"],
)
def test_voicebanks_are_found_wherever_and_however_they_are_named(rig: Rig, folder: str) -> None:
    target = rig.singers / folder
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(rig.singers / SINGER_ID), str(target))
    args = rig.args()
    args[args.index(SINGER_ID)] = folder
    assert main(args) == 0
    assert len(list(rig.package.glob("*.wav"))) == 13


def test_the_voice_mapping_decides_which_line_is_which_voice(rig: Rig) -> None:
    swapped = {
        "tenor": LINES["bass"],
        "lead": LINES["lead"],
        "baritone": LINES["baritone"],
        "bass": LINES["tenor"],
    }
    assert main(rig.args("--keep-project", assign=swapped)) == 0
    project = yaml.safe_load((rig.package / "project" / "project.ustx").read_text(encoding="utf-8"))
    tones = {
        project["tracks"][part["track_no"]]["track_name"]: part["notes"][0]["tone"]
        for part in project["voice_parts"]
    }
    # the score's bass line (C3 = 48) is sung as Tenor and its tenor line (E4 = 64) as Bass
    assert tones == {"Tenor": 48, "Lead": 60, "Baritone": 55, "Bass": 64}


def test_stems_and_project_are_published_only_on_request(rig: Rig) -> None:
    assert main(rig.args("--keep-stems", "--keep-project")) == 0
    manifest = json.loads((rig.package / "manifest.json").read_text(encoding="utf-8"))
    assert sorted(e["name"] for e in manifest["extras"]) == [
        "project/project.ustx",
        "stems/Baritone.wav",
        "stems/Bass.wav",
        "stems/Lead.wav",
        "stems/Tenor.wav",
    ]
    assert (rig.package / "stems" / "Tenor.wav").is_file()


def wipe_render_cache(rig: Rig) -> None:
    for cache in (rig.root / "data" / "runtime").glob("host-*/Cache"):
        shutil.rmtree(cache)


def pcm(path: Path) -> "array.array[int]":
    samples: array.array[int] = array.array("h")
    samples.frombytes(path.read_bytes()[44:])
    return samples


def test_repeated_generation_is_deterministic_for_the_same_cache_state(rig: Rig) -> None:
    assert main(rig.args()) == 0  # cold: the render cache is empty
    cold = {p.name: p.read_bytes() for p in rig.package.iterdir()}
    wipe_render_cache(rig)
    other = rig.root / "again"
    args = rig.args()
    args[args.index("--out") + 1] = str(other)
    assert main(args) == 0
    again = {p.name: p.read_bytes() for p in (other / "song_learning_tracks").iterdir()}
    assert cold == again  # the same WAV bytes and the same manifest

    third = rig.root / "warm"  # the cache is now warm: OpenUtau's cache holds 16-bit audio
    args[args.index("--out") + 1] = str(third)
    assert main(args) == 0
    warm = third / "song_learning_tracks"
    for path in warm.glob("*.wav"):
        worst = max(
            abs(a - b)
            for a, b in zip(pcm(path), pcm(other / "song_learning_tracks" / path.name), strict=True)
        )
        assert worst <= 2  # a 1 LSB stem difference through gains of at most 0.5 and rounding


def test_replacement_and_rollback(rig: Rig, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(rig.args()) == 0
    before = {p.name: p.read_bytes() for p in rig.package.iterdir()}
    assert main(rig.args()) == 2  # exists, not asked to replace
    assert "OUTPUT_EXISTS" in capsys.readouterr().err
    assert main(rig.args("--replace")) == 0
    after = {p.name: p.read_bytes() for p in rig.package.iterdir()}
    assert set(after) == set(before)  # a warm render may differ from the cold one by 1 LSB
    before = after

    rig.write_score(word="zzz")  # a lyric the voicebank cannot sing: silent stems
    assert main(rig.args("--replace")) == 4
    err = capsys.readouterr().err
    assert "STEM_" in err
    assert {p.name: p.read_bytes() for p in rig.package.iterdir()} == before
    assert rig.staging() == []


# --- problems are reported by category ---


def test_a_missing_tempo_or_meter_is_a_source_error(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    rig.write_score(tempo=False)
    assert main(rig.args()) == 1
    assert "TEMPO" in capsys.readouterr().err
    rig.score.write_text(
        re.sub(r"<time>.*?</time>", "", quartet_xml(all_lyrics=True, word="la"), flags=re.S),
        encoding="utf-8",
    )
    assert main(rig.args()) == 1
    assert "TIME_SIGNATURE_MISSING" in capsys.readouterr().err
    assert not rig.out.exists()


def test_missing_harmony_lyrics_need_review_and_nothing_is_rendered(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    rig.write_score(all_lyrics=False, lyric_part=1)
    assert main(rig.args()) == 6
    assert "LYRICS_NEED_REVIEW" in capsys.readouterr().err
    assert not rig.package.exists()
    assert not (rig.root / "data" / "runtime").exists()  # the host was never even installed


def test_approved_lyrics_complete_the_run(rig: Rig) -> None:
    rig.write_score(all_lyrics=False, lyric_part=1)
    assert main(rig.args()) == 6
    template = rig.out / "song_learning_tracks.lyric-review.approvals-template.json"
    document = json.loads(template.read_text(encoding="utf-8"))
    for entry in document["approvals"]:
        entry["text"], entry["approved_by"] = "ba", "tester"
    filled = rig.root / "approved.json"
    filled.write_text(json.dumps(document), encoding="utf-8")
    assert main(rig.args("--approve-lyrics", str(filled), "--keep-project")) == 0
    project = yaml.safe_load((rig.package / "project" / "project.ustx").read_text(encoding="utf-8"))
    lyrics = {
        project["tracks"][p["track_no"]]["track_name"]: p["notes"][0]["lyric"]
        for p in project["voice_parts"]
    }
    assert lyrics == {"Tenor": "ba", "Lead": "la", "Baritone": "ba", "Bass": "ba"}


def test_invalid_singer_and_phonemizer_configuration(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    ghost = rig.args()
    ghost[ghost.index("--singer") + 1] = "ghost"
    assert main(ghost) == 2
    assert "SINGER_NOT_FOUND" in capsys.readouterr().err
    assert main(rig.args("--phonemizer", "Not.A.Real.Phonemizer")) == 2
    err = capsys.readouterr().err
    assert "HOST_UNRESOLVED" in err
    assert "did not resolve" in err
    assert not rig.package.exists()
    assert rig.staging() == []


def test_a_timeout_exits_5_and_leaves_nothing(rig: Rig, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(rig.args("--timeout", "0.3")) == 5
    assert "RENDER_TIMEOUT" in capsys.readouterr().err
    assert not rig.package.exists()
    assert rig.staging() == []
    deadline = time.monotonic() + 15
    while rig.hosts() and time.monotonic() < deadline:
        time.sleep(0.2)
    assert rig.hosts() == 0


# --- MP3 through a fake FFmpeg (the real one is tested in CI below) ---


def fake_ffmpeg(root: Path) -> Path:
    return write_shim(root, "ffmpeg", FAKE_FFMPEG)


def test_an_mp3_failure_publishes_nothing_and_exits_4(
    rig: Rig, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_FFMPEG_MODE", "fail")
    code = main(rig.args("--audio-format", "both", "--ffmpeg", str(fake_ffmpeg(rig.root))))
    # the fake answers -version, so the encoder is accepted and the first encode fails
    assert code == 4
    assert "MIX_MP3_FAILED" in capsys.readouterr().err
    assert not rig.package.exists()
    assert rig.staging() == []


def test_real_ffmpeg_produces_the_mp3_copies(rig: Rig) -> None:
    from barbershop_tracks.core.mixing import find_ffmpeg

    if find_ffmpeg() is None:
        pytest.skip("no FFmpeg (set BLT_FFMPEG or put ffmpeg on PATH)")
    assert main(rig.args("--audio-format", "both")) == 0
    names = [p.name for p in rig.package.iterdir()]
    assert len([n for n in names if n.endswith(".mp3")]) == 13
    assert len([n for n in names if n.endswith(".wav")]) == 13


# --- concurrency ---


def test_concurrent_jobs_do_not_collide(rig: Rig) -> None:
    codes: dict[int, int] = {}

    def work(index: int) -> None:
        args = rig.args("--name", f"song{index}")
        codes[index] = main(args)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=300)
    assert codes == {0: 0, 1: 0, 2: 0}
    packages = sorted(p.name for p in rig.out.iterdir())
    assert packages == [f"song{i}_learning_tracks" for i in range(3)]
    reference = {p.name: p.read_bytes() for p in (rig.out / "song0_learning_tracks").iterdir()}
    for index in (1, 2):
        got = {p.name: p.read_bytes() for p in (rig.out / f"song{index}_learning_tracks").iterdir()}
        assert set(got) == set(reference)
        for name in (n for n in got if n.endswith(".wav")):  # cold vs warm: at most rounding noise
            a, b = (
                pcm(rig.out / f"song{index}_learning_tracks" / name),
                pcm(rig.out / "song0_learning_tracks" / name),
            )
            assert max(abs(x - y) for x, y in zip(a, b, strict=True)) <= 2
    assert rig.staging() == []


# --- Ctrl+Break (Windows) or Ctrl+C (elsewhere) reaches the host ---


def test_ctrl_break_cancels_cleanly(rig: Rig) -> None:
    code = "import sys; from barbershop_tracks.cli import main; sys.exit(main(sys.argv[1:]))"
    child = subprocess.Popen(
        [sys.executable, "-c", code, *rig.args("--progress", "json")],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=os.environ.copy(),
        **(
            {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
            if os.name == "nt"
            else {"start_new_session": True}
        ),
    )
    assert child.stdout is not None
    seen: list[dict[str, Any]] = []
    deadline = time.monotonic() + 120
    for line in child.stdout:
        event = json.loads(line)
        seen.append(event)
        if event.get("event") == "host" and event.get("name") == "init":
            break  # the host is up and rendering
        assert time.monotonic() < deadline
    try:
        child.send_signal(getattr(signal, "CTRL_BREAK_EVENT", signal.SIGINT))
    except OSError:  # no console to deliver Ctrl+Break through (some CI sessions)
        child.kill()
        child.communicate(timeout=60)
        pytest.skip("no console available for Ctrl+Break")
    remaining, err = child.communicate(timeout=60)
    assert child.returncode == 130, err
    assert "cancelling" in err
    tail = [json.loads(line) for line in remaining.splitlines() if line.startswith("{")]
    assert tail[-1]["event"] == "error"
    assert tail[-1]["category"] == "cancelled"
    assert not rig.package.exists()
    assert rig.staging() == []
    deadline = time.monotonic() + 15
    while rig.hosts() and time.monotonic() < deadline:
        time.sleep(0.2)
    assert rig.hosts() == 0
    assert seen[0]["event"] == "stage"


def test_parts_sing_the_leads_words_by_default_and_the_run_completes(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BLT_FOLLOW_LEAD", "1")
    rig.write_score(all_lyrics=False, lyric_part=1, word="ba")
    assert main(rig.args("--keep-project")) == 0
    assert len(list(rig.package.glob("*.wav"))) == 13
    project = yaml.safe_load((rig.package / "project" / "project.ustx").read_text(encoding="utf-8"))
    for part in project["voice_parts"]:
        assert {n["lyric"] for n in part["notes"]} == {"ba"}
    # the switch turns it off again: the same score then needs review
    assert main(rig.args("--replace", "--no-follow-lead")) == 6
