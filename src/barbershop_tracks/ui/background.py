"""Run work off the GUI thread and bring results back onto it.

Results and events cross threads through signals of a :class:`Dispatcher` that lives in the GUI
thread, so every callback runs there (queued connection). Nothing in this module touches a widget;
callers pass plain callables that are invoked on the GUI thread.
"""

import itertools
import threading
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


class Dispatcher(QObject):
    """Created in (and delivering to) the thread that owns the application's widgets."""

    _outcome = Signal(int, bool, object)
    _event = Signal(int, object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._callbacks: dict[
            int, tuple[Callable[[Any], None], Callable[[BaseException], None]]
        ] = {}
        self._events: dict[int, Callable[[dict[str, Any]], None]] = {}
        self._ids = itertools.count(1)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(4)
        self._outcome.connect(self._deliver_outcome)
        self._event.connect(self._deliver_event)
        self.gui_thread = threading.current_thread()

    @Slot(int, bool, object)
    def _deliver_outcome(self, task: int, ok: bool, value: object) -> None:
        on_done, on_failed = self._callbacks.pop(task)
        self._events.pop(task, None)
        if ok:
            on_done(value)
        else:
            assert isinstance(value, BaseException)
            on_failed(value)

    @Slot(int, object)
    def _deliver_event(self, task: int, event: object) -> None:
        handler = self._events.get(task)
        if handler is not None and isinstance(event, dict):
            handler(event)

    def submit(
        self,
        work: Callable[[Callable[[dict[str, Any]], None]], Any],
        on_done: Callable[[Any], None],
        on_failed: Callable[[BaseException], None],
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> int:
        """Run ``work(emit)`` on a pool thread; ``emit(event)`` reaches ``on_event`` on the GUI."""
        task = next(self._ids)
        self._callbacks[task] = (on_done, on_failed)
        if on_event is not None:
            self._events[task] = on_event
        dispatcher = self

        class Job(QRunnable):
            def run(self) -> None:
                def emit(event: dict[str, Any]) -> None:
                    dispatcher._event.emit(task, event)

                try:
                    value = work(emit)
                except BaseException as error:
                    dispatcher._outcome.emit(task, False, error)
                else:
                    dispatcher._outcome.emit(task, True, value)

        job = Job()
        job.setAutoDelete(True)
        self._pool.start(job)
        return task

    def wait(self, milliseconds: int = 10_000) -> bool:
        return self._pool.waitForDone(milliseconds)
