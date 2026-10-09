"""The Python backend driving the real render host with a generated synthetic voicebank.

Nothing here needs a user voicebank. What these tests show is that the backend's contract holds with
the genuine process: typed errors, validation of real WAV output (including OpenUtau's silent
rendering of an unsupported alias), cancellation and timeouts that really end the host, concurrent
jobs, and repeated cold and warm runs.
"""

import array
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest

from barbershop_tracks.core.rendering import (
    CancelToken,
    OpenUtauRenderBackend,
    OutputValidationError,
    RenderCancelledError,
    RenderConfigurationError,
    RenderResult,
    RenderSettings,
    RenderTimeoutError,
)
from barbershop_tracks.core.runtime import RuntimeLayout
from barbershop_tracks.core.synthesis import SynthesisPlan, VoiceEngineRef
from barbershop_tracks.models import VoiceRole
from host_support import host_environment, require_host
from synth_builders import ROLES, full_lyrics, plan_of, sung
from synthetic_voicebank import SINGER_ID, build_voicebank

pytestmark = pytest.mark.integration

PHONEMIZER = "OpenUtau.Core.DefaultPhonemizer"


class Rig:
    def __init__(self, root: Path) -> None:
        self.layout = RuntimeLayout.under(root / "bin", root / "data")
        self.singers = root / "singers"
        build_voicebank(self.singers)
        self.root = root

    def backend(self, **options: object) -> OpenUtauRenderBackend:
        settings = RenderSettings(
            layout=self.layout,
            singers_dir=self.singers,
            host_binaries=require_host(),
            extra_env={k: v for k, v in host_environment().items() if k == "DOTNET_ROOT"},
            **options,  # type: ignore[arg-type]
        )
        return OpenUtauRenderBackend(settings)

    @property
    def runtime_dirs(self) -> list[Path]:
        return sorted(self.layout.runtime.glob("host-*"))

    def staging_entries(self) -> list[str]:
        root = self.layout.staging
        return sorted(p.name for p in root.iterdir()) if root.is_dir() else []


@pytest.fixture(scope="module")
def shared(tmp_path_factory: pytest.TempPathFactory) -> Rig:
    require_host()
    return Rig(tmp_path_factory.mktemp("rig"))


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)


def make_plan(
    words: tuple[str, ...] = ("la", "ba", "la", "ba"),
    *,
    singer: str = SINGER_ID,
    phonemizer: str = PHONEMIZER,
    voices: dict[str, list] | None = None,  # type: ignore[type-arg]
) -> SynthesisPlan:
    engine = VoiceEngineRef(singer=singer, phonemizer=phonemizer, renderer="WORLDLINE-R")
    return plan_of(voices=voices or full_lyrics(words), engine_refs=dict.fromkeys(ROLES, engine))


def host_processes(runtime: Path) -> int:
    script = (
        "(Get-Process blt-render-host -ErrorAction SilentlyContinue | "
        f"Where-Object {{ $_.Path -like '{runtime}*' }} | Measure-Object).Count"
    )
    done = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        check=True,
    )
    return int(done.stdout.strip() or "0")


def no_hosts_soon(runtime: Path) -> bool:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if host_processes(runtime) == 0:
            return True
        time.sleep(0.2)
    return False


def samples(path: Path) -> array.array[int]:
    out: array.array[int] = array.array("h")
    out.frombytes(path.read_bytes()[44:])
    return out


# --- success ---


def test_a_real_render_is_validated_and_published(shared: Rig, tmp_path: Path) -> None:
    plan = make_plan()
    events: list[dict[str, object]] = []
    result = shared.backend().render(plan, tmp_path / "song", on_event=events.append)

    assert sorted(p.name for p in (tmp_path / "song").iterdir()) == [
        "Baritone.wav",
        "Bass.wav",
        "Lead.wav",
        "Tenor.wav",
    ]
    for report in result.stems.values():
        assert report.duration_seconds == pytest.approx(2.4, abs=0.01)
        assert report.first_audible_seconds is not None
        assert report.first_audible_seconds < 0.1
        assert report.notes_checked == 4
        assert (report.sample_rate, report.bit_depth, report.channels) == (44100, 16, 1)
    assert [e["name"] for e in events if e["event"] == "phase"] == [
        "init",
        "load_project",
        "validate",
        "phonemize",
        "render",
    ]
    assert result.host_result["openutau_commit"] == "a60ca5830b9064556157245d4bf8f5920d93e5f8"
    assert shared.staging_entries() == []


def test_leading_silence_is_kept_in_real_output(shared: Rig, tmp_path: Path) -> None:
    voices = {**full_lyrics(("la",) * 4), "tenor": sung(VoiceRole.TENOR, ["la", "ba"] * 2, start=4)}
    result = shared.backend().render(make_plan(voices=voices), tmp_path / "song")
    tenor = result.stems[VoiceRole.TENOR]
    assert tenor.duration_seconds == pytest.approx(4.8, abs=0.01)
    # the first note starts at 2.4 s; OpenUtau's sound starts about 50 ms earlier (the oto
    # preutterance). The stem is not shifted to compensate.
    assert tenor.first_audible_seconds is not None
    assert 2.25 <= tenor.first_audible_seconds <= 2.45


# --- configuration problems are errors, never fallbacks ---


def test_a_missing_singer_is_a_configuration_error(shared: Rig, tmp_path: Path) -> None:
    with pytest.raises(RenderConfigurationError) as info:
        shared.backend().render(make_plan(singer="no-such-singer"), tmp_path / "song")
    assert info.value.code == "HOST_UNRESOLVED"
    assert "no-such-singer" in info.value.message
    assert not (tmp_path / "song").exists()
    assert shared.staging_entries() == []


def test_a_missing_phonemizer_is_a_configuration_error(shared: Rig, tmp_path: Path) -> None:
    with pytest.raises(RenderConfigurationError) as info:
        shared.backend().render(make_plan(phonemizer="Not.A.Real.Phonemizer"), tmp_path / "song")
    assert info.value.code == "HOST_UNRESOLVED"
    assert "did not resolve" in info.value.message
    assert not (tmp_path / "song").exists()


def test_a_missing_native_library_is_a_configuration_error(rig: Rig, tmp_path: Path) -> None:
    rig.backend().render(make_plan(), tmp_path / "first")  # installs the runtime copy
    (rig.runtime_dirs[0] / "worldline.dll").unlink()
    with pytest.raises(RenderConfigurationError) as info:
        rig.backend().render(make_plan(), tmp_path / "second")
    assert info.value.code == "HOST_ENVIRONMENT"
    assert "worldline.dll" in info.value.message
    assert not (tmp_path / "second").exists()


# --- OpenUtau reports success while rendering nothing ---


def test_an_unsupported_alias_that_renders_empty_files_is_caught(
    shared: Rig, tmp_path: Path
) -> None:
    with pytest.raises(OutputValidationError) as info:
        shared.backend().render(make_plan(("zzz",) * 4), tmp_path / "song")
    assert info.value.code == "STEM_EMPTY"
    assert not (tmp_path / "song").exists()
    assert shared.staging_entries() == []


def test_one_unsupported_alias_among_good_ones_is_named(shared: Rig, tmp_path: Path) -> None:
    with pytest.raises(OutputValidationError) as info:
        shared.backend().render(make_plan(("la", "zzz", "ba", "la")), tmp_path / "song")
    assert info.value.code == "STEM_NOTE_SILENT"
    assert info.value.details["notes"] == [1]


# --- cancellation and timeout end the real host ---


def test_cancelling_a_real_render_ends_the_host(rig: Rig, tmp_path: Path) -> None:
    rig.backend().render(make_plan(), tmp_path / "warmup")  # installs the runtime; time-free below
    token = CancelToken()

    def on_event(event: dict[str, object]) -> None:
        if event.get("event") == "phase" and event.get("name") == "init":
            token.cancel()

    with pytest.raises(RenderCancelledError):
        rig.backend().render(
            make_plan(("ba", "la", "ba", "la")), tmp_path / "song", cancel=token, on_event=on_event
        )
    assert no_hosts_soon(rig.runtime_dirs[0])
    assert not (tmp_path / "song").exists()
    assert rig.staging_entries() == []


def test_a_timeout_ends_the_real_host(rig: Rig, tmp_path: Path) -> None:
    rig.backend().render(make_plan(), tmp_path / "warmup")
    with pytest.raises(RenderTimeoutError) as info:
        rig.backend(timeout_seconds=0.4).render(make_plan(("ba",) * 4), tmp_path / "song")
    assert info.value.code == "RENDER_TIMEOUT"
    assert no_hosts_soon(rig.runtime_dirs[0])
    assert not (tmp_path / "song").exists()
    assert rig.staging_entries() == []


# --- concurrency and reproducibility ---


def test_concurrent_real_renders_share_one_runtime_without_collisions(
    shared: Rig, tmp_path: Path
) -> None:
    words = [("la", "ba", "la", "ba"), ("ba", "la", "ba", "la"), ("la", "la", "ba", "ba")]
    outcomes: dict[int, object] = {}

    def work(index: int) -> None:
        try:
            outcomes[index] = shared.backend().render(
                make_plan(words[index]), tmp_path / f"song{index}"
            )
        except BaseException as error:
            outcomes[index] = error

    threads = [threading.Thread(target=work, args=(i,)) for i in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=300)
    assert all(isinstance(o, RenderResult) for o in outcomes.values()), outcomes
    assert len({o.job for o in outcomes.values() if isinstance(o, RenderResult)}) == 3
    for index in range(3):
        assert len(list((tmp_path / f"song{index}").glob("*.wav"))) == 4
    assert shared.staging_entries() == []


def test_repeated_cold_and_warm_runs_are_stable(rig: Rig, tmp_path: Path) -> None:
    plan = make_plan()
    results: dict[str, Path] = {}
    cache: Path | None = None
    for tag in ("cold1", "cold2", "warm1", "warm2"):
        if cache is not None and tag.startswith("cold"):
            shutil.rmtree(cache)
        rig.backend().render(plan, tmp_path / tag)
        cache = rig.runtime_dirs[0] / "Cache"
        results[tag] = tmp_path / tag
        if tag == "cold1":
            assert cache.is_dir()
    for role in ("Tenor", "Lead", "Baritone", "Bass"):
        name = f"{role}.wav"
        assert (results["cold1"] / name).read_bytes() == (results["cold2"] / name).read_bytes()
        assert (results["warm1"] / name).read_bytes() == (results["warm2"] / name).read_bytes()
        worst = max(
            abs(a - b)
            for a, b in zip(
                samples(results["cold1"] / name), samples(results["warm1"] / name), strict=True
            )
        )
        assert worst <= 1  # the render cache stores 16-bit audio


def test_a_failed_second_attempt_keeps_the_first_result(rig: Rig, tmp_path: Path) -> None:
    destination = tmp_path / "song"
    rig.backend().render(make_plan(), destination)
    before = {p.name: p.read_bytes() for p in destination.iterdir()}
    with pytest.raises(OutputValidationError):
        rig.backend().render(make_plan(("zzz",) * 4), destination, replace=True)
    assert {p.name: p.read_bytes() for p in destination.iterdir()} == before
