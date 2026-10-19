"""Small programs that run one of the tests' fake tools with this Python, on any platform."""

import stat
import sys
from pathlib import Path

PROGRAM_SUFFIX = ".cmd" if sys.platform == "win32" else ""


def write_shim(folder: Path, name: str, script: Path) -> Path:
    """A program ``folder/name`` (``name.cmd`` on Windows) that runs ``script`` with this Python.

    BLT starts such a program the way it starts MuseScore, Audiveris or FFmpeg.
    """
    path = folder / f"{name}{PROGRAM_SUFFIX}"
    if sys.platform == "win32":
        path.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="ascii")
    else:
        path.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="ascii")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path
