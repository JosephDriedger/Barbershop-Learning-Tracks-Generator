"""A song gives the same reading from its MuseScore project, its MusicXML and its PDF.

Opt-in, with a folder of your own songs: set ``BLT_PDF_CORPUS`` to a folder that holds, for each
song, ``name.mscz`` and the ``name.pdf`` and ``name.musicxml`` MuseScore exported from it (File >
Export). Each song is opened from all three and BLT's readings are compared: the lines, every note
(time, length, pitch, ties), the words of verse 1, how long each held syllable lasts and the tempo
as played. A song whose PDF cannot show everything (an arrangement where who sings a word, or a
voice's stems, was changed by hand in MuseScore) is listed in ``known-differences.txt`` in the
folder, one name per line with the reason after a ``#``; for those the notes are still compared.
PDFs of the same songs in other engraving styles (another music font, page or staff size,
spacing) can be put in subfolders, ``variants/<style>/name.pdf``: each must read as the project
does too. Needs MuseScore (for the projects). Skipped when the folder is not set.
"""

import os
from pathlib import Path

import pytest

from barbershop_tracks.core.musicxml import parse_musicxml
from barbershop_tracks.core.musicxml.convert import find_musescore, opened_score
from barbershop_tracks.core.musicxml.opened import parse_opened
from barbershop_tracks.core.musicxml.parser import ParseResult
from pdfscore_compare import compare

CORPUS = os.environ.get("BLT_PDF_CORPUS")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not CORPUS, reason="BLT_PDF_CORPUS is not set"),
    pytest.mark.skipif(find_musescore() is None, reason="MuseScore is not installed"),
]


def _songs() -> list[str]:
    """``name`` for each song, and ``name@style`` for each of its PDFs in another style."""
    if not CORPUS:
        return []
    folder = Path(CORPUS)
    found = [p.stem for p in folder.glob("*.pdf") if (folder / f"{p.stem}.mscz").exists()]
    found += [
        f"{p.stem}@{p.parent.name}"
        for p in folder.glob("variants/*/*.pdf")
        if (folder / f"{p.stem}.mscz").exists()
    ]
    return sorted(found)


def _known() -> set[str]:
    path = Path(CORPUS or ".") / "known-differences.txt"
    if not path.exists():
        return set()
    return {
        line.split("#", 1)[0].strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.split("#", 1)[0].strip()
    }


def _read(path: Path, cache: Path) -> ParseResult:
    with opened_score(path, cache=cache) as opened:
        parsed, _reading = parse_opened(opened, parse_musicxml)
    return parsed


def _held(parsed: ParseResult) -> dict[tuple[str, int, object, str], object]:
    assert parsed.song is not None
    return {
        (part.part_id, note.measure, note.beat, lyric.text): lyric.extend_length
        for part in parsed.song.parts
        for note in part.events
        for lyric in note.lyrics
        if lyric.extend_length is not None
    }


def _tempo(parsed: ParseResult) -> list[tuple[object, object]]:
    assert parsed.performed is not None
    return [(t.position, t.bpm) for t in parsed.performed.tempo_events]


@pytest.mark.parametrize("name", _songs())
def test_the_project_the_musicxml_and_the_pdf_read_the_same(name: str, tmp_path: Path) -> None:
    folder = Path(CORPUS or ".")
    name, _at, style = name.partition("@")
    project = _read(folder / f"{name}.mscz", tmp_path)
    pdf_path = folder / "variants" / style / f"{name}.pdf" if style else folder / f"{name}.pdf"
    pdf = _read(pdf_path, tmp_path)
    from_pdf = compare(project, pdf)
    if name in _known():
        assert from_pdf.notes_equal >= 0.98 * from_pdf.notes_compared, from_pdf.summary()
        return
    assert from_pdf.same, from_pdf.differences
    assert _held(pdf) == _held(project)
    assert _tempo(pdf) == _tempo(project)
    musicxml = folder / f"{name}.musicxml"
    if musicxml.exists():
        from_musicxml = _read(musicxml, tmp_path)
        assert compare(project, from_musicxml).same
        assert _tempo(from_musicxml) == _tempo(project)
