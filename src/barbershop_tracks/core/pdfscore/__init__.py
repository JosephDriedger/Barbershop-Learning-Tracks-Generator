"""Reading a score PDF that a notation program wrote, exactly, without optical recognition.

A PDF exported from MuseScore, Dorico or another program that draws music with a SMuFL font holds
every symbol as a character at an exact position and every word of the lyrics as text. This package
reads them (``pdf.py``: the page drawing; ``layout.py``: staves, systems, barlines;
``recognise.py``: notes, rhythm, voices, pitch, ties; ``lyrics.py``: the words; ``directions.py``:
tempo and marks; ``score.py``: the whole score) and writes the result as MusicXML in the shape
MuseScore's own export has (``writer.py``), so BLT reads it like any MusicXML.

A scan or a photograph holds only a picture; for those :class:`NotNotationPdf` is raised and the
caller can fall back to optical recognition.
"""

from collections import defaultdict
from fractions import Fraction
from pathlib import Path

from barbershop_tracks.core.pdfscore.lyrics import UNDERTIE
from barbershop_tracks.core.pdfscore.model import ReadScore
from barbershop_tracks.core.pdfscore.pdf import PdfError
from barbershop_tracks.core.pdfscore.score import NotNotationPdf, read_score
from barbershop_tracks.core.pdfscore.writer import write_musicxml


def pdf_to_musicxml(source: Path, target: Path) -> ReadScore:
    """Read the score PDF ``source`` and write it as MusicXML to ``target``.

    Raises :class:`NotNotationPdf` for a PDF without music-font notes (a scan) and
    :class:`PdfError` for a PDF that cannot be read.
    """
    score = read_score(source)
    write_musicxml(score, target)
    return score


def line_lengths(score: ReadScore) -> dict[int, list[list[tuple[str, Fraction | None]]]]:
    """Per staff (1 for the first), the verse 1 lyrics of each voice in order, with the length of
    the underscore line drawn after each (in quarter notes; None: no line). This is what
    ``mscx_lyrics.read_project_lyrics`` reads from a MuseScore project."""
    staves: dict[int, dict[int, list[tuple[str, Fraction | None]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    ordered = sorted(score.events, key=lambda e: (e.staff.index, e.voice, e.measure, e.onset))
    for e in ordered:
        for lyric in e.lyrics:
            if lyric.number != 1:
                continue
            # a syllable elided with the next is known by its first part, as the MusicXML reads
            staves[e.staff.index + 1][e.voice].append((lyric.text.split(UNDERTIE)[0], lyric.line))
    return {
        number: [voices[v] for v in sorted(voices)] for number, voices in sorted(staves.items())
    }


__all__ = ["NotNotationPdf", "PdfError", "ReadScore", "line_lengths", "pdf_to_musicxml"]
