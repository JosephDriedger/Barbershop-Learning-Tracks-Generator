"""How far each held syllable (the underscore of an "oo", "doo" or "loo") runs, per the project.

MuseScore draws a line after a syllable that is held over several notes and keeps its length in
the project (``<ticks_f>9/8</ticks_f>`` in the lyric: nine eighths of a whole note, so 4.5 quarter
notes from the note the lyric is on). Its MusicXML export writes only a bare ``<extend/>`` at the
start of the line, so from MusicXML alone BLT cannot tell where the line ends and has to guess. For
a ``.mscz`` or ``.mscx`` the project itself is at hand, and this reads the lengths from it.

Only lyrics are read: their text, their verse and the length of their line, per staff and voice, in
the order they are written. Nothing else of the project is used.
"""

import zipfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from xml.etree import ElementTree as ET

from barbershop_tracks.core.errors import ScoreLoadError
from barbershop_tracks.core.musicxml.safe_xml import parse_xml

_MAX_BYTES = 128 * 1024 * 1024  # of the score inside the archive (a project is a few hundred KB)
_TICKS_PER_QUARTER = 480
_WHOLE = 4  # quarter notes in a whole note


@dataclass(frozen=True, slots=True)
class ProjectLyric:
    text: str
    line: Fraction | None  # how many quarter notes its line runs from its note; None: no line


def _text(element: ET.Element) -> str:
    return "".join(element.itertext()).strip()


def _line_length(lyric: ET.Element) -> Fraction | None:
    fraction = lyric.findtext("ticks_f")
    try:
        if fraction:
            return Fraction(fraction.strip()) * _WHOLE
        ticks = lyric.findtext("ticks")
        if ticks:
            return Fraction(int(ticks.strip()), _TICKS_PER_QUARTER)
    except (ValueError, ZeroDivisionError):
        return None
    return None


def _score_xml(path: Path) -> bytes:
    if path.suffix.lower() == ".mscx":
        return path.read_bytes()
    with zipfile.ZipFile(path) as archive:
        names = [i for i in archive.infolist() if i.filename.lower().endswith(".mscx")]
        if len(names) != 1 or names[0].file_size > _MAX_BYTES:
            raise ScoreLoadError(f"{path.name} does not hold exactly one readable score", path=path)
        with archive.open(names[0]) as stream:
            return stream.read(_MAX_BYTES + 1)


def read_project_lyrics(path: Path) -> dict[int, list[list[ProjectLyric]]]:
    """Per staff (1 for the first), the verse 1 lyrics of each voice in order; {} if unreadable."""
    try:
        root = parse_xml(_score_xml(path), what=path.name, path=path)
    except (ScoreLoadError, zipfile.BadZipFile, OSError, ET.ParseError, ValueError):
        return {}
    staves: dict[int, list[list[ProjectLyric]]] = {}
    for staff in root.iter("Staff"):
        measures = staff.findall("Measure")
        if not measures:
            continue  # the part's own listing of its staves, not the music
        try:
            number = int(staff.get("id", ""))
        except ValueError:
            continue
        voices: dict[int, list[ProjectLyric]] = {}
        for measure in measures:
            for index, voice in enumerate(measure.findall("voice")):
                for chord in voice.iter("Chord"):
                    for lyric in chord.findall("Lyrics"):
                        verse = lyric.findtext("no")
                        if verse is not None and verse.strip() not in ("", "0"):
                            continue  # another verse: only verse 1 is read
                        found = lyric.find("text")
                        text = _text(found) if found is not None else ""
                        if text:
                            voices.setdefault(index, []).append(
                                ProjectLyric(text, _line_length(lyric))
                            )
        staves[number] = [voices[i] for i in sorted(voices)]
    return staves
