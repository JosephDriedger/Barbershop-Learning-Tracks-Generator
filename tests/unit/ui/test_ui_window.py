"""The main window, driven like a user would, with a fake pipeline."""

import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QDialog, QGroupBox, QWidget
from pytestqt.qtbot import QtBot

from barbershop_tracks.core.pipeline import ErrorCategory, PipelineError
from barbershop_tracks.core.rendering import CancelToken
from barbershop_tracks.models import VoiceRole
from barbershop_tracks.ui.assignments import Ignore
from barbershop_tracks.ui.controller import AppController
from barbershop_tracks.ui.dialogs import AdvancedDialog
from barbershop_tracks.ui.main_window import MainWindow
from barbershop_tracks.ui.preferences import Preferences
from cli_scores import LINES, write_quartet
from gui_support import FakePrompts

pytestmark = pytest.mark.gui

ROLE_BY_NAME = {
    "tenor": VoiceRole.TENOR,
    "lead": VoiceRole.LEAD,
    "baritone": VoiceRole.BARITONE,
    "bass": VoiceRole.BASS,
}


class FakePipeline:
    def __init__(self) -> None:
        self.requests: list[Any] = []
        self.error: PipelineError | None = None
        self.gate = threading.Event()
        self.gate.set()
        self.began = threading.Event()
        self.destination = Path("C:/Tracks/quartet_learning_tracks")

    def __call__(self, request: Any, config: Any, *, cancel: CancelToken, on_event: Any) -> Any:
        self.requests.append(request)
        self.began.set()
        for stage in ("source_loading", "score_analysis", "stem_rendering"):
            on_event({"event": "stage", "stage": stage, "status": "started"})
            on_event({"event": "stage", "stage": stage, "status": "finished"})
        on_event({"event": "stage", "stage": "mixing", "status": "started"})
        for number in range(1, 4):
            on_event({"event": "progress", "stage": "mixing", "completed": number, "total": 13})
        while not self.gate.wait(0.01):
            if cancel.cancelled:
                raise PipelineError(ErrorCategory.CANCELLED, "CANCELLED", "cancelled")
        if self.error is not None:
            raise self.error
        formats = ["wav"] if request.formats and len(request.formats) == 1 else ["mp3", "wav"]
        manifest = {"tracks": list(range(13)), "settings": {"formats": formats}}
        return SimpleNamespace(
            destination=self.destination, package=SimpleNamespace(manifest=manifest)
        )


class Rig:
    def _open(self, path: Path) -> bool:
        self.opened.append(path)
        return True

    def __init__(self, qtbot: QtBot, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.prefs = Preferences.at(tmp_path / "prefs.ini")
        self.pipeline = FakePipeline()
        self.prompts = FakePrompts()
        self.opened: list[Path] = []
        voices = tmp_path / "voices"
        for name in ("alto-voice", "bass-voice"):
            (voices / name).mkdir(parents=True)
            (voices / name / "character.txt").write_text("name=x", encoding="utf-8")
        self.prefs.singers_dir = str(voices)
        self.controller = AppController(
            self.prefs,
            generate_fn=self.pipeline,
            environ={
                "BLT_CONFIG": str(tmp_path / "none.json"),
                "BLT_DATA_DIR": str(tmp_path / "d"),
            },
            config_file=tmp_path / "none.json",
            debounce_ms=1,
        )
        self.window = MainWindow(
            self.prefs,
            controller=self.controller,
            prompts=self.prompts,
            opener=self._open,
        )
        qtbot.addWidget(self.window)
        self.qtbot = qtbot
        self.window.show()
        qtbot.waitUntil(lambda: self.controller.installed is not None, timeout=10000)

    def load(self, **options: Any) -> Path:
        options.setdefault("all_lyrics", True)
        score = write_quartet(self.tmp, **options)
        with self.qtbot.waitSignal(self.controller.score_loaded, timeout=20000):
            self.window.open_score(score)
        return score

    def assign(self) -> None:
        for name, role in ROLE_BY_NAME.items():
            combo = self.window.assignment_section.combo_for(LINES[name])
            assert combo is not None
            combo.setCurrentIndex(combo.findData(role))
        self.qtbot.waitUntil(lambda: not self.controller.validating, timeout=20000)

    def choose_voices(self) -> None:
        for role in ROLE_BY_NAME.values():
            combo = self.window.voices_section.combos[role]
            combo.setCurrentIndex(combo.findData("alto-voice"))
            combo.activated.emit(combo.currentIndex())

    def ready(self) -> None:
        self.load()
        self.assign()
        self.choose_voices()
        self.prompts.answers["Where should the tracks be saved?"] = str(self.tmp / "out")
        self.window.choose_output_folder()


@pytest.fixture
def rig(qtbot: QtBot, tmp_path: Path) -> Rig:
    return Rig(qtbot, tmp_path)


# --- startup and shutdown ---


def test_the_window_starts_empty_and_closes_cleanly(rig: Rig) -> None:
    window = rig.window
    assert window.windowTitle() == "BLT Music Generator"
    assert not window.generate.isEnabled()
    assert "Choose a score first." in window.why.text()
    titles = {box.title() for box in window.findChildren(QGroupBox)}
    for section in (
        "Score",
        "Voice Assignment",
        "Singing Voices",
        "Lyrics and Validation",
        "Output Settings",
        "Generation Progress",
    ):
        assert section in titles
    assert window.close()
    assert not rig.prefs.geometry.isEmpty()


def test_the_window_can_be_resized_and_clips_nothing(rig: Rig) -> None:
    rig.load()
    for width, height in ((780, 540), (1100, 700), (1600, 1000)):
        rig.window.resize(width, height)
        rig.qtbot.wait(20)
        assert rig.window.width() >= 780
    assert rig.window.minimumWidth() <= 800


def test_no_internal_terms_in_the_visible_interface(rig: Rig) -> None:
    rig.ready()
    visible = " ".join(
        label.text()
        for label in rig.window.findChildren(QWidget)
        if hasattr(label, "text") and callable(label.text) and isinstance(label.text(), str)
    ).lower()
    for term in ("ustx", "openutau", "worldline", "renderer"):
        assert term not in visible


# --- loading and drag and drop ---


def test_loading_shows_the_title_file_and_parts(rig: Rig) -> None:
    score = rig.load()
    section = rig.window.score_section
    assert section.headline.text() == "quartet"
    assert section.filename.text() == score.name
    assert "4 parts found" in section.parts.text()
    assert "Tenor (8 notes)" in section.parts.text()
    assert rig.window.windowTitle() == "quartet \u2014 BLT Music Generator"


def test_a_bad_file_shows_a_plain_explanation(rig: Rig) -> None:
    junk = rig.tmp / "junk.musicxml"
    junk.write_text("<oops", encoding="utf-8")
    with rig.qtbot.waitSignal(rig.controller.score_failed, timeout=20000):
        rig.window.open_score(junk)
    assert "could not be read as a score" in rig.window.score_section.problem.text()
    assert rig.window.progress_section.result_box.isVisible()
    assert "MusicXML" in rig.window.progress_section.result_text.text()


def test_dropping_a_score_loads_it(rig: Rig) -> None:
    score = write_quartet(rig.tmp, all_lyrics=True)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(score))])
    event = QDropEvent(
        QPointF(10, 10),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    with rig.qtbot.waitSignal(rig.controller.score_loaded, timeout=20000):
        rig.window.dropEvent(event)
    assert rig.controller.score is not None
    assert rig.controller.score.path == score


def test_dropping_something_else_is_refused_politely(rig: Rig) -> None:
    rig.window.handle_drop([QUrl.fromLocalFile(str(rig.tmp / "notes.txt"))])
    assert any("That is not a score BLT can read." in w for w in rig.prompts.warnings)
    rig.window.handle_drop([QUrl.fromLocalFile(str(rig.tmp / "Hymn.docx"))])
    assert any(
        "Drop a .musicxml, .xml, .mxl, .mscz, .mscx or .pdf file" in w for w in rig.prompts.warnings
    )


def test_a_file_that_cannot_be_converted_is_explained_not_ignored(rig: Rig) -> None:
    rig.window.handle_drop([QUrl.fromLocalFile(str(rig.tmp / "Hymn.mid"))])
    said = rig.prompts.warnings[-1]
    assert "Hymn.mid is a MIDI file" in said
    assert "export MusicXML" in said
    assert "Drop a .musicxml, .xml, .mxl, .mscz, .mscx or .pdf file" in said


def test_any_local_file_may_be_dropped_so_that_it_can_be_explained(rig: Rig) -> None:
    from PySide6.QtCore import QMimeData as Mime

    mime = Mime()
    mime.setUrls([QUrl.fromLocalFile(str(rig.tmp / "Hymn.pdf"))])
    accepted: list[bool] = []
    event: Any = SimpleNamespace(
        mimeData=lambda: mime,
        acceptProposedAction=lambda: accepted.append(True),
        ignore=lambda: accepted.append(False),
    )
    rig.window.dragEnterEvent(event)
    assert accepted == [True]
    assert rig.controller.score is None


def test_the_open_dialog_loads_the_chosen_score(rig: Rig) -> None:
    score = write_quartet(rig.tmp, all_lyrics=True)
    rig.prompts.answers["score"] = str(score)
    with rig.qtbot.waitSignal(rig.controller.score_loaded, timeout=20000):
        rig.window.choose_score()
    assert rig.controller.score is not None


# --- voice assignment ---


def test_every_part_starts_undecided_and_a_complete_mapping_is_accepted(rig: Rig) -> None:
    rig.load()
    section = rig.window.assignment_section
    for name in LINES:
        combo = section.combo_for(LINES[name])
        assert combo is not None
        assert combo.currentData() is None
    assert "Choose a part for" in section.status.text()
    rig.assign()
    assert "Every voice has a part" in section.status.text()


def test_a_voice_already_taken_cannot_be_picked_again(rig: Rig) -> None:
    rig.load()
    section = rig.window.assignment_section
    first = section.combo_for(LINES["tenor"])
    assert first is not None
    first.setCurrentIndex(first.findData(VoiceRole.LEAD))
    second = section.combo_for(LINES["lead"])
    assert second is not None
    index = second.findData(VoiceRole.LEAD)
    item = second.model().index(index, 0)
    assert not (second.model().flags(item) & Qt.ItemFlag.ItemIsEnabled)
    assert rig.controller.assignments is not None
    assert not rig.controller.assignments.can_choose(LINES["lead"], VoiceRole.LEAD)


def test_suggestions_are_labelled_and_must_be_confirmed(rig: Rig) -> None:
    rig.load()
    section = rig.window.assignment_section
    section.suggest.click()
    assert rig.controller.assignments is not None
    assert len(rig.controller.assignments.suggested) == 4
    assert section.confirm.isEnabled()
    assert "confirm" in section.status.text().lower()
    assert not rig.window.generate.isEnabled()
    section.confirm.click()
    assert not rig.controller.assignments.suggested
    assert "Every voice has a part" in section.status.text()


def test_a_part_can_be_ignored_on_purpose(rig: Rig) -> None:
    rig.load()
    rig.assign()
    combo = rig.window.assignment_section.combo_for(LINES["bass"])
    assert combo is not None
    combo.setCurrentIndex(combo.findData(Ignore.IGNORE))
    assert any("Bass" in p for p in rig.controller.assignments.problems())  # type: ignore[union-attr]


# --- singing voices ---


def test_installed_voices_are_listed_and_none_is_preselected(rig: Rig) -> None:
    combo = rig.window.voices_section.combos[VoiceRole.TENOR]
    assert [combo.itemText(i) for i in range(combo.count())] == [
        "\u2014 choose a voice \u2014",
        "alto-voice",
        "bass-voice",
    ]
    assert combo.currentData() == ""
    assert "2 voice(s) installed" in rig.window.voices_section.status.text()


def test_choosing_voices_and_using_the_same_for_all(rig: Rig) -> None:
    section = rig.window.voices_section
    combo = section.combos[VoiceRole.TENOR]
    combo.setCurrentIndex(combo.findData("bass-voice"))
    combo.activated.emit(combo.currentIndex())
    assert rig.controller.singers[VoiceRole.TENOR] == "bass-voice"
    assert section.same.isEnabled()
    section.same.click()
    assert set(rig.controller.singers.values()) == {"bass-voice"}
    assert section.combos[VoiceRole.BASS].currentData() == "bass-voice"


def test_a_voice_that_is_gone_is_flagged_not_silently_replaced(
    qtbot: QtBot, tmp_path: Path
) -> None:
    prefs = Preferences.at(tmp_path / "prefs.ini")
    prefs.set_singer(VoiceRole.LEAD, "vanished")
    voices = tmp_path / "voices"
    (voices / "alto-voice").mkdir(parents=True)
    (voices / "alto-voice" / "oto.ini").write_text("", encoding="utf-8")
    prefs.singers_dir = str(voices)
    controller = AppController(
        prefs, environ={"BLT_CONFIG": str(tmp_path / "n.json")}, config_file=tmp_path / "n.json"
    )
    window = MainWindow(prefs, controller=controller, prompts=FakePrompts())
    qtbot.addWidget(window)
    qtbot.waitUntil(lambda: controller.installed is not None, timeout=10000)
    combo = window.voices_section.combos[VoiceRole.LEAD]
    assert combo.currentText() == "vanished (not installed)"
    assert "not installed" in window.voices_section.status.text()
    assert not window.generate.isEnabled()
    assert window.voices_section.combos[VoiceRole.TENOR].currentData() == ""


def test_the_voices_folder_can_be_changed_and_refreshed(rig: Rig) -> None:
    other = rig.tmp / "more-voices"
    (other / "new-voice").mkdir(parents=True)
    (other / "new-voice" / "character.txt").write_text("name=n", encoding="utf-8")
    rig.prompts.answers["Folder with your singing voices"] = str(other)
    with rig.qtbot.waitSignal(rig.controller.voices_changed, timeout=10000):
        rig.window.choose_voices_folder()
    combo = rig.window.voices_section.combos[VoiceRole.LEAD]
    assert [combo.itemText(i) for i in range(1, combo.count())] == ["new-voice"]
    assert rig.prefs.singers_dir == str(other)


# --- output settings ---


def test_the_exact_output_location_is_shown(rig: Rig) -> None:
    rig.load()
    rig.prompts.answers["Where should the tracks be saved?"] = str(rig.tmp / "out")
    rig.window.choose_output_folder()
    section = rig.window.output_section
    assert section.location.text() == str(rig.tmp / "out" / "quartet_learning_tracks")
    section.name.setText("My Song")
    section.name.textEdited.emit("My Song")
    assert section.location.text() == str(rig.tmp / "out" / "My_Song_learning_tracks")


def test_format_choice_controls_the_mp3_widgets(rig: Rig) -> None:
    section = rig.window.output_section
    assert section.wav.isChecked()
    assert not section.quality.isEnabled()
    section.both.setChecked(True)
    assert rig.controller.options.audio_format == "both"
    assert section.quality.isEnabled()
    assert section.ffmpeg_button.isEnabled()
    section.mp3.setChecked(True)
    assert rig.controller.options.audio_format == "mp3"


def test_custom_gains_appear_only_for_the_custom_preset(rig: Rig) -> None:
    section = rig.window.output_section
    assert section.gain_row.isHidden()
    section.preset.setCurrentIndex(section.preset.findData("custom"))
    section.preset.activated.emit(section.preset.currentIndex())
    assert not section.gain_row.isHidden()
    section.focus.setValue(0.3)
    section.others.setValue(0.4)
    assert "above zero and below" in section.status.text()
    assert not rig.window.generate.isEnabled()


def test_mp3_without_ffmpeg_blocks_and_explains(rig: Rig) -> None:
    rig.load()
    rig.window.output_section.mp3.setChecked(True)
    assert any("FFmpeg" in b for b in rig.controller.blockers())


def test_the_ffmpeg_program_can_be_chosen(rig: Rig) -> None:
    program = rig.tmp / "ffmpeg.exe"
    program.write_bytes(b"x")
    rig.prompts.answers["file"] = str(program)
    rig.window.output_section.mp3.setChecked(True)
    rig.window.choose_ffmpeg()
    assert rig.window.output_section.ffmpeg.text() == str(program)


def test_advanced_settings_are_saved(rig: Rig) -> None:
    def accept_with_values(dialog: QDialog) -> bool:
        assert isinstance(dialog, AdvancedDialog)
        dialog.pronunciation.setText("Some.Engine.Phonemizer")
        dialog.timeout.setValue(30)
        dialog.accept()
        return True

    rig.window.run_dialog = accept_with_values
    rig.window.open_advanced()
    assert rig.prefs.phonemizer == "Some.Engine.Phonemizer"
    assert rig.prefs.timeout_minutes == 30


def test_advanced_settings_refuse_a_pronunciation_engine_this_version_lacks(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtWidgets import QMessageBox

    shown: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: shown.append(str(args[2])))
    rig.prefs.phonemizer = ""

    def try_removed(dialog: QDialog) -> bool:
        assert isinstance(dialog, AdvancedDialog)
        dialog.pronunciation.setText("OpenUtau.Plugin.Builtin.EnglishCpVPhonemizer")
        dialog.accept()
        assert dialog.result() != QDialog.DialogCode.Accepted  # the dialog stays open
        return False

    rig.window.run_dialog = try_removed
    rig.window.open_advanced()
    assert rig.prefs.phonemizer == ""
    assert shown
    assert "English C+V" in shown[0]
    assert "ArpasingPhonemizer" in shown[0]


def test_advanced_settings_offer_only_the_renderers_the_shipped_host_can_run(rig: Rig) -> None:
    offered: list[str] = []

    def look(dialog: QDialog) -> bool:
        assert isinstance(dialog, AdvancedDialog)
        offered.extend(dialog.engine.itemText(i) for i in range(dialog.engine.count()))
        return False

    rig.window.run_dialog = look
    rig.window.open_advanced()
    assert offered == ["", "WORLDLINE-R"]


# --- generating ---


def test_generate_stays_disabled_until_everything_is_decided(rig: Rig) -> None:
    rig.load()
    assert not rig.window.generate.isEnabled()
    rig.assign()
    assert not rig.window.generate.isEnabled()
    rig.choose_voices()
    assert not rig.window.generate.isEnabled()  # no output folder yet
    assert (
        "Choose an output folder." in rig.window.why.text()
        or "output" in rig.window.generate.toolTip()
    )
    rig.prompts.answers["Where should the tracks be saved?"] = str(rig.tmp / "out")
    rig.window.choose_output_folder()
    assert rig.window.generate.isEnabled()
    assert rig.window.why.text() == "Everything is ready."


def test_a_successful_generation_shows_progress_then_the_result(rig: Rig) -> None:
    rig.ready()
    rig.pipeline.gate.clear()
    rig.window.generate.click()
    assert rig.pipeline.began.wait(10)
    rig.qtbot.waitUntil(lambda: rig.window.progress_section.bar.value() == 3, timeout=10000)
    progress = rig.window.progress_section
    assert progress.cancel.isEnabled()
    assert progress.bar.maximum() == 13  # real progress: 3 of 13 mixes
    assert "3 of 13" in progress.detail.text()
    assert not rig.window.generate.isEnabled()
    assert "Mixing the 13 tracks" in progress.stage.text()
    assert progress.steps.count() == 9  # no MP3 step for WAV only
    rig.qtbot.waitUntil(lambda: bool(progress.elapsed.text()), timeout=5000)
    assert not progress.result_box.isVisible()  # no success message before the end
    with rig.qtbot.waitSignal(rig.controller.generation_finished, timeout=10000):
        rig.pipeline.gate.set()
    assert progress.result_box.isVisible()
    assert "ready" in progress.result_title.text()
    assert "13 tracks (WAV)" in progress.result_text.text()
    assert str(rig.pipeline.destination) in progress.result_text.text()
    assert not progress.cancel.isEnabled()
    progress.open_folder.click()
    assert rig.opened == [rig.pipeline.destination]


def test_synthesis_stages_show_no_invented_percentage(rig: Rig) -> None:
    rig.ready()
    rig.pipeline.gate.clear()
    rig.window.generate.click()
    assert rig.pipeline.began.wait(10)
    progress = rig.window.progress_section
    rig.window._generation_event({"event": "stage", "stage": "stem_rendering", "status": "started"})
    assert progress.bar.minimum() == 0
    assert progress.bar.maximum() == 0  # a busy indicator, not a percentage
    rig.pipeline.gate.set()
    rig.qtbot.waitUntil(lambda: not rig.controller.running, timeout=10000)


def test_a_second_click_cannot_start_a_second_generation(rig: Rig) -> None:
    rig.ready()
    rig.pipeline.gate.clear()
    rig.window.generate.click()
    assert rig.pipeline.began.wait(10)
    assert not rig.window.generate.isEnabled()
    rig.window.on_generate_clicked()  # as if the button were somehow triggered again
    assert len(rig.pipeline.requests) == 1
    rig.pipeline.gate.set()
    rig.qtbot.waitUntil(lambda: not rig.controller.running, timeout=10000)


def test_cancelling_stops_the_work_and_says_so(rig: Rig) -> None:
    rig.ready()
    rig.pipeline.gate.clear()
    rig.window.generate.click()
    assert rig.pipeline.began.wait(10)
    with rig.qtbot.waitSignal(rig.controller.generation_failed, timeout=10000):
        rig.window.progress_section.cancel.click()
    progress = rig.window.progress_section
    assert "cancelled" in progress.result_title.text().lower()
    assert "Nothing was saved" in progress.result_text.text()
    assert not progress.open_folder.isVisible()
    assert rig.window.generate.isEnabled()


FAILURES = [
    (
        PipelineError(
            ErrorCategory.SOURCE,
            "SOURCE_NOT_READY",
            "x",
            {"findings": [{"code": "TEMPO_MISSING", "message": "no tempo"}]},
        ),
        "no tempo",
    ),
    (
        PipelineError(
            ErrorCategory.SOURCE,
            "SOURCE_NOT_READY",
            "x",
            {"findings": [{"code": "TIME_SIGNATURE_MISSING", "message": "m"}]},
        ),
        "no time signature",
    ),
    (PipelineError(ErrorCategory.REVIEW, "LYRICS_NEED_REVIEW", "x", {}), "need lyrics"),
    (PipelineError(ErrorCategory.CONFIGURATION, "SINGER_NOT_FOUND", "x"), "voice was not found"),
    (PipelineError(ErrorCategory.SYNTHESIS, "HOST_FAILED", "x"), "could not be sung"),
    (PipelineError(ErrorCategory.AUDIO, "STEM_SILENT", "x"), "silent or wrong"),
    (PipelineError(ErrorCategory.AUDIO, "MIX_MP3_FAILED", "x"), "mp3 files could not be made"),
    (PipelineError(ErrorCategory.CONFIGURATION, "FFMPEG_NOT_CONFIGURED", "x"), "needs ffmpeg"),
    (PipelineError(ErrorCategory.TIMEOUT, "RENDER_TIMEOUT", "x"), "took too long"),
]


@pytest.mark.parametrize(("failure", "words"), FAILURES, ids=[f[0].code for f in FAILURES])
def test_each_kind_of_failure_is_explained_with_next_steps(
    rig: Rig, failure: PipelineError, words: str
) -> None:
    rig.ready()
    rig.pipeline.error = failure
    with rig.qtbot.waitSignal(rig.controller.generation_failed, timeout=10000):
        rig.window.generate.click()
    progress = rig.window.progress_section
    assert words in progress.result_title.text().lower()
    assert progress.result_box.isVisible()
    assert "\u2022" in progress.result_text.text() or failure.category is ErrorCategory.SYNTHESIS
    assert failure.code in progress.technical.toPlainText()
    assert not progress.technical.isVisible()  # technical details are one click away
    progress.technical_button.click()
    assert progress.technical.isVisible()
    assert progress.result_title.text() != ""
    assert "published" not in progress.result_title.text().lower()


def test_events_reach_widgets_only_on_the_gui_thread(rig: Rig) -> None:
    rig.ready()
    threads: set[int] = set()
    original = rig.window._generation_event

    def spy(event: dict[str, Any]) -> None:
        threads.add(threading.get_ident())
        original(event)

    rig.controller.generation_event.disconnect(rig.window._generation_event)
    rig.controller.generation_event.connect(spy)
    with rig.qtbot.waitSignal(rig.controller.generation_finished, timeout=10000):
        rig.window.generate.click()
    assert threads == {threading.get_ident()}


def test_the_technical_log_records_events(rig: Rig) -> None:
    rig.ready()
    with rig.qtbot.waitSignal(rig.controller.generation_finished, timeout=10000):
        rig.window.generate.click()
    log = rig.window.progress_section.log
    assert not log.isVisible()
    rig.window.progress_section.log_button.click()
    assert log.isVisible()
    assert '"stage": "source_loading"' in log.toPlainText()


def test_replacing_an_existing_package_asks_first(rig: Rig) -> None:
    rig.ready()
    package = rig.tmp / "out" / "quartet_learning_tracks"
    package.mkdir(parents=True)
    rig.controller.state_changed.emit()
    assert not rig.window.generate.isEnabled()  # exists, and replace is not ticked
    assert "already exists" in rig.window.output_section.status.text()
    rig.window.output_section.replace.setChecked(True)
    assert rig.window.generate.isEnabled()
    rig.prompts.confirm_answer = False
    rig.window.generate.click()
    assert rig.prompts.confirmations == ["Replace the existing tracks?"]
    assert rig.pipeline.requests == []
    rig.prompts.confirm_answer = True
    with rig.qtbot.waitSignal(rig.controller.generation_finished, timeout=10000):
        rig.window.generate.click()
    assert rig.pipeline.requests[0].replace is True


def test_closing_while_generating_asks_and_can_be_declined(rig: Rig) -> None:
    rig.ready()
    rig.pipeline.gate.clear()
    rig.window.generate.click()
    assert rig.pipeline.began.wait(10)
    rig.prompts.confirm_answer = False
    assert not rig.window.close()
    assert rig.controller.running
    rig.prompts.confirm_answer = True
    assert rig.window.close()
    rig.qtbot.waitUntil(lambda: not rig.controller.running, timeout=10000)


# --- persistence ---


def test_ordinary_choices_come_back_on_the_next_launch(qtbot: QtBot, tmp_path: Path) -> None:
    first = Rig(qtbot, tmp_path)
    first.ready()
    first.window.output_section.both.setChecked(True)
    first.window.output_section.keep_stems.setChecked(True)
    first.window.output_section.quality.setValue(5)
    first.window.close()
    first.prefs.sync()

    prefs = Preferences.at(tmp_path / "prefs.ini")
    controller = AppController(
        prefs, environ={"BLT_CONFIG": str(tmp_path / "n.json")}, config_file=tmp_path / "n.json"
    )
    window = MainWindow(prefs, controller=controller, prompts=FakePrompts())
    qtbot.addWidget(window)
    qtbot.waitUntil(lambda: controller.installed is not None, timeout=10000)
    assert window.output_section.both.isChecked()
    assert window.output_section.keep_stems.isChecked()
    assert window.output_section.quality.value() == 5
    assert window.output_section.folder.text() == str(tmp_path / "out")
    assert window.voices_section.combos[VoiceRole.LEAD].currentData() == "alto-voice"
    assert prefs.last_score_dir == str(tmp_path)
    assert controller.score is None  # no score, assignments or approvals are carried over
    assert controller.approvals == ()


def test_window_sizes_fit_a_scaled_screen() -> None:
    from PySide6.QtCore import QSize

    from barbershop_tracks.ui.main_window import fitted_sizes

    assert fitted_sizes(None) == (QSize(780, 540), QSize(1200, 780))
    assert fitted_sizes(QSize(1920, 1040)) == (QSize(780, 540), QSize(1200, 780))
    smallest, first = fitted_sizes(QSize(1280, 680))  # 1080p at 150 % display scaling
    assert first.height() <= 680
    assert first.width() <= 1280
    assert smallest.height() <= 680
    smallest, first = fitted_sizes(QSize(640, 340))  # 1080p at 300 %
    assert smallest == first == QSize(608, 323)


def test_the_step_where_it_stopped_is_marked(rig: Rig) -> None:
    from barbershop_tracks.ui.explain import Explanation

    progress = rig.window.progress_section
    progress.start(["reading", "rendering", "mixing"])
    progress.stage_started("reading")
    progress.stage_finished("reading")
    progress.stage_started("rendering")
    progress.show_failure(Explanation("audio_failed", "Stopped", "A voice came out wrong."))
    marks = [progress.steps.item(i).text()[0] for i in range(progress.steps.count())]
    assert marks == ["✔", "✖", "○"]
    progress.start(["reading", "rendering"])
    progress.stage_started("rendering")
    progress.show_failure(Explanation("cancelled", "Cancelled", "", cancelled=True))
    assert [progress.steps.item(i).text()[0] for i in range(2)] == ["○", "■"]
