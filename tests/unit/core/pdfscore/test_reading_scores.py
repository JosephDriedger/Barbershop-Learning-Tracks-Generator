"""Reading a score from a PDF that MuseScore made: the same reading as the MusicXML it came from."""

from fractions import Fraction
from pathlib import Path

import pytest

from barbershop_tracks.core.musicxml import parse_musicxml
from barbershop_tracks.core.pdfscore import line_lengths, pdf_to_musicxml
from barbershop_tracks.core.pdfscore.score import NotNotationPdf, read_score
from pdf_builders import one_page_pdf
from pdfscore_compare import compare

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"
PDFS = FIXTURES / "pdf"
INPUTS = FIXTURES / "musicxml" / "inputs"

EXACT = [
    "e1_tenor_clef8vb_pitch_oct4",  # an octave clef
    "e3b_four_parts",  # four staves
    "e4_forward_gap",  # a voice that starts late
    "e5_pickup",
    "e6_ties",  # a tie over the barline
    "e7_triplet",
    "e8_simple_repeat",
    "e9_volta",  # first and second endings
    "e10_lyrics",  # hyphens, a held syllable, an elision, a second verse
    "e11_dacapo",
    "e12_volta_1_2_3",  # an ending for passes 1 and 2
]


@pytest.mark.parametrize("name", EXACT)
def test_the_pdf_reads_as_the_musicxml_it_was_made_from(name: str, tmp_path: Path) -> None:
    target = tmp_path / f"{name}.musicxml"
    pdf_to_musicxml(PDFS / f"{name}.pdf", target)
    result = compare(parse_musicxml(INPUTS / f"{name}.musicxml"), parse_musicxml(target))
    assert result.same, result.differences
    assert result.notes_equal == result.notes_compared > 0


def test_a_quartet_on_four_staves_reads_with_its_words(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[4] / "docs/acceptance/fixtures"
    target = tmp_path / "quartet.musicxml"
    pdf_to_musicxml(PDFS / "english-quartet-known-words.pdf", target)
    result = compare(
        parse_musicxml(source / "english-quartet-known-words.musicxml"), parse_musicxml(target)
    )
    # the notes, rhythms and words are all there; the fixture's tempo is one MuseScore keeps
    # hidden (nothing in the PDF shows it), so it is the only difference
    assert result.notes_equal == result.notes_compared == 104
    assert result.lyrics_equal == result.lyrics_compared == 28
    assert all(d.startswith(("tempo:", "key:")) for d in result.differences)


def test_what_the_reading_found_is_kept_with_the_score() -> None:
    score = read_score(PDFS / "e10_lyrics.pdf")
    assert len(score.parts) == 1
    held = [ly for e in score.events for ly in e.lyrics if ly.text == "love"]
    assert held
    assert held[0].line == 2  # the line after "love" runs over the next two notes
    assert line_lengths(score)[1][0][3] == ("love", Fraction(2))


def test_a_pdf_without_notation_is_not_read_as_a_score(tmp_path: Path) -> None:
    page = tmp_path / "scan.pdf"
    page.write_bytes(one_page_pdf(b"BT /F1 12 Tf 72 700 Td (A picture of music) Tj ET"))
    with pytest.raises(NotNotationPdf):
        read_score(page)
