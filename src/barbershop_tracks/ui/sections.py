"""The six sections of the main window. They show state; the controller owns it.

Each section is a plain group box with a ``refresh`` that reads the controller and updates
itself without emitting user-change signals, so refreshing can never change a choice.
"""

from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpinBox,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from barbershop_tracks.core.pipeline import STAGE_LABELS
from barbershop_tracks.core.synthesis import VOICE_ORDER
from barbershop_tracks.models import VoiceRole
from barbershop_tracks.ui.assignments import Choice, Ignore
from barbershop_tracks.ui.controller import AppController
from barbershop_tracks.ui.explain import Explanation
from barbershop_tracks.ui.formatting import clock

NOTICE_LIMIT = 8  # notices shown under a finished run; the rest are in the technical log

ROLE_TEXT = {
    VoiceRole.TENOR: "Tenor",
    VoiceRole.LEAD: "Lead",
    VoiceRole.BARITONE: "Baritone",
    VoiceRole.BASS: "Bass",
}


def hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setObjectName("hint")
    return label


def _button(text: str, tip: str = "") -> QPushButton:
    button = QPushButton(text)
    if tip:
        button.setToolTip(tip)
    return button


class ScoreSection(QGroupBox):
    browse_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Score", parent)
        self.headline = QLabel("No score chosen yet")
        self.headline.setObjectName("success")
        self.filename = QLabel("")
        self.filename.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.parts = QLabel("")
        self.parts.setWordWrap(True)
        self.problem = QLabel("")
        self.problem.setObjectName("error")
        self.problem.setWordWrap(True)
        self.browse = _button("&Choose score…", "Open a MusicXML file (.musicxml, .xml, .mxl)")
        self.browse.setAccessibleName("Choose score")
        self.browse.clicked.connect(self.browse_requested)
        drop = hint("You can also drag a MusicXML file onto this window.")
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(self.browse)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addWidget(self.headline)
        layout.addWidget(self.filename)
        layout.addWidget(self.parts)
        layout.addWidget(self.problem)
        layout.addWidget(drop)

    def show_loading(self, name: str) -> None:
        self.headline.setText(f"Loading {name}…")
        self.problem.setText("")

    def show_score(self, title: str, path: Path, parts: list[str]) -> None:
        self.headline.setText(title)
        self.filename.setText(path.name)
        self.filename.setToolTip(str(path))
        noun = "part" if len(parts) == 1 else "parts"
        self.parts.setText(f"{len(parts)} {noun} found: " + "; ".join(parts))
        self.problem.setText("")

    def show_failure(self, text: str) -> None:
        self.problem.setText(text)

    def clear_failure(self) -> None:
        self.problem.setText("")


class AssignmentSection(QGroupBox):
    def __init__(self, controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__("Voice Assignment", parent)
        self.controller = controller
        self._signature: object = None
        self.table = QTableWidget(0, 3)
        self.table.setAccessibleName("Parts of the score and the voice each one sings")
        self.table.setHorizontalHeaderLabels(["Part in the score", "What it contains", "Sings as"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.suggest = _button("&Suggest voices", "Fill in likely voices from the part names")
        self.confirm = _button("C&onfirm suggestions", "Accept the suggested voices as they are")
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.empty = hint("Choose a score to see its parts.")
        self.suggest.clicked.connect(self._suggest)
        self.confirm.clicked.connect(controller.confirm_suggestions)
        layout = QVBoxLayout(self)
        layout.addWidget(self.empty)
        layout.addWidget(self.table)
        row = QHBoxLayout()
        row.addWidget(self.suggest)
        row.addWidget(self.confirm)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addWidget(self.status)
        layout.addWidget(
            hint("Give each part to exactly one voice, or ignore parts that should not be sung.")
        )

    def _suggest(self) -> None:
        self.controller.suggest()

    def refresh(self) -> None:
        state = self.controller.assignments
        score = self.controller.score
        has = state is not None and score is not None
        self.empty.setVisible(not has)
        self.table.setVisible(has)
        self.suggest.setEnabled(has)
        self.confirm.setEnabled(bool(has and state is not None and state.suggested))
        if not has or state is None or score is None:
            self.status.setText("")
            return
        signature = (id(state), tuple(state.choices.items()), tuple(sorted(state.suggested)))
        if signature != self._signature:
            self._signature = signature
            self._rebuild(state)
        problems = state.problems()
        self.status.setText("\n".join(problems) if problems else "✔ Every voice has a part.")
        self.status.setObjectName("" if not problems else "hint")

    def _rebuild(self, state: object) -> None:
        from barbershop_tracks.ui.assignments import AssignmentState

        assert isinstance(state, AssignmentState)
        for row in range(self.table.rowCount()):
            for column in range(self.table.columnCount()):
                old = self.table.cellWidget(row, column)
                if old is not None:
                    self.table.removeCellWidget(row, column)
                    old.deleteLater()
        self.table.clearContents()
        self.table.setRowCount(len(state.lines))
        for row, info in enumerate(state.lines):
            name = QTableWidgetItem(f"{info.part_name}  ({info.line_id})")
            bars = (
                f"bars {info.first_measure} to {info.last_measure}"
                if info.first_measure is not None
                else "empty"
            )
            lyrics = "has lyrics" if info.has_lyrics else "no lyrics"
            detail = QTableWidgetItem(f"{info.sounding_attacks} notes, {bars}, {lyrics}")
            for item in (name, detail):
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row, 0, name)
            self.table.setItem(row, 1, detail)
            combo = QComboBox()
            combo.setAccessibleName(f"Voice for {info.part_name}")
            combo.addItem("— choose —", None)
            for role in VOICE_ORDER:
                combo.addItem(ROLE_TEXT[role], role)
            combo.addItem("Ignore this part", Ignore.IGNORE)
            current = state.choices.get(info.line_id)
            index = combo.findData(current) if current is not None else 0
            combo.setCurrentIndex(max(index, 0))
            model = combo.model()
            assert isinstance(model, QStandardItemModel)
            for i in range(combo.count()):
                data = combo.itemData(i)
                if isinstance(data, VoiceRole) and not state.can_choose(info.line_id, data):
                    taken = model.item(i)
                    taken.setEnabled(False)  # a voice can belong to one part only
                    taken.setToolTip("Already used by another part")
            combo.currentIndexChanged.connect(
                lambda _i, line=info.line_id, box=combo: self._chosen(line, box.currentData())
            )
            if info.line_id in state.suggested:
                combo.setToolTip("Suggested from the part name — please confirm")
                note = QLabel(" suggested ")
                note.setObjectName("hint")
                holder = QWidget()
                inner = QHBoxLayout(holder)
                inner.setContentsMargins(0, 0, 0, 0)
                inner.addWidget(combo)
                inner.addWidget(note)
                self.table.setCellWidget(row, 2, holder)
            else:
                self.table.setCellWidget(row, 2, combo)
        self.table.resizeRowsToContents()
        height = self.table.horizontalHeader().height() + 4
        height += sum(self.table.rowHeight(r) for r in range(self.table.rowCount()))
        self.table.setFixedHeight(height)  # exactly the rows: no empty grey area under them

    def _chosen(self, line_id: str, value: object) -> None:
        choice: Choice = value if isinstance(value, VoiceRole | Ignore) else None
        if not self.controller.set_choice(line_id, choice):
            self._signature = None
            self.refresh()

    def combo_for(self, line_id: str) -> QComboBox | None:
        """The 'Sings as' selector of a line (tests and accessibility helpers)."""
        state = self.controller.assignments
        if state is None:
            return None
        for row, info in enumerate(state.lines):
            if info.line_id == line_id:
                widget = self.table.cellWidget(row, 2)
                if isinstance(widget, QComboBox):
                    return widget
                return widget.findChild(QComboBox) if widget is not None else None
        return None


class VoicesSection(QGroupBox):
    advanced_requested = Signal()
    folder_requested = Signal()

    def __init__(self, controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__("Singing Voices", parent)
        self.controller = controller
        self.folder = QLineEdit()
        self.folder.setReadOnly(True)
        self.folder.setAccessibleName("Folder with the installed singing voices")
        self.folder_button = _button("B&rowse…")
        self.refresh_button = _button("&Refresh", "Look for installed voices again")
        self.same = _button("Same voice for &all parts", "Use the Tenor's voice for every part")
        self.advanced = _button("Ad&vanced…", "Pronunciation and engine settings")
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.combos: dict[VoiceRole, QComboBox] = {}
        form = QFormLayout()
        for role in VOICE_ORDER:
            combo = QComboBox()
            combo.setAccessibleName(f"Singing voice for {ROLE_TEXT[role]}")
            combo.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            combo.setMinimumContentsLength(18)
            combo.activated.connect(lambda _i, r=role, c=combo: self._picked(r, c))
            self.combos[role] = combo
            form.addRow(f"&{ROLE_TEXT[role]}:", combo)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(self.folder_button)
        folder_row.addWidget(self.refresh_button)
        buttons = QHBoxLayout()
        buttons.addWidget(self.same)
        buttons.addStretch(1)
        buttons.addWidget(self.advanced)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Voices folder:"))
        layout.addLayout(folder_row)
        layout.addLayout(form)
        layout.addLayout(buttons)
        layout.addWidget(self.status)
        layout.addWidget(
            hint("BLT does not download or include voices. Install yours in the voices folder.")
        )
        self.folder_button.clicked.connect(self.folder_requested)
        self.advanced.clicked.connect(self.advanced_requested)
        self.refresh_button.clicked.connect(controller.refresh_voices)
        self.same.clicked.connect(self._same)

    def _picked(self, role: VoiceRole, combo: QComboBox) -> None:
        self.controller.set_singer(role, str(combo.currentData() or ""))

    def _same(self) -> None:
        tenor = self.controller.singers.get(VoiceRole.TENOR, "")
        if tenor:
            self.controller.use_same_singer(tenor)

    def refresh(self) -> None:
        controller = self.controller
        folder = controller.singers_folder()
        self.folder.setText(str(folder) if folder else "")
        self.folder.setPlaceholderText("No voices folder set — choose one")
        installed = controller.installed or []
        for role, combo in self.combos.items():
            chosen = controller.singers.get(role, "")
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("— choose a voice —", "")
            for name in installed:
                combo.addItem(name, name)
            if chosen and chosen not in installed:
                label = f"{chosen} (not installed)" if controller.installed is not None else chosen
                combo.addItem(label, chosen)
            combo.setCurrentIndex(max(combo.findData(chosen), 0))
            combo.blockSignals(False)
        self.same.setEnabled(bool(controller.singers.get(VoiceRole.TENOR)))
        problems = [
            p
            for role in VOICE_ORDER
            if controller.singers.get(role) and (p := controller.singer_problem(role))
        ]
        if controller.installed is None:
            self.status.setText("Looking for voices…")
        elif not installed:
            self.status.setText("No voices were found in this folder.")
        else:
            self.status.setText(
                "\n".join(problems) if problems else f"✔ {len(installed)} voice(s) installed."
            )


class ValidationSection(QGroupBox):
    review_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Lyrics and Validation", parent)
        self.summary = QLabel("Choose a score to check it.")
        self.summary.setWordWrap(True)
        self.summary.setObjectName("success")
        self.list = QListWidget()
        self.list.setAccessibleName("Things to fix before generating")
        self.list.setWordWrap(True)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.list.setMinimumHeight(120)
        self.review = _button("Review &lyrics…", "Decide what the notes without lyrics are sung to")
        self.review.setEnabled(False)
        self.review.clicked.connect(self.review_requested)
        self.details_button = _button("Show &technical details")
        self.details_button.setCheckable(True)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setAccessibleName("Technical details of the check")
        self.details.setVisible(False)
        self.details.setMaximumHeight(160)
        self.details_button.toggled.connect(self.details.setVisible)
        layout = QVBoxLayout(self)
        layout.addWidget(self.summary)
        layout.addWidget(self.list, 1)
        row = QHBoxLayout()
        row.addWidget(self.review)
        row.addStretch(1)
        row.addWidget(self.details_button)
        layout.addLayout(row)
        layout.addWidget(self.details)

    def show_items(
        self, items: list[tuple[str, str]], summary: str, review_count: int, technical: str
    ) -> None:
        self.summary.setText(summary)
        self.list.clear()
        style = self.style()
        icons = {
            "error": QStyle.StandardPixmap.SP_MessageBoxCritical,
            "warning": QStyle.StandardPixmap.SP_MessageBoxWarning,
            "info": QStyle.StandardPixmap.SP_MessageBoxInformation,
            "ok": QStyle.StandardPixmap.SP_DialogApplyButton,
        }
        for severity, text in items:
            item = QListWidgetItem(style.standardIcon(icons[severity]), text)
            item.setToolTip(text)
            self.list.addItem(item)
        self.review.setEnabled(review_count > 0)
        self.review.setText(
            f"Review &lyrics ({review_count} note{'s' if review_count != 1 else ''})…"
            if review_count
            else "Review &lyrics…"
        )
        self.details.setPlainText(technical)


class OutputSection(QGroupBox):
    browse_requested = Signal()
    ffmpeg_requested = Signal()

    def __init__(self, controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__("Output Settings", parent)
        self.controller = controller
        self.folder = QLineEdit()
        self.folder.setReadOnly(True)
        self.folder.setPlaceholderText("Choose where the tracks should be saved")
        self.folder.setAccessibleName("Output folder")
        self.browse = _button("&Browse…")
        self.name = QLineEdit()
        self.name.setAccessibleName("Package name")
        self.location = QLabel("")
        self.location.setWordWrap(True)
        self.location.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.wav = QRadioButton("&WAV (lossless)")
        self.mp3 = QRadioButton("&MP3")
        self.both = QRadioButton("Both WAV and MP&3")
        self.quality = QSpinBox()
        self.quality.setRange(0, 9)
        self.quality.setToolTip("0 is the best quality and the largest files; 9 is the smallest")
        self.quality.setAccessibleName("MP3 quality (0 best, 9 smallest)")
        self.ffmpeg = QLineEdit()
        self.ffmpeg.setReadOnly(True)
        self.ffmpeg.setAccessibleName("FFmpeg program")
        self.ffmpeg_button = _button("Choose &FFmpeg…")
        self.preset = QComboBox()
        self.preset.setAccessibleName("Mix balance")
        for text, key in (
            ("Balanced (recommended)", "default"),
            ("Featured voice stands out more", "strong-focus"),
            ("Featured voice stands out less", "gentle-focus"),
            ("Custom…", "custom"),
        ):
            self.preset.addItem(text, key)
        self.focus = QDoubleSpinBox()
        self.others = QDoubleSpinBox()
        for box, tip in (
            (self.focus, "Loudness of the featured voice"),
            (self.others, "Loudness of the other voices"),
        ):
            box.setRange(0.0, 1.0)
            box.setSingleStep(0.05)
            box.setDecimals(2)
            box.setToolTip(tip)
        self.focus.setAccessibleName("Featured voice loudness")
        self.others.setAccessibleName("Other voices loudness")
        self.keep_stems = QCheckBox("Keep the four separate voice recordings")
        self.keep_project = QCheckBox("Keep the singing project file")
        self.replace = QCheckBox("&Replace existing tracks with this name")
        self.status = QLabel("")
        self.status.setWordWrap(True)

        form = QFormLayout()
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(self.browse)
        form.addRow("Output &folder:", folder_row)
        form.addRow("Package &name:", self.name)
        formats = QHBoxLayout()
        for radio in (self.wav, self.mp3, self.both):
            formats.addWidget(radio)
        formats.addStretch(1)
        form.addRow("Format:", formats)
        quality = QHBoxLayout()
        quality.addWidget(self.quality)
        quality.addWidget(hint("0 = best"))
        quality.addStretch(1)
        form.addRow("MP3 &quality:", quality)
        ffmpeg_row = QHBoxLayout()
        ffmpeg_row.addWidget(self.ffmpeg, 1)
        ffmpeg_row.addWidget(self.ffmpeg_button)
        form.addRow("FFmpeg (for MP3):", ffmpeg_row)
        form.addRow("Mix &balance:", self.preset)
        gains = QHBoxLayout()
        gains.addWidget(QLabel("Featured voice"))
        gains.addWidget(self.focus)
        gains.addWidget(QLabel("Other voices"))
        gains.addWidget(self.others)
        gains.addStretch(1)
        self.gain_row = QWidget()
        self.gain_row.setLayout(gains)
        gains.setContentsMargins(0, 0, 0, 0)
        form.addRow("", self.gain_row)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.keep_stems)
        layout.addWidget(self.keep_project)
        layout.addWidget(self.replace)
        layout.addWidget(QLabel("The tracks will be saved in:"))
        layout.addWidget(self.location)
        layout.addWidget(self.status)

        self.browse.clicked.connect(self.browse_requested)
        self.ffmpeg_button.clicked.connect(self.ffmpeg_requested)
        self.name.textEdited.connect(lambda text: controller.set_options(name=text))
        for radio, key in ((self.wav, "wav"), (self.mp3, "mp3"), (self.both, "both")):
            radio.toggled.connect(lambda on, k=key: self._format_toggled(on, k))
        self.quality.valueChanged.connect(lambda v: controller.set_options(mp3_quality=v))
        self.preset.activated.connect(
            lambda _i: controller.set_options(gain_preset=str(self.preset.currentData()))
        )
        self.focus.valueChanged.connect(lambda v: controller.set_options(custom_focus=v))
        self.others.valueChanged.connect(lambda v: controller.set_options(custom_others=v))
        self.keep_stems.toggled.connect(lambda v: controller.set_options(keep_stems=v))
        self.keep_project.toggled.connect(lambda v: controller.set_options(keep_project=v))
        self.replace.toggled.connect(lambda v: controller.set_options(replace=v))

    def _format_toggled(self, on: bool, key: str) -> None:
        if on:
            self.controller.set_options(audio_format=key)

    def refresh(self) -> None:
        controller, options = self.controller, self.controller.options
        widgets = (
            self.wav,
            self.mp3,
            self.both,
            self.quality,
            self.preset,
            self.focus,
            self.others,
            self.keep_stems,
            self.keep_project,
            self.replace,
            self.name,
        )
        for widget in widgets:
            widget.blockSignals(True)
        try:
            self.folder.setText(controller.output_dir)
            if self.name.text() != options.name and not self.name.hasFocus():
                self.name.setText(options.name)
            score = controller.score
            self.name.setPlaceholderText(
                score.path.stem if score else "Name of the folder for the tracks"
            )
            {"wav": self.wav, "mp3": self.mp3, "both": self.both}[options.audio_format].setChecked(
                True
            )
            self.quality.setValue(options.mp3_quality)
            self.preset.setCurrentIndex(max(self.preset.findData(options.gain_preset), 0))
            self.focus.setValue(options.custom_focus)
            self.others.setValue(options.custom_others)
            self.keep_stems.setChecked(options.keep_stems)
            self.keep_project.setChecked(options.keep_project)
            self.replace.setChecked(options.replace)
        finally:
            for widget in widgets:
                widget.blockSignals(False)
        wants_mp3 = options.audio_format != "wav"
        for mp3_widget in (self.quality, self.ffmpeg, self.ffmpeg_button):
            mp3_widget.setEnabled(wants_mp3)
        ffmpeg = controller.ffmpeg_path()
        self.ffmpeg.setText(str(ffmpeg) if ffmpeg else "")
        self.ffmpeg.setPlaceholderText(
            "FFmpeg not found — choose ffmpeg.exe" if wants_mp3 else "Only needed for MP3"
        )
        self.gain_row.setVisible(options.gain_preset == "custom")
        location = controller.expected_location()
        self.location.setText(str(location) if location else "— (choose an output folder)")
        problem = controller.gain_problem()
        if problem:
            self.status.setText(problem)
            self.status.setObjectName("error")
        elif controller.existing_package() and not options.replace:
            self.status.setText(
                "A package with this name already exists. Tick “Replace” or change the name."
            )
            self.status.setObjectName("error")
        elif controller.existing_package():
            self.status.setText("The existing package will be replaced after you confirm.")
            self.status.setObjectName("hint")
        else:
            self.status.setText("")


STATUS_MARK = {"pending": "○", "active": "▶", "done": "✔", "failed": "✖", "stopped": "■"}


class ProgressSection(QGroupBox):
    cancel_requested = Signal()
    open_folder_requested = Signal()
    review_requested = Signal()
    pronunciation_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Generation Progress", parent)
        self.stage = QLabel("Ready.")
        self.stage.setAccessibleName("Current step")
        self.stage.setObjectName("success")
        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.bar = QProgressBar()
        self.bar.setAccessibleName("Progress")
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        self.bar.setVisible(False)
        self.elapsed = QLabel("")
        self.elapsed.setMinimumWidth(110)
        self.steps = QListWidget()
        self.steps.setAccessibleName("Steps")
        self.steps.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.steps.setMaximumHeight(190)
        self.steps.setVisible(False)
        self.cancel = _button("Cancel generation")
        self.cancel.setEnabled(False)
        self.cancel.clicked.connect(self.cancel_requested)
        self.log_button = _button("Show technical &log")
        self.log_button.setCheckable(True)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        self.log.setAccessibleName("Technical log")
        self.log.setVisible(False)
        self.log.setMaximumHeight(180)
        self.log_button.toggled.connect(self.log.setVisible)
        # the result
        self.result_title = QLabel("")
        self.result_title.setWordWrap(True)
        self.result_text = QLabel("")
        self.result_text.setWordWrap(True)
        self.result_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.open_folder = _button("&Open output folder")
        self.open_folder.clicked.connect(self.open_folder_requested)
        self.open_review = _button("Open lyric &review")
        self.open_review.clicked.connect(self.review_requested)
        self.open_pronunciation = _button("Open &Pronunciations")
        self.open_pronunciation.clicked.connect(self.pronunciation_requested)
        self.technical_button = _button("Show technical &details")
        self.technical_button.setCheckable(True)
        self.technical = QPlainTextEdit()
        self.technical.setReadOnly(True)
        self.technical.setAccessibleName("Technical details of the problem")
        self.technical.setMaximumHeight(160)
        self.technical.setVisible(False)
        self.technical_button.toggled.connect(self.technical.setVisible)
        self.result_box = QWidget()
        box = QVBoxLayout(self.result_box)
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(self.result_title)
        box.addWidget(self.result_text)
        buttons = QHBoxLayout()
        buttons.addWidget(self.open_folder)
        buttons.addWidget(self.open_review)
        buttons.addWidget(self.open_pronunciation)
        buttons.addWidget(self.technical_button)
        buttons.addStretch(1)
        box.addLayout(buttons)
        box.addWidget(self.technical)
        self.result_box.setVisible(False)

        layout = QVBoxLayout(self)
        layout.addWidget(self.stage)
        layout.addWidget(self.detail)
        layout.addWidget(self.bar)
        top = QHBoxLayout()
        top.addWidget(self.elapsed)
        top.addStretch(1)
        top.addWidget(self.cancel)
        layout.addLayout(top)
        layout.addWidget(self.steps)
        layout.addWidget(self.result_box)
        row = QHBoxLayout()
        row.addWidget(self.log_button)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addWidget(self.log)
        layout.addStretch(1)
        self.states: dict[str, str] = {}
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

    # --- running ---------------------------------------------------------------------------

    def start(self, stages: list[str]) -> None:
        self.states = dict.fromkeys(stages, "pending")
        self.result_box.setVisible(False)
        self.technical.clear()
        self.technical_button.setChecked(False)
        self.log.clear()
        self.stage.setText("Starting…")
        self.detail.setText("")
        self.bar.setVisible(True)
        self.bar.setRange(0, 0)  # busy: we do not know how long it will take
        self.cancel.setEnabled(True)
        self._draw_steps()

    def _draw_steps(self) -> None:
        self.steps.clear()
        self.steps.setVisible(bool(self.states))
        for key, state in self.states.items():
            item = QListWidgetItem(f"{STATUS_MARK[state]}  {STAGE_LABELS.get(key, key)}")
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            if state == "failed":
                item.setForeground(QColor("#b00020"))
                item.setToolTip("This step is where it stopped.")
            self.steps.addItem(item)

    def stage_started(self, key: str) -> None:
        if key in self.states:
            self.states[key] = "active"
        self.stage.setText(STAGE_LABELS.get(key, key) + "…")
        if key not in ("mixing", "mp3_encoding"):
            self.bar.setRange(0, 0)  # busy, no invented percentage
        self._draw_steps()

    def stage_finished(self, key: str) -> None:
        if key in self.states:
            self.states[key] = "done"
        self._draw_steps()

    def counted(self, stage: str, done: int, total: int) -> None:
        """Real progress: items finished out of a known number."""
        self.bar.setRange(0, total)
        self.bar.setValue(done)
        self.detail.setText(f"{STAGE_LABELS.get(stage, stage)}: {done} of {total}")

    def note(self, text: str) -> None:
        self.detail.setText(text)

    def set_elapsed(self, seconds: float) -> None:
        self.elapsed.setText(f"Elapsed {clock(seconds)}")

    def append_log(self, line: str) -> None:
        self.log.appendPlainText(line)

    def finish_running(self) -> None:
        self.cancel.setEnabled(False)
        self.bar.setRange(0, 1)
        self.bar.setValue(0)

    # --- results ---------------------------------------------------------------------------

    def show_success(
        self, location: Path, tracks: int, formats: list[str], notices: Sequence[str] = ()
    ) -> None:
        self.finish_running()
        self.bar.setValue(1)
        self.stage.setText("Finished")
        self.detail.setText("")
        self.result_title.setText("✔ Your learning tracks are ready.")
        self.result_title.setObjectName("success")
        text = (
            f"{tracks} tracks ({', '.join(f.upper() for f in formats)}) were saved in:\n{location}"
        )
        if notices:
            shown = list(notices[:NOTICE_LIMIT])
            text += "\n\nPlease check these by ear:" + "".join(f"\n• {n}" for n in shown)
            if len(notices) > len(shown):
                text += f"\n• and {len(notices) - len(shown)} more (see the technical log)"
        self.result_text.setText(text)
        self.open_folder.setVisible(True)
        self.open_review.setVisible(False)
        self.open_pronunciation.setVisible(False)
        self.technical_button.setVisible(False)
        self.result_box.setVisible(True)

    def show_failure(self, explanation: Explanation) -> None:
        self.finish_running()
        for key, state in self.states.items():
            if state == "active":  # the step it stopped in
                self.states[key] = "stopped" if explanation.cancelled else "failed"
        self._draw_steps()
        self.stage.setText("Cancelled" if explanation.cancelled else "Stopped")
        self.result_title.setText(explanation.title)
        self.result_title.setObjectName("hint" if explanation.cancelled else "error")
        steps = "".join(f"\n• {s}" for s in explanation.steps)
        self.result_text.setText(explanation.summary + steps)
        self.technical.setPlainText(explanation.technical)
        self.open_folder.setVisible(False)
        self.open_review.setVisible(explanation.review)
        self.open_pronunciation.setVisible(explanation.pronunciation)
        self.technical_button.setVisible(bool(explanation.technical))
        self.result_box.setVisible(True)
        self.style().unpolish(self.result_title)
        self.style().polish(self.result_title)

    def reset(self) -> None:
        self.states = {}
        self.steps.clear()
        self.result_box.setVisible(False)
        self.stage.setText("Ready.")
        self.detail.setText("")
        self.elapsed.setText("")
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        self.bar.setVisible(False)


__all__ = [
    "AssignmentSection",
    "OutputSection",
    "ProgressSection",
    "ScoreSection",
    "ValidationSection",
    "VoicesSection",
]
