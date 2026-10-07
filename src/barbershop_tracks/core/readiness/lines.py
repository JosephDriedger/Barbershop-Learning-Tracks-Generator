"""Describing the source lines of a parsed score (the ``lines`` command's data). Pure."""

from dataclasses import dataclass
from fractions import Fraction

from barbershop_tracks.core.musicxml import ParseResult
from barbershop_tracks.core.readiness.suggest import RoleSuggestion, suggest_roles


@dataclass(frozen=True, slots=True, kw_only=True)
class LineInfo:
    """One source line: its stable identifier and what it contains."""

    line_id: str
    part_name: str
    source_name: str | None
    staff: int | None
    voice: str | None
    sounding_attacks: int
    has_lyrics: bool
    first_measure: int | None
    last_measure: int | None
    first_start: Fraction | None
    suggestion: RoleSuggestion


def describe_lines(parsed: ParseResult) -> tuple[LineInfo, ...]:
    """The lines of ``parsed`` in score order with deterministic, unconfirmed suggestions."""
    if parsed.song is None:
        return ()
    song = parsed.song
    suggestions = suggest_roles(song.parts)
    attacks_by_line: dict[str, int] = {}
    if parsed.performed is not None:
        for line, merged in zip(parsed.performed.lines, parsed.performed.merged, strict=True):
            attacks_by_line[line.part_id] = sum(1 for a in merged if not a.is_rest)
    infos = []
    for part, suggestion in zip(song.parts, suggestions, strict=True):
        sounding = part.sounding_notes
        link = part.source_line
        infos.append(
            LineInfo(
                line_id=part.part_id,
                part_name=part.name,
                source_name=part.source_name,
                staff=None if link is None else link.staff,
                voice=None if link is None else link.voice,
                sounding_attacks=attacks_by_line.get(part.part_id, len(sounding)),
                has_lyrics=any(note.lyrics for note in sounding),
                first_measure=min((n.measure for n in sounding), default=None),
                last_measure=max((n.measure for n in sounding), default=None),
                first_start=min((n.start for n in sounding), default=None),
                suggestion=suggestion,
            )
        )
    return tuple(infos)
