"""Loading a MusicXML file of any supported kind into a safely parsed XML tree.

This module only gets a score *safely into memory*. It does not interpret music: no parts,
notes, durations, voices, clefs, tempo, lyrics or repeats.
"""

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from barbershop_tracks.core.errors import (
    ScoreFileError,
    ScoreResourceLimitError,
    UnsupportedScoreFormatError,
)
from barbershop_tracks.core.musicxml.archive import read_score_from_mxl
from barbershop_tracks.core.musicxml.limits import (
    DEFAULT_LIMITS,
    LoaderLimits,
    describe_size,
    read_limited,
)
from barbershop_tracks.core.musicxml.safe_xml import parse_xml

PLAIN_XML_SUFFIXES = frozenset({".musicxml", ".xml"})
COMPRESSED_SUFFIX = ".mxl"
SUPPORTED_ROOT = "score-partwise"
_TIMEWISE_ROOT = "score-timewise"


class SourceKind(Enum):
    PLAIN_XML = "plain_xml"
    COMPRESSED = "compressed"


@dataclass(frozen=True, slots=True)
class MusicXmlSource:
    """A safely loaded score document and where it came from. No musical content."""

    root: ET.Element
    path: Path
    kind: SourceKind
    member_name: str | None  # score member inside an .mxl; None for plain XML
    size_bytes: int  # size of the score XML that was parsed


_EXPORT = "export MusicXML from the notation program the score came from"
_MUSESCORE = (
    "a MuseScore project, which BLT cannot read: in MuseScore choose File > Export, pick MusicXML "
    "(.musicxml) or Compressed MusicXML (.mxl), and open that file"
)
_PICTURE = (
    "a picture of the music (it holds no notes, words or voices that BLT could read, and BLT will "
    f"not guess them): {_EXPORT}; if only the picture exists, the music first has to be entered "
    "in a notation program (scanning programs exist, but their result must be checked bar by bar)"
)
# what a person is likely to hand over instead of a MusicXML file, and what to do about it
WRONG_FILE_KINDS: dict[str, str] = {
    ".mscz": _MUSESCORE,
    ".mscx": _MUSESCORE,
    ".pdf": _PICTURE.replace("a picture of the music", "a PDF, a picture of the music", 1),
    ".png": _PICTURE,
    ".jpg": _PICTURE,
    ".jpeg": _PICTURE,
    ".mid": f"a MIDI file, which has no lyrics and no voice names: {_EXPORT}",
    ".midi": f"a MIDI file, which has no lyrics and no voice names: {_EXPORT}",
}


def wrong_file_advice(name: str) -> str | None:
    """What to do about a file that is not a score BLT reads, by its extension; None if unknown."""
    kind = WRONG_FILE_KINDS.get(Path(name).suffix.lower())
    return None if kind is None else f"{name} is {kind}"


def load_musicxml_source(
    path: str | os.PathLike[str], limits: LoaderLimits = DEFAULT_LIMITS
) -> MusicXmlSource:
    """Load a ``.musicxml``, ``.xml`` or ``.mxl`` file and return its ``score-partwise`` root.

    The file kind is chosen by extension (case-insensitive). Raises a ``ScoreLoadError``
    subclass if the input cannot be loaded safely.
    """
    file_path = Path(path)
    _require_readable_file(file_path)
    suffix = file_path.suffix.lower()
    if suffix in PLAIN_XML_SUFFIXES:
        kind = SourceKind.PLAIN_XML
        data = _read_plain_file(file_path, limits)
        member_name = None
    elif suffix == COMPRESSED_SUFFIX:
        kind = SourceKind.COMPRESSED
        archive_score = read_score_from_mxl(file_path, limits)
        data, member_name = archive_score.data, archive_score.member_name
    else:
        advice = wrong_file_advice(file_path.name)
        raise ScoreFileError(
            f"{advice}. BLT opens .musicxml, .xml and .mxl files"
            if advice is not None
            else f"{file_path.name} has an unsupported extension; expected .musicxml, .xml or .mxl",
            path=file_path,
        )
    what = file_path.name if member_name is None else f"score '{member_name}'"
    root = parse_xml(data, what=what, path=file_path)
    _require_partwise(root, file_path)
    return MusicXmlSource(
        root=root, path=file_path, kind=kind, member_name=member_name, size_bytes=len(data)
    )


def _require_readable_file(path: Path) -> None:
    if not path.exists():
        raise ScoreFileError(f"{path.name} does not exist", path=path)
    if not path.is_file():
        raise ScoreFileError(f"{path.name} is not a file", path=path)


def _read_plain_file(path: Path, limits: LoaderLimits) -> bytes:
    try:
        size = path.stat().st_size
        if size > limits.max_score_bytes:
            raise ScoreResourceLimitError(
                f"{path.name} is larger than the limit of {describe_size(limits.max_score_bytes)}",
                path=path,
            )
        with path.open("rb") as stream:
            return read_limited(stream, limits.max_score_bytes, what=path.name, path=path)
    except OSError as exc:
        raise ScoreFileError(f"cannot read {path.name}: {exc.strerror or exc}", path=path) from exc


def _require_partwise(root: ET.Element, path: Path) -> None:
    if root.tag == SUPPORTED_ROOT:
        return
    if root.tag == _TIMEWISE_ROOT:
        raise UnsupportedScoreFormatError(
            f"{path.name} is a score-timewise MusicXML file, which is not supported; "
            "export it as score-partwise",
            path=path,
        )
    shown = root.tag if len(root.tag) <= 60 else root.tag[:57] + "..."
    raise UnsupportedScoreFormatError(
        f"{path.name} is not a MusicXML score-partwise document (root element '{shown}')",
        path=path,
    )
