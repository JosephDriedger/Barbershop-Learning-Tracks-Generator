"""The frozen program remakes NumPy's renamed copy of the PC's MSVCP140 if it has gone missing."""

import json
import shutil
from pathlib import Path

import pytest

from barbershop_tracks import frozen_fixups

NAME = "numpy.libs/msvcp140-0123456789abcdef0123456789abcdef.dll"


def _layout(tmp_path: Path, manifest: object | None = None) -> tuple[Path, Path]:
    internal = tmp_path / "app" / "_internal"
    internal.mkdir(parents=True)
    system = tmp_path / "System32"
    system.mkdir()
    (system / "msvcp140.dll").write_bytes(b"the PC's own file")
    if manifest is not None:
        (internal / frozen_fixups.MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    return internal, system


def test_a_missing_copy_is_made_from_the_system_file(tmp_path: Path) -> None:
    internal, system = _layout(tmp_path, {NAME: "msvcp140.dll"})
    assert frozen_fixups.restore(internal, system) == [NAME]
    assert (internal / NAME).read_bytes() == b"the PC's own file"


def test_an_existing_copy_is_left_alone(tmp_path: Path) -> None:
    internal, system = _layout(tmp_path, {NAME: "msvcp140.dll"})
    (internal / "numpy.libs").mkdir()
    (internal / NAME).write_bytes(b"installed earlier")
    assert frozen_fixups.restore(internal, system) == []
    assert (internal / NAME).read_bytes() == b"installed earlier"


def test_nothing_happens_without_a_manifest_or_without_the_system_file(tmp_path: Path) -> None:
    internal, system = _layout(tmp_path)
    assert frozen_fixups.restore(internal, system) == []
    (internal / frozen_fixups.MANIFEST).write_text(json.dumps({NAME: "msvcp140.dll"}))
    (system / "msvcp140.dll").unlink()
    assert frozen_fixups.restore(internal, system) == []
    assert not (internal / NAME).exists()


def test_a_damaged_manifest_is_ignored(tmp_path: Path) -> None:
    internal, system = _layout(tmp_path)
    (internal / frozen_fixups.MANIFEST).write_text("{not json", encoding="utf-8")
    assert frozen_fixups.restore(internal, system) == []


@pytest.mark.parametrize(
    "relative", ["../outside.dll", "../../outside.dll", "numpy.libs/../../outside.dll"]
)
def test_it_never_writes_outside_the_program_folder(tmp_path: Path, relative: str) -> None:
    internal, system = _layout(tmp_path, {relative: "msvcp140.dll"})
    assert frozen_fixups.restore(internal, system) == []
    assert not (tmp_path / "app" / "outside.dll").exists()
    assert not (tmp_path / "outside.dll").exists()


def test_a_read_only_program_folder_is_not_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    internal, system = _layout(tmp_path, {NAME: "msvcp140.dll"})

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("read-only")

    monkeypatch.setattr(shutil, "copyfile", refuse)
    assert frozen_fixups.restore(internal, system) == []


def test_outside_the_frozen_program_it_does_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr("sys.frozen", raising=False)
    assert frozen_fixups.restore_for_frozen_app() == []
