"""Opening a PDF that a notation program wrote: read by BLT itself, nothing recognised."""

from pathlib import Path

from barbershop_tracks.core.musicxml import parse_musicxml
from barbershop_tracks.core.musicxml.convert import (
    PDF_READER,
    is_notation_pdf,
    needs_recognition,
    opened_score,
)
from barbershop_tracks.core.musicxml.opened import parse_opened
from pdf_builders import one_page_pdf

PDFS = Path(__file__).resolve().parents[3] / "fixtures" / "pdf"


def test_a_notation_pdf_needs_no_recognition(tmp_path: Path) -> None:
    assert is_notation_pdf(PDFS / "e6_ties.pdf")
    assert not needs_recognition(PDFS / "e6_ties.pdf")
    scan = tmp_path / "scan.pdf"
    scan.write_bytes(one_page_pdf(b"BT /F1 12 Tf 72 700 Td (no notes here) Tj ET"))
    assert needs_recognition(scan)  # a picture of music still needs a recognising program
    assert needs_recognition("photo.png")


def test_a_notation_pdf_opens_without_any_program_or_acceptance(tmp_path: Path) -> None:
    empty_path = {"PATH": "", "ProgramFiles": str(tmp_path)}  # no MuseScore, no Audiveris
    with opened_score(PDFS / "e10_lyrics.pdf", cache=tmp_path / "cache", environ=empty_path) as one:
        assert one.conversion is not None
        assert (one.conversion.tool, one.conversion.kind) == (PDF_READER, "pdf-reading")
        assert one.conversion.recognised is False
        assert one.lyric_lines is not None
        assert one.lyric_lines[1][0][3].text == "love"
        parsed, reading = parse_opened(one, parse_musicxml)
        first = one.conversion.converted_sha256
    assert parsed.song is not None
    held = [
        lyric
        for part in parsed.song.parts
        for note in part.events
        for lyric in note.lyrics
        if lyric.text == "love"
    ]
    assert held[0].extend_length == 2  # the line the PDF draws, as a MuseScore project keeps it
    assert reading.lines.applied == 1
    # read again from the cache: the same MusicXML
    with opened_score(PDFS / "e10_lyrics.pdf", cache=tmp_path / "cache", environ=empty_path) as two:
        assert two.conversion is not None
        assert two.conversion.converted_sha256 == first
        assert two.lyric_lines == one.lyric_lines
