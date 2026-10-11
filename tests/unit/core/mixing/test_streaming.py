"""The streaming mixer against the whole-array reference: same bytes, bounded memory."""

import tracemalloc
from pathlib import Path

import numpy as np
import pytest

from barbershop_tracks.core.mixing.audio import (
    TailPolicy,
    fit_stem,
    load_stem,
    mix_float,
    quantize,
    wav_bytes,
)
from barbershop_tracks.core.mixing.errors import (
    MixClippingError,
    MixDurationError,
    MixInputError,
)
from barbershop_tracks.core.mixing.specs import MixKind, MixSpec, standard_mix_specs
from barbershop_tracks.core.mixing.streaming import BLOCK_FRAMES, place_stem, write_mix
from barbershop_tracks.core.synthesis import VOICE_ORDER
from barbershop_tracks.models import VoiceRole

SPECS = standard_mix_specs()
RATE = 44100


def write_stems(
    folder: Path, lengths: dict[VoiceRole, int], *, seed: int = 7, amplitude: int = 20000
) -> dict[VoiceRole, Path]:
    rng = np.random.default_rng(seed)
    paths = {}
    for role, length in lengths.items():
        samples = rng.integers(-amplitude, amplitude, size=length).astype(np.int16)
        samples[: length // 5] = 0  # a leading silence
        path = folder / f"{role.value}.wav"
        path.write_bytes(wav_bytes(samples))
        paths[role] = path
    return paths


def reference(paths: dict[VoiceRole, Path], frames: int, spec: MixSpec, tail: TailPolicy) -> bytes:
    fitted = {role: fit_stem(load_stem(role, paths[role]), frames, tail) for role in VOICE_ORDER}
    pcm, _ = quantize(mix_float(spec, fitted), spec.identifier)
    return wav_bytes(pcm)


def streamed(
    paths: dict[VoiceRole, Path],
    frames: int,
    spec: MixSpec,
    tail: TailPolicy,
    out: Path,
    block: int,
) -> float:
    placed = {role: place_stem(role, paths[role], frames, tail) for role in VOICE_ORDER}
    return write_mix(spec, placed, frames, out, block_frames=block)


LENGTHS = {
    VoiceRole.TENOR: 30000,
    VoiceRole.LEAD: 12345,  # short: padded
    VoiceRole.BARITONE: 30000,  # exact
    VoiceRole.BASS: 30010,  # a sliver past the end: trimmed
}


@pytest.mark.parametrize("block", [7, 977, 4096, BLOCK_FRAMES])
def test_every_standard_mix_is_byte_identical_to_the_reference_at_any_block_size(
    tmp_path: Path, block: int
) -> None:
    paths = write_stems(tmp_path, LENGTHS, amplitude=1000)  # the sliver stays below -60 dBFS
    tail = TailPolicy(max_trim_seconds=0.05, max_trim_peak=1.0)
    for spec in SPECS:
        out = tmp_path / f"{spec.identifier}.wav"
        streamed(paths, 30000, spec, tail, out, block)
        assert out.read_bytes() == reference(paths, 30000, spec, tail), (spec.identifier, block)


def test_one_frame_blocks_also_agree(tmp_path: Path) -> None:
    paths = write_stems(tmp_path, dict.fromkeys(VOICE_ORDER, 300), amplitude=3000)
    tail = TailPolicy()
    for spec in SPECS:
        out = tmp_path / "o.wav"
        streamed(paths, 300, spec, tail, out, 1)
        assert out.read_bytes() == reference(paths, 300, spec, tail)


def test_the_float_peak_matches_the_reference(tmp_path: Path) -> None:
    paths = write_stems(tmp_path, dict.fromkeys(VOICE_ORDER, 5000), amplitude=30000)
    tail = TailPolicy()
    spec = SPECS[0]
    fitted = {r: fit_stem(load_stem(r, paths[r]), 5000, tail) for r in VOICE_ORDER}
    _, expected_peak = quantize(mix_float(spec, fitted), spec.identifier)
    assert streamed(paths, 5000, spec, tail, tmp_path / "o.wav", 333) == expected_peak


def test_clipping_reports_the_same_numbers_as_the_reference(tmp_path: Path) -> None:
    paths = write_stems(tmp_path, dict.fromkeys(VOICE_ORDER, 9000), amplitude=32767)
    loud = MixSpec(1, "loud", "Loud", MixKind.FULL, None, (0.9, 0.9, 0.9, 0.9))
    tail = TailPolicy()
    fitted = {r: fit_stem(load_stem(r, paths[r]), 9000, tail) for r in VOICE_ORDER}
    with pytest.raises(MixClippingError) as expected:
        quantize(mix_float(loud, fitted), "loud")
    with pytest.raises(MixClippingError) as got:
        streamed(paths, 9000, loud, tail, tmp_path / "o.wav", 1000)
    assert got.value.details == expected.value.details
    assert str(got.value) == str(expected.value)


def test_a_late_clip_in_a_later_block_is_still_found(tmp_path: Path) -> None:
    samples = np.zeros(20000, dtype=np.int16)
    samples[17000:17010] = 32767
    for role in VOICE_ORDER:
        (tmp_path / f"{role.value}.wav").write_bytes(wav_bytes(samples))
    paths = {r: tmp_path / f"{r.value}.wav" for r in VOICE_ORDER}
    loud = MixSpec(1, "loud", "Loud", MixKind.FULL, None, (1.0, 1.0, 0.0, 0.0))
    with pytest.raises(MixClippingError) as error:
        streamed(paths, 20000, loud, TailPolicy(), tmp_path / "o.wav", 4096)
    assert error.value.details["first"] == 17000
    assert error.value.details["clipped_samples"] == 10


def test_stem_fitting_errors_match_the_reference(tmp_path: Path) -> None:
    lengths = {**LENGTHS, VoiceRole.BASS: 30000 + 5000}
    paths = write_stems(tmp_path, lengths, amplitude=20000)
    with pytest.raises(MixDurationError) as expected:
        fit_stem(load_stem(VoiceRole.BASS, paths[VoiceRole.BASS]), 30000, TailPolicy())
    with pytest.raises(MixDurationError) as got:
        place_stem(VoiceRole.BASS, paths[VoiceRole.BASS], 30000, TailPolicy())
    assert str(got.value) == str(expected.value)
    assert got.value.details == expected.value.details


@pytest.mark.parametrize("data", [b"junk", b""])
def test_unreadable_stems_are_the_same_typed_error(tmp_path: Path, data: bytes) -> None:
    path = tmp_path / "bad.wav"
    path.write_bytes(data)
    with pytest.raises(MixInputError) as error:
        place_stem(VoiceRole.LEAD, path, 100, TailPolicy())
    assert error.value.code == "MIX_STEM_UNREADABLE"


def test_a_truncated_stem_is_refused_from_its_header(tmp_path: Path) -> None:
    path = tmp_path / "t.wav"
    path.write_bytes(wav_bytes(np.ones(1000, dtype=np.int16))[:-100])
    with pytest.raises(MixInputError) as error:
        place_stem(VoiceRole.LEAD, path, 100, TailPolicy())
    assert error.value.details["wav_code"] == "WAV_TRUNCATED"


def test_cancelling_stops_between_blocks(tmp_path: Path) -> None:
    paths = write_stems(tmp_path, dict.fromkeys(VOICE_ORDER, 50000), amplitude=1000)
    placed = {r: place_stem(r, paths[r], 50000, TailPolicy()) for r in VOICE_ORDER}
    seen = {"blocks": 0}

    def stop() -> bool:
        seen["blocks"] += 1
        return seen["blocks"] > 2

    write_mix(SPECS[0], placed, 50000, tmp_path / "o.wav", should_stop=stop, block_frames=4096)
    assert seen["blocks"] == 3  # it asked before each block and quit at the third
    assert (tmp_path / "o.wav").stat().st_size < 44 + 2 * 50000


# --- memory ---


def traced_peak(folder: Path, frames: int) -> int:
    paths = write_stems(folder, dict.fromkeys(VOICE_ORDER, frames - 700), amplitude=1000)
    placed = {r: place_stem(r, paths[r], frames, TailPolicy()) for r in VOICE_ORDER}
    tracemalloc.start()
    try:
        for spec in (SPECS[0], SPECS[1], SPECS[9]):
            write_mix(spec, placed, frames, folder / "o.wav")
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def test_memory_does_not_grow_with_the_length_of_the_song(tmp_path: Path) -> None:
    short_dir, long_dir = tmp_path / "short", tmp_path / "long"
    short_dir.mkdir()
    long_dir.mkdir()
    short = traced_peak(short_dir, 20 * RATE)  # 20 s
    long = traced_peak(long_dir, 10 * 60 * RATE)  # 10 minutes: 30 times longer
    assert long < 40 * 1024 * 1024  # a handful of blocks, never the song
    assert long < short * 1.5 + 2_000_000  # and independent of the length
