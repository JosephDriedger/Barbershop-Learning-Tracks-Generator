"""The questions the window asks the user, behind one object so tests can answer them."""

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

SCORE_FILTER = (
    "Scores (*.musicxml *.xml *.mxl *.mscz *.mscx *.pdf);;"
    "MusicXML (*.musicxml *.xml *.mxl);;MuseScore projects (*.mscz *.mscx);;"
    "PDF or image of music (*.pdf *.png *.jpg *.jpeg);;All files (*)"
)


class Prompts:
    def open_score(self, parent: QWidget, start: str) -> str:
        path, _ = QFileDialog.getOpenFileName(parent, "Choose a score", start, SCORE_FILTER)
        return path

    def choose_folder(self, parent: QWidget, title: str, start: str) -> str:
        return QFileDialog.getExistingDirectory(parent, title, start)

    def choose_file(self, parent: QWidget, title: str, start: str, file_filter: str) -> str:
        path, _ = QFileDialog.getOpenFileName(parent, title, start, file_filter)
        return path

    def save_file(self, parent: QWidget, title: str, start: str, file_filter: str) -> str:
        path, _ = QFileDialog.getSaveFileName(parent, title, start, file_filter)
        return path

    def confirm(self, parent: QWidget, title: str, text: str, accept: str = "Continue") -> bool:
        box = QMessageBox(QMessageBox.Icon.Question, title, text, parent=parent)
        yes = box.addButton(accept, QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() is yes

    def inform(self, parent: QWidget, title: str, text: str) -> None:
        QMessageBox.information(parent, title, text)

    def warn(self, parent: QWidget, title: str, text: str) -> None:
        QMessageBox.warning(parent, title, text)


Opener = Callable[[Path], bool]


def open_in_explorer(path: Path) -> bool:
    """Show a folder in the system file manager."""
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
