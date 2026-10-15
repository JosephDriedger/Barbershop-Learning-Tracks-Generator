"""The packaged GUI starter opens no window to say Qt is missing when it is run unattended."""

import subprocess
import sys
import textwrap
from pathlib import Path

ENTRY = Path(__file__).resolve().parents[2] / "packaging" / "entry_gui.py"

# a Python process in which PySide6.QtWidgets cannot be imported, as when a package lost Qt6Widgets.dll
RUN_WITHOUT_QT = textwrap.dedent(
    f"""
    import runpy, sys
    class Missing:
        @staticmethod
        def find_spec(name, path=None, target=None):
            if name.startswith("PySide6.QtWidgets"):
                raise ImportError("DLL load failed while importing QtWidgets")
            return None
    sys.meta_path.insert(0, Missing)
    sys.argv = ["entry_gui", *sys.argv[2:]]
    runpy.run_path({str(ENTRY)!r}, run_name="__main__")
    """
)


def run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", RUN_WITHOUT_QT, "--", *arguments],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_a_smoke_test_without_qt_exits_with_a_message_and_no_window() -> None:
    result = run("--smoke-test")
    assert result.returncode == 3
    assert "BLT cannot start" in result.stderr
    assert "QtWidgets" in result.stderr


def test_a_normal_start_without_qt_still_reports_the_problem() -> None:
    result = run()
    assert result.returncode != 0
    assert "ImportError" in result.stderr
