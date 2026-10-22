"""Giving each held syllable the length MuseScore drew its line to, instead of a guess.

The MusicXML of a MuseScore project says where an underscore line starts (``<extend/>``) and not
where it ends, so BLT has to guess, and a guess that cuts a held "oo", "doo" or "loo" short makes a
part sing the Lead's words over a line that goes on. The project itself has the length
(``mscx_lyrics.py``). Here each voice of the parsed score is matched to a voice of the project **by
what it sings**: the same lyrics in the same order. A voice that matches exactly gets the real
length on every held syllable; a voice that does not match (a lyric that reads differently, another
number of them) is left to the guess as before, and nothing is ever applied on a doubtful match.
The notes, their timing and every other lyric are left exactly as they were.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from barbershop_tracks.core.musicxml.mscx_lyrics import ProjectLyric
from barbershop_tracks.core.musicxml.parser import ParseResult
from barbershop_tracks.core.timeline import perform_song
from barbershop_tracks.models import LyricKind, Melisma, Part


@dataclass(frozen=True, slots=True)
class LyricLines:
    """What was done with the project's line lengths (said to the person, kept in the package)."""

    applied: int  # held syllables that now have the length MuseScore drew
    wanted: int  # held syllables in the score
    note: str  # said to the person; empty when there is nothing to say

    def as_record(self) -> dict[str, object]:
        return {
            "source": "MuseScore project",
            "applied": self.applied,
            "held": self.wanted,
            "note": self.note,
        }


NOT_READ = LyricLines(0, 0, "")


def _slots(part: Part) -> list[tuple[int, int]]:
    """(note index, lyric index) of every text lyric of verse 1 of a part, in order."""
    found: list[tuple[int, int]] = []
    for n, note in enumerate(part.events):
        for j, lyric in enumerate(note.lyrics):
            if lyric.kind is LyricKind.TEXT and lyric.verse in (None, "1"):
                found.append((n, j))
    return found


def apply_lyric_lines(
    parsed: ParseResult, project: Mapping[int, Sequence[Sequence[ProjectLyric]]]
) -> tuple[ParseResult, LyricLines]:
    """``parsed`` with the project's line lengths on the syllables it matches; what was done."""
    song = parsed.song
    if song is None or not project or any(p.source_line is None for p in song.parts):
        return parsed, NOT_READ
    staves_of: dict[str, int] = {}
    for part in song.parts:
        link = part.source_line
        assert link is not None
        staves_of[link.part_id] = max(staves_of.get(link.part_id, 0), link.staff)
    first_staff: dict[str, int] = {}
    running = 0
    for part_id in staves_of:
        first_staff[part_id] = running
        running += staves_of[part_id]
    taken: dict[int, set[int]] = {}
    rebuilt: list[Part] = []
    applied = wanted = 0
    for part in song.parts:
        link = part.source_line
        assert link is not None
        slots = _slots(part)
        held = [(n, j) for n, j in slots if part.events[n].lyrics[j].melisma is Melisma.UNTYPED]
        wanted += len(held)
        if not held:
            rebuilt.append(part)
            continue
        staff = first_staff[link.part_id] + link.staff
        texts = [part.events[n].lyrics[j].text.strip() for n, j in slots]
        used = taken.setdefault(staff, set())
        voices = project.get(staff, ())
        match = next(
            (
                i
                for i, voice in enumerate(voices)
                if i not in used and [lyric.text for lyric in voice] == texts
            ),
            None,
        )
        if match is None:
            rebuilt.append(part)  # not the same words in the same order: the guess stays
            continue
        used.add(match)
        events = list(part.events)
        for (n, j), found in zip(slots, voices[match], strict=True):
            lyric = events[n].lyrics[j]
            if lyric.melisma is Melisma.UNTYPED and found.line is not None:
                lyrics = list(events[n].lyrics)
                lyrics[j] = replace(lyric, extend_length=found.line)
                events[n] = replace(events[n], lyrics=tuple(lyrics))
                applied += 1
        rebuilt.append(part.with_events(events))
    if not applied:
        return parsed, LyricLines(0, wanted, "")
    song = replace(song, parts=tuple(rebuilt))
    done = LyricLines(
        applied,
        wanted,
        f"Held syllables (oo, doo, loo) last as long as MuseScore draws them: {applied} of {wanted}"
        + (
            "."
            if applied == wanted
            else f"; the other {wanted - applied} could not be matched to the project and are read "
            "as before."
        ),
    )
    return replace(parsed, song=song, performed=perform_song(song)), done
