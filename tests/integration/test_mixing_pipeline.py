"""Render four stems with the real host (generated voicebank), then mix the 13-track package.

The mixing step needs neither OpenUtau nor a voicebank: the host runtime is deleted before it runs
to show that nothing is synthesised twice. The MP3 test needs a real FFmpeg (``BLT_FFMPEG`` or
``PATH``) and is skipped without one.
"""

import shutil
from pathlib import Path

import pytest

from barbershop_tracks.core.mixing import (
    MANIFEST_NAME,
    AudioFormat,
    FfmpegMp3Encoder,
    PackageResult,
    PackageSettings,
    PackageSource,
    build_learning_tracks,
    find_ffmpeg,
    standard_mix_specs,
    stems_from_render,
)
from barbershop_tracks.core.mixing.audio import SAMPLE_RATE
from barbershop_tracks.core.mixing.timeline import duration_frames
from barbershop_tracks.core.rendering import (
    OpenUtauRenderBackend,
    RenderResult,
    RenderSettings,
)
from barbershop_tracks.core.rendering.wav import read_raw
from barbershop_tracks.core.runtime import RuntimeLayout
from barbershop_tracks.core.synthesis import SynthesisPlan, VoiceEngineRef
from barbershop_tracks.models import VoiceRole
from host_support import host_environment, require_host
from synth_builders import ROLES, full_lyrics, plan_of, sung
from synthetic_voicebank import SINGER_ID, build_voicebank

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def rendered(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[SynthesisPlan, RenderResult, RuntimeLayout]:
    require_host()
    root = tmp_path_factory.mktemp("pipeline")
    layout = RuntimeLayout.under(root / "bin", root / "data")
    build_voicebank(root / "singers")
    engine = VoiceEngineRef(
        singer=SINGER_ID, phonemizer="OpenUtau.Core.DefaultPhonemizer", renderer="WORLDLINE-R"
    )
    voices = {
        **full_lyrics(("la", "ba", "la", "ba")),
        "tenor": sung(VoiceRole.TENOR, ["la", "ba", "la", "ba"], start=4),  # enters 2.4 s late
    }
    plan = plan_of(voices=voices, engine_refs=dict.fromkeys(ROLES, engine))
    backend = OpenUtauRenderBackend(
        RenderSettings(
            layout=layout,
            singers_dir=root / "singers",
            host_binaries=require_host(),
            extra_env={k: v for k, v in host_environment().items() if k == "DOTNET_ROOT"},
        )
    )
    result = backend.render(plan, root / "stems")
    shutil.rmtree(layout.runtime)  # from here on nothing can synthesise
    return plan, result, layout


def test_four_rendered_stems_make_the_complete_thirteen_track_package(
    rendered: tuple[SynthesisPlan, RenderResult, RuntimeLayout], tmp_path: Path
) -> None:
    plan, result, layout = rendered
    package = build_learning_tracks(
        PackageSource.from_plan(plan),
        stems_from_render(result),
        tmp_path / "package",
        PackageSettings(layout=layout),
    )
    assert isinstance(package, PackageResult)
    expected = duration_frames(plan.tempo, plan.output.performed_length, SAMPLE_RATE)
    assert package.frames == expected  # 16 quarters at 100 BPM = 9.6 s, not the stems' 4.8 s
    wavs = sorted((tmp_path / "package").glob("*.wav"))
    assert [w.stem for w in wavs] == sorted(s.filename_stem for s in standard_mix_specs())
    for wav in wavs:
        info, _ = read_raw(wav)
        assert info.frames == expected

    # the late entrance and the early onset survive: the tenor solo starts where the stem does
    tenor_stem = result.stems[VoiceRole.TENOR]
    _, stem_body = read_raw(tenor_stem.path)
    _, solo_body = read_raw(tmp_path / "package" / "06_Tenor_Solo.wav")
    first_stem = (
        next(i for i in range(0, len(stem_body), 2) if stem_body[i : i + 2] != b"\x00\x00") // 2
    )
    first_solo = (
        next(i for i in range(0, len(solo_body), 2) if solo_body[i : i + 2] != b"\x00\x00") // 2
    )
    assert (
        abs(first_solo - first_stem) <= 1
    )  # equal, apart from gain rounding at the very first sample
    assert first_stem > 2.0 * SAMPLE_RATE
    assert (tmp_path / "package" / MANIFEST_NAME).is_file()


def test_the_package_is_reproducible_from_the_same_stems(
    rendered: tuple[SynthesisPlan, RenderResult, RuntimeLayout], tmp_path: Path
) -> None:
    plan, result, layout = rendered
    for name in ("a", "b"):
        build_learning_tracks(
            PackageSource.from_plan(plan),
            stems_from_render(result),
            tmp_path / name,
            PackageSettings(layout=layout),
        )
    for path in sorted((tmp_path / "a").iterdir()):
        assert path.read_bytes() == (tmp_path / "b" / path.name).read_bytes()


def test_real_ffmpeg_makes_valid_mp3_copies(
    rendered: tuple[SynthesisPlan, RenderResult, RuntimeLayout], tmp_path: Path
) -> None:
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        pytest.skip("no FFmpeg (set BLT_FFMPEG or put ffmpeg on PATH)")
    plan, result, layout = rendered
    package = build_learning_tracks(
        PackageSource.from_plan(plan),
        stems_from_render(result),
        tmp_path / "package",
        PackageSettings(
            layout=layout,
            formats=frozenset({AudioFormat.WAV, AudioFormat.MP3}),
            mp3=FfmpegMp3Encoder([ffmpeg]),
        ),
    )
    assert len(list((tmp_path / "package").glob("*.mp3"))) == 13
    assert len(list((tmp_path / "package").glob("*.wav"))) == 13
    for track in package.manifest["tracks"]:
        mp3 = track["files"][1]
        assert mp3["format"] == "mp3"
        assert abs(mp3["decoded_minus_wav_samples"]) <= 3 * 1152  # close, not sample-exact
    assert package.manifest["settings"]["mp3"]["encoder"] == "libmp3lame"


def test_stems_that_fill_the_whole_score_need_at_most_a_frame_of_trimming(
    rendered: tuple[SynthesisPlan, RenderResult, RuntimeLayout], tmp_path: Path
) -> None:
    """Measured: OpenUtau writes one frame more than the score's exact duration."""
    _, _, layout = rendered
    root = tmp_path / "full"
    build_voicebank(root / "singers")
    engine = VoiceEngineRef(
        singer=SINGER_ID, phonemizer="OpenUtau.Core.DefaultPhonemizer", renderer="WORLDLINE-R"
    )
    plan = plan_of(
        voices={role.value: sung(role, ["la"] * 16) for role in ROLES},  # all 16 quarters
        engine_refs=dict.fromkeys(ROLES, engine),
    )
    own = RuntimeLayout.under(root / "bin", root / "data")
    backend = OpenUtauRenderBackend(
        RenderSettings(
            layout=own,
            singers_dir=root / "singers",
            host_binaries=require_host(),
            extra_env={k: v for k, v in host_environment().items() if k == "DOTNET_ROOT"},
        )
    )
    result = backend.render(plan, root / "stems")
    package = build_learning_tracks(
        PackageSource.from_plan(plan),
        stems_from_render(result),
        root / "package",
        PackageSettings(layout=layout),
    )
    assert package.frames == 423360
    assert all(s["trimmed_frames"] <= 1 for s in package.manifest["stems"])
    assert all(s["padded_frames"] == 0 for s in package.manifest["stems"])
