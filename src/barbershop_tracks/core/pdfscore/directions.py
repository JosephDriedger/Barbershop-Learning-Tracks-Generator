"""Tempo marks, words over the music (rit., a tempo, Swing) and fermatas.

A metronome mark is a note symbol of the music font's text face followed by "= 70"; the words in
front of it on the same line ("Freely") belong to it. "a tempo" and "Tempo I" go back to a tempo
that was marked before, as a notation program plays them. Bold or italic text over a system that is
not a metronome mark is kept as words, at the note it stands over.
"""

import re
from collections import defaultdict
from fractions import Fraction

from barbershop_tracks.core.pdfscore.layout import System
from barbershop_tracks.core.pdfscore.model import Direction, Event
from barbershop_tracks.core.pdfscore.pdf import Glyph, Page
from barbershop_tracks.core.pdfscore.symbols import (
    FERMATAS,
    METRONOME_DOT,
    METRONOME_NOTES,
    is_music_symbol,
)

_RETURN = re.compile(r"^\s*(a\s+tempo|tempo\s+i|tempo\s+primo|tempo\s+1)\b", re.IGNORECASE)
_TEMPO_LINE = re.compile(
    r"^\s*\(?(rit|ritard|ritardando|rall|rallentando|accel|accelerando)\b", re.IGNORECASE
)


def _anchor(events: list[Event], system: System, x: float) -> tuple[int, Fraction] | None:
    """(measure, onset) of the column a mark written at ``x`` stands over."""
    sp = system.space
    candidates = [e for e in events if e.system is system]
    if not candidates:
        return None
    after = [e for e in candidates if e.x >= x - 1.5 * sp]
    pool = after or candidates
    best = min(pool, key=lambda e: (abs(e.x - x), e.measure, e.onset))
    return best.measure, best.onset


def read_directions(
    page: Page, system: System, events: list[Event], lyric_fonts: set[tuple[str, float]]
) -> list[Direction]:
    sp = system.space
    found: list[Direction] = []
    rows: dict[float, list[Glyph]] = defaultdict(list)
    for g in page.glyphs:
        if not (system.x0 - 2 <= g.x <= system.x1 + 2):
            continue
        if not (system.bottom - 10 * sp <= g.y <= system.top + 10 * sp):
            continue
        if is_music_symbol(g.text) and g.text not in METRONOME_NOTES and g.text != METRONOME_DOT:
            continue
        if not is_music_symbol(g.text):
            name = g.font.lower()
            if (g.font, round(g.size, 1)) in lyric_fonts and "bold" not in name:
                continue
            if "italic" in name and g.text.isdigit():
                continue  # a measure number or a tuplet number
        rows[round(g.y, 0)].append(g)
    for y, glyphs in rows.items():
        glyphs.sort(key=lambda g: g.x)
        for phrase in _phrases(glyphs, sp):
            direction = _direction(phrase, events, system, y)
            if direction is None:
                continue
            found.append(direction)
            if _TEMPO_LINE.match(direction.words):
                end = _line_end(page, system, events, phrase)
                if end is not None:
                    direction.line_to = end
                    direction.dashes = "start"
                    found.append(
                        Direction(end[0], end[1], direction.staff_index, above=True, dashes="stop")
                    )
    return found


def _line_end(
    page: Page, system: System, events: list[Event], phrase: list[Glyph]
) -> tuple[int, Fraction] | None:
    """Where the dashed line after "rit." (or "accel.") ends: at the first note to the right of
    the end of the line, or of the word itself when the line is too short to be drawn."""
    sp = system.space
    y = phrase[0].y
    size = max(g.size for g in phrase)
    end = max(g.x + g.width for g in phrase)
    for s in sorted(page.segments, key=lambda s: min(s.x0, s.x1)):
        if abs(s.y0 - s.y1) > 0.01 or not (y - 0.6 * size <= s.y0 <= y + 0.9 * size):
            continue
        a, b = sorted((s.x0, s.x1))
        if end - 1 <= a <= end + 3 * sp:
            end = max(end, b)
    later = [e for e in events if e.system is system and e.x > end + 0.3]
    if not later:
        return None
    first = min(later, key=lambda e: (e.x, e.measure, e.onset))
    return first.measure, first.onset


def _phrases(glyphs: list[Glyph], sp: float) -> list[list[Glyph]]:
    phrases: list[list[Glyph]] = []
    for g in glyphs:
        if phrases:
            last = phrases[-1][-1]
            if g.x - (last.x + last.width) <= 2.5 * sp:
                phrases[-1].append(g)
                continue
        phrases.append([g])
    return phrases


def _direction(
    phrase: list[Glyph], events: list[Event], system: System, y: float
) -> Direction | None:
    anchor = _anchor(events, system, phrase[0].x)
    if anchor is None:
        return None
    measure, onset = anchor
    staff = min(system.staves, key=lambda s: min(abs(y - s.top), abs(y - s.bottom)))
    bold = any("bold" in g.font.lower() for g in phrase)
    notes = [i for i, g in enumerate(phrase) if g.text in METRONOME_NOTES]
    if notes:
        i = notes[0]
        unit = METRONOME_NOTES[phrase[i].text]
        rest = phrase[i + 1 :]
        if rest and rest[0].text == METRONOME_DOT:
            unit = unit * Fraction(3, 2)
            rest = rest[1:]
        words = _text(phrase[:i])
        after = _text(rest).replace(" ", "")
        match = re.match(r"^=?\s*(\d+(?:[.,]\d+)?)(.*)$", after)
        if match:
            number = Fraction(match.group(1).replace(",", "."))
            return Direction(
                measure,
                onset,
                staff.index,
                words=words.strip(),
                above=y > staff.middle,
                tempo=number * unit,
                beat_unit=unit,
                per_minute=match.group(1) + match.group(2),
                bold=bold,
            )
    text = _text(phrase).strip()
    if not text or all(is_music_symbol(c) for c in text):
        return None
    return Direction(measure, onset, staff.index, words=text, above=y > staff.middle, bold=bold)


def _text(glyphs: list[Glyph]) -> str:
    out = ""
    for i, g in enumerate(glyphs):
        if i:
            prev = glyphs[i - 1]
            if g.x - (prev.x + prev.width) > 0.2 * g.size:
                out += " "
        out += g.text
    return out


def resolve_returns(directions: list[Direction]) -> None:
    """Give "a tempo" and "Tempo I" the tempo they return to."""
    ordered = sorted(directions, key=lambda d: (d.measure, d.onset))
    first: Fraction | None = None
    last: Fraction | None = None
    for d in ordered:
        if d.tempo is not None:
            if first is None:
                first = d.tempo
            last = d.tempo
            continue
        match = _RETURN.match(d.words)
        if match is None:
            continue
        if match.group(1).lower().startswith("a"):
            d.tempo = last
        else:
            d.tempo = first


def read_fermatas(page: Page, system: System, events: list[Event], systems: list[System]) -> None:
    """Mark the notes that have a fermata. A fermata belongs to the staff nearest it, of the
    system it is in (one under a system is not read again with the system below)."""
    sp = system.space
    staves = [s for other in systems for s in other.staves]
    for g in page.glyphs:
        if g.text not in FERMATAS:
            continue
        if not (
            system.x0 <= g.x <= system.x1 and system.bottom - 8 * sp <= g.y <= system.top + 8 * sp
        ):
            continue
        nearest = min(staves, key=lambda s: min(abs(g.y - s.top), abs(g.y - s.bottom)))
        if nearest not in system.staves:
            continue
        above = FERMATAS[g.text]
        center = g.x + g.width / 2
        pool = [
            e for e in events if e.system is system and abs(e.x + _w(e) / 2 - center) < 1.5 * sp
        ]
        if not pool:
            continue
        staff = min(
            {e.staff.index: e.staff for e in pool}.values(),
            key=lambda s: min(abs(g.y - s.top), abs(g.y - s.bottom)),
        )
        mine = [e for e in pool if e.staff is staff]
        if not mine:
            continue
        chosen = min(
            mine, key=lambda e: (e.voice != (1 if above else 2), abs(e.x + _w(e) / 2 - center))
        )
        chosen.fermata = True


def _w(e: Event) -> float:
    if e.heads:
        return e.heads[0].w
    return e.rest_glyph.width if e.rest_glyph is not None else 0.0


__all__ = ["read_directions", "read_fermatas", "resolve_returns"]
