"""MP3 inspection and the FFmpeg-backed encoder, with a fake ffmpeg (no real FFmpeg needed)."""

import json
import sys
import threading
import time
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from barbershop_tracks.core.mixing import (
    AudioFormat,
    MixCancelledError,
    MixConfigurationError,
    MixEncodingError,
    PackageSettings,
    PackageSource,
    build_learning_tracks,
)
from barbershop_tracks.core.mixing.audio import wav_bytes
from barbershop_tracks.core.mixing.mp3 import FfmpegMp3Encoder, find_ffmpeg, inspect_mp3
from barbershop_tracks.core.rendering import CancelToken
from barbershop_tracks.core.runtime import RuntimeLayout
from barbershop_tracks.core.synthesis import SourceIdentity, TempoPoint

FAKE = Path(__file__).resolve().parents[3] / "fake_ffmpeg.py"
HEADER = b"\xff\xfb\x90\xc0"  # MPEG-1 Layer III, 128 kbit/s, 44.1 kHz, mono, no padding
FRAME = HEADER + b"\x00" * 413
INFO = HEADER + b"\x00" * 17 + b"Info" + b"\x00" * 392


def encoder(
    mode: str = "ok", monkeypatch: pytest.MonkeyPatch | None = None, **kw: object
) -> FfmpegMp3Encoder:
    if monkeypatch is not None:
        monkeypatch.setenv("FAKE_FFMPEG_MODE", mode)
    return FfmpegMp3Encoder([sys.executable, FAKE], **kw)  # type: ignore[arg-type]


def wav_file(tmp_path: Path, frames: int = 44100) -> Path:
    path = tmp_path / "in.wav"
    path.write_bytes(wav_bytes(np.zeros(frames, dtype=np.int16)))
    return path


# --- inspecting an MP3 ---


def test_a_clean_stream_is_counted_without_its_info_frame(tmp_path: Path) -> None:
    path = tmp_path / "a.mp3"
    path.write_bytes(INFO + FRAME * 5)
    info = inspect_mp3(path)
    assert info.audio_frames == 5
    assert info.average_kbps == 128


def test_id3_tags_around_the_audio_are_skipped(tmp_path: Path) -> None:
    id3v2 = b"ID3\x03\x00\x00\x00\x00\x00\x0a" + b"x" * 10
    id3v1 = b"TAG" + b"\x00" * 125
    path = tmp_path / "a.mp3"
    path.write_bytes(id3v2 + FRAME * 3 + id3v1)
    assert inspect_mp3(path).audio_frames == 3


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not an mp3 at all",
        FRAME * 3 + b"\x00\x00",  # junk after the last frame
        FRAME * 2 + FRAME[:-10],  # the last frame is cut off
        FRAME + b"\x00" * 417 + FRAME,  # sync lost in the middle
        INFO,  # a header and no audio
        b"\xff\xf3\x90\xc0" + b"\x00" * 413,  # MPEG-2
        b"\xff\xfb\x90\x00" + b"\x00" * 413,  # stereo
        b"\xff\xfb\x94\xc0" + b"\x00" * 413,  # 48 kHz
    ],
    ids=["empty", "text", "junk-tail", "cut", "sync-lost", "no-audio", "mpeg2", "stereo", "48k"],
)
def test_anything_else_is_refused(tmp_path: Path, data: bytes) -> None:
    path = tmp_path / "a.mp3"
    path.write_bytes(data)
    with pytest.raises(MixEncodingError) as error:
        inspect_mp3(path)
    assert error.value.code in {"MIX_MP3_INVALID"}


def test_an_unreadable_file_is_a_typed_error(tmp_path: Path) -> None:
    with pytest.raises(MixEncodingError) as error:
        inspect_mp3(tmp_path / "nope.mp3")
    assert error.value.code == "MIX_MP3_UNREADABLE"


# --- configuring FFmpeg ---


def test_the_settings_are_recorded_without_any_path(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = encoder("ok", monkeypatch).settings()
    assert settings["encoder"] == "libmp3lame"
    assert settings["quality"] == 2
    assert settings["ffmpeg"] == "ffmpeg version fake-1.0 Copyright (c) the tests"
    assert str(FAKE) not in json.dumps(settings)
    assert "sample-exact" in settings["timing"]


@pytest.mark.parametrize(
    ("mode", "code"),
    [("version_fail", "MIX_FFMPEG_UNUSABLE"), ("no_lame", "MIX_FFMPEG_NO_MP3")],
)
def test_an_unusable_ffmpeg_is_a_configuration_error(
    monkeypatch: pytest.MonkeyPatch, mode: str, code: str
) -> None:
    with pytest.raises(MixConfigurationError) as error:
        encoder(mode, monkeypatch)
    assert error.value.code == code


def test_a_missing_executable_is_a_configuration_error(tmp_path: Path) -> None:
    with pytest.raises(MixConfigurationError) as error:
        FfmpegMp3Encoder([tmp_path / "ffmpeg-not-here.exe"])
    assert error.value.code == "MIX_FFMPEG_UNUSABLE"


def test_the_quality_is_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_FFMPEG_MODE", "ok")
    with pytest.raises(MixConfigurationError):
        encoder(quality=10)
    assert encoder(quality=0).settings()["quality"] == 0


def test_ffmpeg_is_found_from_configuration_the_environment_or_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exe = tmp_path / "ffmpeg.exe"
    exe.write_bytes(b"x")
    monkeypatch.delenv("BLT_FFMPEG", raising=False)
    assert find_ffmpeg(exe) == exe
    assert find_ffmpeg(tmp_path / "missing.exe") is None  # an explicit choice is not second-guessed
    monkeypatch.setenv("BLT_FFMPEG", str(exe))
    assert find_ffmpeg() == exe
    monkeypatch.delenv("BLT_FFMPEG")
    monkeypatch.setenv("PATH", str(tmp_path))
    assert find_ffmpeg() == exe or find_ffmpeg() is None  # PATH lookup depends on PATHEXT


# --- encoding ---


def test_a_successful_encode_is_validated_and_described(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "out.mp3"
    info = encoder("ok", monkeypatch).encode(
        wav_file(tmp_path), out, expected_frames=44100, cancel=CancelToken()
    )
    assert out.stat().st_size > 0
    assert info["average_kbps"] == 128
    assert abs(info["mp3_audio_frames"] * 1152 - 44100) <= 3 * 1152
    assert abs(info["decoded_minus_wav_samples"]) <= 3 * 1152


@pytest.mark.parametrize(
    ("mode", "code"),
    [
        ("fail", "MIX_MP3_FAILED"),
        ("garbage", "MIX_MP3_INVALID"),
        ("truncated", "MIX_MP3_INVALID"),
        ("empty", "MIX_MP3_EMPTY"),
        ("short", "MIX_MP3_LENGTH"),
        ("decode_fail", "MIX_MP3_DECODE"),
        ("noisy_decode", "MIX_MP3_DECODE"),
    ],
)
def test_encoder_failures_and_bad_output_are_typed_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, code: str
) -> None:
    out = tmp_path / "out.mp3"
    good = encoder("ok", monkeypatch)
    monkeypatch.setenv("FAKE_FFMPEG_MODE", mode)
    with pytest.raises(MixEncodingError) as error:
        good.encode(wav_file(tmp_path), out, expected_frames=44100, cancel=CancelToken())
    assert error.value.code == code


def test_a_hung_encoder_times_out_and_leaves_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slow = encoder("ok", monkeypatch, timeout_seconds=0.5)
    monkeypatch.setenv("FAKE_FFMPEG_MODE", "hang")
    with pytest.raises(MixEncodingError) as error:
        slow.encode(
            wav_file(tmp_path), tmp_path / "out.mp3", expected_frames=44100, cancel=CancelToken()
        )
    assert error.value.code == "MIX_MP3_TIMEOUT"
    assert not (tmp_path / "out.mp3").exists()


def test_cancelling_a_running_encode_ends_ffmpeg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    patient = encoder("ok", monkeypatch)
    monkeypatch.setenv("FAKE_FFMPEG_MODE", "hang")
    token = CancelToken()
    outcome: list[BaseException] = []

    def work() -> None:
        try:
            patient.encode(
                wav_file(tmp_path), tmp_path / "out.mp3", expected_frames=44100, cancel=token
            )
        except BaseException as error:
            outcome.append(error)

    thread = threading.Thread(target=work)
    thread.start()
    time.sleep(0.5)
    token.cancel()
    thread.join(timeout=20)
    assert not thread.is_alive()
    assert isinstance(outcome[0], MixCancelledError)


# --- through the package ---

SOURCE = PackageSource(
    SourceIdentity(display_name="demo.musicxml", sha256="cd" * 32, title="Demo"),
    (TempoPoint(position=Fraction(0), bpm=Fraction(100)),),
    Fraction(4),
)


def package_rig(tmp_path: Path) -> tuple[PackageSettings, dict]:  # type: ignore[type-arg]
    from barbershop_tracks.core.synthesis import VOICE_ORDER

    stems = {}
    for role in VOICE_ORDER:
        path = tmp_path / "stems" / f"{role.value}.wav"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(wav_bytes(np.full(50000, 3000, dtype=np.int16)))
        stems[role] = path
    layout = RuntimeLayout.under(tmp_path / "bin", tmp_path / "data")
    return PackageSettings(layout=layout), stems


def test_wav_and_mp3_publish_together_with_a_consistent_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings, stems = package_rig(tmp_path)
    settings = PackageSettings(
        layout=settings.layout,
        formats=frozenset({AudioFormat.WAV, AudioFormat.MP3}),
        mp3=encoder("ok", monkeypatch),
    )
    result = build_learning_tracks(SOURCE, stems, tmp_path / "out", settings)
    names = sorted(p.name for p in (tmp_path / "out").iterdir())
    assert "01_Full_Quartet.wav" in names
    assert "01_Full_Quartet.mp3" in names
    assert len(names) == 27
    track = result.manifest["tracks"][0]
    assert [f["format"] for f in track["files"]] == ["wav", "mp3"]
    assert track["files"][1]["average_kbps"] == 128
    assert result.manifest["settings"]["mp3"]["quality"] == 2
    assert "sample-exact" in result.manifest["settings"]["mp3"]["timing"]


def test_a_bad_mp3_on_the_ninth_track_publishes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings, stems = package_rig(tmp_path)
    good = encoder("ok", monkeypatch)
    settings = PackageSettings(
        layout=settings.layout, formats=frozenset({AudioFormat.MP3}), mp3=good
    )
    calls = {"n": 0}
    real = good.encode

    def flaky(wav: Path, mp3: Path, **kw: object) -> dict:  # type: ignore[type-arg]
        calls["n"] += 1
        if calls["n"] == 9:
            monkeypatch.setenv("FAKE_FFMPEG_MODE", "garbage")
        return real(wav, mp3, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(good, "encode", flaky)
    with pytest.raises(MixEncodingError):
        build_learning_tracks(SOURCE, stems, tmp_path / "out", settings)
    assert not (tmp_path / "out").exists()
    assert not any((tmp_path / "data" / "staging").iterdir())
