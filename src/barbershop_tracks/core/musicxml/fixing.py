"""Putting a score in front of a person so they can correct it, in the program meant for that.

A score with errors (a recognised PDF above all: a bar short of notes, a voice split in two) cannot
be repaired by BLT, which never guesses music. The person repairs it in a notation program and
opens the corrected file here again. This module only makes that easy: it gives the score BLT read
from a PDF a name a person recognises, starts MuseScore on a file, and finds the corrected score the
person saved, so that the learning tracks are made from it. It changes no music.
"""

import os
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from barbershop_tracks.core.musicxml.convert import clean_environment, find_musescore

_TRIES = 20

# how each kind of conversion names the copy a person corrects (Conversion.kind): a score read
# from a PDF or recognised from a picture. A MuseScore project is the person's own file.
COPY_LABELS = {"recognition": "recognised", "pdf-reading": "from PDF"}

# the files a notation program saves a corrected score as, the one BLT reads best first
SCORE_SUFFIXES = (".mscz", ".musicxml", ".mxl", ".xml")

# a file changed less than this long ago may still be being written
_SETTLE_SECONDS = 1.0


def editable_copy(
    converted: Path, original: Path, fallback: Path | None = None, label: str = "recognised"
) -> Path:
    """A copy of converted MusicXML named after the file it came from, to open and correct.

    ``Hymn (recognised).musicxml`` beside ``Hymn.pdf`` (``label`` says how it was read); in
    ``fallback`` if that folder cannot be written. A copy that already exists with the same content
    is reused, and one with different content (a person's own file) is never overwritten: the next
    free name is taken. If nothing can be written the converted file itself is returned.
    """
    data = converted.read_bytes()
    suffix = converted.suffix.lower()
    for folder in (original.parent, fallback):
        if folder is None:
            continue
        for number in range(1, _TRIES + 1):
            name = label if number == 1 else f"{label} {number}"
            target = folder / f"{original.stem} ({name}){suffix}"
            try:
                if not target.exists():
                    target.write_bytes(data)
                    return target
                if target.read_bytes() == data:
                    return target
            except OSError:
                break  # this folder cannot be written; try the next
    return converted


def open_in_musescore(path: Path, environ: Mapping[str, str] | None = None) -> Path | None:
    """Start MuseScore on ``path`` without waiting for it; the program used, or None if not found.

    The program is started apart from BLT: without BLT's own Qt and Python variables, and it keeps
    running if BLT is closed.
    """
    env = os.environ if environ is None else environ
    program = find_musescore(env)
    if program is None:
        return None
    command = [str(program), str(path)]
    try:
        if sys.platform == "win32":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(
                command,
                cwd=path.parent,
                env=clean_environment(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
            )
        else:
            subprocess.Popen(
                command,
                cwd=path.parent,
                env=clean_environment(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
    except OSError:
        return None
    return program


def musescore_score_folders(environ: Mapping[str, str] | None = None) -> list[Path]:
    """Where MuseScore 4 offers to save a score by default: its Scores folder in Documents (also
    when OneDrive keeps Documents)."""
    env = os.environ if environ is None else environ
    homes = [Path.home()]
    for variable in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        if env.get(variable):
            homes.append(Path(env[variable]))
    folders: list[Path] = []
    for home in homes:
        for documents in (home / "Documents", home / "Documents" / "Documents"):
            folder = documents / "MuseScore4" / "Scores"
            if folder not in folders:
                folders.append(folder)
    return folders


def saved_correction(
    opened: Path, since: float, folders: Sequence[Path] = (), now: float | None = None
) -> Path | None:
    """The score the person saved after opening ``opened`` to correct it at ``since`` (a time
    stamp); None while there is none.

    It is ``opened`` itself, saved again, or a score of the same name saved as another kind of file
    (MuseScore saves an opened MusicXML file as a ``.mscz`` project) beside it or in one of
    ``folders``. A MuseScore project comes first, then the most recent. A file still being written
    (changed within the last second) is not taken yet.
    """
    moment = time.time() if now is None else now
    found: list[tuple[int, float, Path]] = []
    seen: set[Path] = set()
    for folder in (opened.parent, *folders):
        for suffix in SCORE_SUFFIXES:
            path = folder / f"{opened.stem}{suffix}"
            if path in seen:
                continue
            seen.add(path)
            try:
                changed = path.stat().st_mtime
            except OSError:
                continue
            if changed <= since or changed > moment - _SETTLE_SECONDS:
                continue
            found.append((SCORE_SUFFIXES.index(suffix), -changed, path))
    if not found:
        return None
    return min(found)[2]
