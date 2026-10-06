import struct
import zipfile
import zlib
from collections.abc import Callable
from pathlib import Path

import pytest

from barbershop_tracks.core.errors import (
    ScoreArchiveError,
    ScoreResourceLimitError,
    ScoreXmlError,
    ScoreXmlSecurityError,
)
from barbershop_tracks.core.musicxml import LoaderLimits, load_musicxml_source
from barbershop_tracks.core.musicxml.archive import (
    CONTAINER_PATH,
    MUSICXML_MEDIA_TYPES,
    validate_member_path,
)

pytestmark = pytest.mark.usefixtures("no_network")

MXL_TYPE = "application/vnd.recordare.musicxml+xml"
HEAD, TAIL = b"<score-partwise>", b"</score-partwise>"
STORED = zipfile.ZIP_STORED


def _xml_of_size(size: int) -> bytes:
    return HEAD + b" " * (size - len(HEAD) - len(TAIL)) + TAIL


def _deflated_size(data: bytes) -> int:
    compressor = zlib.compressobj(zlib.Z_DEFAULT_COMPRESSION, zlib.DEFLATED, -15)
    return len(compressor.compress(data) + compressor.flush())


def _payload_with_exact_ratio() -> tuple[bytes, int]:
    """A valid score whose deflate ratio is exactly a whole number; returns (data, ratio)."""
    for pad in range(2000, 60000):
        data = HEAD + b" " * pad + TAIL
        compressed = _deflated_size(data)
        if len(data) % compressed == 0:
            return data, len(data) // compressed
    raise AssertionError("no payload with an exact ratio found")


def _patch_central_directory(path: Path, patch: Callable[[bytearray, int], None]) -> None:
    data = bytearray(path.read_bytes())
    offset = data.find(b"PK\x01\x02")
    while offset != -1:
        patch(data, offset)
        offset = data.find(b"PK\x01\x02", offset + 1)
    path.write_bytes(bytes(data))


# --- happy paths ----------------------------------------------------------------------


def test_musescore_style_archive_without_media_type_loads(musescore_mxl: Path) -> None:
    source = load_musicxml_source(musescore_mxl)
    assert source.member_name == "score.xml"


def test_archive_with_media_type_loads(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes], minimal_score: bytes
) -> None:
    path = make_mxl(
        [
            (CONTAINER_PATH, make_container(("score.xml", MXL_TYPE))),
            ("score.xml", minimal_score),
        ]
    )
    assert load_musicxml_source(path).root.tag == "score-partwise"


def test_stored_uncompressed_archive_loads(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes], minimal_score: bytes
) -> None:
    path = make_mxl(
        [(CONTAINER_PATH, make_container("score.xml")), ("score.xml", minimal_score)],
        compression=STORED,
    )
    assert load_musicxml_source(path).root.tag == "score-partwise"


def test_score_in_a_subdirectory(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes], minimal_score: bytes
) -> None:
    path = make_mxl(
        [(CONTAINER_PATH, make_container("scores/a.xml")), ("scores/a.xml", minimal_score)]
    )
    assert load_musicxml_source(path).member_name == "scores/a.xml"


def test_non_musicxml_rootfiles_are_ignored(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes], minimal_score: bytes
) -> None:
    path = make_mxl(
        [
            (
                CONTAINER_PATH,
                make_container(("score.xml", MXL_TYPE), ("score.pdf", "application/pdf")),
            ),
            ("score.xml", minimal_score),
            ("score.pdf", b"%PDF-"),
        ]
    )
    assert load_musicxml_source(path).member_name == "score.xml"


def test_supported_media_types_are_the_documented_values() -> None:
    documented = {"application/vnd.recordare.musicxml+xml", "application/vnd.recordare.musicxml"}
    assert set(MUSICXML_MEDIA_TYPES) == documented


@pytest.mark.parametrize("media_type", [*sorted(MUSICXML_MEDIA_TYPES), MXL_TYPE.upper()])
def test_each_supported_media_type_selects_the_rootfile(
    make_mxl: Callable[..., Path],
    make_container: Callable[..., bytes],
    minimal_score: bytes,
    media_type: str,
) -> None:
    path = make_mxl(
        [(CONTAINER_PATH, make_container(("score.xml", media_type))), ("score.xml", minimal_score)]
    )
    assert load_musicxml_source(path).member_name == "score.xml"


def test_unsupported_media_type_alone_is_not_a_candidate(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes], minimal_score: bytes
) -> None:
    path = make_mxl(
        [
            (CONTAINER_PATH, make_container(("score.xml", "application/xml"))),
            ("score.xml", minimal_score),
        ]
    )
    with pytest.raises(ScoreArchiveError, match="no MusicXML rootfile"):
        load_musicxml_source(path)


def test_untyped_and_musicxml_typed_rootfiles_are_ambiguous(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes], minimal_score: bytes
) -> None:
    path = make_mxl(
        [
            (CONTAINER_PATH, make_container("a.xml", ("b.xml", MXL_TYPE))),
            ("a.xml", minimal_score),
            ("b.xml", minimal_score),
        ]
    )
    with pytest.raises(ScoreArchiveError, match="several possible"):
        load_musicxml_source(path)


def test_namespaced_container_is_accepted(
    make_mxl: Callable[..., Path], minimal_score: bytes
) -> None:
    container = (
        b'<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        b'<rootfiles><rootfile full-path="s.xml"/></rootfiles></container>'
    )
    path = make_mxl([(CONTAINER_PATH, container), ("s.xml", minimal_score)])
    assert load_musicxml_source(path).member_name == "s.xml"


def test_unrelated_members_are_ignored_and_never_read(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes], minimal_score: bytes
) -> None:
    bomb = b"\x00" * (8 * 1024 * 1024)  # compresses far beyond 100:1, but is unrelated
    path = make_mxl(
        [
            (CONTAINER_PATH, make_container("score.xml")),
            ("score.xml", minimal_score),
            ("preview.png", b"\x89PNG"),
            ("notes/readme.txt", b"hello"),
            ("junk.bin", bomb),
        ]
    )
    assert load_musicxml_source(path).root.tag == "score-partwise"


# --- container / archive structure ----------------------------------------------------


def test_not_a_zip(tmp_path: Path) -> None:
    path = tmp_path / "x.mxl"
    path.write_bytes(b"this is not a zip file")
    with pytest.raises(ScoreArchiveError, match="not a valid ZIP"):
        load_musicxml_source(path)


def test_empty_zip(make_mxl: Callable[..., Path]) -> None:
    with pytest.raises(ScoreArchiveError, match="no files"):
        load_musicxml_source(make_mxl([]))


def test_corrupt_zip_truncated(musescore_mxl: Path) -> None:
    data = musescore_mxl.read_bytes()
    musescore_mxl.write_bytes(data[: len(data) // 2])
    with pytest.raises(ScoreArchiveError, match="not a valid ZIP"):
        load_musicxml_source(musescore_mxl)


def test_corrupt_member_data_is_rejected(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes]
) -> None:
    path = make_mxl(
        [
            (CONTAINER_PATH, make_container("score.xml")),
            ("score.xml", b"<score-partwise/>" + b"A" * 2000),
        ],
        compression=STORED,
    )
    data = bytearray(path.read_bytes())
    marker = data.find(b"A" * 100)
    data[marker + 10] = ord("B")  # flip a byte; CRC no longer matches
    path.write_bytes(bytes(data))
    with pytest.raises(ScoreArchiveError, match="corrupt"):
        load_musicxml_source(path)


# Python's zipfile cannot *write* encrypted members, and adding an encryption library just
# for tests is not worth it. These tests set the "encrypted" general-purpose flag on a
# chosen member's central-directory entry, which is exactly what the loader inspects; the
# loader must decide from that flag alone, before it opens (or tries to decrypt) anything.
def _mark_encrypted(path: Path, member: str) -> None:
    data = bytearray(path.read_bytes())
    offset = data.find(b"PK\x01\x02")
    marked = False
    while offset != -1:
        name_length = struct.unpack_from("<H", data, offset + 28)[0]
        name = bytes(data[offset + 46 : offset + 46 + name_length]).decode()
        if name == member:
            flags = struct.unpack_from("<H", data, offset + 8)[0]
            struct.pack_into("<H", data, offset + 8, flags | 0x1)
            marked = True
        offset = data.find(b"PK\x01\x02", offset + 1)
    assert marked, f"{member} not found in archive"
    path.write_bytes(bytes(data))


def test_encrypted_container_is_rejected(musescore_mxl: Path) -> None:
    _mark_encrypted(musescore_mxl, CONTAINER_PATH)
    with pytest.raises(ScoreArchiveError, match=r"container\.xml.*encrypted"):
        load_musicxml_source(musescore_mxl)


def test_encrypted_selected_rootfile_is_rejected(musescore_mxl: Path) -> None:
    _mark_encrypted(musescore_mxl, "score.xml")
    with pytest.raises(ScoreArchiveError, match=r"rootfile 'score\.xml'.*encrypted"):
        load_musicxml_source(musescore_mxl)


def test_encrypted_unrelated_member_does_not_prevent_loading(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes], minimal_score: bytes
) -> None:
    path = make_mxl(
        [
            (CONTAINER_PATH, make_container("score.xml")),
            ("score.xml", minimal_score),
            ("cover.png", b"not really an image"),
        ]
    )
    _mark_encrypted(path, "cover.png")
    assert load_musicxml_source(path).root.tag == "score-partwise"


def test_encrypted_non_selected_rootfile_is_ignored(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes], minimal_score: bytes
) -> None:
    path = make_mxl(
        [
            (
                CONTAINER_PATH,
                make_container(("score.xml", MXL_TYPE), ("score.pdf", "application/pdf")),
            ),
            ("score.xml", minimal_score),
            ("score.pdf", b"%PDF-"),
        ]
    )
    _mark_encrypted(path, "score.pdf")
    assert load_musicxml_source(path).member_name == "score.xml"


def test_encrypted_unrelated_members_still_count_toward_the_entry_limit(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes], minimal_score: bytes
) -> None:
    path = make_mxl(
        [
            (CONTAINER_PATH, make_container("score.xml")),
            ("score.xml", minimal_score),
            ("a.bin", b"a"),
            ("b.bin", b"b"),
        ]
    )
    _mark_encrypted(path, "a.bin")
    assert load_musicxml_source(path, LoaderLimits(max_archive_entries=4))
    with pytest.raises(ScoreResourceLimitError, match="entries"):
        load_musicxml_source(path, LoaderLimits(max_archive_entries=3))


def test_missing_container(make_mxl: Callable[..., Path], minimal_score: bytes) -> None:
    path = make_mxl([("score.xml", minimal_score)])
    with pytest.raises(ScoreArchiveError, match=r"no META-INF/container\.xml"):
        load_musicxml_source(path)


def test_container_lookup_is_case_sensitive(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes], minimal_score: bytes
) -> None:
    path = make_mxl(
        [("meta-inf/container.xml", make_container("score.xml")), ("score.xml", minimal_score)]
    )
    with pytest.raises(ScoreArchiveError, match=r"no META-INF/container\.xml"):
        load_musicxml_source(path)


def test_malformed_container_xml(make_mxl: Callable[..., Path], minimal_score: bytes) -> None:
    path = make_mxl([(CONTAINER_PATH, b"<container><rootfiles>"), ("score.xml", minimal_score)])
    with pytest.raises(ScoreXmlError, match=r"container\.xml"):
        load_musicxml_source(path)


def test_container_with_entity_is_rejected(
    make_mxl: Callable[..., Path], minimal_score: bytes
) -> None:
    container = (
        b'<!DOCTYPE container [<!ENTITY x "score.xml">]>'
        b'<container><rootfiles><rootfile full-path="&x;"/></rootfiles></container>'
    )
    path = make_mxl([(CONTAINER_PATH, container), ("score.xml", minimal_score)])
    with pytest.raises(ScoreXmlSecurityError):
        load_musicxml_source(path)


def test_container_with_wrong_root(make_mxl: Callable[..., Path], minimal_score: bytes) -> None:
    path = make_mxl([(CONTAINER_PATH, b"<other/>"), ("score.xml", minimal_score)])
    with pytest.raises(ScoreArchiveError, match="<container> root"):
        load_musicxml_source(path)


def test_container_without_rootfile(make_mxl: Callable[..., Path], minimal_score: bytes) -> None:
    path = make_mxl(
        [(CONTAINER_PATH, b"<container><rootfiles/></container>"), ("score.xml", minimal_score)]
    )
    with pytest.raises(ScoreArchiveError, match="no rootfile"):
        load_musicxml_source(path)


def test_rootfile_without_full_path(make_mxl: Callable[..., Path], minimal_score: bytes) -> None:
    container = b"<container><rootfiles><rootfile/></rootfiles></container>"
    path = make_mxl([(CONTAINER_PATH, container), ("score.xml", minimal_score)])
    with pytest.raises(ScoreArchiveError, match="no full-path"):
        load_musicxml_source(path)


def test_ambiguous_rootfiles_are_rejected(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes], minimal_score: bytes
) -> None:
    path = make_mxl(
        [
            (CONTAINER_PATH, make_container("a.xml", "b.xml")),
            ("a.xml", minimal_score),
            ("b.xml", minimal_score),
        ]
    )
    with pytest.raises(ScoreArchiveError, match="several possible"):
        load_musicxml_source(path)


def test_two_musicxml_typed_rootfiles_are_ambiguous(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes], minimal_score: bytes
) -> None:
    path = make_mxl(
        [
            (CONTAINER_PATH, make_container(("a.xml", MXL_TYPE), ("b.xml", MXL_TYPE))),
            ("a.xml", minimal_score),
            ("b.xml", minimal_score),
        ]
    )
    with pytest.raises(ScoreArchiveError, match="several possible"):
        load_musicxml_source(path)


def test_only_non_musicxml_rootfiles(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes]
) -> None:
    path = make_mxl(
        [
            (CONTAINER_PATH, make_container(("a.pdf", "application/pdf"))),
            ("a.pdf", b"%PDF-"),
        ]
    )
    with pytest.raises(ScoreArchiveError, match="no MusicXML rootfile"):
        load_musicxml_source(path)


def test_rootfile_absent_from_archive(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes]
) -> None:
    path = make_mxl([(CONTAINER_PATH, make_container("missing.xml"))])
    with pytest.raises(ScoreArchiveError, match=r"no rootfile 'missing\.xml'"):
        load_musicxml_source(path)


@pytest.mark.parametrize(
    "bad_path",
    [
        "/etc/passwd",
        "\\score.xml",
        "C:/score.xml",
        "C:score.xml",
        "../score.xml",
        "a/../score.xml",
        "a/./score.xml",
        "a//score.xml",
        "dir\\score.xml",
        "dir/",
        "",
    ],
)
def test_unsafe_rootfile_paths_are_rejected_before_reading(
    make_mxl: Callable[..., Path], minimal_score: bytes, bad_path: str
) -> None:
    container = f'<container><rootfiles><rootfile full-path="{bad_path}"/></rootfiles></container>'
    path = make_mxl([(CONTAINER_PATH, container.encode()), ("score.xml", minimal_score)])
    with pytest.raises(ScoreArchiveError, match="refusing to read"):
        load_musicxml_source(path)


def test_traversal_member_is_never_followed(
    make_mxl: Callable[..., Path],
    make_container: Callable[..., bytes],
    minimal_score: bytes,
    tmp_path: Path,
    tree_snapshot: Callable[[], list[str]],
) -> None:
    path = make_mxl(
        [(CONTAINER_PATH, make_container("../escape.xml")), ("../escape.xml", minimal_score)]
    )
    before = tree_snapshot()
    with pytest.raises(ScoreArchiveError, match="refusing to read"):
        load_musicxml_source(path)
    assert tree_snapshot() == before
    assert not (tmp_path.parent / "escape.xml").exists()


def test_validate_member_path_accepts_normal_paths() -> None:
    assert validate_member_path("score.xml") == "score.xml"
    assert validate_member_path("a/b/score.musicxml") == "a/b/score.musicxml"


def test_validate_member_path_rejects_nul_and_overlong() -> None:
    with pytest.raises(ScoreArchiveError):
        validate_member_path("a\x00b.xml")
    with pytest.raises(ScoreArchiveError):
        validate_member_path("a/" * 600 + "b.xml")


def test_duplicate_container_member_is_ambiguous(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes], minimal_score: bytes
) -> None:
    path = make_mxl(
        [
            (CONTAINER_PATH, make_container("score.xml")),
            (CONTAINER_PATH, make_container("other.xml")),
            ("score.xml", minimal_score),
        ]
    )
    with pytest.raises(ScoreArchiveError, match="more than once"):
        load_musicxml_source(path)


def test_duplicate_rootfile_member_is_ambiguous(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes], minimal_score: bytes
) -> None:
    path = make_mxl(
        [
            (CONTAINER_PATH, make_container("score.xml")),
            ("score.xml", minimal_score),
            ("score.xml", b"<score-partwise><part-list/></score-partwise>"),
        ]
    )
    with pytest.raises(ScoreArchiveError, match="more than once"):
        load_musicxml_source(path)


# --- resource limits ------------------------------------------------------------------


def _archive_with_score(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes], score: bytes
) -> Path:
    return make_mxl(
        [(CONTAINER_PATH, make_container("score.xml")), ("score.xml", score)], compression=STORED
    )


def test_rootfile_exactly_at_size_limit_loads(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes]
) -> None:
    path = _archive_with_score(make_mxl, make_container, _xml_of_size(600))
    source = load_musicxml_source(path, LoaderLimits(max_score_bytes=600))
    assert source.size_bytes == 600


def test_rootfile_just_over_size_limit_is_rejected(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes]
) -> None:
    path = _archive_with_score(make_mxl, make_container, _xml_of_size(601))
    with pytest.raises(ScoreResourceLimitError, match="larger than the limit"):
        load_musicxml_source(path, LoaderLimits(max_score_bytes=600))


def test_total_content_limit_boundary(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes]
) -> None:
    container = make_container("score.xml")
    score = _xml_of_size(400)
    path = _archive_with_score(make_mxl, make_container, score)
    total = len(container) + len(score)
    assert load_musicxml_source(path, LoaderLimits(max_total_bytes=total)).size_bytes == 400
    with pytest.raises(ScoreResourceLimitError):
        load_musicxml_source(path, LoaderLimits(max_total_bytes=total - 1))


def test_oversized_container_is_rejected(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes], minimal_score: bytes
) -> None:
    container = make_container("score.xml")
    path = _archive_with_score(make_mxl, make_container, minimal_score)
    assert load_musicxml_source(path, LoaderLimits(max_container_bytes=len(container)))
    with pytest.raises(ScoreResourceLimitError, match=r"container\.xml"):
        load_musicxml_source(path, LoaderLimits(max_container_bytes=len(container) - 1))


def test_too_many_archive_entries(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes], minimal_score: bytes
) -> None:
    members = [
        (CONTAINER_PATH, make_container("score.xml")),
        ("score.xml", minimal_score),
        ("a.txt", b"a"),
        ("b.txt", b"b"),
    ]
    path = make_mxl(members)
    assert load_musicxml_source(path, LoaderLimits(max_archive_entries=4))
    with pytest.raises(ScoreResourceLimitError, match="entries"):
        load_musicxml_source(path, LoaderLimits(max_archive_entries=3))


def test_default_ratio_rejects_a_decompression_bomb(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes]
) -> None:
    bomb = HEAD + b" " * (20 * 1024 * 1024) + TAIL
    path = make_mxl([(CONTAINER_PATH, make_container("score.xml")), ("score.xml", bomb)])
    with pytest.raises(ScoreResourceLimitError, match="decompression bomb"):
        load_musicxml_source(path)


def test_compression_ratio_exactly_at_the_limit_loads(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes]
) -> None:
    data, ratio = _payload_with_exact_ratio()
    path = make_mxl([(CONTAINER_PATH, make_container("score.xml")), ("score.xml", data)])
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo("score.xml")
        assert info.file_size == ratio * info.compress_size  # exactly at the boundary
    assert load_musicxml_source(path, LoaderLimits(max_compression_ratio=ratio)).size_bytes == len(
        data
    )


def test_compression_ratio_just_above_the_limit_is_rejected(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes]
) -> None:
    data, ratio = _payload_with_exact_ratio()
    path = make_mxl([(CONTAINER_PATH, make_container("score.xml")), ("score.xml", data)])
    with pytest.raises(ScoreResourceLimitError, match="decompression bomb"):
        load_musicxml_source(path, LoaderLimits(max_compression_ratio=ratio - 1))


def test_understated_zip_metadata_does_not_bypass_checks(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes]
) -> None:
    path = _archive_with_score(make_mxl, make_container, _xml_of_size(900))

    def understate(data: bytearray, offset: int) -> None:
        struct.pack_into("<I", data, offset + 24, 10)  # claim a tiny uncompressed size

    _patch_central_directory(path, understate)
    with pytest.raises((ScoreArchiveError, ScoreResourceLimitError)):
        load_musicxml_source(path)


def test_overstated_zip_metadata_is_rejected_early(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes]
) -> None:
    path = _archive_with_score(make_mxl, make_container, _xml_of_size(400))

    def overstate(data: bytearray, offset: int) -> None:
        struct.pack_into("<I", data, offset + 24, 1 << 30)

    _patch_central_directory(path, overstate)
    with pytest.raises(ScoreResourceLimitError):
        load_musicxml_source(path)
