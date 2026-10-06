"""Placeholder main window; exists only to prove the GUI entry point works."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow, QWidget


class MainWindow(QMainWindow):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("BarbershopLearningTracks")
        label = QLabel("BarbershopLearningTracks (M1 scaffold)")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCentralWidget(label)
        self.resize(480, 240)
