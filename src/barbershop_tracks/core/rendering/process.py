"""Run one child process so that it, and everything it starts, can be ended together.

On Windows the child is placed in its own job object: terminating the job ends exactly the
processes that job owns (the child and its descendants) and nothing else, whatever their pids are.
Closing the job also kills its members, so an abandoned render cannot outlive BLT. Elsewhere the
child leads its own process group.
"""

import contextlib
import os
import signal
import subprocess
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    _PROCESS_SET_QUOTA = 0x0100
    _PROCESS_TERMINATE = 0x0001

    class _BasicLimits(ctypes.Structure):
        _fields_ = (
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        )

    class _IoCounters(ctypes.Structure):
        _fields_ = tuple((name, ctypes.c_uint64) for name in ("a", "b", "c", "d", "e", "f"))

    class _ExtendedLimits(ctypes.Structure):
        _fields_ = (
            ("BasicLimitInformation", _BasicLimits),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        )

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _k32.CreateJobObjectW.restype = wintypes.HANDLE
    _k32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    _k32.SetInformationJobObject.restype = wintypes.BOOL
    _k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _k32.AssignProcessToJobObject.restype = wintypes.BOOL
    _k32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _k32.TerminateJobObject.restype = wintypes.BOOL
    _k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _k32.CloseHandle.restype = wintypes.BOOL


class OwnedProcess:
    """A started child plus the means to end its whole tree; stdout and stderr are drained."""

    def __init__(
        self,
        command: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        on_stdout_line: Callable[[str], None] | None = None,
    ) -> None:
        self.command = list(command)
        self._job: int | None = None
        self.stdout_lines: list[str] = []
        self.stderr_text = ""
        self._on_stdout_line = on_stdout_line
        flags = 0
        if sys.platform == "win32":
            flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        self.process: subprocess.Popen[bytes] = subprocess.Popen(
            self.command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=None if env is None else dict(env),
            cwd=cwd,
            creationflags=flags,
            start_new_session=sys.platform != "win32",
        )
        self._attach_job()
        self._threads = [
            threading.Thread(target=self._drain_stdout, daemon=True),
            threading.Thread(target=self._drain_stderr, daemon=True),
        ]
        for thread in self._threads:
            thread.start()

    @property
    def pid(self) -> int:
        return self.process.pid

    def _attach_job(self) -> None:
        if sys.platform != "win32":
            return
        job = _k32.CreateJobObjectW(None, None)
        if not job:
            return
        limits = _ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        _k32.SetInformationJobObject(
            job,
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        )
        handle = _k32.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, self.pid)
        if handle:
            assigned = _k32.AssignProcessToJobObject(job, handle)
            _k32.CloseHandle(handle)
            if assigned:
                self._job = int(job)
                return
        _k32.CloseHandle(job)

    def _drain_stdout(self) -> None:
        assert self.process.stdout is not None
        for raw in iter(self.process.stdout.readline, b""):
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            self.stdout_lines.append(line)
            if self._on_stdout_line is not None:
                with contextlib.suppress(Exception):
                    self._on_stdout_line(line)

    def _drain_stderr(self) -> None:
        assert self.process.stderr is not None
        self.stderr_text = self.process.stderr.read().decode("utf-8", errors="replace")

    def poll(self) -> int | None:
        return self.process.poll()

    def terminate_tree(self) -> None:
        """End the child and every descendant it started; safe to call repeatedly."""
        if self._job is not None:
            _k32.TerminateJobObject(self._job, 1)
        elif sys.platform != "win32":
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(os.getpgid(self.pid), signal.SIGKILL)
        with contextlib.suppress(OSError):
            self.process.kill()

    def finish(self, grace: float = 5.0) -> int:
        """Wait for the child, drain its pipes, then release the job (killing any stragglers)."""
        try:
            code = self.process.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            self.terminate_tree()
            code = self.process.wait()
        for thread in self._threads:
            thread.join(timeout=grace)
        self.close()
        return code

    def close(self) -> None:
        """Release the job handle; with kill-on-close this also ends leftover descendants."""
        if self._job is not None:
            _k32.TerminateJobObject(self._job, 1)
            _k32.CloseHandle(self._job)
            self._job = None
