"""A cross-process exclusive lock on a file, polled so waiting can be cancelled.

OpenUtau's render cache (``Cache/wdl-<hash>.wav`` beside the host) is shared by every host run
from the same runtime copy, and two hosts rendering the same phrase at once collide on one cache
file ("being used by another process"). Hosts therefore take this lock for the duration of their
run: concurrent generations queue for the host stage only (mixing and everything else stay
concurrent), and the OS releases the lock if the holder dies.
"""

import contextlib
import sys
import time
from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from typing import IO

if sys.platform == "win32":
    import msvcrt

    def _try_lock(handle: IO[bytes]) -> bool:
        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    def _unlock(handle: IO[bytes]) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _try_lock(handle: IO[bytes]) -> bool:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        return True

    def _unlock(handle: IO[bytes]) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class LockWaitAbortedError(Exception):
    """``should_stop`` returned true while waiting for the lock."""


class FileLock:
    def __init__(self, path: Path, *, poll_seconds: float = 0.1) -> None:
        self.path = path
        self.poll_seconds = poll_seconds
        self._handle: IO[bytes] | None = None

    def acquire(
        self,
        *,
        should_stop: Callable[[], bool] = lambda: False,
        on_wait: Callable[[], None] | None = None,
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # unbuffered: a write that the OS refuses must not leave a byte behind that close() retries
        handle = self.path.open("a+b", buffering=0)
        if self.path.stat().st_size == 0:
            # a concurrent opener may have seen the empty file too and locked the byte already
            # (Windows locks are mandatory); locking that byte below works either way
            with contextlib.suppress(OSError):
                handle.write(b"\0")
        waited = False
        while not _try_lock(handle):
            if should_stop():
                handle.close()
                raise LockWaitAbortedError
            if not waited and on_wait is not None:
                on_wait()
            waited = True
            time.sleep(self.poll_seconds)
        self._handle = handle

    def release(self) -> None:
        if self._handle is not None:
            try:
                _unlock(self._handle)
            finally:
                self._handle.close()
                self._handle = None

    def __enter__(self) -> "FileLock":
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()
