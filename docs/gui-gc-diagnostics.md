# The GUI tests' garbage-collection workaround: what is known, what is not, and how to look further

**The underlying problem is not identified and not fixed.** The test suite carries a workaround; this page records the evidence, the opt-in way to run the tests *without* it, and what would have to be shown
before anyone says the problem is solved.

## What happened

From commit `56d5db3` on, the `checks` job of CI aborted at random: `Fatal Python error: Aborted`, always inside `MainWindow.changeEvent` (`src/barbershop_tracks/ui/main_window.py`), always while the `rig` fixture of
`tests/unit/ui/test_ui_window.py` waited for a freshly shown window (`qtbot.waitUntil`). PySide6 6.12.0, Windows, `QT_QPA_PLATFORM=offscreen`. No Qt message was ever printed.

Measured on CI by repeating the plain `pytest` run on the same runner image (each number is one full run of the suite on its own machine):

| Code under test | Runs | Aborts |
|---|---|---|
| `b4b99bb` (end of M15) | 10 | 0 (one run failed for another reason) |
| `99d1648` (M16) | 10 | 5 |
| `99d1648`, only the GUI tests | 8 | 0 |
| `99d1648`, a handful of the new non-GUI tests left out (two different selections) | 8 each | 0 |
| `99d1648` plus the workaround below | 20 | 0 |
| `e2b6b68` (workaround in the suite) | 16 | 0 |

What that pattern says: the abort needs the GUI tests to run **after** other tests in the same process, and it depends on what those tests allocated, not on any single test. That is how the timing of Python's cycle
collector behaves. Whether the collector is the cause or only the trigger is not known.

## The workaround (`tests/conftest.py`)

Inside every test below `tests/unit/ui/`, collection is switched off (`gc.disable()`), and run explicitly before and after the test. It stays in the suite. It is **not** a fix and **not** evidence of one: it only keeps
the collector from running while Qt delivers events. Turning off `pytest-qt`'s own Qt-log capture (`--no-qt-log`) did not change the failure rate and was dropped.

Two things the evidence does *not* show: that the product can crash this way (the abort has not been seen in the packaged program, whose GUI objects live for the whole run), and that the objects left behind by
the tests are the only ones involved.

## Running the tests without the workaround (opt-in; the default run is unchanged)

Options of `tests/conftest.py` (also environment variables), implemented in `tests/gui_diagnostics.py`:

| Option | Environment | Effect |
|---|---|---|
| `--gui-gc-stress` | `BLT_GUI_GC_STRESS=1` | do **not** apply the workaround |
| `--gui-gc-threshold N` | `BLT_GUI_GC_THRESHOLD` | `gc.set_threshold(N, N, N)`: collect every N allocations. Small numbers make a collection-related fault likely and the run very slow (5 is hopeless on a full suite; 50-200 is usable) |
| `--gui-gc-trace FILE` | `BLT_GUI_GC_TRACE` | one flushed line per test start and per collection start/stop, with the thread and the test. If the process dies, the last collection line tells you whether it died *inside* a collection (a `start` with no `stop`) |
| `--gui-crash-log FILE` | `BLT_GUI_CRASH_LOG` | Python's fatal-error traceback of **all** threads goes to FILE, where a CI log cannot lose it |

Locally:

```
pytest tests/unit --gui-gc-stress --gui-gc-threshold 100 --gui-gc-trace research-output/gc.log --gui-crash-log research-output/crash.txt
```

On CI: **Actions > gui-stress > Run workflow** (`.github/workflows/gui-stress.yml`; manual only, nothing triggers it, nothing depends on it). It repeats the unit tests *N* times without the workaround, enables Windows
crash dumps for `python.exe` (`HKLM\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps`, full dumps), and uploads `stress-logs/` (the per-run pytest output, GC traces, crash logs, dumps and a summary line)
as an artifact kept for 14 days. A red run there is a finding, not a broken build.

## Reading a result

* **No abort in many runs at a small threshold**: the collector alone does not trigger it under that load; it proves nothing about the cause.
* **Abort, last trace line `gc start` with no `stop`**: the process died inside a collection: a finaliser of a Qt/PySide object is the suspect. The crash log shows the Python frames that were live; the dump
  (open it in WinDbg with the PySide6 and Python symbols) shows the native stack, which is what names the object.
* **Abort, last trace line a test start or a `gc stop`**: not a collection in flight. The collector is then a bystander and the workaround worked by luck; look at the native stack in the dump.

## What would count as a fix

All of: (1) the object (or class of objects) whose lifetime is wrong is named from a crash log or dump; (2) a targeted test fails without the correction and passes with it; (3) the full suite passes
**without** the workaround in at least 100 consecutive CI runs including runs at a small collection threshold; (4) the workaround is then removed in a change of its own. Until then it stays, and this page stays.
