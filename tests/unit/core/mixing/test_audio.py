from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from barbershop_tracks.core.mixing.audio import (
    SCALE,
    FittedStem,
    StemAudio,
    TailPolicy,
    fit_stem,
    load_stem,
    mix_float,
    quantize,
    wav_bytes,
)
from barbershop_tracks.core.mixing.errors import (
    MixClippingError,
    MixConfigurationError,
    MixDurationError,
    MixInputError,
)
from barbershop_tracks.core.mixing.specs import standard_mix_specs
from barbershop_tracks.core.mixing.timeline import duration_frames, exact_seconds
from barbershop_tracks.core.rendering.wav import read_wav
from barbershop_tracks.core.synthesis import VOICE_ORDER, TempoPoint
from barbershop_tracks.models import VoiceRole
from wav_builders import RATE, chunk, fmt_chunk, riff, tone, wav16, write

SPECS = {s.identifier: s for s in standard_mix_specs()}


def stem(role: VoiceRole, values: list[int]) -> StemAudio:
    return StemAudio(role, np.array(values, dtype=np.int16))


def fitted(role: VoiceRole, values: list[float]) -> FittedStem:
    return FittedStem(role, np.array(values, dtype=np.float64), 0, 0)


# --- timeline: exact duration, documented rounding ---


def tempo(*points: tuple[int, Fraction]) -> list[TempoPoint]:
    return [TempoPoint(position=Fraction(p), bpm=b) for p, b in points]


def test_exact_seconds_follow_the_tempo_map() -> None:
    changes = tempo((0, Fraction(100)), (2, Fraction(200)))
    assert exact_seconds(changes, Fraction(2)) == Fraction(6, 5)
    assert exact_seconds(changes, Fraction(4)) == Fraction(9, 5)
    assert exact_seconds(changes, Fraction(0)) == 0


def test_a_whole_number_of_frames_is_not_rounded() -> None:
    assert duration_frames(tempo((0, Fraction(100))), Fraction(16), RATE) == 423360  # 9.6 s


def test_a_fractional_frame_count_rounds_up_never_down() -> None:
    # 1 quarter at 70 BPM = 6/7 s = 37800 frames exactly ... 3 quarters is 18/7 s = 113400 exactly;
    # use 7 BPM-free values: 1 quarter at 61 BPM = 60/61 s = 43377.049... frames
    frames = duration_frames(tempo((0, Fraction(61))), Fraction(1), RATE)
    assert frames == 43378
    assert frames - 60 * RATE / 61 < 1  # less than one frame longer than exact


def test_a_quarter_frame_still_rounds_up() -> None:
    # 1/4 of a frame beyond a whole number
    one_frame = Fraction(1, RATE)
    bpm = Fraction(60) / (Fraction(10) + one_frame / 4)  # 1 quarter lasts 10 s + 1/4 frame
    assert duration_frames(tempo((0, bpm)), Fraction(1), RATE) == 10 * RATE + 1


def test_tempo_and_length_errors_are_typed() -> None:
    with pytest.raises(MixConfigurationError):
        duration_frames([], Fraction(4), RATE)
    with pytest.raises(MixConfigurationError):
        duration_frames(tempo((0, Fraction(100))), Fraction(0), RATE)
    with pytest.raises(MixConfigurationError):
        duration_frames(tempo((0, Fraction(100))), Fraction(4), 0)


# --- loading ---


def test_a_supported_stem_loads_as_int16(tmp_path: Path) -> None:
    loaded = load_stem(VoiceRole.LEAD, write(tmp_path / "l.wav", wav16(tone(0.1))))
    assert loaded.role is VoiceRole.LEAD
    assert loaded.frames == 4410
    assert loaded.samples.dtype == np.int16


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"not a wav", "MIX_STEM_UNREADABLE"),
        (wav16(tone(0.1))[:-300], "MIX_STEM_UNREADABLE"),
        (wav16(tone(0.1, rate=48000), rate=48000), "MIX_STEM_FORMAT"),
        (wav16(tone(0.1) * 2, channels=2), "MIX_STEM_FORMAT"),
        (riff(fmt_chunk(bits=24), chunk(b"data", b"\x00\x00\x00" * 100)), "MIX_STEM_FORMAT"),
        (riff(fmt_chunk(bits=32, tag=3), chunk(b"data", b"\x00" * 400)), "MIX_STEM_FORMAT"),
        (wav16([]), "MIX_STEM_EMPTY"),
    ],
    ids=["garbage", "truncated", "48kHz", "stereo", "24bit", "float32", "empty"],
)
def test_missing_malformed_and_incompatible_stems_are_typed_errors(
    tmp_path: Path, data: bytes, code: str
) -> None:
    with pytest.raises(MixInputError) as error:
        load_stem(VoiceRole.TENOR, write(tmp_path / "t.wav", data))
    assert error.value.code == code


def test_a_missing_file_is_a_typed_error(tmp_path: Path) -> None:
    with pytest.raises(MixInputError) as error:
        load_stem(VoiceRole.TENOR, tmp_path / "nope.wav")
    assert error.value.code == "MIX_STEM_UNREADABLE"


# --- placing stems on the common timeline ---


def test_a_short_stem_is_padded_with_exact_zeros_at_the_end_only() -> None:
    placed = fit_stem(stem(VoiceRole.BASS, [0, 0, 16384, -16384]), 8, TailPolicy())
    assert placed.samples.shape == (8,)
    assert list(placed.samples) == [0, 0, 0.5, -0.5, 0, 0, 0, 0]
    assert placed.padded_frames == 4
    assert placed.trimmed_frames == 0


def test_leading_silence_and_a_late_entrance_stay_where_they_are() -> None:
    values = [0] * 1000 + [8192] * 10
    placed = fit_stem(stem(VoiceRole.TENOR, values), 5000, TailPolicy())
    assert np.flatnonzero(placed.samples)[0] == 1000
    assert placed.samples.shape == (5000,)


def test_preutterance_before_the_note_is_not_moved() -> None:
    values = [0] * 950 + [4096] * 60  # sound begins 50 frames before a note at frame 1000
    placed = fit_stem(stem(VoiceRole.LEAD, values), 2000, TailPolicy())
    assert np.flatnonzero(placed.samples)[0] == 950


def test_an_exact_length_stem_is_unchanged() -> None:
    placed = fit_stem(stem(VoiceRole.LEAD, [1, 2, 3]), 3, TailPolicy())
    assert list(placed.samples) == [1 / SCALE, 2 / SCALE, 3 / SCALE]
    assert (placed.padded_frames, placed.trimmed_frames) == (0, 0)


def test_a_nearly_silent_short_excess_is_trimmed_and_reported() -> None:
    values = [1000] * 100 + [5] * 20  # 20 frames past the target at -76 dBFS
    placed = fit_stem(stem(VoiceRole.LEAD, values), 100, TailPolicy())
    assert placed.samples.shape == (100,)
    assert placed.trimmed_frames == 20


def test_an_audible_excess_is_an_error_not_a_silent_truncation() -> None:
    values = [1000] * 100 + [4000] * 20
    with pytest.raises(MixDurationError) as error:
        fit_stem(stem(VoiceRole.LEAD, values), 100, TailPolicy())
    assert error.value.code == "MIX_STEM_TOO_LONG"
    assert error.value.details["excess_frames"] == 20


def test_a_long_excess_is_an_error_even_when_quiet() -> None:
    values = [1000] * 100 + [5] * int(0.2 * RATE)
    with pytest.raises(MixDurationError):
        fit_stem(stem(VoiceRole.LEAD, values), 100, TailPolicy())


def test_the_tail_policy_can_be_widened_explicitly() -> None:
    values = [1000] * 100 + [4000] * 20
    wide = TailPolicy(max_trim_seconds=1.0, max_trim_peak=0.5)
    assert fit_stem(stem(VoiceRole.LEAD, values), 100, wide).trimmed_frames == 20
    with pytest.raises(MixConfigurationError):
        TailPolicy(max_trim_peak=2.0)


# --- mixing ---


def four(values: dict[VoiceRole, list[float]]) -> dict[VoiceRole, FittedStem]:
    return {role: fitted(role, v) for role, v in values.items()}


def test_inclusion_and_exclusion_of_voices() -> None:
    stems = four(
        {
            VoiceRole.TENOR: [0.1, 0.0],
            VoiceRole.LEAD: [0.0, 0.2],
            VoiceRole.BARITONE: [0.0, 0.0],
            VoiceRole.BASS: [0.0, 0.0],
        }
    )
    assert list(mix_float(SPECS["tenor_solo"], stems)) == pytest.approx([0.05, 0.0])
    assert list(mix_float(SPECS["lead_solo"], stems)) == pytest.approx([0.0, 0.1])
    without_tenor = mix_float(SPECS["without_tenor"], stems)
    assert list(without_tenor) == pytest.approx([0.0, 0.2 * 0.33])
    full = mix_float(SPECS["full_quartet"], stems)
    assert list(full) == pytest.approx([0.025, 0.05])


def test_predominant_gain_relationship_in_the_audio() -> None:
    one = [0.5, 0.5]
    stems = four(dict.fromkeys(VOICE_ORDER, one))
    out = mix_float(SPECS["lead_predominant"], stems)
    assert out[0] == pytest.approx(0.5 * (0.5 + 3 * 0.15))

    def solo_stem(active: VoiceRole) -> dict[VoiceRole, FittedStem]:
        return four({r: ([0.5, 0.5] if r is active else [0.0, 0.0]) for r in VOICE_ORDER})

    spec = SPECS["lead_predominant"]
    ratio = (
        mix_float(spec, solo_stem(VoiceRole.LEAD))[0]
        / mix_float(spec, solo_stem(VoiceRole.TENOR))[0]
    )
    assert ratio == pytest.approx(0.5 / 0.15)


def test_mixing_is_bit_for_bit_deterministic() -> None:
    rng = np.random.default_rng(1)
    stems = four({r: list(rng.uniform(-1, 1, 1000)) for r in VOICE_ORDER})
    first = mix_float(SPECS["full_quartet"], stems)
    assert np.array_equal(first, mix_float(SPECS["full_quartet"], stems))


def test_mismatched_stem_lengths_are_refused() -> None:
    stems = four({r: [0.0, 0.0] for r in VOICE_ORDER})
    stems[VoiceRole.BASS] = fitted(VoiceRole.BASS, [0.0])
    with pytest.raises(MixInputError) as error:
        mix_float(SPECS["full_quartet"], stems)
    assert error.value.code == "MIX_FRAME_MISMATCH"


def test_a_stem_that_a_mix_needs_must_exist() -> None:
    stems = four({r: [0.0] for r in VOICE_ORDER if r is not VoiceRole.BASS})
    with pytest.raises(MixInputError) as error:
        mix_float(SPECS["full_quartet"], stems)
    assert error.value.code == "MIX_STEM_MISSING"
    mix_float(SPECS["without_bass"], stems)  # it does not need the bass


# --- quantisation and clipping ---


def test_quantisation_rounds_half_to_even_once() -> None:
    values = np.array([0.5, 1.5, 2.5, -0.5, -1.5, 0.4999, 0.5001]) / SCALE
    out, _ = quantize(values, "t")
    assert list(out) == [0, 2, 2, 0, -2, 0, 1]
    assert out.dtype == np.dtype("<i2")


def test_full_scale_stems_pass_through_a_unity_gain_exactly() -> None:
    raw = np.array([-32768, -1, 0, 1, 32767], dtype=np.int16)
    out, peak = quantize(raw / SCALE, "t")
    assert np.array_equal(out, raw)
    assert peak == 1.0


def test_positive_full_scale_one_is_clipping() -> None:
    with pytest.raises(MixClippingError) as error:
        quantize(np.array([0.0, 1.0]), "loud")
    assert error.value.code == "MIX_CLIPPING"
    assert error.value.details["first"] == 1
    assert error.value.details["clipped_samples"] == 1


def test_overflow_in_either_direction_is_reported_with_its_count() -> None:
    with pytest.raises(MixClippingError) as error:
        quantize(np.array([1.2, -1.2, 0.5, 2.0]), "loud")
    assert error.value.details["clipped_samples"] == 3
    assert error.value.details["peak"] == pytest.approx(2.0)


def test_a_value_just_inside_full_scale_is_not_clipping() -> None:
    out, _ = quantize(np.array([32767.4 / SCALE, -32768.0 / SCALE]), "edge")
    assert list(out) == [32767, -32768]


def test_a_gain_above_one_clips_loud_stems_loudly() -> None:
    from dataclasses import replace

    from barbershop_tracks.core.mixing.specs import MixKind, MixSpec

    spec = MixSpec(1, "boost", "Boost", MixKind.SOLO, VoiceRole.LEAD, (0.0, 2.0, 0.0, 0.0))
    stems = four({r: [0.8] for r in VOICE_ORDER})
    with pytest.raises(MixClippingError):
        quantize(mix_float(spec, stems), spec.identifier)
    assert replace(spec, gains=(0.0, 1.0, 0.0, 0.0)).gain(VoiceRole.LEAD) == 1.0


# --- the WAV bytes ---


def test_wav_bytes_are_canonical_and_decode_back(tmp_path: Path) -> None:
    samples = np.array([0, 1, -1, 32767, -32768], dtype=np.int16)
    data = wav_bytes(samples)
    assert len(data) == 44 + 10
    assert data == wav_bytes(samples)
    audio = read_wav(write(tmp_path / "o.wav", data))
    assert (audio.info.sample_rate, audio.info.bit_depth, audio.info.channels) == (44100, 16, 1)
    assert [round(x * SCALE) for x in audio.samples] == [0, 1, -1, 32767, -32768]
