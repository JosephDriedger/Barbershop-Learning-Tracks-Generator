"""A plain-text report of how this installation is set up, for support and for ``blt diagnostics``.

Nothing here reads the user's scores or voicebank contents; it lists where things are and whether
they are there. Paths are the user's own (a home folder name may appear), so the GUI offers the
report to copy rather than sending it anywhere.
"""

import platform
import sys
from pathlib import Path

from barbershop_tracks import __version__
from barbershop_tracks.core.pipeline import (
    SHIPPED_RENDERERS,
    ResolvedConfig,
    config_path,
    discover_singers,
    load_config_file,
    resolve_config,
)
from barbershop_tracks.core.runtime.host_install import (
    HOST_EXE,
    RUNTIME_PREFIX,
    HostInstallError,
    fingerprint,
)
from barbershop_tracks.core.runtime.vcruntime import runtime_status


def _where(config: ResolvedConfig, key: str) -> str:
    return config.sources.get(key, "default")


def _host_lines(config: ResolvedConfig) -> list[str]:
    host = config.host_binaries
    if host is None:
        return [
            "render host:   NOT FOUND (reinstall BLT, or set the host folder in Advanced settings)"
        ]
    lines = [f"render host:   {host}  [{_where(config, 'host_dir')}]"]
    if not (host / HOST_EXE).is_file():
        return [*lines, f"               {HOST_EXE} is MISSING from that folder"]
    try:
        copy = config.layout.runtime / f"{RUNTIME_PREFIX}{fingerprint(host)[:16]}"
    except HostInstallError as error:
        return [*lines, f"               incomplete: {error.message}"]
    state = "installed" if copy.is_dir() else "not installed yet (created on the first generation)"
    return [*lines, f"runtime copy:  {copy}  [{state}]"]


def collect(config: ResolvedConfig) -> list[str]:
    """The report, one line per fact."""
    frozen = bool(getattr(sys, "frozen", False))
    lines = [
        f"BLT Music Generator {__version__}",
        f"program:       {sys.executable}  [{'installed build' if frozen else 'source checkout'}]",
        f"python:        {platform.python_version()}",
        f"windows:       {platform.platform()}",
        f"vc runtime:    Microsoft Visual C++ {runtime_status().text}",
        f"config file:   {config_path()}  [{'exists' if config_path().is_file() else 'none'}]",
        f"data folder:   {config.layout.data}  [{_where(config, 'data_dir')}]",
    ]
    singers = config.singers_dir
    if singers is None:
        lines.append("voices:        NOT SET (choose the folder with your voicebanks)")
    elif not singers.is_dir():
        lines.append(f"voices:        {singers} does not exist  [{_where(config, 'singers_dir')}]")
    else:
        found = discover_singers(singers)
        lines.append(
            f"voices:        {singers}  [{_where(config, 'singers_dir')}], {len(found)} found"
        )
    lines += _host_lines(config)
    if config.ffmpeg is None:
        lines.append(
            "ffmpeg:        not found (WAV works; MP3 needs FFmpeg, which BLT does not include)"
        )
    else:
        usable = "ok" if Path(config.ffmpeg).is_file() else "MISSING"
        lines.append(f"ffmpeg:        {config.ffmpeg}  [{_where(config, 'ffmpeg')}, {usable}]")
    lines.append(
        f"voice engine:  {config.renderer} (this build supports {', '.join(SHIPPED_RENDERERS)})"
    )
    lines.append(f"pronunciation: {config.phonemizer}")
    return lines


def report() -> str:
    """The report for the current user's configuration."""
    config = resolve_config(load_config_file(config_path()))
    return "\n".join(collect(config)) + "\n"
