# PyInstaller spec: one folder holding the windowed app and the console program.
#
#   pyinstaller --noconfirm --distpath research-output/dist --workpath research-output/work packaging/blt.spec
#
# (packaging/build.ps1 uses research-output/release/app instead.) The result (the folder 'BLT Music Generator') is completed by packaging/build.ps1, which
# adds the published render host (host/), the notices and the licence texts, then runs
# packaging/inventory.py: every file must belong to a component listed in the dependency audit.
#
# On macOS the same spec builds 'BLT Music Generator.app' (the windowed program as the app's executable, the console
# program 'blt' beside it in Contents/MacOS); packaging/build_macos.py completes it the same way
# (render host in Contents/Helpers/host, notices in Contents/Resources) and audits it.
import os
import re
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
MAC = sys.platform == "darwin"
VERSION_FILE = str(ROOT / "research-output" / "work" / "version_info.txt")
ICON = str(ROOT / "packaging" / ("blt.icns" if MAC else "blt.ico"))
APP_VERSION = re.search(
    r'__version__ = "([^"]+)"', (ROOT / "src" / "barbershop_tracks" / "__init__.py").read_text(encoding="utf-8")
).group(1)

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
# The same on macOS, where Qt's modules are frameworks (QtNetwork, not Qt6Network.dll) and the plugins are
# lib*.dylib. QtCore, QtGui and QtWidgets are not listed: they are the ones the program uses.
if MAC:
    DROP_PATTERNS += tuple(
        "Qt" + name[3:] for name in DROP_PATTERNS if name.startswith("Qt6")
    ) + (
        "qsecuretransportbackend", "cocoaprintersupport", "qtuiotouchplugin", "qgenericbearer",
        "qmacheif", "qmacjp2", "qpdf", "qiconengine", "qsvgicon",
    )
# qoffscreen is kept so the packaged program can be smoke-tested without a display
KEEP_ALWAYS = ("qwindows.dll", "qico.dll", "qoffscreen.dll")
if MAC:
    KEEP_ALWAYS = ("libqcocoa.dylib", "libqico.dylib", "libqoffscreen.dylib")


RUNTIME_FILE = re.compile(r"^(vcruntime|msvcp|concrt|vcomp|vccorlib)\d+(_\d+|_[a-z_]+)?(-[0-9a-f]{32})?\.dll$", re.I)


def wanted(name: str) -> bool:
    base = os.path.basename(name)
    if base in KEEP_ALWAYS:
        return True
    # The Universal C Runtime is part of Windows 10 and later, which the installer requires; PyInstaller
    # copies it from the build machine only for Windows 7/8. Not shipping it also keeps a Microsoft
    # redistributable out of the package (see docs/dependency-audit.md).
    if base.lower().startswith("api-ms-win-") or base.lower() == "ucrtbase.dll":
        return False
    # Microsoft allows only licensed Visual Studio users to pass on the Visual C++ runtime files, so the
    # wheels' copies (Python, Qt, NumPy's renamed one) are not shipped: the installer requires Microsoft's
    # own redistributable (see packaging/installer.iss and docs/m13-compliance.md).
    if RUNTIME_FILE.match(base):
        return False
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
# a version resource is a Windows thing
VERSION_ARGS = {} if MAC else {"version": VERSION_FILE}
gui_exe = EXE(
    gui_pyz, gui.scripts, [], exclude_binaries=True, name="BLT Music Generator", console=False,
    icon=ICON, upx=False, debug=False, bootloader_ignore_signals=False, strip=False, **VERSION_ARGS,
)
cli_exe = EXE(
    cli_pyz, cli.scripts, [], exclude_binaries=True, name="blt", console=True,
    icon=ICON, upx=False, debug=False, bootloader_ignore_signals=False, strip=False, **VERSION_ARGS,
)
collected = COLLECT(
    gui_exe, gui.binaries, gui.datas, cli_exe, cli.binaries, cli.datas,
    upx=False, strip=False, name="BLT Music Generator",
)
if MAC:
    # Unsigned and not notarised: signing needs an Apple Developer account the owner has not decided on
    # (packaging/build_macos.py has the off-by-default signing and notarisation steps).
    app = BUNDLE(
        collected,
        name="BLT Music Generator.app",
        icon=ICON,
        bundle_identifier="io.github.josephdriedger.blt-music-generator",
        version=APP_VERSION,
        info_plist={
            "CFBundleName": "BLT Music Generator",
            "CFBundleDisplayName": "BLT Music Generator",
            "CFBundleShortVersionString": APP_VERSION,
            "CFBundleVersion": APP_VERSION,
            "LSMinimumSystemVersion": "12.0",
            "NSHighResolutionCapable": True,
            "NSHumanReadableCopyright": "Copyright 2026 Joseph Driedger. Apache-2.0; see NOTICES.txt.",
            "LSApplicationCategoryType": "public.app-category.music",
        },
    )
