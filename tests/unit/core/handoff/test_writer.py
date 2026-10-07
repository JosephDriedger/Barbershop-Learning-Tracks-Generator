"""The transactional writer and the ownership checks: the filesystem safety invariants.

Tests come before cleverness here: each invariant the plan states has its own test.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from barbershop_tracks.core.handoff import (
    MANIFEST_NAME,
    HandoffError,
    owned_files,
    write_package,
)
from barbershop_tracks.core.handoff import writer as writer_module
from barbershop_tracks.core.handoff.manifest import PACKAGE_TYPE, SCHEMA
from handoff_builders import prepared

DIRNAME = "demo.handoff"


def snapshot(directory: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(directory.iterdir())}


def leftovers(parent: Path) -> list[str]:
    return sorted(p.name for p in parent.iterdir() if p.name != DIRNAME)


def install_old(parent: Path) -> dict[str, bytes]:
    """A recognised package (the real thing, built by the writer itself)."""
    old = prepared("demo")
    write_package(parent, DIRNAME, old.files)
    return snapshot(parent / DIRNAME)


def new_files() -> dict[str, bytes]:
    files = dict(prepared("demo").files)
    files["OPENUTAU-STEPS.txt"] += b"changed\n"  # a different package under the same name
    return files


def codes_of(call) -> str:  # type: ignore[no-untyped-def]
    with pytest.raises(HandoffError) as info:
        call()
    return info.value.code


# --- a new destination ---


def test_a_new_destination_succeeds_and_leaves_nothing_else(tmp_path: Path) -> None:
    files = prepared().files
    result = write_package(tmp_path, DIRNAME, files)
    assert result.path == tmp_path / DIRNAME
    assert not result.replaced
    assert snapshot(result.path) == files
    assert leftovers(tmp_path) == []  # no temp or backup directories


def test_a_missing_output_directory_is_created(tmp_path: Path) -> None:
    result = write_package(tmp_path / "a" / "b", DIRNAME, prepared().files)
    assert (result.path / MANIFEST_NAME).is_file()


# --- existing destinations: only a recognised package may be replaced ---


def test_an_existing_unrelated_directory_is_refused_even_with_overwrite(tmp_path: Path) -> None:
    target = tmp_path / DIRNAME
    (target / "sub").mkdir(parents=True)
    (target / "notes.txt").write_text("mine")
    (target / "sub" / "deep.txt").write_text("deeper")
    assert codes_of(lambda: write_package(tmp_path, DIRNAME, prepared().files)) == "HANDOFF_EXISTS"
    assert (
        codes_of(lambda: write_package(tmp_path, DIRNAME, prepared().files, overwrite=True))
        == "HANDOFF_NOT_OURS"
    )
    assert (target / "notes.txt").read_text() == "mine"
    assert (target / "sub" / "deep.txt").read_text() == "deeper"
    assert leftovers(tmp_path) == []


def test_an_existing_empty_directory_is_not_recognised(tmp_path: Path) -> None:
    (tmp_path / DIRNAME).mkdir()
    code = codes_of(lambda: write_package(tmp_path, DIRNAME, prepared().files, overwrite=True))
    assert code == "HANDOFF_NOT_OURS"
    assert (tmp_path / DIRNAME).is_dir()


def good_manifest() -> dict[str, object]:
    return {"schema": SCHEMA, "package_type": PACKAGE_TYPE, "files": [{"name": "a.mid"}]}


@pytest.mark.parametrize(
    "manifest",
    [
        "{not json",
        "[]",
        "null",
        json.dumps({"app": "something else", "files": []}),  # another application's manifest
        json.dumps({**good_manifest(), "schema": "barbershop-tracks.handoff/2"}),  # unsupported
        json.dumps({**good_manifest(), "schema": "barbershop-tracks.handoff"}),  # no version
        json.dumps({**good_manifest(), "schema": "other.handoff/1"}),
        json.dumps({**good_manifest(), "package_type": "other"}),
        json.dumps({**good_manifest(), "files": "a.mid"}),
        json.dumps({**good_manifest(), "files": [{"name": "../escape.txt"}]}),
        json.dumps({**good_manifest(), "files": [{"name": MANIFEST_NAME}]}),
        json.dumps({**good_manifest(), "files": [{"name": "a.mid"}, {"name": "missing.txt"}]}),
    ],
)
def test_a_manifest_that_does_not_prove_ownership_is_refused(tmp_path: Path, manifest: str) -> None:
    target = tmp_path / DIRNAME
    target.mkdir()
    (target / "a.mid").write_bytes(b"x")
    (target / MANIFEST_NAME).write_text(manifest)
    before = snapshot(target)
    code = codes_of(lambda: write_package(tmp_path, DIRNAME, prepared().files, overwrite=True))
    assert code == "HANDOFF_NOT_OURS"
    assert snapshot(target) == before


def test_a_recognised_package_with_an_extra_file_is_refused(tmp_path: Path) -> None:
    install_old(tmp_path)
    (tmp_path / DIRNAME / "precious.txt").write_text("user data")
    code = codes_of(lambda: write_package(tmp_path, DIRNAME, new_files(), overwrite=True))
    assert code == "HANDOFF_NOT_OURS"
    assert (tmp_path / DIRNAME / "precious.txt").read_text() == "user data"


@pytest.mark.parametrize("member", ["demo.mid", "OPENUTAU-STEPS.txt"])
@pytest.mark.parametrize("edit", ["append", "replace_same_size"])
def test_a_hand_edited_package_is_never_overwritten(tmp_path: Path, member: str, edit: str) -> None:
    install_old(tmp_path)
    path = tmp_path / DIRNAME / member
    original = path.read_bytes()
    path.write_bytes(
        original + b"user edit" if edit == "append" else bytes([original[0] ^ 1]) + original[1:]
    )  # the manifest is not updated
    before = snapshot(tmp_path / DIRNAME)
    code = codes_of(lambda: write_package(tmp_path, DIRNAME, new_files(), overwrite=True))
    assert code == "HANDOFF_MODIFIED"
    assert snapshot(tmp_path / DIRNAME) == before  # the user's change survives, byte for byte
    assert leftovers(tmp_path) == []  # no temp or backup directory


def test_a_hand_edited_manifest_entry_is_also_detected(tmp_path: Path) -> None:
    install_old(tmp_path)
    manifest_path = tmp_path / DIRNAME / MANIFEST_NAME
    data = json.loads(manifest_path.read_text())
    data["files"][0]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(data))
    code = codes_of(lambda: write_package(tmp_path, DIRNAME, new_files(), overwrite=True))
    assert code == "HANDOFF_MODIFIED"


def test_a_manifest_without_recorded_integrity_is_not_recognised(tmp_path: Path) -> None:
    install_old(tmp_path)
    manifest_path = tmp_path / DIRNAME / MANIFEST_NAME
    data = json.loads(manifest_path.read_text())
    del data["files"][0]["sha256"]
    manifest_path.write_text(json.dumps(data))
    code = codes_of(lambda: write_package(tmp_path, DIRNAME, new_files(), overwrite=True))
    assert code == "HANDOFF_NOT_OURS"


def test_a_recognised_package_without_overwrite_is_refused_untouched(tmp_path: Path) -> None:
    old = install_old(tmp_path)
    assert codes_of(lambda: write_package(tmp_path, DIRNAME, new_files())) == "HANDOFF_EXISTS"
    assert snapshot(tmp_path / DIRNAME) == old
    assert leftovers(tmp_path) == []


def test_a_recognised_package_with_overwrite_is_replaced_without_leftovers(tmp_path: Path) -> None:
    old = install_old(tmp_path)
    files = new_files()
    result = write_package(tmp_path, DIRNAME, files, overwrite=True)
    assert result.replaced
    assert result.warnings == ()
    assert snapshot(tmp_path / DIRNAME) == files != old
    assert leftovers(tmp_path) == []  # no backup, no temp directory


def test_owned_files_lists_exactly_the_manifest_and_what_it_names(tmp_path: Path) -> None:
    install_old(tmp_path)
    names = owned_files(tmp_path / DIRNAME)
    assert names == tuple(sorted(prepared().files))


# --- failures leave the previous package intact ---


def test_a_failure_while_constructing_the_new_package_leaves_the_old_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = install_old(tmp_path)
    real = writer_module._write_file
    calls: list[Path] = []

    def flaky(path: Path, data: bytes) -> None:
        calls.append(path)
        if len(calls) == 2:
            raise OSError("disk full")
        real(path, data)

    monkeypatch.setattr(writer_module, "_write_file", flaky)
    assert (
        codes_of(lambda: write_package(tmp_path, DIRNAME, new_files(), overwrite=True))
        == "HANDOFF_IO"
    )
    assert snapshot(tmp_path / DIRNAME) == old
    assert leftovers(tmp_path) == []  # the half-written temp directory is gone


def test_a_failed_new_destination_leaves_no_package_and_no_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(path: Path, data: bytes) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(writer_module, "_write_file", boom)
    assert codes_of(lambda: write_package(tmp_path, DIRNAME, prepared().files)) == "HANDOFF_IO"
    assert list(tmp_path.iterdir()) == []


def test_a_package_that_reads_back_wrong_is_never_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = install_old(tmp_path)

    def bad(directory: Path, files: object) -> None:
        raise HandoffError("HANDOFF_VERIFY_FAILED", "x differs")

    monkeypatch.setattr(writer_module, "_read_back", bad)
    code = codes_of(lambda: write_package(tmp_path, DIRNAME, new_files(), overwrite=True))
    assert code == "HANDOFF_VERIFY_FAILED"
    assert snapshot(tmp_path / DIRNAME) == old
    assert leftovers(tmp_path) == []


def test_a_failure_after_the_old_package_moved_aside_restores_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = install_old(tmp_path)
    real = writer_module._rename
    seen: list[tuple[str, str]] = []

    def failing_install(source: Path, destination: Path) -> None:
        seen.append((source.name, destination.name))
        if destination.name == DIRNAME and ".tmp-" in source.name:
            raise OSError("cannot move the new package into place")
        real(source, destination)

    monkeypatch.setattr(writer_module, "_rename", failing_install)
    code = codes_of(lambda: write_package(tmp_path, DIRNAME, new_files(), overwrite=True))
    assert code == "HANDOFF_IO"
    assert any(".bak-" in destination for _, destination in seen)  # it really moved aside first
    assert snapshot(tmp_path / DIRNAME) == old  # and was put back, identical
    assert leftovers(tmp_path) == []


def test_if_the_rollback_itself_fails_the_backup_is_preserved_and_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = install_old(tmp_path)
    real = writer_module._rename

    def failing(source: Path, destination: Path) -> None:
        if destination.name == DIRNAME:
            raise OSError("final name unavailable")
        real(source, destination)

    monkeypatch.setattr(writer_module, "_rename", failing)
    with pytest.raises(HandoffError) as info:
        write_package(tmp_path, DIRNAME, new_files(), overwrite=True)
    assert info.value.code == "HANDOFF_ROLLBACK_FAILED"
    backups = [p for p in tmp_path.iterdir() if ".bak-" in p.name]
    assert len(backups) == 1
    assert backups[0].name in info.value.message
    assert snapshot(backups[0]) == old  # the previous package is intact under its backup name
    assert not [p for p in tmp_path.iterdir() if ".tmp-" in p.name]


def test_a_backup_that_cannot_be_removed_is_a_warning_not_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_old(tmp_path)

    def stuck(directory: Path, names: tuple[str, ...]) -> None:
        raise OSError("file in use")

    monkeypatch.setattr(writer_module, "_remove_owned", stuck)
    files = new_files()
    result = write_package(tmp_path, DIRNAME, files, overwrite=True)
    assert snapshot(tmp_path / DIRNAME) == files  # the new package is installed
    assert result.warnings
    assert ".bak-" in result.warnings[0]  # and the leftover is named, never auto-deleted


def test_a_transient_sharing_violation_is_retried_a_bounded_number_of_times(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(time, "sleep", lambda _: None)

    class Flaky:
        attempts = 0

        def __init__(self, failures: int) -> None:
            self.failures = failures

        def rename(self, destination: object) -> None:
            Flaky.attempts += 1
            if Flaky.attempts <= self.failures:
                raise PermissionError("in use")

    writer_module._rename(Flaky(2), Path("x"))  # type: ignore[arg-type]
    assert Flaky.attempts == 3
    Flaky.attempts = 0
    with pytest.raises(PermissionError):
        writer_module._rename(Flaky(99), Path("x"))  # type: ignore[arg-type]
    assert Flaky.attempts == 4  # bounded


# --- links and reparse points are never followed ---


def make_link(link: Path, target: Path) -> bool:
    try:
        link.symlink_to(target, target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        pass
    if not sys.platform.startswith("win"):  # (a str test: mypy folds a literal platform check)
        return False
    # a junction needs no privilege
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, check=False
    )
    return result.returncode == 0


def test_a_link_at_the_destination_is_refused_not_followed(tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "keep.txt").write_text("keep")
    parent = tmp_path / "out"
    parent.mkdir()
    if not make_link(parent / DIRNAME, elsewhere):
        pytest.skip("cannot create a symlink or junction here")
    for overwrite in (False, True):
        code = codes_of(
            lambda flag=overwrite: write_package(parent, DIRNAME, prepared().files, overwrite=flag)
        )
        assert code in {"HANDOFF_UNSAFE_PATH", "HANDOFF_EXISTS"}
    assert (elsewhere / "keep.txt").read_text() == "keep"
    assert sorted(p.name for p in elsewhere.iterdir()) == ["keep.txt"]


def test_a_link_inside_a_recognised_package_blocks_the_overwrite(tmp_path: Path) -> None:
    install_old(tmp_path)
    package = tmp_path / DIRNAME
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "keep.txt").write_text("keep")
    # replace the instructions file with a directory link that the manifest still names
    (package / "OPENUTAU-STEPS.txt").unlink()
    if not make_link(package / "OPENUTAU-STEPS.txt", elsewhere):
        pytest.skip("cannot create a symlink or junction here")
    code = codes_of(lambda: write_package(tmp_path, DIRNAME, new_files(), overwrite=True))
    assert code == "HANDOFF_NOT_OURS"
    assert (elsewhere / "keep.txt").read_text() == "keep"
