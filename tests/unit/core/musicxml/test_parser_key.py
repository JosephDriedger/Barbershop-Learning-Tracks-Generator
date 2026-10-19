"""The key signature at the start of the score, for the tune-up note."""

from pathlib import Path

import pytest

from barbershop_tracks.models import KeySignature
from cli_scores import quartet_xml
from xml_builders import parse_text

pytestmark = pytest.mark.usefixtures("no_network")


def with_key(key_xml: str) -> str:
    xml = quartet_xml()
    assert "<divisions>2</divisions>" in xml
    return xml.replace("<divisions>2</divisions>", "<divisions>2</divisions>" + key_xml, 1)


def test_a_score_without_a_key_signature_has_none(tmp_path: Path) -> None:
    result = parse_text(tmp_path, quartet_xml())
    assert result.song is not None
    assert result.song.key_signature is None


def test_the_first_key_signature_is_read_with_its_mode(tmp_path: Path) -> None:
    result = parse_text(tmp_path, with_key("<key><fifths>-3</fifths><mode>minor</mode></key>"))
    assert result.song is not None
    assert result.song.key_signature == KeySignature(fifths=-3, mode="minor")
    assert result.song.key_signature.tonic_name == "C"  # three flats, minor: C minor


def test_a_key_without_a_mode_is_read_as_it_is(tmp_path: Path) -> None:
    result = parse_text(tmp_path, with_key("<key><fifths>2</fifths></key>"))
    assert result.song is not None
    assert result.song.key_signature == KeySignature(fifths=2, mode=None)
    assert result.song.key_signature.tonic_name == "D"


def test_a_key_that_is_not_a_number_is_ignored(tmp_path: Path) -> None:
    result = parse_text(tmp_path, with_key("<key><fifths>many</fifths></key>"))
    assert result.song is not None
    assert result.song.key_signature is None
