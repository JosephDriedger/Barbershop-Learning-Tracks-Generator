"""The pronunciation dialog: say how each place with a word the dictionary lacks is sung.

BLT stops at a word the pronunciation dictionary has no entry for (it never guesses and never drops
a syllable). Here the person decides, place by place, how that word is sung: one row is one voice at one
note. The score's own lyric text is shown as written and never edited; what is typed is a pronunciation
in the notation of that voice's pronunciation engine, kept beside the score text and tied to this score.
Nothing is filled in by itself. "Same for the other voices here" copies a decision only to the other voices
at the same place and word, and only when it is clicked. "Check" asks the engine itself whether it accepts
what was typed, before anything is rendered.
"""

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    Qt,
)
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from barbershop_tracks.core.pipeline import PipelineError
from barbershop_tracks.core.wording import agree, counted
from barbershop_tracks.ui.controller import AppController
from barbershop_tracks.ui.explain import explain
from barbershop_tracks.ui.prompts import Prompts
from barbershop_tracks.ui.pronunciation_review import PronunciationState, RowState

COLUMNS = (
    "Voice",
    "Where",
    "The score says",
    "Word sent to the engine",
    "Engine",
    "Pronunciation",
    "Status",
)
TEXT_COLUMN = COLUMNS.index("Pronunciation")
JSON_FILTER = "Pronunciations (*.json);;All files (*)"

_COLORS = {
    RowState.UNDECIDED: "#b26a00",
    RowState.DECIDED: "#2e7d32",
    RowState.INVALID: "#c62828",
}


def engine_name(phonemizer: str | None) -> str:
    if not phonemizer:
        return "unknown"
    return phonemizer.rsplit(".", 1)[-1].removesuffix("Phonemizer")


class PronunciationTableModel(QAbstractTableModel):
    def __init__(self, state: PronunciationState, parent: QWidget | None = None) -> None:
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
        if index.column() == TEXT_COLUMN and self.state.rows[index.row()].supported:
            return base | Qt.ItemFlag.ItemIsEditable
        return base

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = 0) -> Any:
        if not index.isValid():
            return None
        row, column = self.state.rows[index.row()], index.column()
        status = row.state.value
        if row.error:
            status = f"{status}: {row.error}"
        elif row.note:
            status = f"{status}: {row.note}"
        elif not row.supported:
            status = "This engine takes no pronunciations: change the spelling in the score"
        cells = (
            row.role.display_name,
            row.where,
            " · ".join(row.score_lyrics) or row.word,
            row.word + (" (part of a longer word)" if row.fragment else ""),
            engine_name(row.phonemizer),
            row.text,
            status,
        )
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return cells[column]
        if role == Qt.ItemDataRole.ForegroundRole and column == len(COLUMNS) - 1:
            return QBrush(QColor(_COLORS[row.state]))
        if role == Qt.ItemDataRole.ToolTipRole:
            if column == TEXT_COLUMN:
                return row.notation
            return row.error or row.note or None
        return None

    def setData(
        self, index: QModelIndex | QPersistentModelIndex, value: Any, role: int = 0
    ) -> bool:
        if role != Qt.ItemDataRole.EditRole or index.column() != TEXT_COLUMN:
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


class PronunciationDialog(QDialog):
    """Decide how each place with a word the dictionary lacks is sung."""

    def __init__(
        self,
        state: PronunciationState,
        controller: AppController,
        prompts: Prompts,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.state = state
        self._controller = controller
        self._prompts = prompts
        self._saved = [(r.text, r.error, r.note) for r in state.rows]
        self.setWindowTitle("Pronunciations")
        self.setModal(True)
        self.resize(1100, 560)
        self.setSizeGripEnabled(True)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        intro = QLabel(
            "The pronunciation dictionary has no entry for these words, and BLT will not guess how "
            "they sound or leave a syllable out. Say how each place is sung, in the notation of "
            "its pronunciation engine (hover over a pronunciation to see it). One row is one voice "
            "at one place: nothing is applied anywhere else. Your score is never changed; what you "
            "write is kept beside it, tied to this score."
        )
        intro.setWordWrap(True)
        intro.setObjectName("hint")
        self.notation = QLabel()
        self.notation.setWordWrap(True)
        self.notation.setObjectName("hint")
        self.notation.setAccessibleName("Notation of the selected row")

        self.model = PronunciationTableModel(state, self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setAccessibleName("Places that need a pronunciation")
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
        header.setSectionResizeMode(TEXT_COLUMN, QHeaderView.ResizeMode.Stretch)
        header.setMinimumSectionSize(60)
        self.table.verticalHeader().setVisible(False)
        selection = self.table.selectionModel()
        assert selection is not None
        selection.selectionChanged.connect(lambda *_: self._show_notation())

        self.approver = QLineEdit(state.approver)
        self.approver.setAccessibleName("Decided by")
        self.approver.editingFinished.connect(self._approver_changed)

        def button(text: str, handler: Any, tip: str = "") -> QPushButton:
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(handler)
            return b

        self.same_button = button(
            "&Same for the Other Voices Here",
            self.fill_same_place,
            "Copy the selected row's pronunciation to the other voices that sing the same word "
            "at the same place (nothing else is changed)",
        )
        self.check_button = button(
            "&Check with the Engine",
            self.check,
            "Ask the pronunciation engine whether it accepts these pronunciations; nothing is rendered",
        )
        actions = [
            self.same_button,
            button("Clear Selected", self.clear_selected),
            self.check_button,
        ]
        files = [
            button("&Load Pronunciations…", self.load_file),
            button("&Save Pronunciations…", self.save_file),
        ]
        top = QHBoxLayout()
        top.addStretch(1)
        top.addWidget(QLabel("Decided by:"))
        top.addWidget(self.approver)
        row1, row2 = QHBoxLayout(), QHBoxLayout()
        for b in actions:
            row1.addWidget(b)
        row1.addStretch(1)
        for b in files:
            row2.addWidget(b)
        row2.addStretch(1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        assert ok is not None
        ok.setText("Done")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.summary)
        layout.addWidget(intro)
        layout.addWidget(self.notation)
        layout.addLayout(top)
        layout.addWidget(self.table, 1)
        layout.addLayout(row1)
        layout.addLayout(row2)
        layout.addWidget(buttons)
        self.model.dataChanged.connect(lambda *_: self._update_summary())
        controller.pronunciation_checked.connect(self._checked)
        self._update_summary()
        self._show_notation()

    # --- helpers --------------------------------------------------------------------------------

    def _selected(self) -> list[int]:
        selection = self.table.selectionModel()
        assert selection is not None
        return sorted({i.row() for i in selection.selectedRows()})

    def _approver_changed(self) -> None:
        name = self.approver.text().strip()
        if name:
            self.state.approver = name

    def _show_notation(self) -> None:
        rows = self._selected()
        if rows:
            self.notation.setText("Notation: " + self.state.rows[rows[0]].notation)
        else:
            engines = sorted({r.notation for r in self.state.rows if r.supported})
            self.notation.setText("Notation: " + "; ".join(engines) if engines else "")

    def _update_summary(self) -> None:
        state = self.state
        text = (
            f"{state.decided} of {counted(len(state.rows), 'place')} decided; "
            f"{state.undecided} still {agree(state.undecided, 'needs', 'need')} a pronunciation"
        )
        if state.invalid:
            text += f"; {state.invalid} cannot be used as written"
        self.summary.setText(text + ".")

    def _touched(self, rows: list[int]) -> None:
        self.model.changed_rows(rows)
        self._update_summary()

    # --- actions --------------------------------------------------------------------------------

    def fill_same_place(self) -> int:
        rows = self._selected()
        if len(rows) != 1:
            return 0
        changed = self.state.fill_same_place(rows[0])
        self.model.changed_all()
        self._update_summary()
        return changed

    def clear_selected(self) -> None:
        rows = self._selected()
        self.state.clear(rows)
        self._touched(rows)

    def check(self) -> bool:
        self._approver_changed()
        started = self._controller.start_pronunciation_check()
        if not started:
            reasons = self._controller.blockers_for_check()
            self._prompts.warn(
                self,
                "Cannot check yet",
                "\n".join(reasons) if reasons else "A check is already running.",
            )
        else:
            self.summary.setText("Asking the pronunciation engine…")
            self.check_button.setEnabled(False)
        return started

    def _checked(self, outcome: object) -> None:
        self.check_button.setEnabled(True)
        self.model.changed_all()
        self._update_summary()
        if isinstance(outcome, PipelineError):
            explanation = explain(outcome)
            self._prompts.warn(self, explanation.title, explanation.summary)
        else:
            self._prompts.inform(
                self,
                "The engine accepts these pronunciations",
                "Nothing was rendered. Press Done, then Generate.",
            )

    def load_file(self) -> None:
        path = self._prompts.choose_file(self, "Load pronunciations", "", JSON_FILTER)
        if not path:
            return
        try:
            applied, ignored = self.state.load_file(Path(path))
        except PipelineError as error:
            self._prompts.warn(self, "These pronunciations cannot be used", error.message)
            return
        self.model.changed_all()
        self._update_summary()
        note = f"{counted(applied, 'pronunciation')} applied."
        if ignored:
            note += (
                f" {ignored} did not match any place listed here (another voice, place, word or "
                f"pronunciation engine) and {agree(ignored, 'was', 'were')} ignored."
            )
        self._prompts.inform(self, "Pronunciations loaded", note)

    def save_file(self) -> None:
        path = self._prompts.save_file(
            self, "Save pronunciations", "pronunciations.json", JSON_FILTER
        )
        if not path:
            return
        self._approver_changed()
        Path(path).write_text(json.dumps(self.state.document(), indent=2) + "\n", encoding="utf-8")

    def reject(self) -> None:
        for row, (text, error, note) in zip(self.state.rows, self._saved, strict=False):
            row.text, row.error, row.note = (
                text,
                error,
                note,
            )  # Cancel leaves the decisions as they were
        super().reject()


__all__ = ["COLUMNS", "TEXT_COLUMN", "PronunciationDialog", "PronunciationTableModel"]
