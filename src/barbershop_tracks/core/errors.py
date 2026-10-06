"""Typed application exceptions.

Exceptions describe input that cannot be *safely loaded*. Musical problems in a score that
loads fine are reported later as ``ValidationIssue`` objects, never as exceptions.

Messages are written for end users (CLI/UI) and kept short: they never embed XML fragments
or binary data. The original low-level exception, when there is one, is chained as
``__cause__`` for developers.
"""

from pathlib import Path


class BarbershopTracksError(Exception):
    """Base class for expected, user-reportable application errors."""


class ScoreLoadError(BarbershopTracksError):
    """A score file could not be safely loaded."""

    def __init__(self, message: str, *, path: Path | None = None) -> None:
        super().__init__(message)
        self.path = path


class ScoreFileError(ScoreLoadError):
    """The path is missing, not a file, unreadable, or has an unsupported extension."""


class ScoreResourceLimitError(ScoreLoadError):
    """A size or compression-ratio limit was exceeded."""


class ScoreXmlError(ScoreLoadError):
    """The XML is empty or not well-formed."""


class ScoreXmlSecurityError(ScoreXmlError):
    """The XML uses a construct that is forbidden for safety (entities, external resources)."""


class ScoreArchiveError(ScoreLoadError):
    """A compressed ``.mxl`` archive is invalid, unsafe, or does not identify a score."""


class UnsupportedScoreFormatError(ScoreLoadError):
    """The file loads but is not a format this application supports (e.g. score-timewise)."""
