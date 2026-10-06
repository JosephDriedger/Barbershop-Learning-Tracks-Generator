"""MusicXML loading and (M3b1) structural parsing. No lyrics, ties, tempo or repeats yet."""

from barbershop_tracks.core.musicxml.limits import DEFAULT_LIMITS, LoaderLimits
from barbershop_tracks.core.musicxml.parser import ParseResult, parse_musicxml, parse_score
from barbershop_tracks.core.musicxml.source import (
    MusicXmlSource,
    SourceKind,
    load_musicxml_source,
)

__all__ = [
    "DEFAULT_LIMITS",
    "LoaderLimits",
    "MusicXmlSource",
    "ParseResult",
    "SourceKind",
    "load_musicxml_source",
    "parse_musicxml",
    "parse_score",
]
