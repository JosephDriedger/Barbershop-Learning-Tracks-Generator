import gc
import os
import socket
import warnings
import zipfile
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import NoReturn

import pytest

# The opt-in diagnostics for the GUI tests' garbage-collection workaround are a plugin, so that a
# manual workflow can also load them into an OLDER checkout (docs/gui-gc-diagnostics.md).
pytest_plugins = ["gui_diagnostics"]

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


@pytest.fixture(autouse=True)
def _parts_do_not_follow_the_lead_unless_a_test_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """Most tests are about lyrics the score leaves open, which the convention would fill in."""
    monkeypatch.setenv("BLT_FOLLOW_LEAD", "0")


@pytest.fixture(autouse=True)
def _every_test_has_its_own_cache_folder(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Never the person's real cache: converted scores (and their playback) are kept there, so a
    test would find what an earlier test left (the same bytes make the same key) and the installed
    app would be handed the stand-in programs' conversions."""
    import platformdirs

    folder = str(tmp_path_factory.mktemp("cache"))
    monkeypatch.setattr(platformdirs, "user_cache_dir", lambda *args, **kwargs: folder)


@pytest.fixture(autouse=True)
def _no_garbage_collection_inside_a_gui_test(request: pytest.FixtureRequest) -> Iterator[None]:
    """Collect garbage only between GUI tests, never inside a test's Qt event loop.

    Without this, CI aborted at random ("Fatal Python error: Aborted" in ``MainWindow.changeEvent``
    while a fixture waited for the window; PySide6 6.12.0, offscreen) in about half of the runs of
    the whole suite and in none of the runs of the GUI tests alone. The cause is the timing of
    Python's cycle collector: a collection that happens to run inside Qt's event dispatch can
    finalise wrappers of objects left over from earlier tests. With collection switched off
    during each GUI test and run before and after it, 20 of 20 CI runs passed (10 of 10 with only
    the collections around the test).

    This is a WORKAROUND, not a fix: the lifetime problem underneath is not identified. To run the
    tests without it (and keep the evidence if they abort): ``pytest --gui-gc-stress``
    (docs/gui-gc-diagnostics.md).
    """
    import gui_diagnostics  # a plugin (above); imported late so that pytest can rewrite its asserts

    if "ui" not in request.path.parts or request.config.stash.get(gui_diagnostics.GC_STRESS, False):
        yield
        return
    gc.collect()
    gc.disable()
    try:
        yield
    finally:
        gc.enable()
        gc.collect()
