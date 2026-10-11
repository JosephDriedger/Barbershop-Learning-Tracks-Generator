"""The package as a transaction, driven with synthetic WAV stems (no OpenUtau, no FFmpeg)."""

import hashlib
import json
import threading
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from barbershop_tracks.core.mixing import (
    DEFAULT_PROFILE,
    MANIFEST_NAME,
    AudioFormat,
    GainProfile,
    MixCancelledError,
    MixClippingError,
    MixConfigurationError,
    MixDurationError,
    MixEncodingError,
    MixInputError,
    MixOutputError,
    PackageResult,
    PackageSettings,
    PackageSource,
    TailPolicy,
    build_learning_tracks,
    standard_mix_specs,
)
from barbershop_tracks.core.rendering import CancelToken
from barbershop_tracks.core.rendering.wav import read_raw
from barbershop_tracks.core.runtime import RuntimeLayout
from barbershop_tracks.core.synthesis import VOICE_ORDER, SourceIdentity, TempoPoint
from barbershop_tracks.models import VoiceRole
from wav_builders import RATE, wav16, write

SOURCE = PackageSource(
    SourceIdentity(display_name="demo.musicxml", sha256="ab" * 32, title="Demo"),
    (TempoPoint(position=Fraction(0), bpm=Fraction(100)),),
    Fraction(4),  # four quarters at 100 BPM: 2.4 s = 105840 frames
)
TARGET = 105840
SPECS = standard_mix_specs()


def stem_wav(first: int, length: int, level: int = 8000) -> bytes:
    """Silence for ``first`` frames, then a constant ``level`` up to ``length`` frames."""
    samples = np.zeros(length, dtype=np.int16)
    samples[first:] = level
    return _pcm(samples)


def _pcm(samples: "np.ndarray[Any, np.dtype[np.int16]]") -> bytes:
    from barbershop_tracks.core.mixing.audio import wav_bytes

    return wav_bytes(samples)


class Rig:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.layout = RuntimeLayout.under(root / "bin", root / "data")
        self.destination = root / "out" / "package"
        self.stems = self.write_stems()

    def write_stems(
        self, layout: dict[VoiceRole, tuple[int, int, int]] | None = None
    ) -> dict[VoiceRole, Path]:
        """Per role: (frames of leading silence, stem length, level)."""
        layout = layout or {
            VoiceRole.TENOR: (0, 100000, 8000),
            VoiceRole.LEAD: (22050, 90000, 8000),  # enters half a second late, ends early
            VoiceRole.BARITONE: (950, 105000, 8000),  # sound begins 50 frames before frame 1000
            VoiceRole.BASS: (0, 50000, 8000),  # short
        }
        folder = self.root / "stems"
        folder.mkdir(exist_ok=True)
        paths = {}
        for role, (first, length, level) in layout.items():
            paths[role] = write(folder / f"{role.display_name}.wav", stem_wav(first, length, level))
        return paths

    def settings(self, **overrides: Any) -> PackageSettings:
        return PackageSettings(layout=self.layout, **overrides)

    def build(self, **kwargs: Any) -> PackageResult:
        settings = kwargs.pop("settings", None) or self.settings()
        return build_learning_tracks(SOURCE, self.stems, self.destination, settings, **kwargs)

    def staging(self) -> list[str]:
        root = self.layout.staging
        return sorted(p.name for p in root.iterdir()) if root.is_dir() else []

    def samples(self, name: str) -> "np.ndarray[Any, np.dtype[np.int16]]":
        _, body = read_raw(self.destination / name)
        return np.frombuffer(body, dtype="<i2")


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)


# --- the package ---


def test_all_thirteen_tracks_are_written_with_stable_names(rig: Rig) -> None:
    result = rig.build()
    names = sorted(p.name for p in rig.destination.iterdir())
    assert names == sorted([MANIFEST_NAME, *(f"{s.filename_stem}.wav" for s in SPECS)])
    assert len([n for n in names if n.endswith(".wav")]) == 13
    assert [f.mix for f in result.files] == [s.identifier for s in SPECS]
    assert rig.staging() == []


def test_every_track_has_exactly_the_same_frame_count_derived_from_the_score(rig: Rig) -> None:
    result = rig.build()
    assert result.frames == TARGET  # not 105000, the longest stem
    for spec in SPECS:
        info, _ = read_raw(rig.destination / f"{spec.filename_stem}.wav")
        assert info.frames == TARGET
        assert (info.sample_rate, info.bit_depth, info.channels) == (44100, 16, 1)


def test_the_length_comes_from_the_tempo_map_not_the_stems(rig: Rig) -> None:
    slower = PackageSource(
        SOURCE.identity, (TempoPoint(position=Fraction(0), bpm=Fraction(50)),), Fraction(4)
    )
    result = build_learning_tracks(slower, rig.stems, rig.destination, rig.settings())
    assert result.frames == 2 * TARGET  # 4.8 s, though every stem is shorter than 2.4 s


def test_leading_silence_and_late_entrances_are_untouched(rig: Rig) -> None:
    rig.build()
    lead = rig.samples("07_Lead_Solo.wav")
    assert int(np.flatnonzero(lead)[0]) == 22050  # the lead enters half a second late
    assert not lead[:22050].any()
    tenor = rig.samples("06_Tenor_Solo.wav")
    assert int(np.flatnonzero(tenor)[0]) == 0
    full = rig.samples("01_Full_Quartet.wav")
    assert int(np.flatnonzero(full)[0]) == 0  # the tenor and others are in from the start
    without_tenor = rig.samples("10_Without_Tenor.wav")
    assert int(np.flatnonzero(without_tenor)[0]) == 0  # baritone preutterance at 950: bass at 0


def test_early_preutterance_is_preserved_and_not_compensated(rig: Rig) -> None:
    rig.build()
    baritone = rig.samples("08_Baritone_Solo.wav")
    assert int(np.flatnonzero(baritone)[0]) == 950  # the sound begins before the note at 1000


def test_short_stems_are_padded_with_silence_at_the_end(rig: Rig) -> None:
    rig.build()
    bass = rig.samples("09_Bass_Solo.wav")
    assert bass[:50000].all()
    assert not bass[50000:].any()
    assert len(bass) == TARGET


def test_voices_are_included_and_excluded_per_mix(rig: Rig) -> None:
    rig.stems = rig.write_stems(
        {
            VoiceRole.TENOR: (0, TARGET, 1000),
            VoiceRole.LEAD: (0, TARGET, 2000),
            VoiceRole.BARITONE: (0, TARGET, 4000),
            VoiceRole.BASS: (0, TARGET, 8000),
        }
    )
    rig.build()
    level = {
        n: int(rig.samples(n)[0])
        for n in (
            "01_Full_Quartet.wav",
            "06_Tenor_Solo.wav",
            "09_Bass_Solo.wav",
            "10_Without_Tenor.wav",
            "03_Lead_Predominant.wav",
        )
    }
    assert level["06_Tenor_Solo.wav"] == round(1000 * 0.5)
    assert level["09_Bass_Solo.wav"] == round(8000 * 0.5)
    assert level["01_Full_Quartet.wav"] == round(0.25 * (1000 + 2000 + 4000 + 8000))
    assert level["10_Without_Tenor.wav"] == round(0.33 * (2000 + 4000 + 8000))
    assert level["03_Lead_Predominant.wav"] == round(0.5 * 2000 + 0.15 * (1000 + 4000 + 8000))


def test_repeated_generation_is_byte_identical(rig: Rig, tmp_path: Path) -> None:
    first = rig.build()
    again = tmp_path / "again"
    second = build_learning_tracks(SOURCE, rig.stems, again, rig.settings())
    for name in (p.name for p in rig.destination.iterdir()):
        assert (rig.destination / name).read_bytes() == (again / name).read_bytes()
    assert first.manifest == second.manifest


# --- the manifest ---


def test_the_manifest_describes_every_track_and_leaks_no_paths(rig: Rig) -> None:
    result = rig.build()
    text = (rig.destination / MANIFEST_NAME).read_text(encoding="utf-8")
    manifest = json.loads(text)
    assert manifest == json.loads(json.dumps(result.manifest))
    assert manifest["schema"] == "blt.learning-tracks/1"
    assert manifest["source"] == {
        "display_name": "demo.musicxml",
        "sha256": "ab" * 32,
        "title": "Demo",
    }
    assert manifest["audio"]["frames"] == TARGET
    assert manifest["audio"]["duration_exact_seconds"] == "12/5"
    assert manifest["settings"]["duration_policy"] == "ceil(exact_seconds*sample_rate)"
    assert manifest["settings"]["normalization"] == "none"
    assert [s["voice"] for s in manifest["stems"]] == [r.value for r in VOICE_ORDER]
    tracks = manifest["tracks"]
    assert [t["id"] for t in tracks] == [s.identifier for s in SPECS]
    lead_pred = tracks[2]
    assert lead_pred["voices"] == ["tenor", "lead", "baritone", "bass"]
    assert lead_pred["gains"] == {"tenor": 0.15, "lead": 0.5, "baritone": 0.15, "bass": 0.15}
    for track in tracks:
        (entry,) = track["files"]
        file = rig.destination / entry["name"]
        assert entry["sha256"] == hashlib.sha256(file.read_bytes()).hexdigest()
        assert entry["bytes"] == file.stat().st_size
        assert entry["frames"] == TARGET
    assert str(rig.root) not in text
    assert "\\" not in text
    assert ":/" not in text


def test_the_manifest_records_padding(rig: Rig) -> None:
    manifest = rig.build().manifest
    bass = next(s for s in manifest["stems"] if s["voice"] == "bass")
    assert (bass["frames"], bass["padded_frames"], bass["trimmed_frames"]) == (
        50000,
        TARGET - 50000,
        0,
    )


# --- bad input publishes nothing ---


def assert_untouched(rig: Rig) -> None:
    assert not rig.destination.exists()
    assert rig.staging() == []


def test_a_missing_stem_is_refused(rig: Rig) -> None:
    del rig.stems[VoiceRole.BASS]
    with pytest.raises(MixInputError) as error:
        rig.build()
    assert error.value.code == "MIX_STEM_MISSING"
    assert_untouched(rig)


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"junk", "MIX_STEM_UNREADABLE"),
        (wav16([0.1] * 100, rate=48000), "MIX_STEM_FORMAT"),
        (wav16([0.1] * 100, channels=2), "MIX_STEM_FORMAT"),
    ],
)
def test_malformed_and_incompatible_stems_are_refused(rig: Rig, data: bytes, code: str) -> None:
    write(rig.stems[VoiceRole.LEAD], data)
    with pytest.raises(MixInputError) as error:
        rig.build()
    assert error.value.code == code
    assert_untouched(rig)


def test_a_stem_sounding_past_the_score_is_an_error_not_a_truncation(rig: Rig) -> None:
    write(rig.stems[VoiceRole.TENOR], stem_wav(0, TARGET + 5000))
    with pytest.raises(MixDurationError):
        rig.build()
    assert_untouched(rig)


def test_a_quiet_sliver_past_the_end_is_trimmed_and_recorded(rig: Rig) -> None:
    samples = np.zeros(TARGET + 20, dtype=np.int16)
    samples[:1000] = 8000
    samples[TARGET:] = 5
    write(rig.stems[VoiceRole.TENOR], _pcm(samples))
    manifest = rig.build().manifest
    tenor = manifest["stems"][0]
    assert tenor["trimmed_frames"] == 20
    assert manifest["audio"]["frames"] == TARGET


def test_clipping_is_an_error_and_nothing_is_published(rig: Rig) -> None:
    rig.stems = rig.write_stems(dict.fromkeys(VOICE_ORDER, (0, TARGET, 32767)))
    loud = GainProfile(name="loud", full_quartet=1.0)
    with pytest.raises(MixClippingError) as error:
        rig.build(settings=rig.settings(profile=loud))
    assert error.value.details["mix"] == "full_quartet"
    assert_untouched(rig)


def test_default_gains_never_clip_even_full_scale_stems(rig: Rig) -> None:
    rig.stems = rig.write_stems(dict.fromkeys(VOICE_ORDER, (0, TARGET, 32767)))
    rig.build()
    assert int(rig.samples("01_Full_Quartet.wav")[0]) == round(4 * 0.25 * 32767)


def test_no_format_and_missing_encoder_are_configuration_errors(rig: Rig) -> None:
    with pytest.raises(MixConfigurationError) as none:
        rig.build(settings=rig.settings(formats=frozenset()))
    assert none.value.code == "MIX_NO_FORMAT"
    with pytest.raises(MixConfigurationError) as mp3:
        rig.build(settings=rig.settings(formats=frozenset({AudioFormat.MP3})))
    assert mp3.value.code == "MIX_MP3_NO_ENCODER"
    assert_untouched(rig)


# --- collisions and the user's own files ---


def test_an_existing_package_is_not_overwritten_unless_asked(rig: Rig) -> None:
    rig.build()
    with pytest.raises(MixConfigurationError) as error:
        rig.build()
    assert error.value.code == "PUBLISH_DESTINATION_EXISTS"
    rig.build(replace=True)
    assert rig.staging() == []


def test_replace_refuses_a_folder_that_is_not_ours(rig: Rig) -> None:
    rig.destination.mkdir(parents=True)
    (rig.destination / "my-notes.txt").write_text("precious", encoding="utf-8")
    with pytest.raises(MixConfigurationError) as error:
        rig.build(replace=True)
    assert error.value.code == "MIX_DESTINATION_FOREIGN"
    assert (rig.destination / "my-notes.txt").read_text(encoding="utf-8") == "precious"


def test_a_failed_replacement_keeps_the_previous_package(rig: Rig) -> None:
    rig.build()
    before = {p.name: p.read_bytes() for p in rig.destination.iterdir()}
    rig.stems = rig.write_stems(dict.fromkeys(VOICE_ORDER, (0, TARGET, 32767)))
    with pytest.raises(MixClippingError):
        rig.build(
            settings=rig.settings(profile=GainProfile(name="loud", full_quartet=1.0)), replace=True
        )
    assert {p.name: p.read_bytes() for p in rig.destination.iterdir()} == before


# --- cancellation, rollback, concurrency ---


def test_cancelling_midway_discards_everything(rig: Rig) -> None:
    token = CancelToken()

    def progress(event: dict[str, Any]) -> None:
        if event["number"] == 5:
            token.cancel()

    with pytest.raises(MixCancelledError):
        rig.build(cancel=token, on_progress=progress)
    assert_untouched(rig)


def test_cancelling_before_the_start_does_nothing(rig: Rig) -> None:
    token = CancelToken()
    token.cancel()
    with pytest.raises(MixCancelledError):
        rig.build(cancel=token)
    assert_untouched(rig)


def test_a_failure_on_the_seventh_track_publishes_none_of_the_thirteen(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    from barbershop_tracks.core.mixing.audio import quantize as real

    calls: list[str] = []

    def failing(mixed: Any, mix_id: str) -> Any:
        calls.append(mix_id)
        if len(calls) == 7:
            raise MixClippingError("MIX_CLIPPING", "simulated")
        return real(mixed, mix_id)

    monkeypatch.setattr("barbershop_tracks.core.mixing.package.quantize", failing)
    with pytest.raises(MixClippingError):
        rig.build()
    assert len(calls) == 7
    assert_untouched(rig)


def test_a_wav_of_the_wrong_length_is_caught_by_the_final_check(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    from barbershop_tracks.core.mixing.audio import wav_bytes as real

    monkeypatch.setattr(
        "barbershop_tracks.core.mixing.package.wav_bytes", lambda pcm: real(pcm[:-1])
    )
    with pytest.raises(MixOutputError) as error:
        rig.build()
    assert error.value.code == "MIX_OUTPUT_FRAMES"
    assert_untouched(rig)


def test_concurrent_generation_into_different_destinations(rig: Rig) -> None:
    results: dict[int, object] = {}

    def work(index: int) -> None:
        try:
            results[index] = build_learning_tracks(
                SOURCE, rig.stems, rig.root / f"out{index}", rig.settings()
            )
        except BaseException as error:
            results[index] = error

    threads = [threading.Thread(target=work, args=(i,)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert all(isinstance(r, PackageResult) for r in results.values()), results
    assert len({r.job for r in results.values() if isinstance(r, PackageResult)}) == 4
    first = {p.name: p.read_bytes() for p in (rig.root / "out0").iterdir()}
    for index in range(1, 4):
        assert {p.name: p.read_bytes() for p in (rig.root / f"out{index}").iterdir()} == first
    assert rig.staging() == []


def test_two_generations_for_one_destination_publish_exactly_one(rig: Rig) -> None:
    results: list[object] = []

    def work() -> None:
        try:
            results.append(rig.build())
        except BaseException as error:
            results.append(error)

    threads = [threading.Thread(target=work) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert sum(isinstance(r, PackageResult) for r in results) == 1
    losers = [r for r in results if isinstance(r, MixConfigurationError)]
    assert len(losers) == 1
    assert losers[0].code == "PUBLISH_DESTINATION_EXISTS"
    assert len(list(rig.destination.glob("*.wav"))) == 13


# --- MP3 plumbing (the real encoder is tested in test_mp3.py) ---


class FakeEncoder:
    def __init__(self, fail_at: int | None = None) -> None:
        self.calls = 0
        self.fail_at = fail_at

    def settings(self) -> dict[str, Any]:
        return {"encoder": "fake", "quality": 2}

    def encode(
        self, wav: Path, mp3: Path, *, expected_frames: int, cancel: CancelToken
    ) -> dict[str, Any]:
        self.calls += 1
        if self.fail_at == self.calls:
            raise MixEncodingError("MIX_MP3_FAILED", "simulated encoder failure")
        mp3.write_bytes(b"ID3" + wav.read_bytes()[:100])
        return {"encoder": "fake", "frames_estimate": expected_frames}


@pytest.mark.parametrize(
    ("formats", "extensions"),
    [
        ({AudioFormat.WAV}, {"wav"}),
        ({AudioFormat.MP3}, {"mp3"}),
        ({AudioFormat.WAV, AudioFormat.MP3}, {"wav", "mp3"}),
    ],
)
def test_the_requested_formats_are_exactly_what_is_published(
    rig: Rig, formats: set[AudioFormat], extensions: set[str]
) -> None:
    encoder = FakeEncoder()
    result = rig.build(settings=rig.settings(formats=frozenset(formats), mp3=encoder))
    published = {p.suffix[1:] for p in rig.destination.iterdir() if p.name != MANIFEST_NAME}
    assert published == extensions
    assert len(list(rig.destination.iterdir())) == 13 * len(extensions) + 1
    assert result.manifest["settings"]["formats"] == sorted(extensions)
    assert (encoder.calls == 13) == ("mp3" in extensions)
    if "mp3" in extensions:
        assert result.manifest["settings"]["mp3"] == {"encoder": "fake", "quality": 2}
        entry = result.manifest["tracks"][0]["files"][-1]
        assert entry["format"] == "mp3"
        assert entry["frames_estimate"] == TARGET


def test_an_encoder_failure_publishes_no_partial_set(rig: Rig) -> None:
    both = frozenset({AudioFormat.WAV, AudioFormat.MP3})
    with pytest.raises(MixEncodingError):
        rig.build(settings=rig.settings(formats=both, mp3=FakeEncoder(fail_at=9)))
    assert_untouched(rig)


def test_an_encoder_failure_keeps_the_previous_package(rig: Rig) -> None:
    rig.build()
    before = {p.name: p.read_bytes() for p in rig.destination.iterdir()}
    both = frozenset({AudioFormat.WAV, AudioFormat.MP3})
    with pytest.raises(MixEncodingError):
        rig.build(settings=rig.settings(formats=both, mp3=FakeEncoder(fail_at=3)), replace=True)
    assert {p.name: p.read_bytes() for p in rig.destination.iterdir()} == before


def test_unused_default_profile_import() -> None:
    assert DEFAULT_PROFILE.name == "default"
    assert TailPolicy().max_trim_seconds == 0.05
    assert RATE == 44100
