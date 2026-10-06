"""MusicXML loading. M3a covers only safe loading; no musical interpretation yet."""

from barbershop_tracks.core.musicxml.limits import DEFAULT_LIMITS, LoaderLimits
from barbershop_tracks.core.musicxml.source import (
    MusicXmlSource,
    SourceKind,
    load_musicxml_source,
)

__all__ = [
    "DEFAULT_LIMITS",
    "LoaderLimits",
    "MusicXmlSource",
    "SourceKind",
    "load_musicxml_source",
]
