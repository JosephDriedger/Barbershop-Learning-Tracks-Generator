r"""The Microsoft Visual C++ runtime BLT needs but does not ship.

Qt, NumPy, Python and the native resampler are built with Microsoft's compiler and need its runtime
DLLs (VCRUNTIME140, MSVCP140...). Microsoft only lets licensed Visual Studio users pass those files
on, so BLT does not include them: the installer checks for Microsoft's own "Visual C++
Redistributable" and helps the user install it, and the program checks again before it renders (a
missing runtime otherwise shows up as an unexplained "DLL load failed").

The runtime registers itself under HKLM\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64
(Microsoft's documented detection method); 14.x runtimes are binary compatible and the newest wins.
"""

import sys
from dataclasses import dataclass

# The oldest runtime the shipped binaries accept: the Visual C++ files inside the PySide6 6.11.2
# wheels (14.44.35211) are the newest of the ones BLT's binaries were built against.
REQUIRED = (14, 44, 35211)
DOWNLOAD_PAGE = "https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist"
DOWNLOAD_URL = "https://aka.ms/vc14/vc_redist.x64.exe"
_KEY = r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"


@dataclass(frozen=True, slots=True)
class RuntimeStatus:
    installed: tuple[int, int, int] | None  # (major, minor, build) of the newest, if any

    @property
    def ok(self) -> bool:
        return self.installed is not None and self.installed >= REQUIRED

    @property
    def text(self) -> str:
        want = "{}.{}.{}".format(*REQUIRED)
        if self.installed is None:
            return f"not installed (needs {want} or newer)"
        have = "{}.{}.{}".format(*self.installed)
        return f"{have} ok" if self.ok else f"{have} is too old (needs {want} or newer)"


def runtime_status() -> RuntimeStatus:
    """The installed Visual C++ runtime (always "ok" off Windows, where it does not apply)."""
    if sys.platform == "win32":
        return _windows_runtime_status()
    else:
        return RuntimeStatus(REQUIRED)


if sys.platform == "win32":

    def _windows_runtime_status() -> RuntimeStatus:
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, _KEY, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY
            ) as key:
                if winreg.QueryValueEx(key, "Installed")[0] != 1:
                    return RuntimeStatus(None)
                parts = tuple(
                    int(winreg.QueryValueEx(key, name)[0]) for name in ("Major", "Minor", "Bld")
                )
        except OSError:
            return RuntimeStatus(None)
        return RuntimeStatus((parts[0], parts[1], parts[2]))
