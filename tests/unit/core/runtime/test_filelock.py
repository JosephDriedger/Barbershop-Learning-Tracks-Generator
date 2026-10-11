import threading
import time
from pathlib import Path

import pytest

from barbershop_tracks.core.runtime.filelock import FileLock, LockWaitAbortedError


def test_a_second_holder_waits_until_the_first_releases(tmp_path: Path) -> None:
    path = tmp_path / "x.lock"
    first = FileLock(path, poll_seconds=0.01)
    first.acquire()
    order: list[str] = []

    def other() -> None:
        with FileLock(path, poll_seconds=0.01) as lock:
            assert lock is not None
            order.append("second")

    thread = threading.Thread(target=other)
    thread.start()
    time.sleep(0.2)
    assert order == []  # still blocked
    order.append("first-done")
    first.release()
    thread.join(timeout=10)
    assert order == ["first-done", "second"]


def test_waiting_can_be_abandoned_and_reports_that_it_waited(tmp_path: Path) -> None:
    path = tmp_path / "x.lock"
    held = FileLock(path)
    held.acquire()
    waits: list[int] = []
    attempts = {"n": 0}

    def stop() -> bool:
        attempts["n"] += 1
        return attempts["n"] > 3

    with pytest.raises(LockWaitAbortedError):
        FileLock(path, poll_seconds=0.01).acquire(should_stop=stop, on_wait=lambda: waits.append(1))
    assert waits == [1]  # reported once, however long the wait
    held.release()
    with FileLock(path):  # and the lock is free again
        pass


def test_release_is_idempotent_and_the_lock_is_reusable(tmp_path: Path) -> None:
    lock = FileLock(tmp_path / "sub" / "x.lock")
    lock.acquire()
    lock.release()
    lock.release()
    lock.acquire()
    lock.release()
