import os
import subprocess
import sys

import pytest
from pytestqt.qtbot import QtBot

from barbershop_tracks.ui.main_window import MainWindow


@pytest.mark.gui
def test_main_window_constructs(qtbot: QtBot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.windowTitle() == "BarbershopLearningTracks"


@pytest.mark.gui
def test_gui_entry_point_smoke_test() -> None:
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    result = subprocess.run(
        [sys.executable, "-m", "barbershop_tracks", "--smoke-test"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
