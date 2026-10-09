"""Opt-in: the backend with a real, user-installed voicebank (nothing here ships or installs one).

Needs the production render host (see ``tests/host_support.py``) and:

* ``BLT_TEST_SINGER``: the id of an installed singer, e.g. ``alys-db-002-fra``;
* ``BLT_TEST_SINGERS_DIR``: the directory that contains it (OpenUtau's ``Singers`` folder).

"la" is used as a short alias such a singer is likely to have. Passing proves the pipeline renders,
validates and publishes real output; it says nothing about pronunciation or lyric accuracy.
"""

import math
import os
from pathlib import Path

import pytest

from barbershop_tracks.core.rendering import (
    OpenUtauRenderBackend,
    RenderConfigurationError,
    RenderResult,
    RenderSettings,
)
from barbershop_tracks.core.rendering.wav import read_wav
from barbershop_tracks.core.runtime import RuntimeLayout
from barbershop_tracks.core.synthesis import SynthesisPlan, VoiceEngineRef
from barbershop_tracks.models import Melisma, Pitch, Step, VoiceRole
from host_support import host_environment, require_host
from readiness_builders import note
from synth_builders import ROLES, full_lyrics, plan_of, text

pytestmark = pytest.mark.integration

PHONEMIZER = "OpenUtau.Core.DefaultPhonemizer"
E4, G4 = Pitch(Step.E, 4), Pitch(Step.G, 4)
BOUNDARY = 1.2  # two quarters at the builders' 100 BPM


@pytest.fixture
def setup(tmp_path: Path) -> tuple[OpenUtauRenderBackend, str]:
    singer, singers_dir = os.environ.get("BLT_TEST_SINGER"), os.environ.get("BLT_TEST_SINGERS_DIR")
    if not singer or not singers_dir or not Path(singers_dir).is_dir():
        pytest.skip("needs BLT_TEST_SINGER and BLT_TEST_SINGERS_DIR (see module docstring)")
    settings = RenderSettings(
        layout=RuntimeLayout.under(tmp_path / "bin", tmp_path / "data"),
        singers_dir=Path(singers_dir),
        host_binaries=require_host(),
        extra_env={k: v for k, v in host_environment().items() if k == "DOTNET_ROOT"},
    )
    return OpenUtauRenderBackend(settings), singer


def plan_with(singer: str, tenor: list | None = None) -> SynthesisPlan:  # type: ignore[type-arg]
    engine = VoiceEngineRef(singer=singer, phonemizer=PHONEMIZER, renderer="WORLDLINE-R")
    voices = full_lyrics(("la",) * 4)
    if tenor is not None:
        voices["tenor"] = tenor
    return plan_of(voices=voices, engine_refs=dict.fromkeys(ROLES, engine))


def test_four_validated_stems_from_the_installed_singer(
    setup: tuple[OpenUtauRenderBackend, str], tmp_path: Path
) -> None:
    backend, singer = setup
    result = backend.render(plan_with(singer), tmp_path / "song")
    assert isinstance(result, RenderResult)
    assert sorted(p.name for p in (tmp_path / "song").iterdir()) == [
        "Baritone.wav",
        "Bass.wav",
        "Lead.wav",
        "Tenor.wav",
    ]
    for report in result.stems.values():
        assert report.duration_seconds == pytest.approx(2.4, abs=0.01)


def test_a_singer_that_is_not_installed_is_a_configuration_error(
    setup: tuple[OpenUtauRenderBackend, str], tmp_path: Path
) -> None:
    backend, _ = setup
    with pytest.raises(RenderConfigurationError) as info:
        backend.render(plan_with("no-such-singer"), tmp_path / "song")
    assert info.value.code == "HOST_UNRESOLVED"


def _envelope(samples: list[float], rate: int, window: float = 0.01) -> list[float]:
    n = int(rate * window)
    return [
        math.sqrt(sum(x * x for x in samples[i : i + n]) / n) for i in range(0, len(samples) - n, n)
    ]


def _pitch_hz(samples: list[float], rate: int, centre: float) -> float:
    segment = samples[int((centre - 0.02) * rate) : int((centre + 0.02) * rate)]
    best, best_lag = 0.0, 0
    for lag in range(int(rate / 500), int(rate / 80)):
        score = sum(segment[i] * segment[i + lag] for i in range(len(segment) - lag))
        if score > best:
            best, best_lag = score, lag
    return rate / best_lag if best_lag else 0.0


def test_plus_continues_the_syllable_where_a_repeated_lyric_restarts_it(
    setup: tuple[OpenUtauRenderBackend, str], tmp_path: Path
) -> None:
    """M7b review item 3, now through the production backend."""
    backend, singer = setup
    extended = [
        note(0, 2, E4, lyrics=text("la", melisma=Melisma.UNTYPED)),
        note(2, 2, G4),  # the score's continuation, written as "+"
    ]
    restarted = [note(0, 2, E4, lyrics=text("la")), note(2, 2, G4, lyrics=text("la"))]
    boundary = int(BOUNDARY / 0.01)

    plus = read_wav(
        backend.render(plan_with(singer, extended), tmp_path / "plus").stems[VoiceRole.TENOR].path
    )
    again = read_wav(
        backend.render(plan_with(singer, restarted), tmp_path / "again").stems[VoiceRole.TENOR].path
    )
    plus_samples, again_samples = list(plus.samples), list(again.samples)
    rate = plus.info.sample_rate
    plus_env, again_env = _envelope(plus_samples, rate), _envelope(again_samples, rate)

    def dip(env: list[float]) -> float:  # quietest 10 ms near the boundary relative to the peak
        return min(env[boundary - 8 : boundary + 9]) / max(env)

    assert dip(again_env) < 0.4  # a repeated lyric starts a new syllable: the sound drops
    assert dip(plus_env) > 0.5  # "+" does not: the same sound carries across the boundary
    before = _pitch_hz(plus_samples, rate, BOUNDARY - 0.3)
    after = _pitch_hz(plus_samples, rate, BOUNDARY + 0.3)
    assert abs(before - 329.6) / 329.6 < 0.05  # E4
    assert abs(after - 392.0) / 392.0 < 0.05  # G4
