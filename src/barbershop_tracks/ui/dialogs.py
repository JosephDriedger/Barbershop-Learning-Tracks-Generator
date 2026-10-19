"""The two dialogs: the lyric review editor and the advanced settings."""

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from barbershop_tracks.core.pipeline import (
    DEFAULT_PHONEMIZER,
    DEFAULT_RENDERER,
    SHIPPED_RENDERERS,
    PipelineError,
    approvals_document,
    removed_phonemizer,
    review_report,
)
from barbershop_tracks.core.synthesis import SynthesisPlan
from barbershop_tracks.core.wording import agree, counted
from barbershop_tracks.ui.lyric_review import LyricReviewState, RowState
from barbershop_tracks.ui.preferences import Preferences
from barbershop_tracks.ui.prompts import Prompts

COLUMNS = (
    "Voice",
    "Where",
    "Pitch",
    "Length",
    "Why it needs a lyric",
    "Lead sings",
    "Suggested",
    "Lyric",
    "Status",
)
LYRIC_COLUMN = COLUMNS.index("Lyric")
JSON_FILTER = "Lyric approvals (*.json);;All files (*)"

_STATE_COLORS = {
    RowState.UNDECIDED: "#b26a00",
    RowState.DRAFT: "#1565c0",
    RowState.APPROVED: "#2e7d32",
    RowState.INVALID: "#c62828",
    RowState.FOLLOWS: "#616161",
}


class LyricTableModel(QAbstractTableModel):
    def __init__(self, state: LyricReviewState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self.state.rows)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return COLUMNS[section]
        return None

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == LYRIC_COLUMN:
            return base | Qt.ItemFlag.ItemIsEditable
        return base

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = 0) -> Any:
        if not index.isValid():
            return None
        row, column = self.state.rows[index.row()], index.column()
        cells = (
            row.role.display_name,
            row.where,
            row.pitch,
            row.length,
            row.reason,
            row.lead_text or "",
            row.proposal or "",
            row.text,
            row.state.value,
        )
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return cells[column]
        if role == Qt.ItemDataRole.ForegroundRole and column == len(COLUMNS) - 1:
            return QBrush(QColor(_STATE_COLORS[row.state]))
        if role == Qt.ItemDataRole.ToolTipRole:
            if row.error:
                return row.error
            if column == COLUMNS.index("Lead sings") and row.lead_text:
                return "What the Lead sings at this moment. Shown for reference only."
            return row.detail or None
        return None

    def setData(
        self, index: QModelIndex | QPersistentModelIndex, value: Any, role: int = 0
    ) -> bool:
        if role != Qt.ItemDataRole.EditRole or index.column() != LYRIC_COLUMN:
            return False
        self.state.set_text(index.row(), str(value))
        self.changed_rows([index.row()])
        return True

    def changed_rows(self, rows: list[int]) -> None:
        for row in rows:
            self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLUMNS) - 1))

    def changed_all(self) -> None:
        if self.state.rows:
            self.dataChanged.emit(
                self.index(0, 0), self.index(len(self.state.rows) - 1, len(COLUMNS) - 1)
            )


class _Filter(QSortFilterProxyModel):
    def __init__(self, state: LyricReviewState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.voice = ""
        self.only_open = False

    def configure(self, voice: str, only_open: bool) -> None:
        self.voice, self.only_open = voice, only_open
        self.invalidate()

    def filterAcceptsRow(
        self, source_row: int, source_parent: QModelIndex | QPersistentModelIndex
    ) -> bool:
        row = self.state.rows[source_row]
        if self.voice and row.role.value != self.voice:
            return False
        return not (self.only_open and (row.approved or row.inherited))


class LyricReviewDialog(QDialog):
    """Decide, note by note, what the notes without a lyric are sung to."""

    def __init__(
        self,
        state: LyricReviewState,
        baseline: SynthesisPlan,
        prompts: Prompts,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.state = state
        self._baseline = baseline
        self._prompts = prompts
        self._saved = state.snapshot()
        self.setWindowTitle("Lyric Review")
        self.setModal(True)
        self.resize(1100, 620)
        self.setSizeGripEnabled(True)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        note = QLabel(
            "These notes have no lyric of their own in the score. Notes marked “Follows another "
            "part” sing what the Lead sings, or what another part sings on the very same note (the "
            "usual barbershop convention), and need nothing from you; "
            "to change one, type what it should sing and approve it. Notes that need a lyric must "
            "be decided before generating. Words the score already provides are not listed here."
        )
        note.setWordWrap(True)
        note.setObjectName("hint")

        self.model = LyricTableModel(state, self)
        self.proxy = _Filter(state, self)
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setAccessibleName("Notes that need a lyric")
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(LYRIC_COLUMN, QHeaderView.ResizeMode.Stretch)
        header.setMinimumSectionSize(60)
        self.table.verticalHeader().setVisible(False)

        self.voice_filter = QComboBox()
        self.voice_filter.setAccessibleName("Show notes of")
        self.voice_filter.addItem("All Voices", "")
        for role in sorted({r.role for r in state.rows}, key=lambda r: r.value):
            self.voice_filter.addItem(role.display_name, role.value)
        self.open_only = QPushButton("Hide Approved and Followed Notes")
        self.open_only.setCheckable(True)
        self.voice_filter.currentIndexChanged.connect(self._refilter)
        self.open_only.toggled.connect(self._refilter)

        self.approver = QLineEdit(state.approver)
        self.approver.setAccessibleName("Approved by")
        self.approver.editingFinished.connect(self._approver_changed)

        def button(text: str, handler: Any, tip: str = "") -> QPushButton:
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(handler)
            return b

        self.approve_button = button(
            "&Approve Selected",
            self.approve_selected,
            "Approve the typed lyric of each selected note",
        )
        self.approve_all_button = button(
            "Approve All &Typed Lyrics",
            self.approve_typed,
            "Approve every note that has a lyric typed in",
        )
        batch = [
            self.approve_button,
            self.approve_all_button,
            button("&Un-Approve Selected", self.unapprove_selected),
            button("Type One Lyric for the Selected Notes…", self.fill_selected),
            button(
                "Use Suggested Lyrics",
                self.use_proposals,
                "Fill selected notes with BLT's suggestion",
            ),
            button(
                "Copy the Lead's Words…",
                self.copy_lead,
                "Copy what the Lead sings into the selected notes (you still approve them)",
            ),
            button("Clear Selected", self.clear_selected),
        ]
        files = [
            button("&Load Approvals…", self.load_file),
            button("&Save Approvals…", self.save_file),
            button("Export &Report…", self.export_report),
        ]

        top = QHBoxLayout()
        top.addWidget(QLabel("Show:"))
        top.addWidget(self.voice_filter)
        top.addWidget(self.open_only)
        top.addStretch(1)
        top.addWidget(QLabel("Approved by:"))
        top.addWidget(self.approver)
        row1, row2 = QHBoxLayout(), QHBoxLayout()
        for b in batch:
            row1.addWidget(b)
        row1.addStretch(1)
        for b in files:
            row2.addWidget(b)
        row2.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText("Done")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.summary)
        layout.addWidget(note)
        layout.addLayout(top)
        layout.addWidget(self.table, 1)
        layout.addLayout(row1)
        layout.addLayout(row2)
        layout.addWidget(buttons)
        self.model.dataChanged.connect(lambda *_: self._update_summary())
        self._update_summary()

    # --- helpers ---------------------------------------------------------------------------

    def _selected(self) -> list[int]:
        rows = {self.proxy.mapToSource(i).row() for i in self.table.selectionModel().selectedRows()}
        return sorted(rows)

    def _visible(self) -> list[int]:
        return [
            self.proxy.mapToSource(self.proxy.index(r, 0)).row()
            for r in range(self.proxy.rowCount())
        ]

    def _touched(self, rows: list[int]) -> None:
        self.model.changed_rows(rows)
        self._update_summary()

    def _refilter(self) -> None:
        self.proxy.configure(str(self.voice_filter.currentData() or ""), self.open_only.isChecked())

    def _approver_changed(self) -> None:
        name = self.approver.text().strip()
        if name:
            self.state.approver = name

    def _update_summary(self) -> None:
        total = len(self.state.rows) - self.state.following_count
        left = self.state.unresolved
        drafts = sum(1 for r in self.state.rows if r.state is RowState.DRAFT)
        text = (
            f"{self.state.approved_count} of {counted(total, 'note')} approved; "
            f"{left} still {agree(left, 'needs', 'need')} a lyric"
        )
        followed = self.state.following_count
        if followed:
            text += f"; {followed} follow the Lead"
        if drafts:
            text += f" ({drafts} typed but not approved yet)"
        self.summary.setText(text + ".")

    # --- actions ---------------------------------------------------------------------------

    def approve_selected(self) -> int:
        self._approver_changed()
        rows = self._selected()
        done = self.state.approve(rows)
        self._touched(rows)
        return done

    def approve_typed(self) -> int:
        self._approver_changed()
        rows = self._visible()
        done = self.state.approve(rows)
        self._touched(rows)
        return done

    def unapprove_selected(self) -> None:
        rows = self._selected()
        self.state.unapprove(rows)
        self._touched(rows)

    def fill_selected(self) -> None:
        rows = self._selected()
        if not rows:
            return
        text, ok = QInputDialog.getText(
            self, "One lyric for several notes", "Lyric for the selected notes:"
        )
        if ok and text.strip():
            self.state.fill_text(rows, text.strip())
            self._touched(rows)

    def use_proposals(self) -> None:
        rows = self._selected()
        self.state.use_proposals(rows)
        self._touched(rows)

    def copy_lead(self) -> None:
        rows = self._selected()
        usable = [r for r in rows if self.state.rows[r].lead_text]
        if not usable:
            return
        if not self._prompts.confirm(
            self,
            "Copy the Lead's words?",
            f"Copy what the Lead sings into {counted(len(usable), 'selected note')}? You still "
            f"have to approve {agree(len(usable), 'it', 'them')}, and harmony parts do not "
            "always sing the Lead's words.",
            "Copy",
        ):
            return
        self.state.use_lead_words(usable)
        self._touched(usable)

    def clear_selected(self) -> None:
        rows = self._selected()
        self.state.clear(rows)
        self._touched(rows)

    def load_file(self) -> None:
        path = self._prompts.choose_file(self, "Load approvals", "", JSON_FILTER)
        if not path:
            return
        try:
            applied, skipped = self.state.load_file(Path(path))
        except PipelineError as error:
            self._prompts.warn(self, "These approvals cannot be used", error.message)
            return
        self.model.changed_all()
        self._update_summary()
        note = f"{counted(applied, 'approval')} applied."
        if skipped:
            note += (
                f" {skipped} did not match any note that needs a lyric and "
                f"{agree(skipped, 'was', 'were')} ignored."
            )
        self._prompts.inform(self, "Approvals loaded", note)

    def save_file(self) -> None:
        path = self._prompts.save_file(self, "Save approvals", "lyric-approvals.json", JSON_FILTER)
        if not path:
            return
        document = approvals_document(self.state.approvals(), self.state.source_sha256)
        Path(path).write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    def export_report(self) -> None:
        path = self._prompts.save_file(
            self, "Export review report", "lyric-review.json", JSON_FILTER
        )
        if path:
            Path(path).write_text(
                json.dumps(review_report(self._baseline), indent=2) + "\n", encoding="utf-8"
            )

    def reject(self) -> None:
        self.state.restore(self._saved)  # Cancel leaves the decisions as they were
        super().reject()


class AdvancedDialog(QDialog):
    """Settings most people never need; blank means the built-in default."""

    def __init__(self, prefs: Preferences, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.prefs = prefs
        self.setWindowTitle("Advanced Settings")
        self.pronunciation = QLineEdit(prefs.phonemizer)
        self.pronunciation.setPlaceholderText(DEFAULT_PHONEMIZER)
        self.pronunciation.setAccessibleName("Pronunciation engine")
        self.engine = QComboBox()
        self.engine.setEditable(True)
        self.engine.addItem("")
        self.engine.addItems(SHIPPED_RENDERERS)
        self.engine.setCurrentText(prefs.renderer)
        engine_edit = self.engine.lineEdit()
        assert engine_edit is not None
        engine_edit.setPlaceholderText(DEFAULT_RENDERER)
        self.engine.setAccessibleName("Voice engine")
        self.host = QLineEdit(prefs.host_dir)
        self.host.setPlaceholderText("Found automatically next to BLT")
        self.host.setAccessibleName("Singing engine folder")
        self.runtime = QLineEdit(prefs.dotnet_root)
        self.runtime.setPlaceholderText("Not needed: BLT includes its own")
        self.runtime.setAccessibleName(".NET runtime folder")
        self.timeout = QSpinBox()
        self.timeout.setRange(1, 240)
        self.timeout.setSuffix(" minutes")
        self.timeout.setValue(prefs.timeout_minutes)
        self.timeout.setAccessibleName("Time limit")

        self.follow_lead = QCheckBox("Parts Without Lyrics of Their Own Sing the &Lead's Words")
        self.follow_lead.setChecked(prefs.follow_lead)
        self.follow_lead.setToolTip(
            "The usual barbershop convention. Notes the score gives no lyric take what the Lead "
            "sings at that moment (and hold its vowel when they move under a held word). "
            "Switch off to review every such note yourself."
        )

        form = QFormLayout()
        form.addRow("&Pronunciation:", self.pronunciation)
        form.addRow("Voice &Engine:", self.engine)
        form.addRow("Singing Engine &Folder:", self.host)
        form.addRow(".NET &Runtime Folder:", self.runtime)
        form.addRow("Time &Limit:", self.timeout)
        form.addRow("Lyrics:", self.follow_lead)
        hint = QLabel(
            "Leave a field empty to use BLT's default. Changing these can stop generation from "
            "working; “Restore defaults” puts everything back."
        )
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        restore = QPushButton("Restore Defaults")
        restore.clicked.connect(self._restore)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(hint)
        row = QHBoxLayout()
        row.addWidget(restore)
        row.addStretch(1)
        row.addWidget(buttons)
        layout.addLayout(row)
        self.setMinimumWidth(520)

    def _restore(self) -> None:
        self.pronunciation.clear()
        self.engine.setCurrentText("")
        self.host.clear()
        self.runtime.clear()
        self.timeout.setValue(15)
        self.follow_lead.setChecked(True)

    def accept(self) -> None:
        prefs = self.prefs
        removed = removed_phonemizer(self.pronunciation.text())
        if removed:
            QMessageBox.warning(
                self,
                "Pronunciation engine",
                f"{removed} is not part of this version of BLT: it needs an English dictionary "
                "whose origin could not be verified."
                "\n\nLeave the box empty for the default, or use "
                "OpenUtau.Plugin.Builtin.ArpasingPhonemizer for a voicebank built for ARPAsing.",
            )
            return
        prefs.phonemizer = self.pronunciation.text().strip()
        prefs.renderer = self.engine.currentText().strip()
        prefs.host_dir = self.host.text().strip()
        prefs.dotnet_root = self.runtime.text().strip()
        prefs.timeout_minutes = self.timeout.value()
        prefs.follow_lead = self.follow_lead.isChecked()
        super().accept()
