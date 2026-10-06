"""Resource limits for loading score files, and the helpers that enforce them."""

from dataclasses import dataclass
from pathlib import Path
from typing import IO

from barbershop_tracks.core.errors import ScoreResourceLimitError

MIB = 1024 * 1024
_CHUNK = 64 * 1024


@dataclass(frozen=True, slots=True, kw_only=True)
class LoaderLimits:
    """Defensive limits for MusicXML loading (binary units).

    ``max_score_bytes`` applies to a plain ``.musicxml``/``.xml`` file and to the score
    inside an ``.mxl`` archive, so uncompressed input cannot bypass the protection.
    ``max_total_bytes`` caps all relevant decompressed content in one archive (container
    plus score). ``max_compression_ratio`` is decompressed size divided by compressed size;
    exactly the limit is allowed, anything above is rejected.
    """

    max_score_bytes: int = 50 * MIB
    max_total_bytes: int = 50 * MIB
    max_container_bytes: int = 1 * MIB
    max_compression_ratio: int = 100
    max_archive_entries: int = 1000

    def __post_init__(self) -> None:
        for name in (
            "max_score_bytes",
            "max_total_bytes",
            "max_container_bytes",
            "max_compression_ratio",
            "max_archive_entries",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_LIMITS = LoaderLimits()


def describe_size(size: int) -> str:
    """Human-readable binary size, e.g. ``50 MiB`` or ``1000 bytes``."""
    if size >= MIB and size % MIB == 0:
        return f"{size // MIB} MiB"
    return f"{size} bytes"


def exceeds_ratio(decompressed: int, compressed: int, max_ratio: int) -> bool:
    """True if ``decompressed / compressed`` is above ``max_ratio`` (integer arithmetic).

    Content that is non-empty but claims zero compressed bytes always exceeds the limit.
    """
    return decompressed > max_ratio * compressed


def read_limited(stream: IO[bytes], max_bytes: int, *, what: str, path: Path | None) -> bytes:
    """Read ``stream`` fully, refusing to read more than ``max_bytes`` bytes.

    Counts the bytes actually produced, so the limit holds even if container metadata
    understates the real size. Reading stops as soon as the limit is exceeded.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = stream.read(min(_CHUNK, max_bytes + 1 - total))
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > max_bytes:
            raise ScoreResourceLimitError(
                f"{what} is larger than the limit of {describe_size(max_bytes)}", path=path
            )
        chunks.append(chunk)
