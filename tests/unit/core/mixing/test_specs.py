from dataclasses import replace

import pytest

from barbershop_tracks.core.mixing.errors import MixConfigurationError
from barbershop_tracks.core.mixing.specs import (
    DEFAULT_PROFILE,
    GainProfile,
    MixKind,
    MixSpec,
    standard_mix_specs,
    validate_spec_set,
)
from barbershop_tracks.core.synthesis import VOICE_ORDER
from barbershop_tracks.models import VoiceRole

SPECS = standard_mix_specs()
BY_ID = {s.identifier: s for s in SPECS}


def test_there_are_exactly_thirteen_tracks_in_a_fixed_order() -> None:
    assert [s.identifier for s in SPECS] == [
        "full_quartet",
        "tenor_predominant",
        "lead_predominant",
        "baritone_predominant",
        "bass_predominant",
        "tenor_solo",
        "lead_solo",
        "baritone_solo",
        "bass_solo",
        "without_tenor",
        "without_lead",
        "without_baritone",
        "without_bass",
    ]
    assert [s.number for s in SPECS] == list(range(1, 14))
    assert standard_mix_specs() == SPECS  # deterministic


def test_labels_and_filenames_are_stable_and_human_readable() -> None:
    assert [s.label for s in SPECS] == [
        "Full Quartet",
        "Tenor Predominant",
        "Lead Predominant",
        "Baritone Predominant",
        "Bass Predominant",
        "Tenor Solo",
        "Lead Solo",
        "Baritone Solo",
        "Bass Solo",
        "Without Tenor",
        "Without Lead",
        "Without Baritone",
        "Without Bass",
    ]
    assert SPECS[0].filename_stem == "01_Full_Quartet"
    assert SPECS[4].filename_stem == "05_Bass_Predominant"
    assert SPECS[12].filename_stem == "13_Without_Bass"
    assert all(" " not in s.filename_stem for s in SPECS)


def test_full_quartet_has_four_equal_voices() -> None:
    spec = BY_ID["full_quartet"]
    assert spec.kind is MixKind.FULL
    assert spec.voices == VOICE_ORDER
    assert len(set(spec.gains)) == 1


@pytest.mark.parametrize("role", VOICE_ORDER)
def test_predominant_makes_one_voice_clearly_louder_than_the_other_three(role: VoiceRole) -> None:
    spec = BY_ID[f"{role.value}_predominant"]
    others = [spec.gain(r) for r in VOICE_ORDER if r is not role]
    assert spec.voices == VOICE_ORDER  # everyone still sings
    assert spec.gain(role) > max(others)
    assert len(set(others)) == 1
    assert spec.gain(role) == DEFAULT_PROFILE.predominant_focus
    assert others[0] == DEFAULT_PROFILE.predominant_others


@pytest.mark.parametrize("role", VOICE_ORDER)
def test_solo_contains_only_its_voice(role: VoiceRole) -> None:
    spec = BY_ID[f"{role.value}_solo"]
    assert spec.voices == (role,)
    assert spec.focus is role


@pytest.mark.parametrize("role", VOICE_ORDER)
def test_without_mutes_its_voice_and_balances_the_rest(role: VoiceRole) -> None:
    spec = BY_ID[f"without_{role.value}"]
    assert role not in spec.voices
    assert spec.gain(role) == 0.0
    assert len(spec.voices) == 3
    assert len({spec.gain(r) for r in spec.voices}) == 1


def test_default_gains_cannot_clip_full_scale_stems() -> None:
    assert all(s.worst_case_sum <= 1.0 for s in SPECS)
    assert max(s.worst_case_sum for s in SPECS) == pytest.approx(1.0)  # the full quartet


def test_a_custom_profile_changes_the_gains_and_nothing_else() -> None:
    louder = GainProfile(name="focus", predominant_focus=0.7, predominant_others=0.1)
    specs = standard_mix_specs(louder)
    assert [s.identifier for s in specs] == [s.identifier for s in SPECS]
    assert specs[1].gains == (0.7, 0.1, 0.1, 0.1)
    assert specs[0] == SPECS[0]


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("full_quartet", float("nan"), "MIX_GAIN_INVALID"),
        ("solo", float("inf"), "MIX_GAIN_INVALID"),
        ("solo", -0.1, "MIX_GAIN_RANGE"),
        ("without_each", 5.0, "MIX_GAIN_RANGE"),
        ("full_quartet", 0.0, "MIX_GAIN_SILENT"),
        ("predominant_others", 0.5, "MIX_PREDOMINANT_ORDER"),
        ("predominant_others", 0.0, "MIX_PREDOMINANT_ORDER"),
    ],
)
def test_invalid_profiles_are_refused(field: str, value: float, code: str) -> None:
    with pytest.raises(MixConfigurationError) as error:
        replace(DEFAULT_PROFILE, **{field: value})  # type: ignore[arg-type]
    assert error.value.code == code


def test_a_profile_needs_a_name() -> None:
    with pytest.raises(MixConfigurationError):
        GainProfile(name="")


def test_a_mix_spec_validates_its_own_gains() -> None:
    ok = MixSpec(1, "a", "A", MixKind.FULL, None, (0.1, 0.2, 0.3, 0.4))
    assert ok.worst_case_sum == pytest.approx(1.0)
    for bad in ((0.0, 0.0, 0.0, 0.0), (0.1, -0.1, 0.1, 0.1), (0.1, 9.0, 0.1, 0.1)):
        with pytest.raises(MixConfigurationError):
            MixSpec(1, "a", "A", MixKind.FULL, None, bad)
    with pytest.raises(MixConfigurationError):
        MixSpec(0, "a", "A", MixKind.FULL, None, (0.1,) * 4)
    with pytest.raises(MixConfigurationError):
        MixSpec(1, "", "A", MixKind.FULL, None, (0.1,) * 4)


def test_name_collisions_between_mixes_are_refused() -> None:
    first = SPECS[0]
    for clash in (
        replace(SPECS[1], number=first.number),
        replace(SPECS[1], identifier=first.identifier),
    ):
        with pytest.raises(MixConfigurationError) as error:
            validate_spec_set([first, clash])
        assert error.value.code == "MIX_NAME_COLLISION"
    with pytest.raises(MixConfigurationError):
        validate_spec_set([])
