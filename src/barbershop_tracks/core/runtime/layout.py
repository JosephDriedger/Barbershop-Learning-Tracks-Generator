"""The on-disk layout BLT uses. Nothing here creates directories; callers do, on demand.

* ``binaries``: read-only, shipped with the application (render host, native libraries).
* ``runtime``: writable per-version copies of the host binaries (see ``host_install``);
  OpenUtau.Core keeps its cache, prefs and logs beside the executable it runs from.
* ``singers``: user-installed voicebanks; BLT never copies or ships them.
* ``cache``: reproducible render cache (safe to delete).
* ``staging``: per-job scratch directories, a sibling of ``outputs`` so that publication is a
  same-volume rename.
* ``outputs``: completed, validated results.
"""

from dataclasses import dataclass
from pathlib import Path

import platformdirs

APP_NAME = "BarbershopLearningTracks"


@dataclass(frozen=True, slots=True)
class RuntimeLayout:
    binaries: Path
    data: Path
    runtime: Path
    singers: Path
    cache: Path
    staging: Path
    outputs: Path

    @classmethod
    def under(cls, binaries: Path, data: Path, cache: Path | None = None) -> "RuntimeLayout":
        return cls(
            binaries=binaries,
            data=data,
            runtime=data / "runtime",
            singers=data / "singers",
            cache=cache if cache is not None else data / "cache",
            staging=data / "staging",
            outputs=data / "outputs",
        )


def default_layout(binaries: Path) -> RuntimeLayout:
    """Per-user locations from platformdirs; ``binaries`` is wherever the app is installed."""
    return RuntimeLayout.under(
        binaries,
        Path(platformdirs.user_data_dir(APP_NAME, appauthor=False)),
        Path(platformdirs.user_cache_dir(APP_NAME, appauthor=False)),
    )
