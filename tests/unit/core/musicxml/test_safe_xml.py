from pathlib import Path

import pytest

from barbershop_tracks.core.errors import ScoreLoadError, ScoreXmlError, ScoreXmlSecurityError
from barbershop_tracks.core.musicxml.safe_xml import parse_xml

pytestmark = pytest.mark.usefixtures("no_network")


def test_normal_musescore_doctype_loads(musescore_score: bytes) -> None:
    root = parse_xml(musescore_score, what="score")
    assert root.tag == "score-partwise"
    assert root.get("version") == "4.0"


def test_plain_document_without_doctype_loads(minimal_score: bytes) -> None:
    assert parse_xml(minimal_score, what="score").tag == "score-partwise"


def test_internal_entity_declaration_is_rejected() -> None:
    data = b'<!DOCTYPE a [<!ENTITY x "hello">]><a>&x;</a>'
    with pytest.raises(ScoreXmlSecurityError, match="entity"):
        parse_xml(data, what="score")


def test_entity_expansion_bomb_is_rejected() -> None:
    data = (
        b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
        b'<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
        b'<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">'
        b"]><lolz>&lol3;</lolz>"
    )
    with pytest.raises(ScoreXmlSecurityError):
        parse_xml(data, what="score")


def test_external_file_entity_is_rejected_and_not_read(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET-CONTENT")
    data = f'<!DOCTYPE a [<!ENTITY x SYSTEM "{secret.as_uri()}">]><a>&x;</a>'.encode()
    with pytest.raises(ScoreXmlSecurityError) as excinfo:
        parse_xml(data, what="score")
    assert "TOP-SECRET-CONTENT" not in str(excinfo.value)


def test_external_network_entity_is_rejected() -> None:
    data = b'<!DOCTYPE a [<!ENTITY x SYSTEM "http://127.0.0.1:9/x">]><a>&x;</a>'
    with pytest.raises(ScoreXmlSecurityError):
        parse_xml(data, what="score")


def test_external_parameter_entity_is_rejected() -> None:
    data = b'<!DOCTYPE a [<!ENTITY % p SYSTEM "http://127.0.0.1:9/p.dtd"> %p;]><a/>'
    with pytest.raises(ScoreXmlSecurityError):
        parse_xml(data, what="score")


def test_external_dtd_reference_is_never_resolved() -> None:
    # The same shape as a normal MusicXML DOCTYPE. With sockets blocked by the no_network
    # fixture, a successful parse proves no attempt was made to fetch the DTD.
    data = (
        b'<!DOCTYPE score-partwise SYSTEM "http://127.0.0.1:9/evil.dtd">'
        b'<score-partwise version="4.0"/>'
    )
    assert parse_xml(data, what="score").tag == "score-partwise"


def test_external_dtd_with_local_file_is_never_read(tmp_path: Path) -> None:
    dtd = tmp_path / "evil.dtd"
    dtd.write_text('<!ENTITY injected "INJECTED">')
    data = f'<!DOCTYPE a SYSTEM "{dtd.as_uri()}"><a>&injected;</a>'.encode()
    # Either rejected as a reference to an undefined entity or as a forbidden resource,
    # but the DTD content must never be applied.
    with pytest.raises(ScoreXmlError):
        parse_xml(data, what="score")


def test_security_error_is_a_xml_error_and_load_error() -> None:
    assert issubclass(ScoreXmlSecurityError, ScoreXmlError)
    assert issubclass(ScoreXmlError, ScoreLoadError)


@pytest.mark.parametrize(
    "data",
    [
        b"<a><b></a>",
        b"<a>",
        b"not xml at all",
        b"<a></b>",
        b"<a b=></a>",
        b'<?xml version="1.0" encoding="UTF-8"?><a>\xff\xfe</a>',
    ],
)
def test_malformed_xml_is_rejected(data: bytes) -> None:
    with pytest.raises(ScoreXmlError) as excinfo:
        parse_xml(data, what="score")
    assert not isinstance(excinfo.value, ScoreXmlSecurityError)


@pytest.mark.parametrize("data", [b"", b"   \n\t  "])
def test_empty_xml_is_rejected(data: bytes) -> None:
    with pytest.raises(ScoreXmlError, match="empty"):
        parse_xml(data, what="score")


def test_error_messages_do_not_leak_large_fragments() -> None:
    garbage = b"<a>" + b"<b>" * 5000 + b"X" * 20_000
    with pytest.raises(ScoreXmlError) as excinfo:
        parse_xml(garbage, what="score")
    assert len(str(excinfo.value)) < 400
    assert "XXXX" not in str(excinfo.value)


def test_path_is_attached_to_the_error(tmp_path: Path) -> None:
    target = tmp_path / "bad.xml"
    with pytest.raises(ScoreXmlError) as excinfo:
        parse_xml(b"<a>", what="bad.xml", path=target)
    assert excinfo.value.path == target


def test_arbitrary_constructs_are_not_stripped_to_make_parsing_succeed() -> None:
    # A processing instruction and comments are legal and kept; an illegal construct is an
    # error, never silently removed.
    ok = parse_xml(b"<?pi data?><!-- c --><a/>", what="score")
    assert ok.tag == "a"
    with pytest.raises(ScoreXmlError):
        parse_xml(b"<a><!-- unterminated </a>", what="score")
