"""Where things live at run time: read-only binaries, user data, render staging and outputs."""

from barbershop_tracks.core.runtime.host_install import (
    HostInstallError,
    HostRuntime,
    ensure_host_runtime,
)
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
    "HostInstallError",
    "HostRuntime",
    "RuntimeLayout",
    "StagingArea",
    "StagingError",
    "StagingMarker",
    "default_layout",
    "ensure_host_runtime",
    "find_stale",
    "publish",
    "remove_staging",
]
