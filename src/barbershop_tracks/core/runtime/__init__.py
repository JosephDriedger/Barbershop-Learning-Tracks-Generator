"""Where things live at run time: read-only binaries, user data, render staging and outputs."""

from barbershop_tracks.core.runtime.layout import RuntimeLayout, default_layout
from barbershop_tracks.core.runtime.staging import (
    STAGING_PREFIX,
    StagingArea,
    StagingError,
    StagingMarker,
    find_stale,
    publish,
    remove_staging,
)

__all__ = [
    "STAGING_PREFIX",
    "RuntimeLayout",
    "StagingArea",
    "StagingError",
    "StagingMarker",
    "default_layout",
    "find_stale",
    "publish",
    "remove_staging",
]
