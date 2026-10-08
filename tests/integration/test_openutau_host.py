"""Opt-in: a generated USTX through the pinned M7a render host (needs a real singer).

Skipped unless all of these exist (nothing here ships or installs anything):

* ``BLT_M7A_HOST``: the built ``blt-spike-renderhost.exe`` (see ``spikes/m7a/README.md``); the
  default is the git-ignored ``research-output/spike/host-build`` output when present.
* ``DOTNET_ROOT``: the .NET runtime the host needs (default: ``research-output/spike/dotnet``).
* ``BLT_TEST_SINGER``: the id of a user-installed singer the host can see.
"""

import array
import json
import math
import os
import struct
import subprocess
from pathlib import Path

import pytest

from barbershop_tracks.core.synthesis import VoiceEngineRef
from barbershop_tracks.core.synthesis.openutau import write_ustx
from barbershop_tracks.models import Melisma, Note, Pitch, Step
from readiness_builders import note
from synth_builders import ROLES, full_lyrics, plan_of, refs, text

pytestmark = pytest.mark.integration

_REPO = Path(__file__).resolve().parents[2]
_SPIKE = _REPO / "research-output" / "spike"


def _host() -> Path | None:
    configured = os.environ.get("BLT_M7A_HOST")
    candidate = (
        Path(configured) if configured else _SPIKE / "host-build" / "blt-spike-renderhost.exe"
    )
    return candidate if candidate.is_file() else None


def _dotnet_root() -> Path | None:
    configured = os.environ.get("DOTNET_ROOT")
    candidate = Path(configured) if configured else _SPIKE / "dotnet"
    return candidate if candidate.is_dir() else None


@pytest.fixture
def host() -> tuple[Path, Path, str]:
    exe, dotnet, singer = _host(), _dotnet_root(), os.environ.get("BLT_TEST_SINGER")
    if exe is None or dotnet is None or not singer:
        pytest.skip("needs BLT_M7A_HOST, DOTNET_ROOT and BLT_TEST_SINGER (see module docstring)")
    return exe, dotnet, singer


def _run(
    exe: Path, dotnet: Path, project: Path, out: Path
) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    environment = {**os.environ, "DOTNET_ROOT": str(dotnet)}
    done = subprocess.run(
        [str(exe), "--project", str(project), "--out", str(out), "--base", "case"],
        capture_output=True,
        text=True,
        env=environment,
        timeout=300,
        check=False,
    )
    report: dict[str, object] = json.loads(done.stdout.lstrip("﻿")) if done.stdout else {}
    return done, report


def _wav_frames(path: Path) -> tuple[int, int, bool]:
    """(frames, sample rate, any non-zero byte in the data chunk) from a RIFF/WAVE file."""
    data = path.read_bytes()
    assert data[:4] == b"RIFF"
    assert data[8:12] == b"WAVE"
    position, channels, rate, bits = 12, 0, 0, 0
    while position + 8 <= len(data):
        tag, size = data[position : position + 4], struct.unpack_from("<I", data, position + 4)[0]
        body = data[position + 8 : position + 8 + size]
        if tag == b"fmt ":
            _, channels, rate, _, _, bits = struct.unpack_from("<HHIIHH", body)
        elif tag == b"data":
            return size // (channels * bits // 8), rate, any(body)
        position += 8 + size + (size & 1)
    raise AssertionError("no data chunk")


def test_generated_ustx_renders_four_stems(host: tuple[Path, Path, str], tmp_path: Path) -> None:
    exe, dotnet, singer = host
    base = VoiceEngineRef(
        singer=singer, phonemizer="OpenUtau.Core.DefaultPhonemizer", renderer="WORLDLINE-R"
    )
    plan = plan_of(
        voices=full_lyrics(("la", "la", "la", "la")),
        engine_refs=dict.fromkeys(ROLES, base),
    )
    project = tmp_path / "case.ustx"
    project.write_bytes(write_ustx(plan).encode())
    out = tmp_path / "out"
    out.mkdir()

    done, report = _run(exe, dotnet, project, out)

    assert done.returncode == 0, done.stderr
    stems = sorted(out.glob("*.wav"))
    assert len(stems) == 4, report
    last_end = max(n.start + n.duration for v in plan.voices for n in v.notes)
    expected_seconds = float(last_end) * 60 / 100  # 100 BPM in the builders
    for stem in stems:
        frames, rate, audible = _wav_frames(stem)
        assert audible, f"{stem.name} is silent"
        # stems end at the last note end (padding is the mixer's job, M9)
        assert expected_seconds - 0.2 <= frames / rate <= expected_seconds + 1.0, stem.name


def test_unknown_singer_is_rejected_by_the_host(
    host: tuple[Path, Path, str], tmp_path: Path
) -> None:
    exe, dotnet, _ = host
    plan = plan_of(engine_refs=refs())  # "test-singer" is not installed anywhere
    project = tmp_path / "case.ustx"
    project.write_bytes(write_ustx(plan).encode())
    out = tmp_path / "out"
    out.mkdir()

    done, _ = _run(exe, dotnet, project, out)

    assert done.returncode == 4
    assert list(out.glob("*.wav")) == []


# --- the "+" continuation experiment (M7b review item 3) ---
#
# Rendered with a user-installed singer and the default phonemizer. This establishes only that a
# "+" note continues the previous note's sound (no new onset, pitch follows the new note). It says
# nothing about phonetic correctness of any lyric: "la" is just a short alias the singer has.

_E4, _G4 = Pitch(Step.E, 4), Pitch(Step.G, 4)
_BOUNDARY_SECONDS = 1.2  # two quarters at the builders' 100 BPM


def _samples(path: Path) -> tuple[array.array[float], int]:
    data = path.read_bytes()
    position, fmt = 12, (0, 0, 0, 0, 0, 0)
    while position + 8 <= len(data):
        tag, size = data[position : position + 4], struct.unpack_from("<I", data, position + 4)[0]
        body = data[position + 8 : position + 8 + size]
        if tag == b"fmt ":
            fmt = struct.unpack_from("<HHIIHH", body)
        elif tag == b"data":
            kind, channels, rate, _, _, bits = fmt
            out: array.array[float] = array.array("f")
            if kind == 3 or bits == 32:
                out.frombytes(body[: len(body) // 4 * 4])
            else:
                shorts = array.array("h")
                shorts.frombytes(body[: len(body) // 2 * 2])
                out = array.array("f", (x / 32768 for x in shorts))
            return out[::channels], rate
        position += 8 + size + (size & 1)
    raise AssertionError("no data chunk")


def _envelope(samples: array.array[float], rate: int, window: float = 0.01) -> list[float]:
    n = int(rate * window)
    return [
        math.sqrt(sum(x * x for x in samples[i : i + n]) / n) for i in range(0, len(samples) - n, n)
    ]


def _pitch_hz(samples: array.array[float], rate: int, centre: float) -> float:
    segment = samples[int((centre - 0.02) * rate) : int((centre + 0.02) * rate)]
    best, best_lag = 0.0, 0
    for lag in range(int(rate / 500), int(rate / 80)):
        score = sum(segment[i] * segment[i + lag] for i in range(len(segment) - lag))
        if score > best:
            best, best_lag = score, lag
    return rate / best_lag if best_lag else 0.0


def _render_tenor(
    host: tuple[Path, Path, str], tmp_path: Path, name: str, tenor: list[Note]
) -> tuple[array.array[float], int]:
    exe, dotnet, singer = host
    engine = VoiceEngineRef(
        singer=singer, phonemizer="OpenUtau.Core.DefaultPhonemizer", renderer="WORLDLINE-R"
    )
    plan = plan_of(
        voices={**full_lyrics(("la", "la", "la", "la")), "tenor": tenor},
        engine_refs=dict.fromkeys(ROLES, engine),
    )
    project = tmp_path / f"{name}.ustx"
    project.write_bytes(write_ustx(plan).encode())
    out = tmp_path / name
    out.mkdir()
    done, _ = _run(exe, dotnet, project, out)
    assert done.returncode == 0, done.stderr
    return _samples(out / "case_Tenor.wav")


def test_plus_continues_the_syllable_where_a_repeated_lyric_restarts_it(
    host: tuple[Path, Path, str], tmp_path: Path
) -> None:
    la = text("la")
    extended = [
        note(0, 2, _E4, lyrics=text("la", melisma=Melisma.UNTYPED)),
        note(2, 2, _G4),  # the score's continuation: written as "+"
    ]
    restarted = [note(0, 2, _E4, lyrics=la), note(2, 2, _G4, lyrics=la)]
    boundary = int(_BOUNDARY_SECONDS / 0.01)

    plus_samples, rate = _render_tenor(host, tmp_path, "plus", extended)
    again_samples, _ = _render_tenor(host, tmp_path, "again", restarted)
    plus_env, again_env = _envelope(plus_samples, rate), _envelope(again_samples, rate)

    def dip(env: list[float]) -> float:  # quietest 10 ms near the boundary, relative to the peak
        return min(env[boundary - 8 : boundary + 9]) / max(env)

    assert dip(again_env) < 0.4  # a repeated lyric starts a new syllable: the sound drops
    assert dip(plus_env) > 0.5  # "+" does not: the same sound carries across the boundary
    # observed on the development machine: 0.15 versus 0.75
    # ...and the sustained sound follows the new note's pitch (E4 = 330 Hz, G4 = 392 Hz)
    before = _pitch_hz(plus_samples, rate, _BOUNDARY_SECONDS - 0.3)
    after = _pitch_hz(plus_samples, rate, _BOUNDARY_SECONDS + 0.3)
    assert abs(before - 329.6) / 329.6 < 0.05
    assert abs(after - 392.0) / 392.0 < 0.05
