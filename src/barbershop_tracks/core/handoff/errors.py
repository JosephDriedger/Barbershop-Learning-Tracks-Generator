"""Package and filesystem failures. ``code`` is stable and meant for scripts; exit status is 2."""


class HandoffError(RuntimeError):
    """The package could not be named, verified or written safely."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
