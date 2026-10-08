"""The OpenUtau 0.1.565 adapter: a ready synthesis plan to a USTX 0.7 project."""

from barbershop_tracks.core.synthesis.openutau.target import (
    TARGET_0_1_565,
    TARGETS,
    OpenUtauTarget,
    UstxError,
    read_ustx_version,
    require_ustx_version,
    target_for,
)
from barbershop_tracks.core.synthesis.openutau.ustx import (
    MAX_TEMPO_DRIFT_SECONDS,
    MIN_NOTE_TICKS,
    ContinuationToken,
    TempoRecord,
    UstxDocument,
    UstxWarning,
    validate_lyric_text,
    write_ustx,
)

__all__ = [
    "MAX_TEMPO_DRIFT_SECONDS",
    "MIN_NOTE_TICKS",
    "TARGETS",
    "TARGET_0_1_565",
    "ContinuationToken",
    "OpenUtauTarget",
    "TempoRecord",
    "UstxDocument",
    "UstxError",
    "UstxWarning",
    "read_ustx_version",
    "require_ustx_version",
    "target_for",
    "validate_lyric_text",
    "write_ustx",
]
