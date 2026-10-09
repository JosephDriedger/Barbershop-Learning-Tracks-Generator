"""Identify a process by (pid, start time), so a recycled pid is never mistaken for its predecessor.

A staging directory records its owner's pid *and* start time. "Is the owner alive?" then means a
process with that pid exists and started at that moment; a different process that merely reuses the
pid has another start time and the directory is stale.
"""

import sys
from pathlib import Path

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.c_void_p] * 4)]
    _kernel32.GetProcessTimes.restype = wintypes.BOOL
    _kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    _kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _STILL_ACTIVE = 259

    def process_start_time(pid: int) -> int | None:
        """The process creation time (100 ns ticks since 1601) or ``None`` if it is not running."""
        handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return None
        try:
            code = wintypes.DWORD()
            if not _kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return None
            if code.value != _STILL_ACTIVE:
                return None
            created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
            ok = _kernel32.GetProcessTimes(
                handle,
                ctypes.byref(created),
                ctypes.byref(exited),
                ctypes.byref(kernel),
                ctypes.byref(user),
            )
            if not ok:
                return None
            return (created.dwHighDateTime << 32) | created.dwLowDateTime
        finally:
            _kernel32.CloseHandle(handle)

else:

    def process_start_time(pid: int) -> int | None:
        stat = Path(f"/proc/{pid}/stat")
        try:
            fields = stat.read_text(encoding="utf-8").rsplit(")", 1)[1].split()
            return int(fields[19])  # starttime, in clock ticks since boot
        except (OSError, IndexError, ValueError):
            return None


def is_same_process(pid: int, start_time: int | None) -> bool:
    """True when ``pid`` is running and (if a start time was recorded) started at that moment."""
    current = process_start_time(pid)
    if current is None:
        return False
    return start_time is None or current == start_time
