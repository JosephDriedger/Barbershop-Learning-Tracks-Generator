"""The production render host, run for real against a generated synthetic voicebank.

No user voicebank is needed, so these run wherever the host has been built (CI included). They are
about the host contract: structured events, stable exit codes, and no silent fallbacks.
"""

import array
import shutil
from pathlib import Path

import pytest

from barbershop_tracks.core.synthesis import VoiceEngineRef
from barbershop_tracks.core.synthesis.openutau import write_ustx
from host_support import HostRun, install_host, run_host
from synth_builders import ROLES, full_lyrics, plan_of
from synthetic_voicebank import SINGER_ID, build_voicebank

pytestmark = pytest.mark.integration

PHONEMIZER = "OpenUtau.Core.DefaultPhonemizer"


@pytest.fixture(scope="module")
def singers(tmp_path_factory: pytest.TempPathFactory) -> Path:
    folder = tmp_path_factory.mktemp("singers")
    build_voicebank(folder)
    return folder


@pytest.fixture
def exe(tmp_path: Path) -> Path:
    return install_host(tmp_path)


def project(
    tmp_path: Path,
    *,
    words: tuple[str, ...] = ("la",) * 4,
    singer: str = SINGER_ID,
    phonemizer: str = PHONEMIZER,
    renderer: str = "WORLDLINE-R",
) -> Path:
    engine = VoiceEngineRef(singer=singer, phonemizer=phonemizer, renderer=renderer)
    plan = plan_of(voices=full_lyrics(words), engine_refs=dict.fromkeys(ROLES, engine))
    path = tmp_path / "case.ustx"
    path.write_bytes(write_ustx(plan).encode())
    return path


def stems(out: Path) -> dict[str, int]:
    return {p.name: p.stat().st_size for p in sorted(out.glob("*.wav"))}


def test_a_successful_render_streams_events_and_ends_with_a_result(
    exe: Path, singers: Path, tmp_path: Path
) -> None:
    run = run_host(exe, project(tmp_path), tmp_path / "out", singers_dir=singers)

    assert run.returncode == 0, run.stderr
    assert run.result["status"] == "ok"
    assert run.events[0]["event"] == "start"
    phases = [e["name"] for e in run.events if e["event"] == "phase"]
    assert phases == ["init", "load_project", "validate", "phonemize", "render"]
    assert any(e["event"] == "progress" for e in run.events)
    assert run.result["openutau_commit"] == "a60ca5830b9064556157245d4bf8f5920d93e5f8"
    assert run.result["singers_found"] == [SINGER_ID]
    assert sorted(stems(tmp_path / "out")) == [
        "case_Baritone.wav",
        "case_Bass.wav",
        "case_Lead.wav",
        "case_Tenor.wav",
    ]
    assert all(size > 1000 for size in stems(tmp_path / "out").values())


def test_a_missing_singer_is_exit_4_with_no_stems(exe: Path, singers: Path, tmp_path: Path) -> None:
    run = run_host(
        exe, project(tmp_path, singer="no-such-singer"), tmp_path / "out", singers_dir=singers
    )
    assert run.returncode == 4
    assert run.result["status"] == "unresolved_singer_phonemizer_or_renderer"
    assert "no-such-singer" in run.result["error"]
    assert stems(tmp_path / "out") == {}


def test_without_a_singers_directory_the_singer_is_not_found(exe: Path, tmp_path: Path) -> None:
    run = run_host(exe, project(tmp_path), tmp_path / "out")
    assert run.returncode == 4
    assert run.result["singers_found"] == []


def test_an_unknown_phonemizer_is_exit_4_not_a_silent_default(
    exe: Path, singers: Path, tmp_path: Path
) -> None:
    run = run_host(
        exe,
        project(tmp_path, phonemizer="Not.A.Real.Phonemizer"),
        tmp_path / "out",
        singers_dir=singers,
    )
    assert run.returncode == 4
    assert "did not resolve" in run.result["error"]
    assert stems(tmp_path / "out") == {}


def test_a_missing_native_library_is_exit_8(exe: Path, singers: Path, tmp_path: Path) -> None:
    (exe.parent / "worldline.dll").unlink()
    run = run_host(exe, project(tmp_path), tmp_path / "out", singers_dir=singers)
    assert run.returncode == 8
    assert run.result["status"] == "native_library_missing"


def test_a_malformed_project_is_exit_3(exe: Path, singers: Path, tmp_path: Path) -> None:
    broken = tmp_path / "broken.ustx"
    broken.write_text("name: [unclosed\n  tracks: : :\n", encoding="utf-8")
    run = run_host(exe, broken, tmp_path / "out", singers_dir=singers)
    assert run.returncode == 3
    assert run.result["status"] == "load_failed"


def test_a_missing_project_file_is_exit_3(exe: Path, singers: Path, tmp_path: Path) -> None:
    run = run_host(exe, tmp_path / "absent.ustx", tmp_path / "out", singers_dir=singers)
    assert run.returncode == 3


def test_a_missing_singers_directory_is_exit_8(exe: Path, tmp_path: Path) -> None:
    run = run_host(exe, project(tmp_path), tmp_path / "out", singers_dir=tmp_path / "nope")
    assert run.returncode == 8
    assert run.result["status"] == "singers_dir_missing"


@pytest.mark.parametrize(
    ("extra", "code"),
    [(("--bogus",), 2), (("--render-timeout-ms", "soon"), 2)],
)
def test_usage_errors_are_exit_2(
    exe: Path, singers: Path, tmp_path: Path, extra: tuple[str, ...], code: int
) -> None:
    run = run_host(exe, project(tmp_path), tmp_path / "out", singers_dir=singers, extra=extra)
    assert run.returncode == code


def test_a_non_empty_output_directory_is_refused(exe: Path, singers: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "leftover.wav").write_bytes(b"x")
    run = run_host(exe, project(tmp_path), out, singers_dir=singers)
    assert run.returncode == 2
    assert (out / "leftover.wav").read_bytes() == b"x"


def test_an_unsupported_alias_renders_empty_stems_without_any_host_error(
    exe: Path, singers: Path, tmp_path: Path
) -> None:
    # Evidence for the M8c stem validation: the host (and OpenUtau) report success here.
    run: HostRun = run_host(
        exe, project(tmp_path, words=("zzz",) * 4), tmp_path / "out", singers_dir=singers
    )
    assert run.returncode == 0
    assert set(stems(tmp_path / "out").values()) == {46}  # a WAV header and no samples


def _samples(path: Path) -> array.array[int]:
    samples: array.array[int] = array.array("h")
    samples.frombytes(path.read_bytes()[44:])  # the host writes a plain 44-byte PCM16 header
    return samples


def test_renders_are_reproducible_and_the_cache_changes_them_by_at_most_one_lsb(
    exe: Path, singers: Path, tmp_path: Path
) -> None:
    case = project(tmp_path, words=("la", "ba", "la", "ba"))
    cache = exe.parent / "Cache"  # OpenUtau's render cache lives beside the runtime copy
    outputs = {}
    for tag, wipe in (("cold1", True), ("cold2", True), ("warm1", False), ("warm2", False)):
        if wipe:
            shutil.rmtree(cache, ignore_errors=True)
        assert run_host(exe, case, tmp_path / tag, singers_dir=singers).returncode == 0
        outputs[tag] = tmp_path / tag
    assert cache.is_dir()
    for name in stems(outputs["cold1"]):
        cold1, cold2 = (outputs[t] / name for t in ("cold1", "cold2"))
        warm1, warm2 = (outputs[t] / name for t in ("warm1", "warm2"))
        assert cold1.read_bytes() == cold2.read_bytes()  # cold runs are bit-identical
        assert warm1.read_bytes() == warm2.read_bytes()  # so are warm runs
        worst = max(abs(a - b) for a, b in zip(_samples(cold1), _samples(warm1), strict=True))
        assert worst <= 1  # measured: the cache stores 16-bit audio, a 1 LSB difference
