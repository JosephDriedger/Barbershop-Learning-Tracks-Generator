"""GUI entry point."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from barbershop_tracks import __version__
from barbershop_tracks.ui.main_window import TITLE, MainWindow
from barbershop_tracks.ui.preferences import APPLICATION, ORGANIZATION
from barbershop_tracks.ui.style import apply_style


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="barbershop-tracks-gui")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("score", nargs="?", help="a MusicXML score to open at start")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="show the window, then exit immediately (used by CI)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    app = QApplication(sys.argv[:1])
    app.setOrganizationName(ORGANIZATION)
    app.setApplicationName(APPLICATION)
    app.setApplicationDisplayName(TITLE)
    apply_style(app)
    window = MainWindow()
    window.show()
    if args.score:
        window.open_score(Path(args.score))
    if args.smoke_test:
        QTimer.singleShot(0, app.quit)
    code = app.exec()
    window.controller.shutdown()
    return code
