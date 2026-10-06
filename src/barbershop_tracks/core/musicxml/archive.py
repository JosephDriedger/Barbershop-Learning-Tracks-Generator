"""Reading the score out of a compressed ``.mxl`` archive, in memory.

This is deliberately not a general ZIP extractor: it locates ``META-INF/container.xml``,
resolves one rootfile, and reads only those two members into memory. Nothing is written to
disk and unrelated members are never read (all entries still count toward the entry limit).
"""

import xml.etree.ElementTree as ET
import zipfile
import zlib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from barbershop_tracks.core.errors import (
    ScoreArchiveError,
    ScoreFileError,
    ScoreResourceLimitError,
)
from barbershop_tracks.core.musicxml.limits import (
    LoaderLimits,
    describe_size,
    exceeds_ratio,
    read_limited,
)
from barbershop_tracks.core.musicxml.safe_xml import parse_xml

CONTAINER_PATH: Final = "META-INF/container.xml"

# Rootfile selection policy (v1). A <rootfile> is a *candidate* for the score when its
# media-type attribute is absent (MuseScore omits it) or is one of the MusicXML media types
# below (compared case-insensitively, as media types are). Exactly one candidate is used;
# none is an error; several are an error because choosing between them would be a guess.
# Rootfiles declaring any other media type (PDF, MIDI, ...) are not candidates.
MUSICXML_MEDIA_TYPES: Final = frozenset(
    {"application/vnd.recordare.musicxml+xml", "application/vnd.recordare.musicxml"}
)
_MAX_PATH_LENGTH = 1024
_ENCRYPTED_FLAG = 0x1


@dataclass(frozen=True, slots=True)
class ArchiveScore:
    """The score bytes read from an archive and the (validated) member they came from."""

    data: bytes
    member_name: str


def read_score_from_mxl(path: Path, limits: LoaderLimits) -> ArchiveScore:
    """Return the score XML bytes of the ``.mxl`` archive at ``path``."""
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise ScoreArchiveError(f"{path.name} is not a valid ZIP archive", path=path) from exc
    except OSError as exc:
        raise ScoreFileError(f"cannot read {path.name}: {exc.strerror or exc}", path=path) from exc
    with archive:
        members = _index_members(archive, limits, path)
        container_info = _find_unique(members, CONTAINER_PATH, "META-INF/container.xml", path)
        container_bytes = _read_member(
            archive,
            container_info,
            min(limits.max_container_bytes, limits.max_total_bytes),
            "META-INF/container.xml",
            limits,
            path,
        )
        container_root = parse_xml(container_bytes, what="META-INF/container.xml", path=path)
        score_name = _select_rootfile(container_root, path)
        score_info = _find_unique(members, score_name, f"rootfile '{score_name}'", path)
        remaining = limits.max_total_bytes - len(container_bytes)
        score_bytes = _read_member(
            archive,
            score_info,
            min(limits.max_score_bytes, remaining),
            f"rootfile '{score_name}'",
            limits,
            path,
        )
    return ArchiveScore(data=score_bytes, member_name=score_name)


def validate_member_path(raw: str, path: Path | None = None) -> str:
    """Check a rootfile path from ``container.xml`` and return it unchanged.

    Rejects empty, over-long, absolute, drive-qualified, backslash, NUL-containing and
    ``.``/``..``/empty-component paths, and paths that name a directory.
    """
    problem: str | None = None
    if not raw or len(raw) > _MAX_PATH_LENGTH:
        problem = "is empty or too long"
    elif "\x00" in raw:
        problem = "contains a NUL character"
    elif "\\" in raw:
        problem = "uses backslashes"
    elif raw.startswith("/") or (len(raw) > 1 and raw[1] == ":"):
        problem = "is an absolute path"
    elif raw.endswith("/"):
        problem = "names a directory"
    elif any(part in ("", ".", "..") for part in raw.split("/")):
        problem = "contains empty, '.' or '..' components"
    if problem:
        raise ScoreArchiveError(
            f"container.xml rootfile path {problem}; refusing to read it", path=path
        )
    return raw


def _index_members(
    archive: zipfile.ZipFile, limits: LoaderLimits, path: Path
) -> dict[str, list[zipfile.ZipInfo]]:
    infos = archive.infolist()
    if not infos:
        raise ScoreArchiveError(f"{path.name} contains no files", path=path)
    if len(infos) > limits.max_archive_entries:
        raise ScoreResourceLimitError(
            f"{path.name} has more than {limits.max_archive_entries} entries", path=path
        )
    index: dict[str, list[zipfile.ZipInfo]] = defaultdict(list)
    for info in infos:
        # orig_filename is platform independent (zipfile rewrites separators on Windows).
        index[info.orig_filename.replace("\\", "/")].append(info)
    return index


def _find_unique(
    members: dict[str, list[zipfile.ZipInfo]], name: str, label: str, path: Path
) -> zipfile.ZipInfo:
    matches = members.get(name, [])
    if not matches:
        raise ScoreArchiveError(f"{path.name} has no {label}", path=path)
    if len(matches) > 1:
        raise ScoreArchiveError(
            f"{path.name} contains {label} more than once; the archive is ambiguous", path=path
        )
    return matches[0]


def _select_rootfile(container: ET.Element, path: Path) -> str:
    if _local_name(container.tag) != "container":
        raise ScoreArchiveError(
            "META-INF/container.xml does not have a <container> root", path=path
        )
    rootfiles = [el for el in container.iter() if _local_name(el.tag) == "rootfile"]
    if not rootfiles:
        raise ScoreArchiveError("META-INF/container.xml declares no rootfile", path=path)
    # media-type is optional (MuseScore omits it). Only rootfiles that are MusicXML, or do
    # not say what they are, can be the score; other declared types (PDF, MIDI) are ignored.
    candidates = [el for el in rootfiles if _is_candidate_media_type(el.get("media-type"))]
    if not candidates:
        raise ScoreArchiveError("META-INF/container.xml declares no MusicXML rootfile", path=path)
    if len(candidates) > 1:
        raise ScoreArchiveError(
            "META-INF/container.xml declares several possible score rootfiles; "
            "cannot choose one safely",
            path=path,
        )
    full_path = candidates[0].get("full-path")
    if full_path is None:
        raise ScoreArchiveError("the container.xml rootfile has no full-path", path=path)
    return validate_member_path(full_path, path)


def _is_candidate_media_type(media_type: str | None) -> bool:
    return media_type is None or media_type.strip().lower() in MUSICXML_MEDIA_TYPES


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _read_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    max_bytes: int,
    label: str,
    limits: LoaderLimits,
    path: Path,
) -> bytes:
    # Encryption matters only for members we must read. Unrelated encrypted members are
    # never opened, so they cannot make an otherwise usable score fail.
    if info.flag_bits & _ENCRYPTED_FLAG:
        raise ScoreArchiveError(
            f"{label} in {path.name} is encrypted, which is not supported", path=path
        )
    # Declared sizes give a fast, early rejection but are never trusted: the real limit
    # is enforced on the bytes actually decompressed.
    if info.file_size > max_bytes:
        raise ScoreResourceLimitError(
            f"{label} is larger than the limit of {describe_size(max_bytes)}", path=path
        )
    if exceeds_ratio(info.file_size, info.compress_size, limits.max_compression_ratio):
        raise _ratio_error(label, limits, path)
    try:
        with archive.open(info) as stream:
            data = read_limited(stream, max_bytes, what=label, path=path)
    except ScoreResourceLimitError:
        raise
    except (zipfile.BadZipFile, zlib.error, EOFError) as exc:
        raise ScoreArchiveError(f"{label} in {path.name} is corrupt", path=path) from exc
    except (NotImplementedError, RuntimeError) as exc:
        raise ScoreArchiveError(
            f"{label} in {path.name} uses an unsupported or encrypted compression", path=path
        ) from exc
    if exceeds_ratio(len(data), info.compress_size, limits.max_compression_ratio):
        raise _ratio_error(label, limits, path)
    return data


def _ratio_error(label: str, limits: LoaderLimits, path: Path) -> ScoreResourceLimitError:
    return ScoreResourceLimitError(
        f"{label} in {path.name} is compressed more than {limits.max_compression_ratio}:1, "
        "which looks like a decompression bomb",
        path=path,
    )
