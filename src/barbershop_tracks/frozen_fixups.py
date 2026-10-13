"""Things the frozen program does before it imports anything heavy.

NumPy's wheel imports a copy of Microsoft's C++ runtime that its builder renamed with a hash
(``numpy.libs/msvcp140-<hash>.dll``). BLT does not ship Microsoft's runtime, so the installer copies
the PC's own ``msvcp140.dll`` under that name (``packaging/installer.iss``). If that copy is missing
later (an antivirus removed it, the program folder was copied somewhere without it, the installer's
copy step failed), NumPy fails to import with a long message that tells the user nothing.

``restore_for_frozen_app`` makes the same copy again, from the same system file, before NumPy is
imported. It is a copy of a file the user already has, not a redistribution; it changes nothing
when the file is there; and it never raises: if the copy cannot be made, the normal import error
is what the user sees.
"""

import json
import os
import shutil
import sys
from pathlib import Path

MANIFEST = "blt-runtime-copies.json"


def restore(internal: Path, system_dir: Path) -> list[str]:
    """Copy each missing file named in the manifest from ``system_dir``; returns what it made."""
    try:
        wanted = json.loads((internal / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    made: list[str] = []
    root = internal.resolve()
    for relative, system_name in wanted.items():
        target = (internal / relative).resolve()
        source = system_dir / system_name
        if root not in target.parents or target.exists() or not source.is_file():
            continue  # outside the program folder (never), already there, or nothing to copy from
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        except OSError:
            continue
        made.append(relative)
    return made


def restore_for_frozen_app() -> list[str]:
    """In the frozen program only: ``restore`` for its own folder and this PC's System32."""
    if not getattr(sys, "frozen", False):
        return []
    internal = getattr(sys, "_MEIPASS", None)
    if not internal:
        return []
    system = Path(os.environ.get("SYSTEMROOT", "C:/Windows")) / "System32"
    try:
        return restore(Path(internal), system)
    except Exception:  # never stop the program from starting because of this
        return []
