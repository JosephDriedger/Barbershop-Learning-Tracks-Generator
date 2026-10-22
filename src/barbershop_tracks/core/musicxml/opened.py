"""Parsing a score that was opened, with what its own program can add to the MusicXML.

A MuseScore project exported to MusicXML loses two things BLT needs: how far each underscore line
runs (``lyric_lines.py``) and the tempo MuseScore plays (``playback.py``). When the project is at
hand both are read from it. The order matters: the line lengths change the parsed song, from which
the performance is derived again, so they go first; the playback tempo is then laid on that
performance. Anything that cannot be trusted is left out, and the score is read as MusicXML alone.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from barbershop_tracks.core.musicxml.convert import MUSESCORE_SUFFIXES, OpenedScore
from barbershop_tracks.core.musicxml.lyric_lines import NOT_READ, LyricLines, apply_lyric_lines
from barbershop_tracks.core.musicxml.mscx_lyrics import read_project_lyrics
from barbershop_tracks.core.musicxml.parser import ParseResult
from barbershop_tracks.core.musicxml.playback import PlaybackTempo, follow_playback_tempo


@dataclass(frozen=True, slots=True)
class OpenedReading:
    """What was taken from the score's own program besides its MusicXML."""

    tempo: PlaybackTempo
    lines: LyricLines

    def into(self, conversion: dict[str, object] | None) -> dict[str, object] | None:
        """``conversion`` (as recorded in the package) with what was read from the project."""
        if conversion is None:
            return None
        recorded = dict(conversion)
        if self.tempo.applied or self.tempo.note:
            recorded["playback_tempo"] = self.tempo.as_record()
        if self.lines.applied:
            recorded["lyric_lines"] = self.lines.as_record()
        return recorded

    def notices(self) -> list[tuple[str, str]]:
        """(kind, message) for the person, nothing when there is nothing to say.

        The kind is ``tempo`` (followed), ``tempo_unused`` or ``lines``.
        """
        said: list[tuple[str, str]] = []
        if self.tempo.note:
            said.append(("tempo" if self.tempo.applied else "tempo_unused", self.tempo.note))
        if self.lines.note:
            said.append(("lines", self.lines.note))
        return said


def parse_opened(
    opened: OpenedScore, parse: Callable[[Path], ParseResult]
) -> tuple[ParseResult, OpenedReading]:
    """Parse ``opened``, with the line lengths and the playback tempo of a MuseScore project."""
    parsed = parse(opened.parse_path)
    lines = NOT_READ
    if opened.conversion is not None and opened.original.suffix.lower() in MUSESCORE_SUFFIXES:
        parsed, lines = apply_lyric_lines(parsed, read_project_lyrics(opened.original))
    parsed, tempo = follow_playback_tempo(opened, parsed)
    return parsed, OpenedReading(tempo, lines)
