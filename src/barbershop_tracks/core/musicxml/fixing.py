"""Putting a score in front of a person so they can correct it, in the program meant for that.

A score with errors (a recognised PDF above all: a bar short of notes, a voice split in two) cannot
be repaired by BLT, which never guesses music. The person repairs it in a notation program and
opens the corrected file here again. This module only makes that easy: it gives a recognised score
a name a person recognises, and starts MuseScore on a file. It changes no music.
"""

import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

from barbershop_tracks.core.musicxml.convert import clean_environment, find_musescore

_TRIES = 20


def editable_copy(converted: Path, original: Path, fallback: Path | None = None) -> Path:
    """A copy of recognised MusicXML named after the file it came from, to open and correct.

    ``Hymn (recognised).musicxml`` beside ``Hymn.pdf``; in ``fallback`` if that folder cannot be
    written. A copy that already exists with the same content is reused, and one with different
    content (a person's own file) is never overwritten: the next free name is taken. If nothing can
    be written the converted file itself is returned.
    """
    data = converted.read_bytes()
    suffix = converted.suffix.lower()
    for folder in (original.parent, fallback):
        if folder is None:
            continue
        for number in range(1, _TRIES + 1):
            label = "recognised" if number == 1 else f"recognised {number}"
            target = folder / f"{original.stem} ({label}){suffix}"
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
