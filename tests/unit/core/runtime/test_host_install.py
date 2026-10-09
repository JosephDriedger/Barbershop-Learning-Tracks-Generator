from pathlib import Path

import pytest

from barbershop_tracks.core.runtime import HostInstallError, ensure_host_runtime
from barbershop_tracks.core.runtime.host_install import COMPLETE_MARKER, fingerprint


def fake_build(root: Path, *, payload: bytes = b"core-v1") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "blt-render-host.exe").write_bytes(b"exe")
    (root / "blt-render-host.dll").write_bytes(b"host")
    (root / "OpenUtau.Core.dll").write_bytes(payload)
    (root / "worldline.dll").write_bytes(b"native")
    (root / "sub").mkdir(exist_ok=True)
    (root / "sub" / "extra.dll").write_bytes(b"x")
    return root


def test_the_first_call_installs_a_complete_private_copy(tmp_path: Path) -> None:
    binaries = fake_build(tmp_path / "bin")
    runtime = ensure_host_runtime(binaries, tmp_path / "data" / "runtime")
    assert runtime.freshly_installed
    assert runtime.exe == runtime.directory / "blt-render-host.exe"
    assert (runtime.directory / COMPLETE_MARKER).is_file()
    assert (runtime.directory / "sub" / "extra.dll").read_bytes() == b"x"
    assert (binaries / "blt-render-host.exe").is_file()  # the shipped binaries are untouched


def test_the_second_call_reuses_the_copy_and_keeps_data_written_beside_it(tmp_path: Path) -> None:
    binaries = fake_build(tmp_path / "bin")
    first = ensure_host_runtime(binaries, tmp_path / "rt")
    (first.directory / "Cache").mkdir()
    (first.directory / "Cache" / "keep.wav").write_bytes(b"c")
    second = ensure_host_runtime(binaries, tmp_path / "rt")
    assert not second.freshly_installed
    assert second.directory == first.directory
    assert (second.directory / "Cache" / "keep.wav").is_file()


def test_a_changed_host_build_gets_its_own_directory(tmp_path: Path) -> None:
    old = ensure_host_runtime(fake_build(tmp_path / "a"), tmp_path / "rt")
    new = ensure_host_runtime(fake_build(tmp_path / "b", payload=b"core-v2"), tmp_path / "rt")
    assert old.directory != new.directory
    assert old.directory.is_dir()  # a job still running from the old copy is never disturbed


def test_an_incomplete_earlier_copy_is_never_reused(tmp_path: Path) -> None:
    binaries = fake_build(tmp_path / "bin")
    target = tmp_path / "rt" / f"host-{fingerprint(binaries)[:16]}"
    target.mkdir(parents=True)
    (target / "blt-render-host.exe").write_bytes(b"truncated")  # no completion marker
    runtime = ensure_host_runtime(binaries, tmp_path / "rt")
    assert runtime.freshly_installed
    assert (runtime.directory / "blt-render-host.dll").read_bytes() == b"host"


def test_missing_binaries_are_a_typed_error(tmp_path: Path) -> None:
    with pytest.raises(HostInstallError) as error:
        ensure_host_runtime(tmp_path / "nothing", tmp_path / "rt")
    assert error.value.code == "HOST_BINARIES_MISSING"
    partial = fake_build(tmp_path / "bin")
    (partial / "worldline.dll").unlink()
    with pytest.raises(HostInstallError) as incomplete:
        ensure_host_runtime(partial, tmp_path / "rt")
    assert incomplete.value.code == "HOST_BINARIES_INCOMPLETE"


def test_an_unwritable_runtime_root_is_a_typed_error(tmp_path: Path) -> None:
    blocker = tmp_path / "file-not-dir"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(HostInstallError) as error:
        ensure_host_runtime(fake_build(tmp_path / "bin"), blocker / "runtime")
    assert error.value.code == "HOST_INSTALL_FAILED"
