"""Transactional render staging.

One isolated directory per job, ``.staging-<job>-<pid>``, holding a marker with the owner's pid and
process start time. Results become visible only through :func:`publish_directory`, an atomic
rename of a fully validated directory; a failed or cancelled job leaves ``outputs`` untouched.

A directory is *stale* when its owner is gone: no process with that pid, or one that started at a
different moment (a recycled pid). A directory whose marker cannot be read is stale only once it
is old enough that a live job could not still be writing it. Nothing active is ever listed.
"""

import json
import os
import shutil
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from barbershop_tracks.core.runtime.process_identity import is_same_process, process_start_time

STAGING_PREFIX = ".staging-"
MARKER_NAME = "staging.json"
UNREADABLE_MARKER_GRACE_SECONDS = 120.0


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
    start_time: int | None = None  # the owner's process start time; None if it could not be read


def owner_alive(marker: StagingMarker) -> bool:
    return is_same_process(marker.pid, marker.start_time)


@dataclass(frozen=True, slots=True)
class StagingArea:
    path: Path
    marker: StagingMarker

    @classmethod
    def create(
        cls,
        root: Path,
        job: str,
        *,
        pid: int | None = None,
        start_time: int | None = None,
    ) -> "StagingArea":
        if not job or any(c in job for c in "/\\:") or job.startswith("."):
            raise StagingError("STAGING_JOB_NAME", f"unusable job name {job!r}")
        owner = os.getpid() if pid is None else pid
        marker = StagingMarker(
            job,
            owner,
            time.time(),
            process_start_time(owner) if pid is None and start_time is None else start_time,
        )
        path = root / f"{STAGING_PREFIX}{job}-{marker.pid}"
        if path.exists():
            raise StagingError("STAGING_EXISTS", f"{path.name} already exists")
        root.mkdir(parents=True, exist_ok=True)
        # build under a hidden name and rename, so a directory that carries the staging prefix
        # always has its marker already (a concurrent cleanup never sees a half-made one)
        building = root / f".creating-{uuid.uuid4().hex}"
        building.mkdir()
        (building / MARKER_NAME).write_text(
            json.dumps(
                {
                    "job": marker.job,
                    "pid": marker.pid,
                    "created": marker.created,
                    "start_time": marker.start_time,
                }
            ),
            encoding="utf-8",
        )
        try:
            building.rename(path)
        except OSError:
            shutil.rmtree(building, ignore_errors=True)
            raise StagingError("STAGING_EXISTS", f"{path.name} already exists") from None
        return cls(path, marker)


def read_marker(path: Path) -> StagingMarker | None:
    try:
        raw = json.loads((path / MARKER_NAME).read_text(encoding="utf-8"))
        start = raw.get("start_time")
        return StagingMarker(
            str(raw["job"]),
            int(raw["pid"]),
            float(raw["created"]),
            None if start is None else int(start),
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def find_stale(
    root: Path,
    is_alive: Callable[[StagingMarker], bool] = owner_alive,
    *,
    now: float | None = None,
) -> list[Path]:
    """Staging directories whose owner is gone (never an active job's)."""
    if not root.is_dir():
        return []
    clock = time.time() if now is None else now
    stale: list[Path] = []
    for child in sorted(root.iterdir()):
        if not (child.is_dir() and child.name.startswith(STAGING_PREFIX)):
            continue
        marker = read_marker(child)
        if marker is None:
            try:
                age = clock - child.stat().st_mtime
            except OSError:
                continue
            if age >= UNREADABLE_MARKER_GRACE_SECONDS:
                stale.append(child)
        elif not is_alive(marker):
            stale.append(child)
    return stale


def remove_staging(path: Path) -> None:
    """Delete a staging directory; refuses anything not named like one."""
    if not path.name.startswith(STAGING_PREFIX):
        raise StagingError("STAGING_NOT_STAGING", f"{path.name} is not a staging directory")
    shutil.rmtree(path)


def cleanup_stale(
    root: Path,
    is_alive: Callable[[StagingMarker], bool] = owner_alive,
    *,
    now: float | None = None,
) -> list[Path]:
    """Remove every stale staging directory; returns those removed. Failures are skipped."""
    removed: list[Path] = []
    for path in find_stale(root, is_alive, now=now):
        try:
            remove_staging(path)
        except OSError:
            continue
        removed.append(path)
    return removed


def publish_directory(source: Path, destination: Path, *, replace: bool = False) -> None:
    """Atomically make ``source`` visible as ``destination``.

    With ``replace`` an existing destination is moved aside first and restored if the final rename
    fails, so a failed publication never costs the user their previous result.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        try:
            source.rename(destination)
        except OSError as error:
            if destination.exists():  # lost a race with another job for the same destination
                raise StagingError(
                    "PUBLISH_DESTINATION_EXISTS", f"{destination} already exists"
                ) from error
            raise StagingError(
                "PUBLISH_FAILED", f"cannot publish to {destination}: {error}"
            ) from error
        return
    if not replace:
        raise StagingError("PUBLISH_DESTINATION_EXISTS", f"{destination} already exists")
    aside = destination.with_name(f".replaced-{uuid.uuid4().hex}")
    try:
        destination.rename(aside)
    except OSError as error:
        raise StagingError("PUBLISH_FAILED", f"cannot move {destination} aside: {error}") from error
    try:
        source.rename(destination)
    except OSError as error:
        aside.rename(destination)  # put the previous result back
        raise StagingError("PUBLISH_FAILED", f"cannot publish to {destination}: {error}") from error
    shutil.rmtree(aside, ignore_errors=True)


def publish(area: StagingArea, destination: Path) -> None:
    """Atomically move a *validated* whole staging directory to ``destination`` (must not exist)."""
    if destination.exists():
        raise StagingError("PUBLISH_DESTINATION_EXISTS", f"{destination} already exists")
    (area.path / MARKER_NAME).unlink()
    publish_directory(area.path, destination)
