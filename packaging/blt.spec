# PyInstaller spec: one folder holding the windowed app and the console program.
#
#   pyinstaller --noconfirm --distpath research-output/dist --workpath research-output/work packaging/blt.spec
#
# The result (research-output/dist/BLT Music Generator/) is completed by packaging/build.ps1, which
# adds the published render host (host/), the notices and the licence texts, then runs
# packaging/inventory.py: every file must belong to a component listed in the dependency audit.
import os
from pathlib import Path

ROOT = Path(SPECPATH).parent
VERSION_FILE = str(ROOT / "research-output" / "work" / "version_info.txt")
ICON = str(ROOT / "packaging" / "blt.ico")

# Qt parts BLT does not use. Dropping them keeps the package small and, more to the point, keeps
# libraries out of it whose licences were never reviewed. QtNetwork/QtSvg/QtPdf/QtOpenGL/QtQml...
# are not imported by any BLT module; the Windows platform plugin is the only one needed.
DROP_PATTERNS = (
    "opengl32sw", "d3dcompiler", "Qt6Network", "Qt6Svg", "Qt6Pdf", "Qt6OpenGL", "Qt6Qml", "Qt6Quick",
    "Qt6VirtualKeyboard", "Qt6DBus", "Qt6WebEngine", "Qt63D", "Qt6Multimedia", "Qt6Sql", "Qt6Test",
    "Qt6Xml", "Qt6Concurrent", "Qt6PrintSupport", "Qt6Designer", "Qt6Help", "Qt6Positioning",
    "Qt6Sensors", "Qt6Bluetooth", "Qt6Nfc", "Qt6SerialPort", "Qt6WebChannel", "Qt6WebSockets",
    "Qt6Charts", "Qt6DataVisualization", "Qt6Graphs", "Qt6RemoteObjects", "Qt6Scxml", "Qt6StateMachine",
    "Qt6TextToSpeech", "Qt6HttpServer", "Qt6Location", "Qt6Quick3D", "Qt6ShaderTools", "Qt6Labs",
    "Qt6Core5Compat", "Qt6SpatialAudio", "Qt6NetworkAuth", "Qt6Protobuf",
    "qtuiotouchplugin", "qdirect2d", "qminimal", "virtualkeyboard", ".qm", "qnetworklistmanager", "qschannelbackend",
    "qcertonlybackend", "qopensslbackend", "qgenericbearer", "qsvg", "qgif", "qjpeg", "qpdf", "qtiff",
    "qwebp", "qicns", "qwbmp", "qtga", "qmodernwindowsstyle", "qwindowsvistastyle",
)
# qoffscreen.dll is kept so the packaged program can be smoke-tested without a display
KEEP_ALWAYS = ("qwindows.dll", "qico.dll", "qoffscreen.dll")


def wanted(name: str) -> bool:
    base = os.path.basename(name)
    if base in KEEP_ALWAYS:
        return True
    return not any(pattern.lower() in base.lower() for pattern in DROP_PATTERNS)


EXCLUDES = [
    "tkinter", "PySide6.QtNetwork", "PySide6.QtSvg", "PySide6.QtPdf", "PySide6.QtOpenGL",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtWebEngineCore", "PySide6.QtMultimedia",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtXml", "PySide6.QtPrintSupport", "PySide6.QtDBus",
    "ssl", "_ssl", "yaml", "pytest", "mypy", "numpy.testing", "numpy.f2py", "setuptools", "pip",
]

COMMON = dict(pathex=[str(ROOT / "src")], hiddenimports=[], hookspath=[], runtime_hooks=[], excludes=EXCLUDES, noarchive=False)
gui = Analysis([str(ROOT / "packaging" / "entry_gui.py")], **COMMON)
cli = Analysis([str(ROOT / "packaging" / "entry_cli.py")], **COMMON)
MERGE((gui, "gui", "gui"), (cli, "cli", "cli"))
for analysis in (gui, cli):
    analysis.binaries = [b for b in analysis.binaries if wanted(b[0]) or wanted(b[1])]
    analysis.datas = [d for d in analysis.datas if wanted(d[0]) or wanted(d[1])]

gui_pyz, cli_pyz = PYZ(gui.pure), PYZ(cli.pure)
gui_exe = EXE(
    gui_pyz, gui.scripts, [], exclude_binaries=True, name="BLT Music Generator", console=False,
    icon=ICON, version=VERSION_FILE, upx=False, debug=False, bootloader_ignore_signals=False, strip=False,
)
cli_exe = EXE(
    cli_pyz, cli.scripts, [], exclude_binaries=True, name="blt", console=True,
    icon=ICON, version=VERSION_FILE, upx=False, debug=False, bootloader_ignore_signals=False, strip=False,
)
COLLECT(
    gui_exe, gui.binaries, gui.datas, cli_exe, cli.binaries, cli.datas,
    upx=False, strip=False, name="BLT Music Generator",
)
