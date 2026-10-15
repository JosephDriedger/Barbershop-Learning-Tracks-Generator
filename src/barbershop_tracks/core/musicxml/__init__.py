"""MusicXML loading and (M3b1) structural parsing. No lyrics, ties, tempo or repeats yet."""

from barbershop_tracks.core.musicxml.convert import (
    Conversion,
    OpenedScore,
    needs_recognition,
    opened_score,
)
from barbershop_tracks.core.musicxml.limits import DEFAULT_LIMITS, LoaderLimits
from barbershop_tracks.core.musicxml.parser import ParseResult, parse_musicxml, parse_score
from barbershop_tracks.core.musicxml.source import (
    MusicXmlSource,
    SourceKind,
    load_musicxml_source,
)

__all__ = [
    "DEFAULT_LIMITS",
    "Conversion",
    "LoaderLimits",
    "MusicXmlSource",
    "OpenedScore",
    "ParseResult",
    "SourceKind",
    "load_musicxml_source",
    "needs_recognition",
    "opened_score",
    "parse_musicxml",
    "parse_score",
]
