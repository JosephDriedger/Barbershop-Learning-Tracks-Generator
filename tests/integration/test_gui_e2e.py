"""The GUI's whole workflow against the real pipeline, host and a generated voicebank.

No ALYS, no redistributed voicebank: the singer is a few generated sine waves. A fake file dialog
and a fake "open folder" stand in for the operating system; everything else is the real thing.
"""

import json
import time
from pathlib import Path
from typing import Any

import pytest
import yaml
from pytestqt.qtbot import QtBot

from barbershop_tracks.models import VoiceRole
from barbershop_tracks.ui.controller import AppController
from barbershop_tracks.ui.dialogs import LyricReviewDialog
from barbershop_tracks.ui.main_window import MainWindow
from barbershop_tracks.ui.preferences import Preferences
from cli_scores import LINES, write_quartet
from gui_support import FakePrompts
from host_support import host_environment, require_host
from synthetic_voicebank import SINGER_ID, build_voicebank

pytestmark = [pytest.mark.integration, pytest.mark.gui]

ROLES = {
    "tenor": VoiceRole.TENOR,
    "lead": VoiceRole.LEAD,
    "baritone": VoiceRole.BARITONE,
    "bass": VoiceRole.BASS,
}


class Gui:
    def __init__(self, qtbot: QtBot, root: Path) -> None:
        host = require_host()
        self.qtbot, self.root = qtbot, root
        build_voicebank(root / "voices")
        self.prefs = Preferences.at(root / "prefs.ini")
        self.prefs.singers_dir = str(root / "voices")
        environ = {
            "BLT_CONFIG": str(root / "none.json"),
            "BLT_DATA_DIR": str(root / "data"),
            "BLT_HOST_DIR": str(host),
            **{k: v for k, v in host_environment().items() if k == "DOTNET_ROOT"},
        }
        self.controller = AppController(
            self.prefs, environ=environ, config_file=root / "none.json", debounce_ms=1
        )
        self.prompts = FakePrompts()
        self.opened: list[Path] = []
        self.window = MainWindow(
            self.prefs, controller=self.controller, prompts=self.prompts, opener=self._open
        )
        qtbot.addWidget(self.window)
        self.window.show()
        qtbot.waitUntil(lambda: self.controller.installed is not None, timeout=20000)
        self.events: list[dict[str, Any]] = []
        self.controller.generation_event.connect(self.events.append)

    def _open(self, path: Path) -> bool:
        self.opened.append(path)
        return True

    def prepare(self, **score_options: Any) -> None:
        score_options.setdefault("word", "la")
        score = write_quartet(self.root, **score_options)
        with self.qtbot.waitSignal(self.controller.score_loaded, timeout=30000):
            self.window.open_score(score)
        for name, role in ROLES.items():
            combo = self.window.assignment_section.combo_for(LINES[name])
            assert combo is not None
            combo.setCurrentIndex(combo.findData(role))
        self.qtbot.waitUntil(lambda: not self.controller.validating, timeout=30000)
        for role in ROLES.values():
            box = self.window.voices_section.combos[role]
            assert box.findData(SINGER_ID) > 0  # the generated voice was found by scanning
            box.setCurrentIndex(box.findData(SINGER_ID))
            box.activated.emit(box.currentIndex())
        self.prompts.answers["Where should the tracks be saved?"] = str(self.root / "out")
        self.window.choose_output_folder()

    @property
    def package(self) -> Path:
        return self.root / "out" / "quartet_learning_tracks"

    def staging(self) -> list[str]:
        folder = self.root / "data" / "staging"
        return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []


@pytest.fixture
def gui(qtbot: QtBot, tmp_path: Path) -> Gui:
    return Gui(qtbot, tmp_path)


def test_select_assign_generate_and_open_the_folder(gui: Gui) -> None:
    gui.prepare(all_lyrics=True)
    window, progress = gui.window, gui.window.progress_section
    assert window.generate.isEnabled()
    assert window.output_section.location.text() == str(gui.package)

    with gui.qtbot.waitSignal(gui.controller.generation_finished, timeout=300000):
        window.generate.click()

    names = sorted(p.name for p in gui.package.iterdir())
    assert len([n for n in names if n.endswith(".wav")]) == 13
    assert "manifest.json" in names
    assert len(names) == 14  # nothing else is published by default
    assert progress.result_box.isVisible()
    assert "ready" in progress.result_title.text()
    assert "13 tracks (WAV)" in progress.result_text.text()
    stages = [e["stage"] for e in gui.events if e["event"] == "stage" and e["status"] == "started"]
    assert stages[0] == "source_loading"
    assert "stem_rendering" in stages
    assert "package_publication" in stages
    mixing = [e for e in gui.events if e["event"] == "progress"]
    assert [e["completed"] for e in mixing] == list(range(1, 14))
    assert progress.steps.count() == 9
    assert gui.staging() == []
    progress.open_folder.click()
    assert gui.opened == [gui.package]


def test_missing_harmony_lyrics_are_resolved_in_the_review_then_generated(gui: Gui) -> None:
    gui.prepare(all_lyrics=False, lyric_part=1)
    window = gui.window
    assert not window.generate.isEnabled()
    assert window.validation_section.review.isEnabled()

    def approve(dialog: Any) -> bool:
        assert isinstance(dialog, LyricReviewDialog)
        rows = list(range(dialog.model.rowCount()))
        dialog.state.fill_text(rows, "ba")
        dialog.model.changed_all()
        dialog.approve_typed()
        dialog.accept()
        return True

    window.run_dialog = approve
    window.open_review()
    gui.qtbot.waitUntil(lambda: not gui.controller.validating, timeout=30000)
    assert window.generate.isEnabled()
    window.output_section.keep_project.setChecked(True)
    with gui.qtbot.waitSignal(gui.controller.generation_finished, timeout=300000):
        window.generate.click()
    project = yaml.safe_load((gui.package / "project" / "project.ustx").read_text(encoding="utf-8"))
    lyrics = {
        project["tracks"][part["track_no"]]["track_name"]: part["notes"][0]["lyric"]
        for part in project["voice_parts"]
    }
    assert lyrics == {"Tenor": "ba", "Lead": "la", "Baritone": "ba", "Bass": "ba"}


def test_cancelling_a_real_generation_leaves_no_package(gui: Gui) -> None:
    gui.prepare(all_lyrics=True)
    gui.window.generate.click()
    gui.qtbot.waitUntil(
        lambda: any(e.get("event") == "host" and e.get("name") == "init" for e in gui.events),
        timeout=120000,
    )
    with gui.qtbot.waitSignal(gui.controller.generation_failed, timeout=120000):
        gui.window.progress_section.cancel.click()
    assert "cancelled" in gui.window.progress_section.result_title.text().lower()
    assert not gui.package.exists()
    deadline = time.monotonic() + 15
    while gui.staging() and time.monotonic() < deadline:
        gui.qtbot.wait(100)
    assert gui.staging() == []
    assert gui.window.generate.isEnabled()  # and it can be run again


def test_a_voice_the_synthetic_bank_cannot_sing_is_explained(gui: Gui) -> None:
    gui.prepare(all_lyrics=True, word="zzz")  # not an alias of the generated voicebank
    with gui.qtbot.waitSignal(gui.controller.generation_failed, timeout=300000):
        gui.window.generate.click()
    progress = gui.window.progress_section
    assert "silent or wrong" in progress.result_title.text().lower()
    assert "STEM_" in progress.technical.toPlainText()
    assert not gui.package.exists()
    json.dumps(gui.events)  # every event stayed plain JSON on its way through the GUI
