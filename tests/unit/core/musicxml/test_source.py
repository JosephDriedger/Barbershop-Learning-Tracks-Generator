from collections.abc import Callable
from pathlib import Path

import pytest

from barbershop_tracks.core.errors import (
    ScoreArchiveError,
    ScoreFileError,
    ScoreLoadError,
    ScoreResourceLimitError,
    ScoreXmlError,
    ScoreXmlSecurityError,
    UnsupportedScoreFormatError,
)
from barbershop_tracks.core.musicxml import (
    LoaderLimits,
    MusicXmlSource,
    SourceKind,
    load_musicxml_source,
)

pytestmark = pytest.mark.usefixtures("no_network")

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "musicxml"
REAL_FIXTURES = sorted(
    [*FIXTURES.glob("inputs/*.musicxml"), *FIXTURES.glob("musescore_roundtrip/*")],
    key=lambda p: p.as_posix(),
)


def _xml_of_size(size: int) -> bytes:
    """A valid score document of exactly ``size`` bytes."""
    head, tail = b"<score-partwise>", b"</score-partwise>"
    return head + b" " * (size - len(head) - len(tail)) + tail


# --- plain XML ------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["s.musicxml", "s.xml", "S.MUSICXML", "s.XmL", "S.Musicxml"])
def test_plain_xml_extensions_are_case_insensitive(
    tmp_path: Path, minimal_score: bytes, name: str
) -> None:
    path = tmp_path / name
    path.write_bytes(minimal_score)
    source = load_musicxml_source(path)
    assert source.kind is SourceKind.PLAIN_XML
    assert source.root.tag == "score-partwise"


@pytest.mark.parametrize("name", ["s.mxl", "S.MXL", "s.MxL"])
def test_mxl_extension_is_case_insensitive(
    make_mxl: Callable[..., Path], musescore_mxl: Path, name: str
) -> None:
    renamed = musescore_mxl.with_name(name)
    musescore_mxl.rename(renamed)
    assert load_musicxml_source(renamed).kind is SourceKind.COMPRESSED


def test_source_metadata_for_plain_xml(tmp_path: Path, musescore_score: bytes) -> None:
    path = tmp_path / "song.musicxml"
    path.write_bytes(musescore_score)
    source = load_musicxml_source(path)
    assert isinstance(source, MusicXmlSource)
    assert source.path == path
    assert source.member_name is None
    assert source.size_bytes == len(musescore_score)


def test_accepts_str_and_pathlike(tmp_path: Path, minimal_score: bytes) -> None:
    path = tmp_path / "with space ü.musicxml"
    path.write_bytes(minimal_score)
    assert load_musicxml_source(str(path)).root.tag == "score-partwise"
    assert load_musicxml_source(path).root.tag == "score-partwise"


def test_nonexistent_file(tmp_path: Path) -> None:
    with pytest.raises(ScoreFileError, match="does not exist"):
        load_musicxml_source(tmp_path / "missing.musicxml")


def test_directory_instead_of_file(tmp_path: Path) -> None:
    folder = tmp_path / "folder.musicxml"
    folder.mkdir()
    with pytest.raises(ScoreFileError, match="not a file"):
        load_musicxml_source(folder)


@pytest.mark.parametrize("name", ["score.txt", "score", "score.musicxml.bak", "score.zip"])
def test_unsupported_extension(tmp_path: Path, minimal_score: bytes, name: str) -> None:
    path = tmp_path / name
    path.write_bytes(minimal_score)
    with pytest.raises(ScoreFileError, match="unsupported extension"):
        load_musicxml_source(path)


def test_empty_xml_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.musicxml"
    path.write_bytes(b"")
    with pytest.raises(ScoreXmlError, match="empty"):
        load_musicxml_source(path)


def test_malformed_xml_file(tmp_path: Path) -> None:
    path = tmp_path / "bad.musicxml"
    path.write_bytes(b"<score-partwise><part></score-partwise>")
    with pytest.raises(ScoreXmlError, match="not well-formed"):
        load_musicxml_source(path)


def test_entity_in_plain_file_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "evil.musicxml"
    path.write_bytes(
        b'<!DOCTYPE score-partwise [<!ENTITY x "y">]><score-partwise>&x;</score-partwise>'
    )
    with pytest.raises(ScoreXmlSecurityError):
        load_musicxml_source(path)


def test_plain_file_exactly_at_size_limit_loads(tmp_path: Path) -> None:
    path = tmp_path / "s.musicxml"
    path.write_bytes(_xml_of_size(500))
    source = load_musicxml_source(path, LoaderLimits(max_score_bytes=500))
    assert source.size_bytes == 500


def test_plain_file_over_size_limit_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "s.musicxml"
    path.write_bytes(_xml_of_size(501))
    with pytest.raises(ScoreResourceLimitError, match="larger than the limit"):
        load_musicxml_source(path, LoaderLimits(max_score_bytes=500))


def test_default_limit_applies_to_plain_xml(tmp_path: Path) -> None:
    path = tmp_path / "big.xml"
    with path.open("wb") as handle:
        handle.write(b"<score-partwise>")
        handle.write(b" " * (50 * 1024 * 1024))  # makes the file larger than 50 MiB
        handle.write(b"</score-partwise>")
    with pytest.raises(ScoreResourceLimitError, match="50 MiB"):
        load_musicxml_source(path)


# --- root element ---------------------------------------------------------------------


def test_score_timewise_is_rejected_explicitly(tmp_path: Path) -> None:
    path = tmp_path / "t.musicxml"
    path.write_bytes(b'<score-timewise version="4.0"><part-list/></score-timewise>')
    with pytest.raises(UnsupportedScoreFormatError, match="score-timewise"):
        load_musicxml_source(path)


@pytest.mark.parametrize(
    "xml",
    [
        b"<html/>",
        b'<score-partwise xmlns="urn:x"/>',  # namespaced root is not plain score-partwise
        b"<SCORE-PARTWISE/>",
    ],
)
def test_other_roots_are_rejected(tmp_path: Path, xml: bytes) -> None:
    path = tmp_path / "x.musicxml"
    path.write_bytes(xml)
    with pytest.raises(UnsupportedScoreFormatError, match="score-partwise"):
        load_musicxml_source(path)


def test_long_unknown_root_name_is_truncated_in_message(tmp_path: Path) -> None:
    name = b"r" * 5000
    path = tmp_path / "x.musicxml"
    path.write_bytes(b"<" + name + b"/>")
    with pytest.raises(UnsupportedScoreFormatError) as excinfo:
        load_musicxml_source(path)
    assert len(str(excinfo.value)) < 300


# --- .mxl through the public entry point ----------------------------------------------


def test_mxl_source_metadata(musescore_mxl: Path, musescore_score: bytes) -> None:
    source = load_musicxml_source(musescore_mxl)
    assert source.kind is SourceKind.COMPRESSED
    assert source.member_name == "score.xml"
    assert source.size_bytes == len(musescore_score)
    assert source.root.tag == "score-partwise"


def test_mxl_timewise_score_is_rejected(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes]
) -> None:
    path = make_mxl(
        [
            ("META-INF/container.xml", make_container("s.xml")),
            ("s.xml", b"<score-timewise/>"),
        ]
    )
    with pytest.raises(UnsupportedScoreFormatError, match="score-timewise"):
        load_musicxml_source(path)


def test_mxl_malformed_score_is_rejected(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes]
) -> None:
    path = make_mxl(
        [("META-INF/container.xml", make_container("s.xml")), ("s.xml", b"<score-partwise>")]
    )
    with pytest.raises(ScoreXmlError, match="not well-formed"):
        load_musicxml_source(path)


def test_mxl_empty_score_member_is_rejected(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes]
) -> None:
    path = make_mxl([("META-INF/container.xml", make_container("s.xml")), ("s.xml", b"")])
    with pytest.raises(ScoreXmlError, match="empty"):
        load_musicxml_source(path)


def test_mxl_score_with_entity_is_rejected(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes]
) -> None:
    evil = b'<!DOCTYPE score-partwise [<!ENTITY x "y">]><score-partwise>&x;</score-partwise>'
    path = make_mxl([("META-INF/container.xml", make_container("s.xml")), ("s.xml", evil)])
    with pytest.raises(ScoreXmlSecurityError):
        load_musicxml_source(path)


def test_plain_xml_renamed_to_mxl_is_not_a_valid_archive(
    tmp_path: Path, minimal_score: bytes
) -> None:
    path = tmp_path / "fake.mxl"
    path.write_bytes(minimal_score)
    with pytest.raises(ScoreArchiveError, match="not a valid ZIP"):
        load_musicxml_source(path)


def test_loading_an_mxl_extracts_nothing_to_disk(
    musescore_mxl: Path, tree_snapshot: Callable[[], list[str]]
) -> None:
    before = tree_snapshot()
    load_musicxml_source(musescore_mxl)
    assert tree_snapshot() == before


# --- real MuseScore / hand-written fixtures -------------------------------------------


def test_fixture_directory_is_populated() -> None:
    assert len(REAL_FIXTURES) >= 30


@pytest.mark.parametrize("path", REAL_FIXTURES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_repository_fixtures_load(path: Path) -> None:
    source = load_musicxml_source(path)
    assert source.root.tag == "score-partwise"
    assert source.size_bytes > 0


def test_musescore_exports_with_doctype_load() -> None:
    export = FIXTURES / "musescore_roundtrip" / "e1_control_treble.musicxml"
    assert b"<!DOCTYPE" in export.read_bytes()
    assert load_musicxml_source(export).root.tag == "score-partwise"


def test_repository_mxl_fixture_loads() -> None:
    source = load_musicxml_source(
        FIXTURES / "musescore_roundtrip" / "e1_tenor_clef8vb_pitch_oct4.mxl"
    )
    assert source.kind is SourceKind.COMPRESSED
    assert source.member_name == "score.xml"


def test_all_load_errors_share_a_base_class(tmp_path: Path) -> None:
    with pytest.raises(ScoreLoadError):
        load_musicxml_source(tmp_path / "nope.xml")
