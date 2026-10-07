"""The quartet MIDI handoff package: manifest, naming, verification and transactional writing.

Pure construction lives in ``package``; ``writer`` is the only module that touches the filesystem.
"""

from barbershop_tracks.core.handoff.errors import HandoffError
from barbershop_tracks.core.handoff.manifest import (
    LYRICS_STATUS,
    PACKAGE_TYPE,
    SCHEMA,
    SUPPORTED_VERSIONS,
)
from barbershop_tracks.core.handoff.names import (
    INSTRUCTIONS_NAME,
    MANIFEST_NAME,
    midi_filename,
    package_dirname,
    sanitize_name,
)
from barbershop_tracks.core.handoff.ownership import is_link_or_reparse, owned_files
from barbershop_tracks.core.handoff.package import (
    Preparation,
    PreparedHandoff,
    prepare_handoff,
    verify_package_files,
)
from barbershop_tracks.core.handoff.writer import WriteResult, write_package

__all__ = [
    "INSTRUCTIONS_NAME",
    "LYRICS_STATUS",
    "MANIFEST_NAME",
    "PACKAGE_TYPE",
    "SCHEMA",
    "SUPPORTED_VERSIONS",
    "HandoffError",
    "Preparation",
    "PreparedHandoff",
    "WriteResult",
    "is_link_or_reparse",
    "midi_filename",
    "owned_files",
    "package_dirname",
    "prepare_handoff",
    "sanitize_name",
    "verify_package_files",
    "write_package",
]
