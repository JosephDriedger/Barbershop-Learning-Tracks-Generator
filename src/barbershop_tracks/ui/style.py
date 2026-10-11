"""One look for the whole application: Fusion style, system palette, a few shared rules.

Colours come from the user's palette (so light and dark Windows themes both work) and sizes from
the font (so display scaling and larger text settings carry through). Nothing has a fixed pixel
size except small icons.
"""

from PySide6.QtWidgets import QApplication

STYLESHEET = """
QGroupBox {
    font-weight: 600;
    border: 1px solid palette(mid);
    border-radius: 6px;
    margin-top: 1.4em;
    padding: 0.6em 0.8em 0.8em 0.8em;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 0.8em;
    padding: 0 0.3em;
}
QPushButton#primary {
    background-color: palette(highlight);
    color: palette(highlighted-text);
    border: none;
    border-radius: 5px;
    padding: 0.6em 2em;
    font-weight: 600;
}
QPushButton#primary:disabled {
    background-color: palette(mid);
    color: palette(dark);
}
QPushButton#primary:focus { border: 2px solid palette(text); }
QLabel#hint { color: palette(dark); }
QLabel#error { color: #b00020; font-weight: 600; }
QLabel#success { font-weight: 600; }
"""


def apply_style(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
