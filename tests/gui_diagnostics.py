"""Opt-in diagnostics for the GUI tests' garbage-collection workaround (docs/gui-gc-diagnostics.md).

The workaround in ``conftest.py`` keeps Python's cycle collector from running inside a GUI test. It hides
a crash that was seen on CI ("Fatal Python error: Aborted" inside ``MainWindow.changeEvent``); the
underlying lifetime problem is NOT identified and NOT fixed. These helpers let a person (or the manual
``gui-stress`` workflow) run the same tests WITHOUT the workaround and keep what is needed to learn
more when it aborts:

* ``--gui-gc-stress`` (or ``BLT_GUI_GC_STRESS=1``): do not switch collection off during GUI tests;
* ``--gui-gc-threshold N`` (or ``BLT_GUI_GC_THRESHOLD``): make collections far more frequent
  (``gc.set_threshold(N, N, N)``); small values make a collection-related abort likely, so a lifetime bug
  shows up in a few runs instead of a few dozen;
* ``--gui-gc-trace FILE`` (or ``BLT_GUI_GC_TRACE``): append a line for every test start and every
  collection start/stop (flushed at once, so the last lines survive an abort: a ``start`` with no
  ``stop`` as the last collection means the process died inside a collection);
* ``--gui-crash-log FILE`` (or ``BLT_GUI_CRASH_LOG``): send Python's fatal-error traceback (all threads)
  to FILE instead of the console, where a CI log can lose it.

None of this runs unless asked for; the default test run is unchanged.
"""

from __future__ import annotations

import faulthandler
import gc
import os
import threading
import time
from collections.abc import Callable, Mapping
from typing import IO, Any

import pytest

TRUE_WORDS = ("1", "true", "yes", "on")


def option_or_env(value: Any, env_name: str, environ: Mapping[str, str]) -> str | None:
    """A command-line value if given, else the environment variable, else None."""
    if value not in (None, "", False):
        return str(value)
    found = environ.get(env_name, "").strip()
    return found or None


def stress_requested(flag: bool, environ: Mapping[str, str]) -> bool:
    """True when the workaround must NOT be applied."""
    return bool(flag) or environ.get("BLT_GUI_GC_STRESS", "").strip().lower() in TRUE_WORDS


def threshold_from(value: Any, environ: Mapping[str, str]) -> int | None:
    found = option_or_env(value, "BLT_GUI_GC_THRESHOLD", environ)
    if found is None:
        return None
    number = int(found)
    if number < 1:
        raise ValueError("the garbage-collection threshold must be at least 1")
    return number


class GcTrace:
    """A line-per-event log of test starts and collections, flushed immediately."""

    def __init__(self, handle: IO[str]) -> None:
        self.handle = handle
        self.current = "(none yet)"
        self.callback: Callable[[str, dict[str, int]], None] | None = None

    def write(self, text: str) -> None:
        self.handle.write(f"{time.monotonic():.6f} {text}\n")
        self.handle.flush()

    def test_started(self, nodeid: str) -> None:
        self.current = nodeid
        self.write(f"test start {nodeid}")

    def install(self) -> None:
        def on_collection(phase: str, info: dict[str, int]) -> None:
            tail = f" collected={info.get('collected', 0)}" if phase == "stop" else ""
            self.write(
                f"gc {phase} generation={info.get('generation')}{tail} "
                f"thread={threading.current_thread().name} test={self.current}"
            )

        self.callback = on_collection
        gc.callbacks.append(on_collection)

    def uninstall(self) -> None:
        if self.callback is not None and self.callback in gc.callbacks:
            gc.callbacks.remove(self.callback)
        self.callback = None


def last_collection_unfinished(lines: list[str]) -> bool:
    """Did a trace end inside a collection (the last gc line is a start)?"""
    for line in reversed(lines):
        if " gc start " in line:
            return True
        if " gc stop " in line:
            return False
    return False


def enable_crash_log(path: str) -> IO[str]:
    """Send fatal-error tracebacks of all threads to ``path`` (the caller keeps the handle open)."""
    handle = open(path, "a", buffering=1, encoding="utf-8")  # noqa: SIM115, PTH123
    faulthandler.enable(file=handle, all_threads=True)
    return handle


def summary(environ: Mapping[str, str] | None = None) -> str:
    environ = environ or os.environ
    return (
        f"gc stress={stress_requested(False, environ)} "
        f"threshold={threshold_from(None, environ)} "
        f"trace={option_or_env(None, 'BLT_GUI_GC_TRACE', environ)} "
        f"crash-log={option_or_env(None, 'BLT_GUI_CRASH_LOG', environ)}"
    )


# --- opt-in diagnostics for that workaround (tests/py, docs/gui-gc-diagnostics.md)

GC_STRESS = pytest.StashKey[bool]()
GC_TRACE = pytest.StashKey[GcTrace]()
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
    stress = stress_requested(config.getoption("--gui-gc-stress"), environ)
    config.stash[GC_STRESS] = stress
    threshold = threshold_from(config.getoption("--gui-gc-threshold"), environ)
    if threshold is not None:
        gc.set_threshold(threshold, threshold, threshold)
    trace_path = option_or_env(config.getoption("--gui-gc-trace"), "BLT_GUI_GC_TRACE", environ)
    if trace_path:
        trace = GcTrace(open(trace_path, "a", encoding="utf-8"))  # noqa: SIM115, PTH123
        trace.write(f"session start stress={stress} threshold={threshold}")
        trace.install()
        config.stash[GC_TRACE] = trace
    crash_path = option_or_env(config.getoption("--gui-crash-log"), "BLT_GUI_CRASH_LOG", environ)
    if crash_path:
        config.stash[CRASH_LOG] = enable_crash_log(crash_path)


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
