"""How a voicebank is named: its folder path below the voices folder.

OpenUtau knows a voicebank by ``Path.GetRelativePath(singers folder, voicebank folder)``, so the
names of the folders are joined by the separator of the platform the host runs on: a backslash on
Windows (``Pack\\Bank``), a slash on macOS (``Pack/Bank``). The name a track stores must be exactly
that.
"""

import os
from collections.abc import Iterable

SINGER_SEPARATOR = os.sep


def join_singer_name(parts: Iterable[str]) -> str:
    """The name the singing engine uses for a voicebank at this folder path."""
    return SINGER_SEPARATOR.join(parts)


def split_singer_name(name: str) -> list[str]:
    """The folder names in a voicebank's name."""
    return name.split(SINGER_SEPARATOR)
