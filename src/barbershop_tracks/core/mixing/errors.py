"""Typed failures of the mixer. ``code`` is stable; ``details`` carries diagnostics.

Nothing is published when one of these is raised.
"""

from collections.abc import Mapping
from typing import Any


class MixError(RuntimeError):
    def __init__(self, code: str, message: str, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.details: dict[str, Any] = dict(details or {})


class MixConfigurationError(MixError):
    """Invalid gain profile or mix set, missing/unusable FFmpeg, unusable destination."""


class MixInputError(MixError):
    """A stem is missing, malformed, or not the supported format."""


class MixDurationError(MixError):
    """A stem sounds past the performed-score duration beyond what the tail policy allows."""


class MixClippingError(MixError):
    """A mix would exceed full scale; the mixer never clips silently."""


class MixEncodingError(MixError):
    """MP3 encoding failed or its output did not validate."""


class MixOutputError(MixError):
    """A produced file failed validation before publication."""


class MixCancelledError(MixError):
    """Cancelled; staging was removed and nothing was published."""
