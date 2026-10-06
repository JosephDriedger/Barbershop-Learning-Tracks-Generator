import os
import socket
import warnings
import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NoReturn

import pytest

# Run any Qt code without a display (CI and headless machines).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

MINIMAL_SCORE = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b'<score-partwise version="4.0"><part-list/></score-partwise>\n'
)

# The DOCTYPE MuseScore (and most MusicXML writers) emit.
MUSESCORE_SCORE = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b'<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" '
    b'"http://www.musicxml.org/dtds/partwise.dtd">\n'
    b'<score-partwise version="4.0"><part-list/></score-partwise>\n'
)


@pytest.fixture
def minimal_score() -> bytes:
    return MINIMAL_SCORE


@pytest.fixture
def musescore_score() -> bytes:
    return MUSESCORE_SCORE


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail the test if anything tries to open a socket or resolve a host name."""

    def forbidden(*args: object, **kwargs: object) -> NoReturn:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


@pytest.fixture
def make_container() -> Callable[..., bytes]:
    """Build a ``container.xml``. Each rootfile is a path or a ``(path, media_type)`` pair."""

    def build(*rootfiles: str | tuple[str, str | None]) -> bytes:
        entries = []
        for item in rootfiles:
            path, media = (item, None) if isinstance(item, str) else item
            media_attr = f' media-type="{media}"' if media else ""
            entries.append(f'<rootfile full-path="{path}"{media_attr}/>')
        body = "".join(entries)
        document = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f"<container><rootfiles>{body}</rootfiles></container>"
        )
        return document.encode()

    return build


@pytest.fixture
def make_mxl(tmp_path: Path) -> Callable[..., Path]:
    """Build a ``.mxl`` in ``tmp_path`` from ``(member name, bytes)`` pairs."""

    def build(
        members: Sequence[tuple[str, bytes]],
        *,
        name: str = "score.mxl",
        compression: int = zipfile.ZIP_DEFLATED,
    ) -> Path:
        path = tmp_path / name
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # duplicate member names warn; tests want them
            with zipfile.ZipFile(path, "w", compression=compression) as archive:
                for member, data in members:
                    archive.writestr(member, data)
        return path

    return build


@pytest.fixture
def musescore_mxl(
    make_mxl: Callable[..., Path], make_container: Callable[..., bytes], musescore_score: bytes
) -> Path:
    """A MuseScore-style archive: container without media-type, score.xml."""
    return make_mxl(
        [("META-INF/container.xml", make_container("score.xml")), ("score.xml", musescore_score)]
    )


@pytest.fixture
def tree_snapshot(tmp_path: Path) -> Callable[[], list[str]]:
    """Return a function listing every file under ``tmp_path`` (to prove nothing is extracted)."""

    def snapshot() -> list[str]:
        return sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))

    return snapshot
