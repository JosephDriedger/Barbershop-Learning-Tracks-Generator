"""The main window: six sections, one Generate button, nothing musical decided for the user.

The window only displays what :class:`AppController` reports and forwards the user's actions to
it. Slow work runs in the controller's background threads and arrives here through signals, so the
window stays responsive and widgets are only ever touched from the GUI thread.
"""

import json
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QMimeData, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QGuiApplication,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from barbershop_tracks import __version__
from barbershop_tracks.core.musicxml.convert import CONVERTED_SUFFIXES, needs_recognition
from barbershop_tracks.core.musicxml.source import wrong_file_advice
from barbershop_tracks.core.pipeline import (
    STAGES,
    GenerateResult,
    PipelineError,
    ensure_default_voices_dir,
)
from barbershop_tracks.diagnostics import collect
from barbershop_tracks.ui.controller import AppController, LoadedScore, ValidationView
from barbershop_tracks.ui.dialogs import AdvancedDialog, LyricReviewDialog
from barbershop_tracks.ui.explain import explain
from barbershop_tracks.ui.formatting import clock
from barbershop_tracks.ui.lyric_review import LyricReviewState
from barbershop_tracks.ui.preferences import Preferences
from barbershop_tracks.ui.prompts import Opener, Prompts, open_in_explorer
from barbershop_tracks.ui.pronunciation_dialog import PronunciationDialog
from barbershop_tracks.ui.sections import (
    AssignmentSection,
    OutputSection,
    ProgressSection,
    ScoreSection,
    ValidationSection,
    VoicesSection,
)

SCORE_SUFFIXES = (".musicxml", ".xml", ".mxl", *CONVERTED_SUFFIXES)
TITLE = "BLT Music Generator"


def _scrolling(widget: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    area.setWidget(widget)
    return area


PREFERRED_SIZE = QSize(1200, 780)
SMALLEST_SIZE = QSize(780, 540)


def fitted_sizes(available: QSize | None) -> tuple[QSize, QSize]:
    """(smallest, first-run) window sizes that fit the usable screen area.

    With Windows display scaling at 150 % or more a 1080p screen has fewer than 780 usable logical
    pixels of height, so a fixed 1200x780 window would have its bottom (the Generate button)
    off screen.
    """
    if available is None:
        return SMALLEST_SIZE, PREFERRED_SIZE
    room = QSize(int(available.width() * 0.95), int(available.height() * 0.95))
    smallest = SMALLEST_SIZE.boundedTo(room)
    return smallest, PREFERRED_SIZE.boundedTo(room)


class MainWindow(QMainWindow):
    def __init__(
        self,
        prefs: Preferences | None = None,
        *,
        controller: AppController | None = None,
        prompts: Prompts | None = None,
        opener: Opener = open_in_explorer,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.prefs = prefs or (controller.prefs if controller else Preferences.native())
        self.controller = controller or AppController(self.prefs)
        self.prompts = prompts or Prompts()
        self.opener = opener
        self.setWindowTitle(TITLE)
        self.setAcceptDrops(True)
        minimum, self._first_size = fitted_sizes(self._available_size())
        self.setMinimumSize(minimum)
        self._review_state: LyricReviewState | None = None
        self._last_location: Path | None = None
        self._last_error: PipelineError | None = None
        self._pending_review = False
        self.run_dialog: Callable[[QDialog], bool] = lambda dialog: bool(dialog.exec())

        c = self.controller
        self.score_section = ScoreSection()
        self.assignment_section = AssignmentSection(c)
        self.voices_section = VoicesSection(c)
        self.validation_section = ValidationSection()
        self.output_section = OutputSection(c)
        self.progress_section = ProgressSection()

        left = QWidget()
        left_layout = QVBoxLayout(left)
        for section in (
            self.score_section,
            self.assignment_section,
            self.voices_section,
            self.output_section,
        ):
            left_layout.addWidget(section)
        left_layout.addStretch(1)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.validation_section, 2)
        right_layout.addWidget(self.progress_section, 3)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(_scrolling(left))
        self.splitter.addWidget(_scrolling(right))
        self.splitter.setStretchFactor(0, 5)
        self.splitter.setStretchFactor(1, 4)
        self.splitter.setChildrenCollapsible(False)

        self.why = QLabel("")
        self.why.setWordWrap(True)
        self.why.setObjectName("hint")
        self.why.setAccessibleName("Why generating is not possible yet")
        self.generate = QPushButton("&Generate learning tracks")
        self.generate.setObjectName("primary")
        self.generate.setDefault(True)
        self.generate.setAccessibleName("Generate learning tracks")
        self.generate.clicked.connect(self.on_generate_clicked)
        bottom = QHBoxLayout()
        bottom.addWidget(self.why, 1)
        bottom.addWidget(self.generate)

        central = QWidget()
        outer = QVBoxLayout(central)
        outer.addWidget(self.splitter, 1)
        outer.addLayout(bottom)
        self.setCentralWidget(central)
        self._build_menu()

        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.setInterval(1000)
        self.elapsed_timer.timeout.connect(self._tick)

        # wiring
        self.score_section.browse_requested.connect(self.choose_score)
        self.voices_section.folder_requested.connect(self.choose_voices_folder)
        self.voices_section.open_folder_requested.connect(self.open_voices_folder)
        self.voices_section.add_zip_requested.connect(self.add_voice_from_zip)
        self.voices_section.add_folder_requested.connect(self.add_voice_from_folder)
        self.controller.voice_added.connect(self._voice_added)
        self.controller.voice_add_failed.connect(self._voice_add_failed)
        self.voices_section.advanced_requested.connect(self.open_advanced)
        self.output_section.browse_requested.connect(self.choose_output_folder)
        self.output_section.ffmpeg_requested.connect(self.choose_ffmpeg)
        self.validation_section.review_requested.connect(self.open_review)
        self.progress_section.review_requested.connect(self.open_review)
        self.progress_section.pronunciation_requested.connect(self.open_pronunciations)
        self.progress_section.cancel_requested.connect(self.controller.cancel_generation)
        self.progress_section.open_folder_requested.connect(self.open_output_folder)
        c.state_changed.connect(self.refresh)
        c.score_loaded.connect(self._score_loaded)
        c.score_failed.connect(self._score_failed)
        c.validation_changed.connect(self._validation_changed)
        c.generation_started.connect(self._generation_started)
        c.generation_event.connect(self._generation_event)
        c.generation_finished.connect(self._generation_finished)
        c.generation_failed.connect(self._generation_failed)

        self._restore_geometry()
        self.refresh()
        self.controller.refresh_voices()

    # --- menu and file choosing ------------------------------------------------------------

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        open_action = QAction("&Open score…", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.choose_score)
        self.pronunciation_action = QAction("&Pronunciations…", self)
        self.pronunciation_action.setToolTip(
            "Say how words the pronunciation dictionary lacks are sung (the score is not changed)"
        )
        self.pronunciation_action.triggered.connect(self.open_pronunciations)
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(open_action)
        file_menu.addAction(self.pronunciation_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)
        help_menu = self.menuBar().addMenu("&Help")
        about = QAction("&About", self)
        about.triggered.connect(self._about)
        copy_diagnostics = QAction("&Copy diagnostics", self)
        copy_diagnostics.triggered.connect(self._copy_diagnostics)
        notices = QAction("&Third-party notices", self)
        notices.triggered.connect(self._open_notices)
        help_menu.addAction(copy_diagnostics)
        help_menu.addAction(notices)
        help_menu.addSeparator()
        help_menu.addAction(about)

    def _copy_diagnostics(self) -> None:
        text = chr(10).join(collect(self.controller.config()))
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
        self.prompts.inform(self, TITLE, "Copied: paste it into a message to support.")

    def _open_notices(self) -> None:
        program = Path(sys.executable).resolve().parent
        # inside BLT Music Generator.app the notices are in Contents/Resources
        notices = next(
            (
                p
                for p in (program / "NOTICES.txt", program.parent / "Resources" / "NOTICES.txt")
                if p.is_file()
            ),
            program / "NOTICES.txt",
        )
        if not notices.is_file():
            self.prompts.inform(
                self, TITLE, "The third-party notices are installed with BLT (NOTICES.txt)."
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(notices)))

    def _about(self) -> None:
        QMessageBox.about(
            self,
            f"About {TITLE}",
            f"<b>{TITLE}</b> {__version__}<br>Four-part barbershop learning tracks from a score."
            "<br><br>Copyright 2026 Joseph Driedger. Apache License 2.0."
            "<br>This program uses Qt and PySide6 under the GNU LGPL version 3, and other "
            "third-party software; see Help, Third-party notices.",
        )

    def choose_score(self) -> None:
        start = self.prefs.last_score_dir or str(Path.home())
        path = self.prompts.open_score(self, start)
        if path:
            self.open_score(Path(path))

    def open_score(self, path: Path) -> None:
        if self.controller.running:
            self.prompts.inform(self, TITLE, "Wait for the current generation to finish first.")
            return
        accept = False
        if needs_recognition(path):
            # a picture of music has no notes in it: a program would recognise them, and recognition
            # makes mistakes. Never silently: the person says so first (and then checks the result).
            if not self.prompts.confirm(
                self,
                "Recognise the music in this file?",
                f"{path.name} is a picture of music, not a score. BLT can read it only by having "
                "a program recognise the notes, rhythms and words (it uses Audiveris, which must "
                "be installed). Recognition makes mistakes: a wrong note, a missed tie, a word "
                "under the wrong note. It can take several minutes.\n\nIf you go on, check every "
                "part against the original before you generate: BLT does not check the "
                "recognised music for you.",
                "Recognise it",
            ):
                return
            accept = True
        self.score_section.show_loading(path.name)
        self.controller.load_score(path, accept_recognition=accept)

    def choose_voices_folder(self) -> None:
        current = self.controller.singers_folder()
        folder = self.prompts.choose_folder(
            self, "Folder with your singing voices", str(current or "")
        )
        if folder:
            self.prefs.singers_dir = folder
            self.controller.refresh_voices()

    def add_voice_from_zip(self) -> None:
        path = self.prompts.choose_file(
            self, "Add a voice from a zip", "", "Voicebank zip (*.zip);;All files (*)"
        )
        if path:
            self.controller.add_voice(Path(path))

    def add_voice_from_folder(self) -> None:
        folder = self.prompts.choose_folder(self, "The folder of the voicebank to add", "")
        if folder:
            self.controller.add_voice(Path(folder))

    def _voice_added(self, added: list[Any]) -> None:
        notes = [f"{one.name}: {note}" for one in added for note in one.notes]
        text = "Added: " + ", ".join(one.name for one in added) + "."
        if notes:
            text += "\n\n" + "\n".join(notes)
        self.prompts.inform(self, TITLE, text)

    def _voice_add_failed(self, message: str) -> None:
        self.prompts.warn(self, TITLE, message)

    def open_voices_folder(self) -> None:
        folder = self.controller.singers_folder()
        if folder is None:
            return
        ensure_default_voices_dir(folder)
        if not self.opener(folder):
            self.prompts.warn(self, TITLE, f"Could not open {folder}.")

    def choose_output_folder(self) -> None:
        folder = self.prompts.choose_folder(
            self,
            "Where should the tracks be saved?",
            self.controller.output_dir or str(Path.home()),
        )
        if folder:
            self.controller.set_output_dir(folder)

    def choose_ffmpeg(self) -> None:
        windows = sys.platform == "win32"
        path = self.prompts.choose_file(
            self,
            "Find ffmpeg.exe" if windows else "Find ffmpeg",
            self.prefs.ffmpeg_path,
            "Programs (*.exe);;All files (*)" if windows else "All files (*)",
        )
        if path:
            self.prefs.ffmpeg_path = path
            self.controller.state_changed.emit()

    def open_advanced(self) -> None:
        dialog = AdvancedDialog(self.prefs, self)
        if self.run_dialog(dialog):
            self.controller.refresh_voices()
            self.controller.schedule_validation()
            self.controller.state_changed.emit()

    # --- drag and drop ---------------------------------------------------------------------

    @staticmethod
    def _score_from(mime: QMimeData) -> Path | None:
        for url in mime.urls():
            if url.isLocalFile() and url.toLocalFile().lower().endswith(SCORE_SUFFIXES):
                return Path(url.toLocalFile())
        return None

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        # any local file is accepted, so that a MuseScore project or a PDF dropped here is
        # explained (on drop) instead of meeting a silent "no drop" cursor
        if any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        self.handle_drop(event.mimeData().urls())
        event.acceptProposedAction()

    def handle_drop(self, urls: list[QUrl]) -> None:
        mime = QMimeData()
        mime.setUrls(urls)
        path = self._score_from(mime)
        if path is None:
            local = next((u.toLocalFile() for u in urls if u.isLocalFile()), "")
            advice = wrong_file_advice(Path(local).name) if local else None
            self.prompts.warn(
                self,
                TITLE,
                (advice + "." if advice else "That is not a score BLT can read.")
                + " Drop a .musicxml, .xml, .mxl, .mscz, .mscx or .pdf file.",
            )
            return
        self.open_score(path)

    # --- display ---------------------------------------------------------------------------

    def refresh(self) -> None:
        c = self.controller
        self.assignment_section.refresh()
        self.voices_section.refresh()
        self.output_section.refresh()
        self._refresh_validation()
        blockers = c.blockers()
        self.generate.setEnabled(not blockers)
        if c.running:
            self.why.setText("Generating…")
        elif blockers:
            shown = "\n".join(f"• {b}" for b in blockers[:3])
            more = f"\n…and {len(blockers) - 3} more" if len(blockers) > 3 else ""
            self.why.setText("To generate:\n" + shown + more)
        else:
            self.why.setText("Everything is ready.")
        self.generate.setToolTip("\n".join(blockers))
        state = c.pronunciation_state()
        self.pronunciation_action.setEnabled(state is not None and bool(state.rows))

    def _refresh_validation(self) -> None:
        c = self.controller
        items: list[tuple[str, str]] = []
        review_count = 0
        technical = ""
        if c.score is None:
            self.validation_section.show_items([], "Choose a score to check it.", 0, "")
            return
        summary = "Needs attention"
        conversion = c.score.conversion
        if conversion is not None and conversion.get("recognised"):
            items.append(
                (
                    "warning",
                    "This score was recognised from a picture by "
                    f"{conversion.get('tool')}. Recognition makes mistakes: check the notes, "
                    "rhythms and words of every part against the original before generating.",
                )
            )
        elif conversion is not None:
            items.append(
                ("info", f"Read from a {c.score.path.suffix} file by {conversion.get('tool')}.")
            )
        if c.assignments is not None:
            items.extend(("info", p) for p in c.assignments.problems())
        view = c.validation
        if c.validating:
            summary = "Checking the score…"
        elif view is not None:
            technical = view.technical
            items.extend((m.severity, m.text) for m in view.messages)
            review_count = (view.unresolved + view.following) if c.review is not None else 0
            if view.source_ready and view.unresolved:
                n = view.unresolved
                items.append(
                    (
                        "warning",
                        f"{n} note{'s have' if n != 1 else ' has'} no lyric yet. "
                        "Open the lyric review and decide what they are sung to.",
                    )
                )
            if view.source_ready and view.following:
                n = view.following
                items.append(
                    (
                        "info",
                        f"{n} note{'s' if n != 1 else ''} sing words written for another part, "
                        "usually the Lead's (the usual barbershop convention). Open the lyric "
                        "review to change any.",
                    )
                )
            if view.generatable:
                summary = "The score is ready"
                items.append(("ok", "The score and lyrics are complete."))
        elif c.assignments is not None and not c.assignments.complete:
            summary = "Assign the voices first"
        self.validation_section.show_items(items, summary, review_count, technical)

    # --- score events ----------------------------------------------------------------------

    def _score_loaded(self, score: LoadedScore) -> None:
        parts = [f"{info.part_name} ({info.sounding_attacks} notes)" for info in score.lines]
        self.score_section.show_score(score.title, score.path, parts)
        self.setWindowTitle(f"{score.title} — {TITLE}")
        self.progress_section.reset()
        self._last_error = None

    def _score_failed(self, error: PipelineError) -> None:
        explanation = explain(error)
        self.score_section.show_failure(f"{explanation.title}. {explanation.summary}")
        self.progress_section.show_failure(explanation)
        self._last_error = error

    def _validation_changed(self, view: ValidationView | None) -> None:
        self._review_state = self.controller.review

    # --- lyric review ----------------------------------------------------------------------

    def create_review_dialog(self) -> LyricReviewDialog | None:
        c = self.controller
        if c.review is None or c.validation is None or c.validation.baseline is None:
            return None
        return LyricReviewDialog(c.review, c.validation.baseline, self.prompts, self)

    def open_review(self) -> None:
        dialog = self.create_review_dialog()
        if dialog is None:
            return
        if self.run_dialog(dialog) and self.controller.review is not None:
            self.controller.set_approvals(self.controller.review.approvals())

    # --- pronunciations --------------------------------------------------------------------

    def create_pronunciation_dialog(self) -> PronunciationDialog | None:
        c = self.controller
        state = c.pronunciation_state()
        if state is None or not state.rows:
            return None
        return PronunciationDialog(state, c, self.prompts, self)

    def open_pronunciations(self) -> None:
        dialog = self.create_pronunciation_dialog()
        if dialog is None:
            self.prompts.inform(
                self,
                TITLE,
                "No word needs a pronunciation yet. If the pronunciation dictionary lacks a word "
                "of your score, generating stops and names it; then it is listed here.",
            )
            return
        self.run_dialog(dialog)
        self.controller.state_changed.emit()

    # --- generation ------------------------------------------------------------------------

    def on_generate_clicked(self) -> None:
        c = self.controller
        if c.running or c.blockers():
            return
        location = c.expected_location()
        if c.existing_package():
            if not c.options.replace:
                return
            if not self.prompts.confirm(
                self,
                "Replace the existing tracks?",
                f"The folder\n{location}\nalready holds learning tracks made by BLT. They will be "
                "replaced only if the new ones are completed successfully.",
                "Replace",
            ):
                return
        self._last_location = location
        c.start_generation()

    def _generation_started(self) -> None:
        stages = [s.value for s in STAGES]
        if self.controller.options.audio_format == "wav":
            stages.remove("mp3_encoding")
        self.progress_section.start(stages)
        self.generate.setEnabled(False)
        self._tick()
        self.elapsed_timer.start()

    def _tick(self) -> None:
        if self.controller.running:
            self.progress_section.set_elapsed(time.monotonic() - self.controller.started_at)

    def _generation_event(self, event: dict[str, Any]) -> None:
        elapsed = time.monotonic() - self.controller.started_at
        kind = event.get("event")
        section = self.progress_section
        if kind == "stage":
            if event["status"] == "started":
                section.stage_started(str(event["stage"]))
            else:
                section.stage_finished(str(event["stage"]))
        elif kind == "progress":
            section.counted(str(event["stage"]), int(event["completed"]), int(event["total"]))
        elif kind == "host":
            if event.get("kind") == "blt_wait":
                section.note("Waiting for another generation to finish…")
        elif kind == "warning":
            section.note(str(event.get("message", "")))
        if kind != "progress":
            section.append_log(f"[{clock(elapsed)}] {json.dumps(event, sort_keys=True)}")

    def _generation_finished(self, result: GenerateResult) -> None:
        self.elapsed_timer.stop()
        self._tick_final()
        manifest = result.package.manifest
        self.progress_section.show_success(
            result.destination,
            len(manifest["tracks"]),
            list(manifest["settings"]["formats"]),
            [warning.split(": ", 1)[-1] for warning in result.warnings],
        )
        self._last_location = result.destination
        self._last_error = None

    def _tick_final(self) -> None:
        self.progress_section.set_elapsed(time.monotonic() - self.controller.started_at)

    def _generation_failed(self, error: PipelineError) -> None:
        self.elapsed_timer.stop()
        self._tick_final()
        self._last_error = error
        explanation = explain(error)
        self.progress_section.show_failure(explanation)

    def open_output_folder(self) -> None:
        if self._last_location is not None and not self.opener(self._last_location):
            self.prompts.warn(self, TITLE, f"Could not open {self._last_location}.")

    def changeEvent(self, event: QEvent) -> None:
        """Coming back to the window re-checks the world (a folder may have appeared meanwhile)."""
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            self.refresh()
        super().changeEvent(event)

    # --- closing and geometry --------------------------------------------------------------

    @staticmethod
    def _available_size() -> QSize | None:
        screen = QGuiApplication.primaryScreen()
        return screen.availableGeometry().size() if screen is not None else None

    def _restore_geometry(self) -> None:
        if not self.prefs.geometry.isEmpty():
            self.restoreGeometry(self.prefs.geometry)
        else:
            self.resize(self._first_size)
        if not self.prefs.splitter.isEmpty():
            self.splitter.restoreState(self.prefs.splitter)

    def closeEvent(self, event: QCloseEvent) -> None:
        stop_anyway = self.controller.running and self.prompts.confirm(
            self,
            "Stop generating?",
            "Tracks are still being made. Closing now cancels the work; nothing is saved.",
            "Cancel generation and close",
        )
        if self.controller.running and not stop_anyway:
            event.ignore()
            return
        self.prefs.geometry = self.saveGeometry()
        self.prefs.splitter = self.splitter.saveState()
        self.elapsed_timer.stop()
        self.controller.shutdown()
        event.accept()
