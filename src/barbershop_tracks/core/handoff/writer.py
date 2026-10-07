"""Transactional package writing: build elsewhere, verify, then rename into place.

Guarantees (and their limits, stated accurately):

* The final name never holds a half-written package: files are written into a temporary sibling
  directory (same volume), read back and compared, and only then renamed.
* An existing destination is refused unless ``overwrite`` and it is positively one of ours
  (``ownership.owned_files``). It is never deleted before the new package is complete.
* Replacement is: old package renamed to a backup name, new package renamed into place, backup
  removed. If the second rename fails, the backup is renamed back. Two renames are not one atomic
  step: on a hard crash between them neither name exists (the backup directory still holds the old
  package and is reported by its name, never auto-deleted).
* We only ever remove what we created (the temporary directory) or what we verified to be ours (the
  backup of a recognised package, by its known file names, then ``rmdir``; never a recursive delete
  of anything we did not make).
"""

import os
import shutil
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from barbershop_tracks.core.handoff.errors import HandoffError
from barbershop_tracks.core.handoff.ownership import is_link_or_reparse, owned_files


@dataclass(frozen=True, slots=True)
class WriteResult:
    path: Path
    replaced: bool
    warnings: tuple[str, ...] = ()


def _rename(source: Path, destination: Path) -> None:
    """``os.rename`` with a short bounded retry for transient Windows sharing violations."""
    delay = 0.05
    for attempt in range(4):
        try:
            source.rename(destination)
            return
        except PermissionError:
            if attempt == 3:
                raise
            time.sleep(delay)
            delay *= 2


def _write_file(path: Path, data: bytes) -> None:
    with path.open("xb") as handle:  # exclusive: never overwrites
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _read_back(directory: Path, files: Mapping[str, bytes]) -> None:
    present = sorted(child.name for child in directory.iterdir())
    if present != sorted(files):
        raise HandoffError("HANDOFF_VERIFY_FAILED", f"unexpected contents written: {present}")
    for name, data in files.items():
        if (directory / name).read_bytes() != data:
            raise HandoffError("HANDOFF_VERIFY_FAILED", f"{name} reads back differently")


def _remove_owned(directory: Path, names: tuple[str, ...]) -> None:
    for name in names:
        (directory / name).unlink()
    directory.rmdir()


def write_package(
    parent: Path, dirname: str, files: Mapping[str, bytes], *, overwrite: bool = False
) -> WriteResult:
    try:
        return _write(Path(parent), dirname, files, overwrite)
    except HandoffError:
        raise
    except OSError as error:
        raise HandoffError("HANDOFF_IO", f"filesystem error: {error}") from error


def _write(parent: Path, dirname: str, files: Mapping[str, bytes], overwrite: bool) -> WriteResult:
    parent.mkdir(parents=True, exist_ok=True)
    if not parent.is_dir():
        raise HandoffError("HANDOFF_IO", f"{parent} is not a directory")
    final = parent / dirname
    exists = os.path.lexists(final)
    previous: tuple[str, ...] = ()
    if exists:
        if is_link_or_reparse(final):
            raise HandoffError("HANDOFF_UNSAFE_PATH", f"{dirname} is a link; it was not followed")
        if not overwrite:
            raise HandoffError(
                "HANDOFF_EXISTS", f"{dirname} already exists (use --overwrite to replace a package)"
            )
        previous = owned_files(final)  # refuses anything not positively ours

    temp = Path(tempfile.mkdtemp(prefix=f"{dirname}.tmp-", dir=parent))
    installed = False
    backup: Path | None = None
    try:
        for name, data in files.items():
            _write_file(temp / name, data)
        _read_back(temp, files)  # verified on disk before it can ever appear under its final name
        if exists:
            backup = parent / f"{dirname}.bak-{temp.name.rsplit('-', 1)[-1]}"
            _rename(final, backup)
            try:
                _rename(temp, final)
            except BaseException as failure:
                try:
                    _rename(backup, final)
                except OSError as rollback:
                    raise HandoffError(
                        "HANDOFF_ROLLBACK_FAILED",
                        f"the previous package is preserved as {backup.name}: {rollback}",
                    ) from failure
                raise
        else:
            if os.path.lexists(final):
                raise HandoffError("HANDOFF_EXISTS", f"{dirname} appeared while writing")
            _rename(temp, final)
        installed = True
    finally:
        if not installed:
            shutil.rmtree(temp, ignore_errors=True)  # only the directory we created

    warnings: list[str] = []
    if backup is not None:
        try:
            _remove_owned(backup, previous)
        except OSError as error:
            warnings.append(f"the previous package remains as {backup.name}: {error}")
    return WriteResult(path=final, replaced=exists, warnings=tuple(warnings))
