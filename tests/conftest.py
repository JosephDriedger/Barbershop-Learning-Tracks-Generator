import gc
import os
import socket
import warnings
import zipfile
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import IO, NoReturn

import pytest

import gui_diagnostics

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
    if "ui" not in request.path.parts or request.config.stash.get(GC_STRESS, False):
        yield
        return
    gc.collect()
    gc.disable()
    try:
        yield
    finally:
        gc.enable()
        gc.collect()


# --- opt-in diagnostics for that workaround (tests/gui_diagnostics.py, docs/gui-gc-diagnostics.md)

GC_STRESS = pytest.StashKey[bool]()
GC_TRACE = pytest.StashKey[gui_diagnostics.GcTrace]()
CRASH_LOG = pytest.StashKey[IO[str]]()


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("blt-gui-diagnostics", "GUI garbage-collection diagnostics (opt-in)")
    group.addoption(
        "--gui-gc-stress",
        action="store_true",
        help="run the GUI tests WITHOUT the garbage-collection workaround (or BLT_GUI_GC_STRESS=1)",
    )
    group.addoption(
        "--gui-gc-threshold",
        type=int,
        default=None,
        help="collect garbage at this many allocations (small = often); or BLT_GUI_GC_THRESHOLD",
    )
    group.addoption(
        "--gui-gc-trace",
        default=None,
        metavar="FILE",
        help="log every test start and collection to FILE, flushed at once; or BLT_GUI_GC_TRACE",
    )
    group.addoption(
        "--gui-crash-log",
        default=None,
        metavar="FILE",
        help="write Python's fatal-error traceback (all threads) to FILE; or BLT_GUI_CRASH_LOG",
    )


def pytest_configure(config: pytest.Config) -> None:
    environ = os.environ
    stress = gui_diagnostics.stress_requested(config.getoption("--gui-gc-stress"), environ)
    config.stash[GC_STRESS] = stress
    threshold = gui_diagnostics.threshold_from(config.getoption("--gui-gc-threshold"), environ)
    if threshold is not None:
        gc.set_threshold(threshold, threshold, threshold)
    trace_path = gui_diagnostics.option_or_env(
        config.getoption("--gui-gc-trace"), "BLT_GUI_GC_TRACE", environ
    )
    if trace_path:
        trace = gui_diagnostics.GcTrace(open(trace_path, "a", encoding="utf-8"))  # noqa: SIM115, PTH123
        trace.write(f"session start stress={stress} threshold={threshold}")
        trace.install()
        config.stash[GC_TRACE] = trace
    crash_path = gui_diagnostics.option_or_env(
        config.getoption("--gui-crash-log"), "BLT_GUI_CRASH_LOG", environ
    )
    if crash_path:
        config.stash[CRASH_LOG] = gui_diagnostics.enable_crash_log(crash_path)


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: pytest.Item) -> None:
    trace = item.config.stash.get(GC_TRACE, None)
    if trace is not None:
        trace.test_started(item.nodeid)


def pytest_unconfigure(config: pytest.Config) -> None:
    trace = config.stash.get(GC_TRACE, None)
    if trace is not None:
        trace.write("session end")
        trace.uninstall()
        trace.handle.close()
