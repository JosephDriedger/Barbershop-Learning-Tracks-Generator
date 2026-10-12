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
from barbershop_tracks.core.pipeline import STAGES, GenerateResult, PipelineError
from barbershop_tracks.diagnostics import collect
from barbershop_tracks.ui.controller import AppController, LoadedScore, ValidationView
from barbershop_tracks.ui.dialogs import AdvancedDialog, LyricReviewDialog
from barbershop_tracks.ui.explain import explain
from barbershop_tracks.ui.formatting import clock
from barbershop_tracks.ui.lyric_review import LyricReviewState
from barbershop_tracks.ui.preferences import Preferences
from barbershop_tracks.ui.prompts import Opener, Prompts, open_in_explorer
from barbershop_tracks.ui.sections import (
    AssignmentSection,
    OutputSection,
    ProgressSection,
    ScoreSection,
    ValidationSection,
    VoicesSection,
)

SCORE_SUFFIXES = (".musicxml", ".xml", ".mxl")
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
        self.voices_section.advanced_requested.connect(self.open_advanced)
        self.output_section.browse_requested.connect(self.choose_output_folder)
        self.output_section.ffmpeg_requested.connect(self.choose_ffmpeg)
        self.validation_section.review_requested.connect(self.open_review)
        self.progress_section.review_requested.connect(self.open_review)
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
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(open_action)
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
        notices = Path(sys.executable).resolve().parent / "NOTICES.txt"
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
            f"<b>{TITLE}</b> {__version__}<br>Four-part barbershop learning tracks from a score.",
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
        self.score_section.show_loading(path.name)
        self.controller.load_score(path)

    def choose_voices_folder(self) -> None:
        current = self.controller.singers_folder()
        folder = self.prompts.choose_folder(
            self, "Folder with your singing voices", str(current or "")
        )
        if folder:
            self.prefs.singers_dir = folder
            self.controller.refresh_voices()

    def choose_output_folder(self) -> None:
        folder = self.prompts.choose_folder(
            self,
            "Where should the tracks be saved?",
            self.controller.output_dir or str(Path.home()),
        )
        if folder:
            self.controller.set_output_dir(folder)

    def choose_ffmpeg(self) -> None:
        path = self.prompts.choose_file(
            self, "Find ffmpeg.exe", self.prefs.ffmpeg_path, "Programs (*.exe);;All files (*)"
        )
        if path:
            self.prefs.ffmpeg_path = path
            self.controller.state_changed.emit()

    def open_advanced(self) -> None:
        dialog = AdvancedDialog(self.prefs, self)
        if self.run_dialog(dialog):
            self.controller.refresh_voices()
            self.controller.state_changed.emit()

    # --- drag and drop ---------------------------------------------------------------------

    @staticmethod
    def _score_from(mime: QMimeData) -> Path | None:
        for url in mime.urls():
            if url.isLocalFile() and url.toLocalFile().lower().endswith(SCORE_SUFFIXES):
                return Path(url.toLocalFile())
        return None

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._score_from(event.mimeData()) is not None:
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
            self.prompts.warn(
                self, TITLE, "That is not a MusicXML score. Drop a .musicxml, .xml or .mxl file."
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

    def _refresh_validation(self) -> None:
        c = self.controller
        items: list[tuple[str, str]] = []
        review_count = 0
        technical = ""
        if c.score is None:
            self.validation_section.show_items([], "Choose a score to check it.", 0, "")
            return
        summary = "Needs attention"
        if c.assignments is not None:
            items.extend(("info", p) for p in c.assignments.problems())
        view = c.validation
        if c.validating:
            summary = "Checking the score…"
        elif view is not None:
            technical = view.technical
            items.extend((m.severity, m.text) for m in view.messages)
            review_count = view.unresolved if c.review is not None else 0
            if view.source_ready and view.unresolved:
                n = view.unresolved
                items.append(
                    (
                        "warning",
                        f"{n} note{'s have' if n != 1 else ' has'} no lyric yet. "
                        "Open the lyric review and decide what they are sung to.",
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
            result.destination, len(manifest["tracks"]), list(manifest["settings"]["formats"])
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
