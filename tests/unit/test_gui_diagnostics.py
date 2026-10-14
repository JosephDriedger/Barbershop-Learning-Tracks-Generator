"""The opt-in diagnostics for the GUI tests' garbage-collection workaround."""

import gc
import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

import gui_diagnostics as gd

REPO = Path(__file__).resolve().parents[2]
TARGET = "tests/unit/ui/test_ui_formatting.py"


def test_the_stress_switch_reads_the_flag_or_the_environment() -> None:
    assert gd.stress_requested(True, {}) is True
    assert gd.stress_requested(False, {}) is False
    assert gd.stress_requested(False, {"BLT_GUI_GC_STRESS": "1"}) is True
    assert gd.stress_requested(False, {"BLT_GUI_GC_STRESS": "Yes"}) is True
    assert gd.stress_requested(False, {"BLT_GUI_GC_STRESS": "0"}) is False


def test_the_threshold_must_be_a_positive_number() -> None:
    assert gd.threshold_from(None, {}) is None
    assert gd.threshold_from(7, {}) == 7
    assert gd.threshold_from(None, {"BLT_GUI_GC_THRESHOLD": "3"}) == 3
    with pytest.raises(ValueError, match="at least 1"):
        gd.threshold_from(None, {"BLT_GUI_GC_THRESHOLD": "0"})


def test_a_command_line_value_wins_over_the_environment() -> None:
    assert gd.option_or_env("a.log", "X", {"X": "b.log"}) == "a.log"
    assert gd.option_or_env(None, "X", {"X": "b.log"}) == "b.log"
    assert gd.option_or_env(None, "X", {}) is None


def test_the_trace_records_tests_and_collections_and_flushes_at_once() -> None:
    handle = io.StringIO()
    trace = gd.GcTrace(handle)
    trace.install()
    try:
        trace.test_started("tests/x.py::test_a")
        gc.collect()
    finally:
        trace.uninstall()
    lines = handle.getvalue().splitlines()
    assert any(" test start tests/x.py::test_a" in line for line in lines)
    starts = [line for line in lines if " gc start " in line]
    stops = [line for line in lines if " gc stop " in line]
    assert starts
    assert stops
    assert "test=tests/x.py::test_a" in starts[0]
    assert "collected=" in stops[0]
    assert trace.callback is None
    before = len(handle.getvalue())
    gc.collect()
    assert len(handle.getvalue()) == before  # uninstalled: nothing more is written


def test_a_trace_that_ends_inside_a_collection_is_recognised() -> None:
    done = ["1 gc start generation=2 x", "2 gc stop generation=2 collected=3 x"]
    assert gd.last_collection_unfinished(done) is False
    assert gd.last_collection_unfinished([*done, "3 gc start generation=0 x"]) is True
    assert gd.last_collection_unfinished(["1 test start a"]) is False


def run_pytest(*arguments: str, **environment: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("BLT_GUI_")}
    env.update(environment)
    return subprocess.run(
        [sys.executable, "-m", "pytest", TARGET, "-q", "-p", "no:cacheprovider", *arguments],
        cwd=REPO,
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
        check=False,
    )


def test_a_stress_run_leaves_a_trace_and_a_crash_log(tmp_path: Path) -> None:
    trace, crash = tmp_path / "gc.log", tmp_path / "crash.txt"
    done = run_pytest(
        "--gui-gc-stress",
        "--gui-gc-threshold",
        "5",
        "--gui-gc-trace",
        str(trace),
        "--gui-crash-log",
        str(crash),
    )
    assert done.returncode == 0, done.stdout + done.stderr
    lines = trace.read_text(encoding="utf-8").splitlines()
    assert " session start stress=True threshold=5" in lines[0]
    assert " session end" in lines[-1]
    assert any(f" test start {TARGET}::" in line for line in lines)
    assert sum(" gc start " in line for line in lines) > 50  # a threshold of 5 collects constantly
    assert crash.exists()


def test_the_environment_variables_do_the_same(tmp_path: Path) -> None:
    trace = tmp_path / "env.log"
    done = run_pytest(BLT_GUI_GC_STRESS="1", BLT_GUI_GC_THRESHOLD="9", BLT_GUI_GC_TRACE=str(trace))
    assert done.returncode == 0, done.stdout + done.stderr
    assert " session start stress=True threshold=9" in trace.read_text(encoding="utf-8")


def test_the_crash_log_is_set_up_after_pytests_own_faulthandler() -> None:
    # pytest's faulthandler plugin enables faulthandler onto stderr in its own configure hook; ours
    # must run after it, or the dump of an abort goes to the console and the crash log stays
    # empty (observed on the first stress run of M17)
    options = gd.pytest_configure.pytest_impl  # type: ignore[attr-defined]
    assert options["trylast"] is True
