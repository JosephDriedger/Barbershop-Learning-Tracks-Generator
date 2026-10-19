import sys
from pathlib import Path
from typing import Any

import pytest

from barbershop_tracks.core.runtime import HostInstallError, ensure_host_runtime
from barbershop_tracks.core.runtime.host_install import COMPLETE_MARKER, HOST_EXE, fingerprint

NATIVE_NAME = "worldline.dll" if sys.platform == "win32" else "libworldline.dylib"


def fake_build(root: Path, *, payload: bytes = b"core-v1") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / HOST_EXE).write_bytes(b"exe")
    (root / "blt-render-host.dll").write_bytes(b"host")
    (root / "OpenUtau.Core.dll").write_bytes(payload)
    (root / NATIVE_NAME).write_bytes(b"native")
    (root / "sub").mkdir(exist_ok=True)
    (root / "sub" / "extra.dll").write_bytes(b"x")
    return root


def test_the_first_call_installs_a_complete_private_copy(tmp_path: Path) -> None:
    binaries = fake_build(tmp_path / "bin")
    runtime = ensure_host_runtime(binaries, tmp_path / "data" / "runtime")
    assert runtime.freshly_installed
    assert runtime.exe == runtime.directory / HOST_EXE
    assert (runtime.directory / COMPLETE_MARKER).is_file()
    assert (runtime.directory / "sub" / "extra.dll").read_bytes() == b"x"
    assert (binaries / HOST_EXE).is_file()  # the shipped binaries are untouched


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
    (target / HOST_EXE).write_bytes(b"truncated")  # no completion marker
    runtime = ensure_host_runtime(binaries, tmp_path / "rt")
    assert runtime.freshly_installed
    assert (runtime.directory / "blt-render-host.dll").read_bytes() == b"host"


def test_missing_binaries_are_a_typed_error(tmp_path: Path) -> None:
    with pytest.raises(HostInstallError) as error:
        ensure_host_runtime(tmp_path / "nothing", tmp_path / "rt")
    assert error.value.code == "HOST_BINARIES_MISSING"
    partial = fake_build(tmp_path / "bin")
    (partial / NATIVE_NAME).unlink()
    with pytest.raises(HostInstallError) as incomplete:
        ensure_host_runtime(partial, tmp_path / "rt")
    assert incomplete.value.code == "HOST_BINARIES_INCOMPLETE"


def test_an_unwritable_runtime_root_is_a_typed_error(tmp_path: Path) -> None:
    blocker = tmp_path / "file-not-dir"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(HostInstallError) as error:
        ensure_host_runtime(fake_build(tmp_path / "bin"), blocker / "runtime")
    assert error.value.code == "HOST_INSTALL_FAILED"


def test_concurrent_first_installs_all_end_with_one_complete_copy(tmp_path: Path) -> None:
    import threading

    binaries = fake_build(tmp_path / "bin")
    for index in range(40):  # make the copy slow enough for installs to overlap
        (binaries / "sub" / f"filler{index}.dll").write_bytes(b"x" * 200_000)
    outcomes: list[Any] = []

    def work() -> None:
        try:
            outcomes.append(ensure_host_runtime(binaries, tmp_path / "rt"))
        except BaseException as error:
            outcomes.append(error)

    threads = [threading.Thread(target=work) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert len(outcomes) == 6
    assert not [o for o in outcomes if isinstance(o, BaseException)], outcomes
    directories = {o.directory for o in outcomes if not isinstance(o, BaseException)}
    assert len(directories) == 1
    (directory,) = directories
    assert (directory / COMPLETE_MARKER).is_file()
    assert (directory / "sub" / "filler39.dll").is_file()
    assert [p.name for p in (tmp_path / "rt").iterdir()] == [directory.name]  # no leftovers


def test_old_idle_host_copies_are_pruned_after_an_upgrade(tmp_path: Path) -> None:
    import os
    import time

    from barbershop_tracks.core.runtime.host_install import STALE_AFTER_SECONDS

    old = ensure_host_runtime(fake_build(tmp_path / "a"), tmp_path / "rt")
    recent = ensure_host_runtime(fake_build(tmp_path / "b", payload=b"core-v2"), tmp_path / "rt")
    abandoned = tmp_path / "rt" / ".install-abc"
    abandoned.mkdir()
    (abandoned / "half.dll").write_bytes(b"x")
    user_folder = tmp_path / "rt" / "not-ours"
    user_folder.mkdir()
    long_ago = time.time() - STALE_AFTER_SECONDS - 3600
    for folder in (old.directory, abandoned, user_folder):
        for path in [*folder.rglob("*"), folder]:
            os.utime(path, (long_ago, long_ago))
    newest = ensure_host_runtime(fake_build(tmp_path / "c", payload=b"core-v3"), tmp_path / "rt")
    assert not old.directory.exists()  # idle for more than a day: pruned
    assert not abandoned.exists()
    assert recent.directory.is_dir()  # a copy a run may still be using is kept
    assert newest.directory.is_dir()
    assert user_folder.is_dir()  # only BLT's own folders are ever touched


def test_a_copy_that_a_concurrent_installer_just_finished_is_not_moved_away(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The interleaving that broke concurrent first starts: our two "is it complete?" checks (before
    before another installer renames its finished copy into place, and the next line then finds
    the target present. That finished copy must be used, not taken for an abandoned attempt."""
    from barbershop_tracks.core.runtime import host_install

    binaries = fake_build(tmp_path / "bin")
    runtime_root = tmp_path / "rt"
    first = ensure_host_runtime(binaries, runtime_root)  # the "other" installer's finished copy
    assert first.freshly_installed
    marker = first.directory / COMPLETE_MARKER

    real_complete = host_install._complete
    calls = {"n": 0}

    def late_complete(target: Path) -> bool:
        calls["n"] += 1
        # the two looks before the target is examined both come "too early"; later looks are real
        return False if calls["n"] <= 2 else real_complete(target)

    monkeypatch.setattr(host_install, "_complete", late_complete)
    second = ensure_host_runtime(binaries, runtime_root)
    assert second.directory == first.directory
    assert not second.freshly_installed
    assert marker.is_file()  # the finished copy was not moved aside or removed
    assert not [p for p in runtime_root.iterdir() if p.name.startswith((".discard-", ".install-"))]
