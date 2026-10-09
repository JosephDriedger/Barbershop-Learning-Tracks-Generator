"""The backend's contract, driven with a fake host process (no OpenUtau, no voicebank)."""

import os
import sys
import threading
import time
from pathlib import Path

import pytest

from barbershop_tracks.core.rendering import (
    CancelToken,
    OpenUtauRenderBackend,
    OutputValidationError,
    ProjectValidationError,
    RenderCancelledError,
    RenderConfigurationError,
    RenderResult,
    RenderSettings,
    RenderTimeoutError,
    SynthesisError,
)
from barbershop_tracks.core.runtime import RuntimeLayout, StagingArea
from barbershop_tracks.core.runtime.process_identity import process_start_time
from barbershop_tracks.core.synthesis import SynthesisPlan
from barbershop_tracks.models import VoiceRole
from synth_builders import ROLES, full_lyrics, plan_of, refs, sung

FAKE = Path(__file__).resolve().parents[3] / "fake_render_host.py"


class Env:
    def __init__(self, tmp_path: Path) -> None:
        self.layout = RuntimeLayout.under(tmp_path / "bin", tmp_path / "data")
        self.singers = tmp_path / "singers"
        self.singers.mkdir()
        self.destination = tmp_path / "data" / "outputs" / "song"

    def backend(self, mode: str = "ok", **overrides: object) -> OpenUtauRenderBackend:
        env = {"FAKE_HOST_MODE": mode, **{k: str(v) for k, v in overrides.items() if k.isupper()}}
        options = {k: v for k, v in overrides.items() if not k.isupper()}
        settings = RenderSettings(
            layout=self.layout,
            singers_dir=self.singers,
            host_command=(sys.executable, str(FAKE)),
            extra_env=env,
            timeout_seconds=30,
            poll_seconds=0.01,
            **options,  # type: ignore[arg-type]
        )
        return OpenUtauRenderBackend(settings)

    def staging_entries(self) -> list[str]:
        root = self.layout.staging
        return sorted(p.name for p in root.iterdir()) if root.is_dir() else []


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def plan() -> SynthesisPlan:
    return plan_of(voices=full_lyrics(("la",) * 4), engine_refs=refs())


def code_of(call: object) -> str:
    assert callable(call)
    with pytest.raises(Exception) as info:  # noqa: PT011 - the type is asserted by the callers
        call()
    return str(getattr(info.value, "code", type(info.value).__name__))


# --- success ---


def test_a_ready_plan_is_rendered_validated_and_published(env: Env) -> None:
    events: list[dict[str, object]] = []
    result = env.backend().render(plan(), env.destination, on_event=events.append)

    assert isinstance(result, RenderResult)
    assert sorted(p.name for p in env.destination.iterdir()) == [
        "Baritone.wav",
        "Bass.wav",
        "Lead.wav",
        "Tenor.wav",
    ]
    assert set(result.stems) == set(ROLES)
    assert all(report.path.parent == env.destination for report in result.stems.values())
    assert result.host_result["status"] == "ok"
    assert events[0]["event"] == "start"
    assert events[-1]["event"] == "result"
    assert any(e["event"] == "progress" for e in events)
    assert env.staging_entries() == []  # nothing left behind


# --- host failures map to typed errors, and publish nothing ---


@pytest.mark.parametrize(
    ("mode", "error", "code"),
    [
        ("fail:3:load_failed:bad yaml", ProjectValidationError, "HOST_PROJECT_REJECTED"),
        ("fail:4:unresolved:no singer", RenderConfigurationError, "HOST_UNRESOLVED"),
        ("fail:2:usage:oops", RenderConfigurationError, "HOST_USAGE"),
        ("fail:8:native_library_missing:worldline", RenderConfigurationError, "HOST_ENVIRONMENT"),
        ("fail:5:render_reported_errors:boom", SynthesisError, "HOST_FAILED"),
        ("fail:10:internal_error:bug", SynthesisError, "HOST_FAILED"),
        ("fail:7:phonemize_timeout:slow", RenderTimeoutError, "HOST_PHONEMIZE_TIMEOUT"),
        ("fail:9:render_timeout:slow", RenderTimeoutError, "HOST_RENDER_TIMEOUT"),
        ("crash", SynthesisError, "HOST_NO_RESULT"),
    ],
)
def test_host_exit_codes_become_typed_errors(
    env: Env, mode: str, error: type[Exception], code: str
) -> None:
    with pytest.raises(error) as info:
        env.backend(mode).render(plan(), env.destination)
    assert getattr(info.value, "code", None) == code
    details = getattr(info.value, "details", {})
    assert "exit_code" in details
    assert not env.destination.exists()
    assert env.staging_entries() == []


def test_a_host_that_dies_reports_its_stderr(env: Env) -> None:
    with pytest.raises(SynthesisError) as info:
        env.backend("crash").render(plan(), env.destination)
    assert "boom" in info.value.details["stderr"]


# --- success exit but unacceptable output ---


@pytest.mark.parametrize(
    ("mode", "code"),
    [
        ("missing_wav", "STEM_FILES_MISMATCH"),
        ("extra_file", "STEM_FILES_MISMATCH"),
        ("corrupt_wav", "STEM_NOT_DECODABLE"),
        ("truncated_wav", "STEM_NOT_DECODABLE"),
        ("empty_wav", "STEM_EMPTY"),
        ("silent_wav", "STEM_SILENT"),
        ("silent_note", "STEM_NOTE_SILENT"),
        ("short_wav", "STEM_DURATION"),
        ("long_wav", "STEM_DURATION"),
        ("wrong_rate", "STEM_FORMAT_UNSUPPORTED"),
    ],
)
def test_a_successful_exit_with_bad_output_publishes_nothing(
    env: Env, mode: str, code: str
) -> None:
    with pytest.raises(OutputValidationError) as info:
        env.backend(mode).render(plan(), env.destination)
    assert info.value.code == code
    assert not env.destination.exists()
    assert env.staging_entries() == []


LATE_TENOR = {
    **full_lyrics(("la",) * 4),
    "tenor": sung(VoiceRole.TENOR, ["la"] * 4, start=4),  # four quarters of leading silence
}


def test_leading_silence_is_preserved_when_the_host_keeps_it(env: Env) -> None:
    result = env.backend().render(plan_of(voices=LATE_TENOR, engine_refs=refs()), env.destination)
    onset = result.stems[VoiceRole.TENOR].first_audible_seconds
    assert onset is not None
    assert abs(onset - 2.4) < 0.01  # 4 quarters at 100 BPM


@pytest.mark.parametrize(
    ("mode", "code"),
    [("shifted_early", "STEM_ORIGIN"), ("no_leading_silence", "STEM_DURATION")],
)
def test_a_stem_that_lost_its_place_on_the_timeline_is_refused(
    env: Env, mode: str, code: str
) -> None:
    late = plan_of(voices=LATE_TENOR, engine_refs=refs())
    with pytest.raises(OutputValidationError) as info:
        env.backend(mode).render(late, env.destination)
    assert info.value.code == code
    assert not env.destination.exists()


# --- the plan is checked before any process starts ---


def test_a_plan_that_is_not_ready_never_reaches_the_host(env: Env) -> None:
    unready = plan_of(
        voices={
            **full_lyrics(("la",) * 4),
            "tenor": sung(VoiceRole.TENOR, ["la", None, "la", "la"]),
        },
        engine_refs=refs(),
    )
    with pytest.raises(ProjectValidationError) as info:
        env.backend().render(unready, env.destination)
    assert info.value.code == "PLAN_NOT_READY"
    assert not env.layout.staging.exists()  # not even a staging directory was made


def test_a_missing_singers_directory_is_a_configuration_error(env: Env) -> None:
    env.singers.rmdir()
    with pytest.raises(RenderConfigurationError) as info:
        env.backend().render(plan(), env.destination)
    assert info.value.code == "SINGERS_DIR_MISSING"


def test_a_missing_host_binary_is_a_configuration_error(env: Env) -> None:
    settings = RenderSettings(layout=env.layout, singers_dir=env.singers)
    with pytest.raises(RenderConfigurationError) as info:
        OpenUtauRenderBackend(settings).render(plan(), env.destination)
    assert info.value.code == "HOST_BINARIES_MISSING"


def test_an_unlaunchable_host_command_is_a_configuration_error(env: Env) -> None:
    settings = RenderSettings(
        layout=env.layout, singers_dir=env.singers, host_command=(str(env.singers / "nope.exe"),)
    )
    with pytest.raises(RenderConfigurationError) as info:
        OpenUtauRenderBackend(settings).render(plan(), env.destination)
    assert info.value.code == "HOST_LAUNCH_FAILED"
    assert env.staging_entries() == []


# --- cancellation and timeout end the whole owned tree and leave nothing ---


def wait_for(path: Path, seconds: float = 20.0) -> str:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.exists() and path.read_text(encoding="utf-8"):
            return path.read_text(encoding="utf-8")
        time.sleep(0.02)
    raise AssertionError(f"{path.name} never appeared")


def gone(pid: int, started: int | None) -> bool:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        current = process_start_time(pid)
        if current is None or current != started:
            return True
        time.sleep(0.05)
    return False


def test_cancelling_a_hung_render_ends_the_tree_and_discards_partial_output(
    env: Env, tmp_path: Path
) -> None:
    pid_file = tmp_path / "child.pid"
    token = CancelToken()
    outcome: list[BaseException] = []

    def work() -> None:
        try:
            env.backend("hang", FAKE_HOST_CHILD_PID_FILE=pid_file).render(
                plan(), env.destination, cancel=token
            )
        except BaseException as error:
            outcome.append(error)

    thread = threading.Thread(target=work)
    thread.start()
    child = int(wait_for(pid_file))
    started = process_start_time(child)
    assert started is not None  # the grandchild really is running
    partial = list(env.layout.staging.rglob("*.wav"))
    assert partial  # and a partially written WAV exists in the staging area

    token.cancel()
    thread.join(timeout=30)

    assert not thread.is_alive()
    assert isinstance(outcome[0], RenderCancelledError)
    assert gone(child, started)
    assert env.staging_entries() == []
    assert not env.destination.exists()


def test_cancelling_before_the_start_does_nothing(env: Env) -> None:
    token = CancelToken()
    token.cancel()
    with pytest.raises(RenderCancelledError):
        env.backend().render(plan(), env.destination, cancel=token)
    assert not env.layout.staging.exists()


def test_a_timeout_ends_the_tree_and_discards_partial_output(env: Env, tmp_path: Path) -> None:
    pid_file = tmp_path / "child.pid"
    settings = RenderSettings(
        layout=env.layout,
        singers_dir=env.singers,
        host_command=(sys.executable, str(FAKE)),
        extra_env={"FAKE_HOST_MODE": "hang", "FAKE_HOST_CHILD_PID_FILE": str(pid_file)},
        timeout_seconds=1.5,
        poll_seconds=0.01,
    )
    with pytest.raises(RenderTimeoutError) as info:
        OpenUtauRenderBackend(settings).render(plan(), env.destination)
    assert info.value.code == "RENDER_TIMEOUT"
    child = int(pid_file.read_text(encoding="utf-8"))
    assert gone(child, None)
    assert env.staging_entries() == []
    assert not env.destination.exists()


# --- transactional publication ---


def test_a_failed_attempt_leaves_the_previous_result_untouched(env: Env) -> None:
    env.backend().render(plan(), env.destination)
    before = {p.name: p.read_bytes() for p in env.destination.iterdir()}
    with pytest.raises(OutputValidationError):
        env.backend("silent_wav").render(plan(), env.destination, replace=True)
    with pytest.raises(SynthesisError):
        env.backend("crash").render(plan(), env.destination, replace=True)
    assert {p.name: p.read_bytes() for p in env.destination.iterdir()} == before


def test_an_existing_result_is_not_overwritten_unless_asked(env: Env) -> None:
    env.backend().render(plan(), env.destination)
    with pytest.raises(RenderConfigurationError) as info:
        env.backend().render(plan(), env.destination)
    assert info.value.code == "PUBLISH_DESTINATION_EXISTS"
    env.backend().render(plan(), env.destination, replace=True)
    assert env.staging_entries() == []


# --- concurrency ---


def test_concurrent_renders_do_not_collide(env: Env) -> None:
    destinations = [env.destination.parent / f"song{i}" for i in range(4)]
    results: dict[int, object] = {}

    def work(index: int) -> None:
        try:
            results[index] = env.backend("ok", FAKE_HOST_DELAY=0.4).render(
                plan(), destinations[index]
            )
        except BaseException as error:
            results[index] = error

    threads = [threading.Thread(target=work, args=(i,)) for i in range(4)]
    for thread in threads:
        thread.start()
    time.sleep(0.2)
    assert len(env.staging_entries()) > 1  # genuinely overlapping, each in its own directory
    for thread in threads:
        thread.join(timeout=60)
    assert all(isinstance(r, RenderResult) for r in results.values()), results
    assert len({r.job for r in results.values() if isinstance(r, RenderResult)}) == 4
    for destination in destinations:
        assert len(list(destination.iterdir())) == 4
    assert env.staging_entries() == []


def test_two_jobs_for_one_destination_publish_exactly_one(env: Env) -> None:
    results: list[object] = []

    def work() -> None:
        try:
            results.append(env.backend("ok", FAKE_HOST_DELAY=0.3).render(plan(), env.destination))
        except BaseException as error:
            results.append(error)

    threads = [threading.Thread(target=work) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    wins = [r for r in results if isinstance(r, RenderResult)]
    losses = [r for r in results if isinstance(r, RenderConfigurationError)]
    assert len(wins) == 1
    assert len(losses) == 1
    assert losses[0].code == "PUBLISH_DESTINATION_EXISTS"
    assert len(list(env.destination.iterdir())) == 4


# --- stale staging recovery ---


def test_a_new_render_clears_staging_left_by_a_dead_owner_but_not_an_active_one(env: Env) -> None:
    dead = StagingArea.create(env.layout.staging, "dead", pid=2_000_000_000, start_time=1)
    (dead.path / "partial.wav").write_bytes(b"x")
    live = StagingArea.create(env.layout.staging, "live")  # this very process
    recycled = StagingArea.create(
        env.layout.staging,
        "recycled",
        pid=os.getpid(),
        start_time=(live.marker.start_time or 0) + 1,
    )
    env.backend().render(plan(), env.destination)
    assert not dead.path.exists()
    assert not recycled.path.exists()
    assert live.path.exists()  # an active job's staging directory is never touched
