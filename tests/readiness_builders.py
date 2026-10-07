"""Builders for readiness tests: hand-built songs, performed in memory (no XML)."""

from collections.abc import Mapping, Sequence
from fractions import Fraction

from barbershop_tracks.core.musicxml import ParseResult
from barbershop_tracks.core.readiness import RoleAssignments
from barbershop_tracks.core.timeline import perform_song
from barbershop_tracks.models import (
    Lyric,
    MeasureSpan,
    Note,
    Part,
    Pitch,
    Song,
    Step,
    TempoChange,
    ValidationResult,
    VoiceRole,
)

LINE_IDS = {
    VoiceRole.TENOR: "P1/s1/v1",
    VoiceRole.LEAD: "P2/s1/v1",
    VoiceRole.BARITONE: "P3/s1/v1",
    VoiceRole.BASS: "P4/s1/v1",
}
# comfortably inside the default advisory ranges of each role
PITCHES = {
    VoiceRole.TENOR: Pitch(Step.E, 4),
    VoiceRole.LEAD: Pitch(Step.C, 4),
    VoiceRole.BARITONE: Pitch(Step.G, 3),
    VoiceRole.BASS: Pitch(Step.C, 3),
}


def note(
    start: int | Fraction,
    dur: int | Fraction = 1,
    pitch: Pitch | None = None,
    *,
    to: bool = False,
    frm: bool = False,
    lyrics: tuple[Lyric, ...] = (),
) -> Note:
    """A note in a 4-beat-measure score; ``pitch=None`` makes a rest."""
    position = Fraction(start)
    return Note(
        start=position,
        duration=Fraction(dur),
        measure=int(position // 4) + 1,
        beat=Fraction(1) + position % 4,
        written_pitch=pitch,
        tied_to_next=to,
        tied_from_previous=frm,
        lyrics=lyrics,
    )


def rest(start: int | Fraction, dur: int | Fraction = 1) -> Note:
    return note(start, dur, None)


def melody(pitch: Pitch, count: int = 8) -> list[Note]:
    """``count`` adjacent quarter notes from the start."""
    return [note(i, 1, pitch) for i in range(count)]


def tempo_at(position: int | Fraction = 0, bpm: int = 100) -> TempoChange:
    return TempoChange(position=Fraction(position), bpm=Fraction(bpm))


def song_of(
    lines: Mapping[str, Sequence[Note]],
    *,
    measures: int = 4,
    tempos: Sequence[TempoChange] | None = None,
) -> Song:
    spans = tuple(
        MeasureSpan(index=i, number=i + 1, start=Fraction(4 * i), length=Fraction(4))
        for i in range(measures)
    )
    parts = tuple(
        Part(part_id=line_id, name=line_id, events=tuple(events))
        for line_id, events in lines.items()
    )
    return Song(
        title="t",
        parts=parts,
        measures=spans,
        tempo_map=tuple([tempo_at()] if tempos is None else tempos),
    )


def parsed_of(song: Song, issues: ValidationResult | None = None) -> ParseResult:
    """What ``parse_score`` would return for ``song`` (performance issues included)."""
    performed = perform_song(song)
    merged = performed.issues if issues is None else issues.merged(performed.issues)
    return ParseResult(song=song, issues=merged, performed=performed)


def quartet_lines(**overrides: Sequence[Note]) -> dict[str, Sequence[Note]]:
    """Four well-formed monophonic lines; ``overrides`` replace a role's notes by role name."""
    lines: dict[str, Sequence[Note]] = {}
    for role, line_id in LINE_IDS.items():
        lines[line_id] = overrides.get(role.value, melody(PITCHES[role]))
    return lines


def quartet_assignments(**lines: str) -> RoleAssignments:
    """Every role assigned to its standard line (override a role with ``lead='P9/s1/v1'``)."""
    entries = tuple((role, lines.get(role.value, line_id)) for role, line_id in LINE_IDS.items())
    return RoleAssignments(entries=entries)


def ready_parsed() -> ParseResult:
    return parsed_of(song_of(quartet_lines()))
