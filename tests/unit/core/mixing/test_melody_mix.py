"""The Full Quartet that follows the melody: a gain schedule with crossfades, nothing else."""

from pathlib import Path

import numpy as np
import pytest

from barbershop_tracks.core.mixing.audio import (
    TailPolicy,
    fit_stem,
    gain_block,
    load_stem,
    mix_float,
    quantize,
    wav_bytes,
)
from barbershop_tracks.core.mixing.errors import MixConfigurationError
from barbershop_tracks.core.mixing.specs import (
    DEFAULT_PROFILE,
    PRESETS,
    GainProfile,
    GainStep,
    MixSpec,
    following_melody,
    profile_from_dict,
    standard_mix_specs,
)
from barbershop_tracks.core.mixing.streaming import place_stem, write_mix
from barbershop_tracks.core.synthesis import VOICE_ORDER
from barbershop_tracks.models import VoiceRole

FULL = standard_mix_specs()[0]
LEAD, TENOR, BARI, BASS = (
    VoiceRole.LEAD,
    VoiceRole.TENOR,
    VoiceRole.BARITONE,
    VoiceRole.BASS,
)


def melody_spec(*changes: tuple[int, VoiceRole], ramp: int = 100) -> MixSpec:
    return following_melody(FULL, list(changes), DEFAULT_PROFILE, ramp)


def test_the_melody_gains_leave_headroom_in_every_preset() -> None:
    for profile in PRESETS.values():
        assert profile.melody_focus > profile.melody_others > 0
        assert profile.melody_focus + 3 * profile.melody_others <= 1.0 + 1e-9


def test_a_bad_melody_balance_is_refused() -> None:
    with pytest.raises(MixConfigurationError) as error:
        GainProfile(melody_focus=0.2, melody_others=0.3)
    assert error.value.code == "MIX_MELODY_ORDER"


def test_a_profile_file_may_set_the_melody_gains() -> None:
    profile = profile_from_dict({"name": "mine", "melody_focus": 0.45, "melody_others": 0.18})
    assert (profile.melody_focus, profile.melody_others) == (0.45, 0.18)


def test_the_voice_with_the_melody_is_louder_and_the_sum_stays_within_full_scale() -> None:
    spec = melody_spec((0, LEAD), (1000, TENOR))
    assert [step.frame for step in spec.schedule] == [0, 1000]
    assert spec.schedule[0].gains == (0.2, 0.4, 0.2, 0.2)
    assert spec.schedule[1].gains == (0.4, 0.2, 0.2, 0.2)
    assert spec.worst_case_sum <= 1.0 + 1e-9
    assert spec.gains == (0.4, 0.4, 0.2, 0.2)  # the most each voice ever reaches


def test_one_voice_throughout_is_a_plain_mix_without_a_schedule() -> None:
    spec = melody_spec((0, LEAD), (500, LEAD))
    assert spec.schedule == ()
    assert spec.gains == (0.2, 0.4, 0.2, 0.2)


def test_a_plain_mix_has_one_gain_as_a_plain_number() -> None:
    assert gain_block(FULL, 0, 0, 10) == 0.25


def test_the_gain_crossfades_around_the_change_and_is_steady_elsewhere() -> None:
    spec = melody_spec((0, LEAD), (1000, TENOR), ramp=100)
    tenor = np.asarray(gain_block(spec, 0, 0, 2000))
    assert tenor[0] == pytest.approx(0.2)
    assert tenor[949] == pytest.approx(0.2)  # before the crossfade (950 to 1050)
    assert tenor[1000] == pytest.approx(0.3)  # halfway through it
    assert tenor[1051] == pytest.approx(0.4)
    assert tenor[1999] == pytest.approx(0.4)
    assert (np.diff(tenor) >= 0).all()  # it only rises


def test_the_sum_of_the_gains_never_exceeds_one_during_a_crossfade() -> None:
    spec = melody_spec((0, LEAD), (1000, TENOR), ramp=100)
    total = sum(np.asarray(gain_block(spec, i, 0, 2000)) for i in range(4))
    assert float(np.max(total)) <= 1.0 + 1e-9


def test_a_block_of_the_curve_equals_the_same_frames_of_the_whole() -> None:
    spec = melody_spec((0, LEAD), (1000, TENOR), (1500, BASS), ramp=100)
    whole = np.asarray(gain_block(spec, 2, 0, 3000))
    assert np.array_equal(np.asarray(gain_block(spec, 2, 940, 1560)), whole[940:1560])


def test_changes_closer_together_than_the_crossfade_shorten_it_instead_of_breaking() -> None:
    spec = melody_spec((0, LEAD), (1000, TENOR), (1010, LEAD), ramp=400)
    curve = np.asarray(gain_block(spec, 0, 0, 3000))
    assert np.isfinite(curve).all()
    assert curve.min() >= 0.2 - 1e-12
    assert curve.max() <= 0.4 + 1e-12


def test_a_schedule_must_start_at_zero_and_move_forward() -> None:
    steps = (GainStep(5, (0.2, 0.4, 0.2, 0.2)),)
    with pytest.raises(MixConfigurationError):
        MixSpec(1, "x", "X", FULL.kind, None, (0.2, 0.4, 0.2, 0.2), steps, 10)


def write_stems(folder: Path, length: int) -> dict[VoiceRole, Path]:
    rng = np.random.default_rng(3)
    paths = {}
    for role in VOICE_ORDER:
        samples = rng.integers(-20000, 20000, size=length).astype(np.int16)
        path = folder / f"{role.value}.wav"
        path.write_bytes(wav_bytes(samples))
        paths[role] = path
    return paths


@pytest.mark.parametrize("block", [7, 977, 4096])
def test_the_streamed_melody_mix_is_byte_identical_to_the_reference(
    tmp_path: Path, block: int
) -> None:
    frames = 9000
    paths = write_stems(tmp_path, frames)
    spec = melody_spec((0, LEAD), (3000, TENOR), (6000, BARI))
    tail = TailPolicy()
    fitted = {role: fit_stem(load_stem(role, paths[role]), frames, tail) for role in VOICE_ORDER}
    pcm, _ = quantize(mix_float(spec, fitted), spec.identifier)
    placed = {role: place_stem(role, paths[role], frames, tail) for role in VOICE_ORDER}
    out = tmp_path / "mix.wav"
    write_mix(spec, placed, frames, out, block_frames=block)
    assert out.read_bytes() == wav_bytes(pcm)


def test_the_other_twelve_mixes_are_untouched() -> None:
    specs = standard_mix_specs()
    assert all(not s.schedule for s in specs)
    assert specs[0].gains == (DEFAULT_PROFILE.full_quartet,) * 4
