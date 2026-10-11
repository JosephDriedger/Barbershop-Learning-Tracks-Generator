"""Shared helpers for the GUI tests."""

from typing import Any

from PySide6.QtWidgets import QWidget

from barbershop_tracks.ui.prompts import Prompts


class FakePrompts(Prompts):
    def __init__(self) -> None:
        self.answers: dict[str, Any] = {}
        self.confirmations: list[str] = []
        self.warnings: list[str] = []
        self.informed: list[str] = []
        self.confirm_answer = True

    def open_score(self, parent: QWidget, start: str) -> str:
        return str(self.answers.get("score", ""))

    def choose_folder(self, parent: QWidget, title: str, start: str) -> str:
        return str(self.answers.get(title, self.answers.get("folder", "")))

    def choose_file(self, parent: QWidget, title: str, start: str, file_filter: str) -> str:
        return str(self.answers.get("file", ""))

    def confirm(self, parent: QWidget, title: str, text: str, accept: str = "Continue") -> bool:
        self.confirmations.append(title)
        return self.confirm_answer

    def warn(self, parent: QWidget, title: str, text: str) -> None:
        self.warnings.append(text)

    def inform(self, parent: QWidget, title: str, text: str) -> None:
        self.informed.append(text)
