r"""Install the render host into a BLT-owned, user-writable runtime directory (M8a layout choice).

OpenUtau.Core in "portable" mode keeps its data (cache, prefs, logs, even a ``Singers`` folder)
beside the process executable, so the shipped read-only host cannot run in place (measured: it
fails with ``UnauthorizedAccessException`` from a read-only directory). Its "installed" mode
instead writes into the user's own ``Documents\OpenUtau``, shared with the OpenUtau GUI and
impossible to reset without touching the user's data. BLT therefore copies the *host binaries*
(about 94 MB, never a voicebank) once per host version into ``<data>/runtime/host-<fingerprint>/``
and runs it there in portable mode, pointing it at the user's singers with ``--singers-dir``
(OpenUtau's supported additional-singers preference). The copy is built beside its destination
and renamed into place, so an interrupted install never leaves a half-populated runtime that
looks complete.
"""

import hashlib
import json
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

HOST_EXE = "blt-render-host.exe"
COMPLETE_MARKER = "blt-runtime-complete.json"
RUNTIME_PREFIX = "host-"
_FINGERPRINT_FILES = ("blt-render-host.dll", "OpenUtau.Core.dll", "worldline.dll")


class HostInstallError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class HostRuntime:
    directory: Path
    exe: Path
    fingerprint: str
    freshly_installed: bool


def fingerprint(binaries: Path) -> str:
    """Identify a host build: every file's relative name and size, plus the key files' contents."""
    if not (binaries / HOST_EXE).is_file():
        raise HostInstallError("HOST_BINARIES_MISSING", f"{HOST_EXE} not found in {binaries}")
    digest = hashlib.sha256()
    for path in sorted(p for p in binaries.rglob("*") if p.is_file()):
        digest.update(f"{path.relative_to(binaries).as_posix()}:{path.stat().st_size}\n".encode())
    for name in _FINGERPRINT_FILES:
        target = binaries / name
        if not target.is_file():
            raise HostInstallError("HOST_BINARIES_INCOMPLETE", f"{name} not found in {binaries}")
        digest.update(target.read_bytes())
    return digest.hexdigest()


def ensure_host_runtime(binaries: Path, runtime_root: Path) -> HostRuntime:
    """Return a complete, writable copy of the host; install it first when this build is new."""
    identity = fingerprint(binaries)
    target = runtime_root / f"{RUNTIME_PREFIX}{identity[:16]}"
    marker = target / COMPLETE_MARKER
    if marker.is_file() and (target / HOST_EXE).is_file():
        return HostRuntime(target, target / HOST_EXE, identity, freshly_installed=False)
    try:
        runtime_root.mkdir(parents=True, exist_ok=True)
        partial = runtime_root / f".install-{uuid.uuid4().hex}"
        shutil.copytree(binaries, partial)
        (partial / COMPLETE_MARKER).write_text(
            json.dumps({"fingerprint": identity, "source": binaries.name}), encoding="utf-8"
        )
        if target.exists():  # an earlier, incomplete attempt: never reuse it
            shutil.rmtree(target)
        try:
            partial.replace(target)
        except OSError:
            # a concurrent installer won the rename; use theirs if it is complete
            shutil.rmtree(partial, ignore_errors=True)
            if not (marker.is_file() and (target / HOST_EXE).is_file()):
                raise
            return HostRuntime(target, target / HOST_EXE, identity, freshly_installed=False)
    except OSError as error:
        raise HostInstallError(
            "HOST_INSTALL_FAILED", f"cannot install the render host under {runtime_root}: {error}"
        ) from error
    return HostRuntime(target, target / HOST_EXE, identity, freshly_installed=True)
