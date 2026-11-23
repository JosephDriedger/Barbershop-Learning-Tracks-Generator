"""The PDF reader: what a page draws, read from the page description."""

from pathlib import Path

import pytest

from barbershop_tracks.core.pdfscore.pdf import PdfError, read_pages
from pdf_builders import one_page_pdf as _pdf


def _write(tmp_path: Path, data: bytes) -> Path:
    path = tmp_path / "page.pdf"
    path.write_bytes(data)
    return path


def test_lines_rectangles_and_curves_are_read_in_page_coordinates(tmp_path: Path) -> None:
    content = (
        b"q 1 0 0 1 10 20 cm 0.5 w 100 100 m 200 100 l S Q "
        b"50 50 10 4 re f "
        b"300 300 m 310 320 330 320 340 300 c 330 310 310 310 300 300 c f"
    )
    page = read_pages(_write(tmp_path, _pdf(content)))[0]
    assert (page.width, page.height) == (612, 792)
    line = page.segments[0]
    assert (line.x0, line.y0, line.x1, line.y1) == (110, 120, 210, 120)
    assert line.width == pytest.approx(0.5)
    rectangle, curve = page.shapes
    assert rectangle.bbox == (50.0, 50.0, 60.0, 54.0)
    assert not rectangle.curved
    assert curve.curved
    assert curve.filled


def test_text_is_read_glyph_by_glyph_with_its_position(tmp_path: Path) -> None:
    content = b"BT /F1 10 Tf 1 0 0 1 72 700 Tm (Hi) Tj [( ) -500 (x)] TJ ET"
    page = read_pages(_write(tmp_path, _pdf(content, compress=True)))[0]
    assert [g.text for g in page.glyphs] == ["H", "i", "x"]
    first = page.glyphs[0]
    assert (first.x, first.y, first.size, first.font) == (72, 700, 10, "Helvetica")


def test_a_tounicode_map_gives_a_music_font_its_code_points(tmp_path: Path) -> None:
    cmap = (
        b"begincmap 1 begincodespacerange <00> <FF> endcodespacerange "
        b"1 beginbfchar <41> <E0A4> endbfchar endcmap"
    )
    font = (
        b"<< /Type /Font /Subtype /Type1 /BaseFont /ABCDEF+Leland /FirstChar 65 /LastChar 65 "
        b"/Widths [330] /ToUnicode 6 0 R >>\nendobj\n6 0 obj\n<< /Length "
        + str(len(cmap)).encode()
        + b" >>\nstream\n"
        + cmap
        + b"\nendstream"
    )
    content = b"BT /F1 20 Tf 100 200 Td (A) Tj ET"
    page = read_pages(_write(tmp_path, _pdf(content, font=font)))[0]
    (head,) = page.glyphs
    assert head.text == chr(0xE0A4)  # SMuFL noteheadBlack
    assert head.font == "Leland"  # the subset prefix is dropped
    assert head.width == pytest.approx(6.6)


def test_a_file_that_is_not_a_pdf_is_refused(tmp_path: Path) -> None:
    with pytest.raises(PdfError):
        read_pages(_write(tmp_path, b"not a pdf at all"))


def test_an_encrypted_pdf_is_refused(tmp_path: Path) -> None:
    data = _pdf(b"").replace(b"/Root 1 0 R", b"/Root 1 0 R /Encrypt 9 0 R")
    with pytest.raises(PdfError, match="encrypted"):
        read_pages(_write(tmp_path, data))
