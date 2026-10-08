"""Transactional render staging (the contract; process orchestration is built in M8).

One isolated directory per job, ``.staging-<job>-<pid>``, holding a marker file. Results become
visible only through :func:`publish`, an atomic rename of the fully validated directory; a failed
or cancelled job leaves nothing in ``outputs``. Directories whose owner process is gone are
*stale* and can be listed and removed.
"""

import json
import os
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

STAGING_PREFIX = ".staging-"
MARKER_NAME = "staging.json"


class StagingError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class StagingMarker:
    job: str
    pid: int
    created: float


@dataclass(frozen=True, slots=True)
class StagingArea:
    path: Path
    marker: StagingMarker

    @classmethod
    def create(cls, root: Path, job: str, *, pid: int | None = None) -> "StagingArea":
        if not job or any(c in job for c in "/\\:") or job.startswith("."):
            raise StagingError("STAGING_JOB_NAME", f"unusable job name {job!r}")
        marker = StagingMarker(job, os.getpid() if pid is None else pid, time.time())
        path = root / f"{STAGING_PREFIX}{job}-{marker.pid}"
        root.mkdir(parents=True, exist_ok=True)
        try:
            path.mkdir()
        except FileExistsError:
            raise StagingError("STAGING_EXISTS", f"{path.name} already exists") from None
        (path / MARKER_NAME).write_text(
            json.dumps({"job": marker.job, "pid": marker.pid, "created": marker.created}),
            encoding="utf-8",
        )
        return cls(path, marker)


def read_marker(path: Path) -> StagingMarker | None:
    try:
        raw = json.loads((path / MARKER_NAME).read_text(encoding="utf-8"))
        return StagingMarker(str(raw["job"]), int(raw["pid"]), float(raw["created"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def find_stale(root: Path, is_alive: Callable[[int], bool]) -> list[Path]:
    """Staging directories whose owner is gone, or whose marker is unreadable (never live)."""
    if not root.is_dir():
        return []
    stale: list[Path] = []
    for child in sorted(root.iterdir()):
        if not (child.is_dir() and child.name.startswith(STAGING_PREFIX)):
            continue
        marker = read_marker(child)
        if marker is None or not is_alive(marker.pid):
            stale.append(child)
    return stale


def remove_staging(path: Path) -> None:
    """Delete a staging directory; refuses anything not named like one."""
    if not path.name.startswith(STAGING_PREFIX):
        raise StagingError("STAGING_NOT_STAGING", f"{path.name} is not a staging directory")
    shutil.rmtree(path)


def publish(area: StagingArea, destination: Path) -> None:
    """Atomically move a *validated* staging directory to ``destination`` (must not exist)."""
    if destination.exists():
        raise StagingError("PUBLISH_DESTINATION_EXISTS", f"{destination} already exists")
    (area.path / MARKER_NAME).unlink()
    destination.parent.mkdir(parents=True, exist_ok=True)
    area.path.replace(destination)
