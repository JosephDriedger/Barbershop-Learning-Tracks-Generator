"""The production render host, run for real against a generated synthetic voicebank.

No user voicebank is needed, so these run wherever the host has been built (CI included). They are
about the host contract: structured events, stable exit codes, and no silent fallbacks.
"""

import array
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from barbershop_tracks.core.synthesis import VoiceEngineRef
from barbershop_tracks.core.synthesis.openutau import write_ustx
from host_support import PINNED_COMMIT, REPO, HostRun, host_environment, install_host, run_host
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
    assert run.result["openutau_commit"] == PINNED_COMMIT + "+blt-patched"
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
    # since M17 the host says why: the lyric has no recording in the voicebank
    assert run.result["unsung_phoneme_count"] == 16  # four voices of four notes
    assert {u["lyric"] for u in run.result["unsung_phonemes"]} == {"zzz"}
    assert {u["reason"] for u in run.result["unsung_phonemes"]} == {"lyric_has_no_sound"}


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


@pytest.mark.parametrize(
    "name",
    [
        "OpenUtau.Plugin.Builtin.ArpasingPlusPhonemizer",
        "OpenUtau.Plugin.Builtin.EnglishCpVPhonemizer",
        "OpenUtau.Core.DiffSinger.DiffSingerARPAPlusEnglishPhonemizer",
    ],
)
def test_phonemizers_that_need_the_unverified_english_plus_data_are_not_in_the_host(
    exe: Path, singers: Path, tmp_path: Path, name: str
) -> None:
    run = run_host(exe, project(tmp_path, phonemizer=name), tmp_path / "out", singers_dir=singers)
    assert run.returncode == 4
    assert "did not resolve" in run.result["error"]
    assert stems(tmp_path / "out") == {}


@pytest.mark.parametrize(
    "name",
    [
        "OpenUtau.Plugin.Builtin.ArpasingPhonemizer",
        "OpenUtau.Plugin.Builtin.EnglishVCCVPhonemizer",
        "OpenUtau.Plugin.Builtin.EnXSampaPhonemizer",
    ],
)
def test_the_cmudict_based_english_phonemizers_still_render(
    exe: Path, singers: Path, tmp_path: Path, name: str
) -> None:
    run = run_host(exe, project(tmp_path, phonemizer=name), tmp_path / "out", singers_dir=singers)
    assert run.returncode == 0, run.result
    assert run.result["status"] == "ok"
    assert len(stems(tmp_path / "out")) == 4


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def edited_project(tmp_path: Path, old: str, new: str) -> Path:
    path = project(tmp_path)
    text = path.read_text(encoding="utf-8")
    assert old in text, old
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return path


TENSION_CURVE = "  curves:\n  - abbr: tenc\n    xs: [0, 480]\n    ys: [{y}, {y}]"


def test_a_project_with_a_tension_curve_is_refused_not_rendered_without_it(
    exe: Path, singers: Path, tmp_path: Path
) -> None:
    """BLT's worldline has no tension effect (docs/worldline-provenance.md): asking is refused."""
    path = edited_project(tmp_path, "  curves: []", TENSION_CURVE.format(y=40))
    run = run_host(exe, path, tmp_path / "out", singers_dir=singers)
    assert run.returncode == 3
    assert run.result["status"] == "unsupported_tension"
    assert "tension curve" in run.result["error"]
    assert stems(tmp_path / "out") == {}


def test_a_changed_default_of_the_tension_curve_is_refused_too(
    exe: Path, singers: Path, tmp_path: Path
) -> None:
    old = "    abbr: tenc\n    type: Curve\n    min: -100\n    max: 100\n    default_value: 0"
    path = edited_project(tmp_path, old, old.replace("default_value: 0", "default_value: 20"))
    run = run_host(exe, path, tmp_path / "out", singers_dir=singers)
    assert run.returncode == 3
    assert run.result["status"] == "unsupported_tension"
    assert "default" in run.result["error"]


def test_a_tension_curve_that_changes_nothing_is_accepted(
    exe: Path, singers: Path, tmp_path: Path
) -> None:
    """An all-zero curve is the neutral tension: it renders as a project without the curve does."""
    # each run needs its own host copy: OpenUtau caches rendered phrases (as 16-bit files, so a
    # cache hit differs
    # by one least-significant bit from a fresh render) beside the exe, and a hit never reaches
    # the native code
    base = tmp_path / "base"
    base.mkdir()
    plain = run_host(install_host(base), project(base), base / "out", singers_dir=singers)
    assert plain.returncode == 0, plain.result
    path = edited_project(tmp_path, "  curves: []", TENSION_CURVE.format(y=0))
    run = run_host(exe, path, tmp_path / "out", singers_dir=singers)
    assert run.returncode == 0, run.result
    assert len(stems(tmp_path / "out")) == 4
    # the same audio, byte for byte: the neutral curve takes the same native path as no curve at all
    assert {n: digest(base / "out" / n) for n in stems(base / "out")} == {
        n: digest(tmp_path / "out" / n) for n in stems(tmp_path / "out")
    }


def test_the_same_project_renders_to_the_same_bytes_every_time(
    exe: Path, singers: Path, tmp_path: Path
) -> None:
    """OpenUtau reuses rendered phrases from a 16-bit cache; a reused one differs by one bit.

    The host discards them first, so a second generation of the same score in the same host copy is
    byte-identical to the first (it used to differ).
    """
    first = run_host(exe, project(tmp_path), tmp_path / "out1", singers_dir=singers)
    assert first.returncode == 0, first.result
    assert first.result["rendered_phrases_discarded"] == 0
    second_dir = tmp_path / "again"
    second_dir.mkdir()
    second = run_host(exe, project(second_dir), second_dir / "out", singers_dir=singers)
    assert second.returncode == 0, second.result
    # the first run's phrases were in the cache
    assert second.result["rendered_phrases_discarded"] > 0
    assert {n: digest(tmp_path / "out1" / n) for n in stems(tmp_path / "out1")} == {
        n: digest(second_dir / "out" / n) for n in stems(second_dir / "out")
    }


# --- what the host contains (M17): the packaged artifact against the reviewed allow-list ---


def inventory_of(exe: Path) -> dict[str, Any]:
    done = subprocess.run(
        [str(exe), "--inventory"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=host_environment(),
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    events: list[dict[str, Any]] = [
        json.loads(line) for line in done.stdout.splitlines() if line.startswith("{")
    ]
    assert events[-1]["event"] == "result", events[-1]
    assert events[-1]["status"] == "ok", events[-1]
    return events[-1]


def test_the_host_contains_exactly_what_the_reviewed_allow_list_names(exe: Path) -> None:
    sys.path.insert(0, str(REPO / "packaging"))
    import verify_host_inventory as vhi
    from barbershop_tracks.core.pipeline.config import ENGLISH_PHONEMIZERS, REMOVED_PHONEMIZERS

    expected = json.loads(vhi.EXPECTED.read_text(encoding="utf-8"))
    actual = inventory_of(exe)
    found = vhi.compare(
        actual,
        expected,
        removed=REMOVED_PHONEMIZERS,
        required=(*ENGLISH_PHONEMIZERS, vhi.DEFAULT_PHONEMIZER),
    )
    assert found == []
    assert actual["g2p_model"] in ("included", "excluded")


def test_the_g2p_check_agrees_with_what_the_host_contains(exe: Path) -> None:
    done = subprocess.run(
        [str(exe), "--g2p-check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=host_environment(),
        timeout=120,
        check=False,
    )
    result = json.loads(done.stdout.strip().splitlines()[-1])
    assert result["g2p_model"] == inventory_of(exe)["g2p_model"]
    assert result["g2p_known_phonemes"] == "hh ah l ow"  # a CMUdict word never needs the model
    if result["g2p_model"] == "included":
        assert result["g2p_phonemes"]  # the model guessed a word that CMUdict lacks
        assert result["onnxruntime"]  # ... on an onnxruntime.dll that was loaded
        # the published host keeps it beside the exe (the check then insists on that); a plain
        # `dotnet build` (CI's development host) keeps it under runtimes/win-x64/native
        if (exe.parent / "onnxruntime.dll").is_file():
            assert done.returncode == 0, result
            assert result["onnxruntime_beside_host"]
    else:  # the variant without the model: no guess, and the native runtime is not even loaded
        assert done.returncode == 0, result
        assert result["g2p_phonemes"] == ""
        assert result["onnxruntime"] is None


@pytest.mark.parametrize("word", ["hello", "blorptastic", "ev'ry"])
def test_a_word_outside_cmudict_never_crashes_the_host(
    exe: Path, singers: Path, tmp_path: Path, word: str
) -> None:
    case = project(
        tmp_path,
        words=("la", word, "la", "la"),
        phonemizer="OpenUtau.Plugin.Builtin.ArpasingPhonemizer",
    )
    run = run_host(exe, case, tmp_path / "out", singers_dir=singers)
    assert run.returncode == 0, run.result
    assert len(stems(tmp_path / "out")) == 4
