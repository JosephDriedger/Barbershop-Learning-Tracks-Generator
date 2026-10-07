"""Typed MIDI export failures. Raised before any byte is produced; nothing is ever rounded."""


class MidiExportError(ValueError):
    """The performed score cannot be written as the quartet MIDI exactly. ``code`` is stable."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class MidiVerificationError(ValueError):
    """Encoded bytes decode to something other than the intended export (a defect, not input)."""
