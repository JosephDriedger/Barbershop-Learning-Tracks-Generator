"""Who has the melody, section by section, and the bars a person marks to say otherwise.

BLT reads the melody from the words: the Lead has it, unless the Lead holds an "oo" or rests while
one other part sings the words. The Full Quartet makes the part with the melody louder. The dialog
shows what BLT found, bar by bar, and lets a person mark bars where the melody is somewhere else
(a mark always wins). Nothing is changed until OK; Cancel leaves the marks as they were.
"""

from collections.abc import Sequence

from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from barbershop_tracks.core.melody import (
    MelodyError,
    MelodyMark,
    MelodySection,
    beats_in_bar,
    melody_of,
)
from barbershop_tracks.core.synthesis import VOICE_ORDER, SynthesisPlan
from barbershop_tracks.models import VoiceRole

INTRO = (
    "The Full Quartet makes the part that has the melody louder. BLT finds it from the words: "
    "the Lead has the melody, unless the Lead holds an “oo” or rests while one other part sings "
    "the words. If that is wrong anywhere, mark the bars and beats below; what you mark always "
    "wins."
)


def mark_text(mark: MelodyMark) -> str:
    if mark.first_beat == 1 and mark.last_beat is None:
        bars = (
            f"bar {mark.first_bar}"
            if mark.first_bar == mark.last_bar
            else f"bars {mark.first_bar} to {mark.last_bar}"
        )
    else:
        begin = f"bar {mark.first_bar} beat {mark.first_beat}"
        if mark.last_beat is None:
            end = f"the end of bar {mark.last_bar}"
        else:
            end = f"bar {mark.last_bar} beat {mark.last_beat}"
        bars = begin if begin == end else f"{begin} to {end}"
    return f"{mark.role.display_name}: {bars}"


class MelodyDialog(QDialog):
    def __init__(
        self,
        plan: SynthesisPlan,
        marks: Sequence[MelodyMark],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Who Has the Melody")
        self.plan = plan
        self._marks: list[MelodyMark] = list(marks)
        numbers = sorted({m.number for m in plan.measures})
        self.lowest, self.highest = (numbers[0], numbers[-1]) if numbers else (1, 1)

        intro = QLabel(INTRO)
        intro.setWordWrap(True)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Where", "Has the melody", "How BLT knows"])
        self.table.setAccessibleName("Who has the melody in each stretch of the song")
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        assert header is not None
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.problem = QLabel("")
        self.problem.setObjectName("error")
        self.problem.setWordWrap(True)

        self.voice = QComboBox()
        for role in VOICE_ORDER:
            self.voice.addItem(role.display_name, role)
        self.voice.setAccessibleName("Part that has the melody")
        self.first = QSpinBox()
        self.last = QSpinBox()
        for box, name in ((self.first, "First bar"), (self.last, "Last bar")):
            box.setRange(self.lowest, self.highest)
            box.setAccessibleName(name)
        self.last.setValue(self.lowest)
        self.first_beat = QSpinBox()
        self.first_beat.setAccessibleName("Beat of the first bar to start on")
        self.last_beat = QSpinBox()  # 0 is the end of the bar
        self.last_beat.setSpecialValueText("end of bar")
        self.last_beat.setAccessibleName("Last beat of the last bar")
        self.first.valueChanged.connect(self._set_beat_limits)
        self.last.valueChanged.connect(self._set_beat_limits)
        self._set_beat_limits()
        self.add = QPushButton("&Mark This")
        self.add.clicked.connect(self._add_clicked)
        add_row = QHBoxLayout()
        for widget in (
            QLabel("Part:"),
            self.voice,
            QLabel("From bar"),
            self.first,
            QLabel("beat"),
            self.first_beat,
            QLabel("to bar"),
            self.last,
            QLabel("beat"),
            self.last_beat,
            self.add,
        ):
            add_row.addWidget(widget)
        add_row.addStretch(1)

        self.marks_list = QListWidget()
        self.marks_list.setAccessibleName("Stretches you marked")
        self.marks_list.setMaximumHeight(110)
        self.remove = QPushButton("&Remove Mark")
        self.remove.clicked.connect(self._remove_clicked)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.table, 1)
        layout.addWidget(QLabel("Your marks (they win over the words):"))
        layout.addWidget(self.marks_list)
        layout.addWidget(self.remove)
        layout.addLayout(add_row)
        layout.addWidget(self.problem)
        layout.addWidget(buttons)
        self.resize(720, 560)
        self.refresh()

    # --- state -----------------------------------------------------------------------------

    def marks(self) -> tuple[MelodyMark, ...]:
        return tuple(self._marks)

    def sections(self) -> tuple[MelodySection, ...]:
        try:
            return melody_of(self.plan, self._marks)
        except MelodyError as error:
            self.problem.setText(error.message)
            return ()

    def add_mark(
        self,
        role: VoiceRole,
        first: int,
        last: int,
        first_beat: int = 1,
        last_beat: int | None = None,
    ) -> bool:
        """Mark bars (and beats); False (and the reason shown) if they are not in the score."""
        try:
            mark = MelodyMark(role, first, last, first_beat, last_beat)
            melody_of(self.plan, [*self._marks, mark])
        except MelodyError as error:
            self.problem.setText(error.message)
            return False
        self._marks.append(mark)
        self.refresh()
        return True

    def remove_mark(self, index: int) -> None:
        if 0 <= index < len(self._marks):
            del self._marks[index]
            self.refresh()

    def _set_beat_limits(self) -> None:
        """A bar has as many beats as its time signature says: that is as far as a beat can go."""
        self.first_beat.setRange(1, beats_in_bar(self.plan, self.first.value()))
        self.last_beat.setRange(0, beats_in_bar(self.plan, self.last.value()))

    def _add_clicked(self) -> None:
        role = self.voice.currentData()
        if isinstance(role, VoiceRole):
            self.add_mark(
                role,
                self.first.value(),
                self.last.value(),
                self.first_beat.value(),
                self.last_beat.value() or None,
            )

    def _remove_clicked(self) -> None:
        self.remove_mark(self.marks_list.currentRow())

    # --- display ---------------------------------------------------------------------------

    def refresh(self) -> None:
        self.problem.setText("")
        sections = self.sections()
        self.table.setRowCount(len(sections))
        for row, section in enumerate(sections):
            if section.marked:
                why = "You marked it"
            elif section.note:
                why = section.note[:1].upper() + section.note[1:]
            else:
                why = "The Lead sings the words (the usual)"
            for column, text in enumerate((section.bars or "—", section.role.display_name, why)):
                self.table.setItem(row, column, QTableWidgetItem(text))
        self.marks_list.clear()
        for mark in self._marks:
            self.marks_list.addItem(mark_text(mark))
        self.remove.setEnabled(bool(self._marks))
