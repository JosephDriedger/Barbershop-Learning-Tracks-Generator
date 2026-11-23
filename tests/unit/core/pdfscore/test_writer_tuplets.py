"""Tuplets in the MusicXML the PDF reader writes: one group per number, read alike everywhere."""

import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from barbershop_tracks.core.pdfscore import pdf_to_musicxml
from barbershop_tracks.core.pdfscore.writer import _time_modification, _tuplet_marks

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "pdf"


def test_each_triplet_is_one_group_with_a_start_and_a_stop(tmp_path: Path) -> None:
    target = tmp_path / "triplet.musicxml"
    pdf_to_musicxml(FIXTURES / "e7_triplet.pdf", target)
    root = ET.parse(target).getroot()
    starts = root.findall(".//notations/tuplet[@type='start']")
    stops = root.findall(".//notations/tuplet[@type='stop']")
    modified = root.findall(".//note/time-modification")
    assert starts
    assert len(starts) == len(stops)
    assert len(modified) == 3 * len(starts)  # three notes in each group, not a group per note
    assert {(m.findtext("actual-notes"), m.findtext("normal-notes")) for m in modified} == {
        ("3", "2")
    }


def _event(tuplet: Fraction, shown: tuple[int, int]) -> Any:
    return SimpleNamespace(tuplet=tuplet, tuplet_shown=shown)


def test_finales_duplet_of_quarters_is_four_in_the_time_of_three_showing_two() -> None:
    # two quarters in the time of three eighths: MuseScore takes a tuplet's value from its notes
    # and ignores <normal-type>, so the ratio is said in quarters
    e = _event(Fraction(3, 4), (2, 3))
    note = ET.Element("note")
    _time_modification(note, e)
    assert note.findtext("time-modification/actual-notes") == "4"
    assert note.findtext("time-modification/normal-notes") == "3"
    assert note.find("time-modification/normal-type") is None
    notations = ET.Element("notations")
    _tuplet_marks(note, notations, (True, False), e)
    mark = note.find("notations/tuplet")
    assert mark is not None
    assert mark.get("type") == "start"
    assert mark.get("show-number") == "actual"
    assert mark.findtext("tuplet-actual/tuplet-number") == "2"  # what the score prints
    assert mark.findtext("tuplet-normal/tuplet-number") == "3"


def test_a_plain_triplet_needs_no_printed_number_of_its_own() -> None:
    e = _event(Fraction(2, 3), (3, 2))
    note = ET.Element("note")
    _tuplet_marks(note, ET.Element("notations"), (True, True), e)
    marks = note.findall("notations/tuplet")
    assert [m.get("type") for m in marks] == ["start", "stop"]
    assert marks[0].find("tuplet-actual") is None


def test_a_note_inside_a_group_has_no_tuplet_mark() -> None:
    note = ET.Element("note")
    _tuplet_marks(note, ET.Element("notations"), (False, False), _event(Fraction(2, 3), (3, 2)))
    assert note.find("notations") is None
