from fractions import Fraction
from pathlib import Path

import pytest

from barbershop_tracks.models import (
    JobRequest,
    JobResult,
    JobStatus,
    MixProfile,
    Severity,
    StemMix,
    TrackKind,
    TrackPlan,
    ValidationIssue,
    ValidationResult,
    VoiceRole,
)

T, L, BR, B = VoiceRole.TENOR, VoiceRole.LEAD, VoiceRole.BARITONE, VoiceRole.BASS


def test_default_mix_profile() -> None:
    profile = MixProfile()
    assert profile.target_gain_db == 0.0
    assert profile.background_gain_db == -12.0
    assert dict(profile.panning) == {}  # centered by default


def test_mix_profile_is_configurable() -> None:
    profile = MixProfile(target_gain_db=3.0, background_gain_db=-9.0)
    assert profile.target_gain_db == 3.0
    assert profile.background_gain_db == -9.0


def test_mix_profile_supports_optional_panning() -> None:
    profile = MixProfile(panning={T: -0.5, B: 0.5})
    assert profile.panning[T] == -0.5
    assert VoiceRole.LEAD not in profile.panning


def test_mix_profile_panning_is_immutable_and_copied() -> None:
    source = {T: 0.1}
    profile = MixProfile(panning=source)
    source[T] = 0.9
    assert profile.panning[T] == 0.1
    with pytest.raises(TypeError):
        profile.panning[L] = 0.2  # type: ignore[index]


@pytest.mark.parametrize("pan", [-1.01, 1.5])
def test_mix_profile_rejects_out_of_range_pan(pan: float) -> None:
    with pytest.raises(ValueError, match="pan"):
        MixProfile(panning={T: pan})


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_mix_profile_rejects_non_finite_gain(bad: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        MixProfile(target_gain_db=bad)


def test_default_profiles_are_equal() -> None:
    assert MixProfile() == MixProfile()


def test_track_kinds() -> None:
    assert [kind.name for kind in TrackKind] == ["FULL", "PREDOMINANT", "SOLO", "MINUS"]


def _stems(*roles: VoiceRole) -> tuple[StemMix, ...]:
    return tuple(StemMix(role=role) for role in roles)


def test_full_track_plan() -> None:
    plan = TrackPlan(kind=TrackKind.FULL, inputs=_stems(T, L, BR, B))
    assert plan.target is None
    assert plan.speed == 1
    assert plan.roles == (T, L, BR, B)


def test_predominant_track_plan_uses_profile_gains() -> None:
    profile = MixProfile()
    inputs = tuple(
        StemMix(role=r, gain_db=profile.target_gain_db if r is L else profile.background_gain_db)
        for r in (T, L, BR, B)
    )
    plan = TrackPlan(kind=TrackKind.PREDOMINANT, target=L, inputs=inputs)
    assert [s.gain_db for s in plan.inputs] == [-12.0, 0.0, -12.0, -12.0]


def test_solo_track_plan() -> None:
    plan = TrackPlan(kind=TrackKind.SOLO, target=B, inputs=_stems(B))
    assert plan.roles == (B,)


def test_minus_track_plan() -> None:
    plan = TrackPlan(kind=TrackKind.MINUS, target=T, inputs=_stems(L, BR, B))
    assert T not in plan.roles


@pytest.mark.parametrize(
    ("kind", "target", "roles"),
    [
        (TrackKind.FULL, T, (T, L)),  # FULL must not have a target
        (TrackKind.PREDOMINANT, None, (T, L)),  # needs a target
        (TrackKind.PREDOMINANT, B, (T, L)),  # target missing from inputs
        (TrackKind.SOLO, T, (T, L)),  # solo has exactly one input
        (TrackKind.SOLO, B, (T,)),  # solo input is not the target
        (TrackKind.MINUS, T, (T, L)),  # minus must exclude its target
        (TrackKind.MINUS, None, (L,)),  # needs a target
        (TrackKind.FULL, None, ()),  # no inputs
        (TrackKind.FULL, None, (T, T)),  # duplicate roles
    ],
)
def test_track_plan_rejects_inconsistent_combinations(
    kind: TrackKind, target: VoiceRole | None, roles: tuple[VoiceRole, ...]
) -> None:
    with pytest.raises(ValueError, match=r"track|input|target|SOLO|MINUS|roles"):
        TrackPlan(kind=kind, target=target, inputs=_stems(*roles))


def test_track_plan_speed_is_exact_and_positive() -> None:
    plan = TrackPlan(kind=TrackKind.FULL, inputs=_stems(T), speed=Fraction(3, 4))
    assert plan.speed == Fraction(3, 4)
    with pytest.raises(ValueError, match="speed"):
        TrackPlan(kind=TrackKind.FULL, inputs=_stems(T), speed=Fraction(0))
    with pytest.raises(TypeError, match="Fraction or int"):
        TrackPlan(kind=TrackKind.FULL, inputs=_stems(T), speed=0.75)  # type: ignore[arg-type]


def test_stem_mix_validates_pan() -> None:
    assert StemMix(role=T).pan is None
    with pytest.raises(ValueError, match="pan"):
        StemMix(role=T, pan=2.0)


# --- jobs -----------------------------------------------------------------------------


def test_job_request_defaults() -> None:
    request = JobRequest(musicxml_path=Path("song.musicxml"), output_dir=Path("out"))
    assert request.mix_profile == MixProfile()
    assert request.backend == "manual_openutau"
    assert dict(request.role_assignments) == {}
    assert dict(request.stem_paths) == {}
    assert request.work_dir is None


def test_job_request_role_assignments_are_explicit_and_copied() -> None:
    assignments = {"P1": T, "P2": L}
    request = JobRequest(
        musicxml_path=Path("s.musicxml"), output_dir=Path("o"), role_assignments=assignments
    )
    assignments["P3"] = B
    assert dict(request.role_assignments) == {"P1": T, "P2": L}


def test_job_request_validates_inputs() -> None:
    with pytest.raises(TypeError, match="VoiceRole"):
        JobRequest(
            musicxml_path=Path("s"),
            output_dir=Path("o"),
            role_assignments={"P1": "tenor"},  # type: ignore[dict-item]
        )
    with pytest.raises(ValueError, match="backend"):
        JobRequest(musicxml_path=Path("s"), output_dir=Path("o"), backend="")


def test_job_request_stem_paths_for_external_stems() -> None:
    stems = {r: Path(f"{r.display_name}.wav") for r in VoiceRole}
    request = JobRequest(musicxml_path=Path("s"), output_dir=Path("o"), stem_paths=stems)
    assert request.stem_paths[VoiceRole.BASS] == Path("Bass.wav")


def test_job_result_success() -> None:
    result = JobResult(status=JobStatus.COMPLETED, output_files=[Path("a.mp3")])  # type: ignore[arg-type]
    assert result.succeeded
    assert result.output_files == (Path("a.mp3"),)


def test_job_result_completed_cannot_carry_errors() -> None:
    errors = ValidationResult.of([ValidationIssue(severity=Severity.ERROR, code="X", message="m")])
    with pytest.raises(ValueError, match="validation errors"):
        JobResult(status=JobStatus.COMPLETED, validation=errors)


def test_job_result_failure_needs_a_message() -> None:
    with pytest.raises(ValueError, match="error message"):
        JobResult(status=JobStatus.FAILED)
    failed = JobResult(status=JobStatus.FAILED, error_message="boom")
    assert not failed.succeeded


def test_awaiting_stems_status_exists() -> None:
    assert not JobResult(status=JobStatus.AWAITING_STEMS).succeeded
