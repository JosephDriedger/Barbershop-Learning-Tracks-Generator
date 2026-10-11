"""One error type for the whole generation pipeline, with a category the CLI and GUI can show.

Underlying modules keep their own typed errors (readiness findings, ``SynthesisPlanError``,
``RenderError``, ``MixError``); the coordinator translates each into a :class:`PipelineError` so a
caller handles one thing. Nothing is swallowed: the original is chained as ``__cause__``.
"""

from collections.abc import Mapping
from enum import Enum
from typing import Any


class ErrorCategory(Enum):
    SOURCE = "source"  # the score or the voice mapping cannot be generated from
    REVIEW = "review"  # lyrics need an explicit human decision first
    CONFIGURATION = "configuration"  # singers, host, FFmpeg, output location, options
    SYNTHESIS = "synthesis"  # the render host failed
    AUDIO = "audio"  # stems or mixes did not validate; mixing or encoding failed
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class PipelineError(RuntimeError):
    def __init__(
        self,
        category: ErrorCategory,
        code: str,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.category = category
        self.code = code
        self.message = message
        self.details: dict[str, Any] = dict(details or {})
