"""Typed failures of the rendering backend. ``code`` is stable; ``details`` carries diagnostics."""

from collections.abc import Mapping
from typing import Any


class RenderError(RuntimeError):
    """Base of every rendering failure. Nothing was published when one of these is raised."""

    def __init__(self, code: str, message: str, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.details: dict[str, Any] = dict(details or {})


class RenderConfigurationError(RenderError):
    """The environment cannot render: host, native library, singers directory, unresolved singer,
    phonemizer or renderer, unwritable runtime."""


class ProjectValidationError(RenderError):
    """The plan or the project built from it is not renderable (not ready, unwritable as USTX,
    rejected by the host as malformed)."""


class SynthesisError(RenderError):
    """The host ran but synthesis failed (render errors, crash, no result)."""


class RenderCancelledError(RenderError):
    """The user cancelled; the owned process tree was ended and the staging directory removed."""


class RenderTimeoutError(RenderError):
    """The render exceeded its time limit (BLT's, or one of the host's own)."""


class PronunciationError(RenderError):
    """A word has no pronunciation, or a pronunciation a person gave cannot be used. Nothing was
    rendered and nothing was guessed. ``PRONUNCIATION_UNKNOWN``: ``details['unknown_words']`` names
    each word with its voice and place in the score. ``PRONUNCIATION_INVALID``:
    ``details['invalid_hints']`` names each given pronunciation the engine refused."""


class OutputValidationError(RenderError):
    """The host reported success but its output is not acceptable; nothing was published."""
