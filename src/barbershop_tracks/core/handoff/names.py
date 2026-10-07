"""Package and file naming: safe on Windows, deterministic, ASCII."""

import re

from barbershop_tracks.core.handoff.errors import HandoffError

MAX_NAME_LENGTH = 64
PACKAGE_SUFFIX = ".handoff"
MANIFEST_NAME = "handoff-manifest.json"
INSTRUCTIONS_NAME = "OPENUTAU-STEPS.txt"

_UNSAFE = re.compile(r"[^A-Za-z0-9_-]")
_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def sanitize_name(text: str) -> str:
    """ASCII letters, digits, ``-`` and ``_`` only (anything else becomes ``_``)."""
    name = _UNSAFE.sub("_", text.strip())[:MAX_NAME_LENGTH].strip("_.")
    if not name or not any(ch.isalnum() for ch in name):
        raise HandoffError("HANDOFF_NAME_INVALID", f"{text!r} leaves no usable file name")
    if name.split(".")[0].upper() in _RESERVED:
        raise HandoffError("HANDOFF_NAME_INVALID", f"{name!r} is a reserved Windows device name")
    return name


def package_dirname(name: str) -> str:
    return name + PACKAGE_SUFFIX


def midi_filename(name: str) -> str:
    return name + ".mid"
