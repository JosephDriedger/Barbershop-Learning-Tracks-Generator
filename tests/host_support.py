"""Helpers for tests that run the real render host (``blt-render-host``) as a subprocess.

The host is built by ``host/build.ps1`` into the git-ignored ``research-output/host/build``; point
``BLT_HOST_DIR`` at another build directory to override. Tests skip when no build exists.
"""

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from barbershop_tracks.core.runtime import ensure_host_runtime
from barbershop_tracks.core.runtime.host_install import HOST_EXE

REPO = Path(__file__).resolve().parents[1]
# OpenUtau 0.1.565; the host is built from a patched copy and says so (host/build.ps1)
PINNED_COMMIT = "a60ca5830b9064556157245d4bf8f5920d93e5f8"
DEFAULT_BUILD = REPO / "research-output" / "host" / "build"
LOCAL_SDK = REPO / "research-output" / "spike" / "dotnet"


def build_dir() -> Path | None:
    configured = os.environ.get("BLT_HOST_DIR")
    candidate = Path(configured) if configured else DEFAULT_BUILD
    return candidate if (candidate / HOST_EXE).is_file() else None


def host_processes(root: Path) -> int:
    """How many render hosts run from a copy of the host somewhere below ``root``."""
    if sys.platform == "win32":
        script = (
            "(Get-Process blt-render-host -ErrorAction SilentlyContinue | "
            f"Where-Object {{ $_.Path -like '{root}*' }} | Measure-Object).Count"
        )
        done = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            check=True,
        )
        return int(done.stdout.strip() or "0")
    else:
        # macOS reports the real path of a temporary folder (/private/var/... for /var/...)
        prefixes = {str(root), str(root.resolve())}
        listing = subprocess.run(
            ["ps", "-axo", "command="], capture_output=True, text=True, check=True
        )
        return sum(
            1
            for line in listing.stdout.splitlines()
            if HOST_EXE in line and any(line.startswith(prefix) for prefix in prefixes)
        )


def host_environment() -> dict[str, str]:
    environment = dict(os.environ)
    if os.environ.get("BLT_HOST_SELF_CONTAINED"):  # a self-contained host needs no .NET at all
        environment.pop("DOTNET_ROOT", None)
        return environment
    if "DOTNET_ROOT" not in environment and LOCAL_SDK.is_dir():
        environment["DOTNET_ROOT"] = str(LOCAL_SDK)
    return environment


def require_host() -> Path:
    found = build_dir()
    if found is None:
        pytest.skip("no render host build (run host/build.ps1 or set BLT_HOST_DIR)")
    return found


def install_host(tmp_path: Path) -> Path:
    """A private writable copy of the host (portable mode writes beside the exe); its exe path."""
    return ensure_host_runtime(require_host(), tmp_path / "runtime").exe


@dataclass(frozen=True, slots=True)
class HostRun:
    returncode: int
    events: list[dict[str, Any]]
    stderr: str

    @property
    def result(self) -> dict[str, Any]:
        assert self.events, "the host printed nothing"
        assert self.events[-1]["event"] == "result", self.events[-1]
        return self.events[-1]


def run_host(
    exe: Path,
    project: Path,
    out: Path,
    *,
    singers_dir: Path | None = None,
    extra: tuple[str, ...] = (),
    timeout: float = 300,
) -> HostRun:
    out.mkdir(parents=True, exist_ok=True)
    command = [str(exe), "--project", str(project), "--out", str(out), "--base", "case"]
    if singers_dir is not None:
        command += ["--singers-dir", str(singers_dir)]
    done = subprocess.run(
        [*command, *extra],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=host_environment(),
        timeout=timeout,
        check=False,
    )
    events = [json.loads(line) for line in done.stdout.splitlines() if line.startswith("{")]
    return HostRun(done.returncode, events, done.stderr)


def remove_tree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
