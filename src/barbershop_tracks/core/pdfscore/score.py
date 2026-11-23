"""Reading a whole score PDF: every system of every page, in order, into one ``ReadScore``."""

from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

from barbershop_tracks.core.pdfscore.directions import (
    read_directions,
    read_fermatas,
    resolve_returns,
)
from barbershop_tracks.core.pdfscore.endings import read_endings
from barbershop_tracks.core.pdfscore.layout import System, page_systems
from barbershop_tracks.core.pdfscore.lyrics import is_plain_text, lyric_rows, place_lyrics
from barbershop_tracks.core.pdfscore.model import (
    Direction,
    Event,
    Head,
    LineGoesOn,
    MeasureInfo,
    PartInfo,
    ReadScore,
)
from barbershop_tracks.core.pdfscore.pdf import Glyph, Page, PdfError, Shape, read_pages
from barbershop_tracks.core.pdfscore.recognise import (
    SystemSymbols,
    assign_voices,
    attach_accidentals,
    key_accidentals,
    key_from,
    measure_of,
    read_clefs,
    read_events,
    read_ties,
    read_times,
    retime_short_voices,
    spell,
    tie_reach,
)
from barbershop_tracks.core.pdfscore.slurs import read_slurs
from barbershop_tracks.core.pdfscore.symbols import NOTEHEADS, is_music_symbol


class NotNotationPdf(PdfError):  # noqa: N818 - the name says what the file is
    """The PDF has no music drawn with a music font: a scan or a picture (or no music at all)."""


def _lines_text(glyphs: list[Glyph]) -> list[tuple[float, float, float, str]]:
    """(y, x0, size, text) of each line of plain text, words joined with spaces."""
    rows: dict[float, list[Glyph]] = defaultdict(list)
    for g in glyphs:
        rows[round(g.y, 0)].append(g)
    found = []
    for y, row in rows.items():
        row.sort(key=lambda g: g.x)
        text = ""
        for i, g in enumerate(row):
            if i and g.x - (row[i - 1].x + row[i - 1].width) > 0.2 * g.size:
                text += " "
            text += g.text
        found.append((y, row[0].x, max(g.size for g in row), text.strip()))
    return found


def _titles(page: Page, first: System) -> tuple[str, str, str, str]:
    above = [
        g
        for g in page.glyphs
        if g.text.strip() and not is_music_symbol(g.text) and g.y > first.top + 12 * first.space
    ]
    lines = _lines_text(above)
    if not lines:
        return "", "", "", ""
    lines.sort(key=lambda r: -r[2])
    title = lines[0][3]
    rest = [r for r in lines if r is not lines[0]]
    centre = page.width / 2
    subtitle = next(
        (r[3] for r in sorted(rest, key=lambda r: -r[0]) if abs(r[1] - centre) < page.width * 0.25),
        "",
    )
    right = sorted((r for r in rest if r[1] > centre), key=lambda r: -r[0])
    composer = right[0][3] if right else ""
    arranger = next((r[3] for r in right if "arr" in r[3].lower()), "")
    return title, subtitle, composer, arranger


def _part_names(page: Page, system: System) -> list[str]:
    names: list[str] = []
    labels = [g for g in page.glyphs if is_plain_text(g) and g.x < system.x0 - 1 and g.text.strip()]
    for staff in system.staves:
        mine = [
            g
            for g in labels
            if staff.bottom - 3 * staff.space <= g.y <= staff.top + 3 * staff.space
        ]
        lines = sorted(_lines_text(mine), key=lambda r: -r[0])
        names.append("\n".join(r[3] for r in lines))
    return names


def read_score(path: Path) -> ReadScore:
    pages = read_pages(path)
    if not any(g.text in NOTEHEADS for p in pages for g in p.glyphs):
        raise NotNotationPdf(
            f"{path.name} has no notes written in a music font (it is probably a scan or a picture "
            "of the music)"
        )
    notes: list[str] = []
    systems: list[tuple[Page, System, list[System]]] = []
    for page in pages:
        on_page = page_systems(page)
        for s in on_page:
            systems.append((page, s, on_page))
    if not systems:
        raise NotNotationPdf(f"no staves were found in {path.name}")
    counts = Counter(len(s.staves) for _p, s, _a in systems)
    staff_count = counts.most_common(1)[0][0]
    if len(counts) > 1:
        raise PdfError(
            f"the systems of {path.name} do not all have {staff_count} staves (a staff hidden "
            "where it is empty is not supported): export the PDF with every staff shown"
        )
    events: list[Event] = []
    measures: list[MeasureInfo] = []
    directions: list[Direction] = []
    clef_at: dict[int, list[tuple[int, float, tuple[str, int, int]]]] = defaultdict(list)
    key_at: dict[int, list[tuple[int, int]]] = defaultdict(list)
    time: tuple[int, int] = (4, 4)
    time_seen = False
    head_width = 6.0
    per_system: list[tuple[Page, System, list[Event]]] = []
    for page, system, everything in systems:
        symbols = SystemSymbols(page, system, everything)
        found = read_events(symbols, notes)
        xs = [b.x for b in system.boundaries]
        local: dict[int, list[Event]] = defaultdict(list)
        for e in found:
            m = measure_of(xs, e.x + 0.1)
            if m is not None:
                local[m].append(e)
        kept = [m for m in range(len(xs) - 1) if local.get(m)]
        if not kept:
            continue
        index_of = {m: len(measures) + i for i, m in enumerate(kept)}
        for i, m in enumerate(kept):
            info = MeasureInfo(len(measures), system, xs[m], xs[m + 1])
            if system.boundaries[m].repeat_after or (
                i == 0 and m > 0 and system.boundaries[m].repeat_after
            ):
                info.repeat_start = True
            if system.boundaries[m + 1].repeat_before:
                info.repeat_end = True
            info.barline_end = system.boundaries[m + 1].kind
            measures.append(info)
            for e in local[m]:
                e.measure = info.index

        def owner(
            x: float,
            kept: list[int] = kept,
            xs: list[float] = xs,
            index_of: dict[int, int] = index_of,
        ) -> int | None:
            """The measure a signature at ``x`` belongs to (None: a courtesy one at the end)."""
            for m in kept:
                if x < xs[m + 1]:
                    return index_of[m]
            return None

        for staff in system.staves:
            glyphs = symbols.glyphs[staff.index]
            heads = [h for e in found if e.staff is staff for h in e.heads]
            for x, clef in read_clefs(glyphs, staff):
                m = owner(x)
                if m is not None:
                    clef_at[staff.index].append((m, x, clef))
            firsts = [
                (xs[m], xs[m + 1], min(e.x for e in local[m] if e.staff is staff))
                for m in kept
                if any(e.staff is staff for e in local[m])
            ]
            if firsts:  # the header before the first measure belongs to it
                firsts[0] = (system.x0, firsts[0][1], firsts[0][2])
            clefs_here = [c for m, _x, c in clef_at[staff.index] if m <= index_of[kept[0]]]
            clef = clefs_here[-1] if clefs_here else ("G", 2, 0)
            free = key_accidentals(glyphs, heads, staff, clef, firsts)
            groups: dict[int, list[Glyph]] = defaultdict(list)
            for g in free:
                m = owner(g.x)
                if m is not None:
                    groups[m].append(g)
            first_measure = index_of[kept[0]]
            if first_measure not in groups:
                # every system restates its key; one with no key signature is in C (A minor)
                key_at[staff.index].append((first_measure, 0))
            for m, group in sorted(groups.items()):
                fifths = key_from(group)
                if fifths is not None:
                    key_at[staff.index].append((m, fifths))
            attach_accidentals([g for g in glyphs if g not in free], heads, staff)
            if staff.index == 0:
                for x, sig, symbol in read_times(glyphs, staff):
                    m = owner(x)
                    if m is not None:
                        measures[m].time = sig
                        measures[m].time_symbol = symbol
        widths = [h.w for e in found for h in e.heads]
        if widths:
            head_width = sorted(widths)[len(widths) // 2]
        for i in range(len(measures) - len(kept), len(measures)):
            info = measures[i]
            if info.time is not None:
                time = info.time
                time_seen = True
            info.nominal = Fraction(4 * time[0], time[1])
            lengths: list[Fraction] = []
            for staff in system.staves:
                mine = [e for e in found if e.measure == info.index and e.staff is staff]
                length, cost, twins = assign_voices(mine, info.nominal, head_width)
                found.extend(twins)
                lengths.append(length)
                if cost >= 8:
                    notes.append(
                        f"measure {i + 1}, staff {staff.index + 1}: the rhythm could not be read "
                        "with certainty"
                    )
            info.length = info.nominal if all(n == info.nominal for n in lengths) else max(lengths)
            retime_short_voices(
                [e for e in found if e.measure == info.index], info.length, head_width
            )
            if len(set(lengths)) > 1:
                notes.append(
                    f"measure {i + 1}: the staves do not have the same length "
                    f"({', '.join(str(n) for n in lengths)} quarter notes)"
                )
        events.extend(found)
        per_system.append((page, system, found))
    if not time_seen:
        notes.append("no time signature was found; 4/4 is assumed")
    tie_curves: list[tuple[SystemSymbols, list[tuple[Shape, Head, bool]]]] = []
    systems_symbols = [
        (SystemSymbols(page, system, [system]), found) for page, system, found in per_system
    ]
    # how far a tie lies from its notes, in this score's music font (over all its systems: a
    # tie over a line break has its halves in two of them)
    reach = max((tie_reach(symbols, found) for symbols, found in systems_symbols), default=0.95)
    for symbols, found in systems_symbols:
        tie_curves.append((symbols, read_ties(symbols, found, reach)))
    _join_broken_ties(events)
    spell(events, measures, clef_at, key_at)
    _pair_ties(events)
    # the curves that are not ties (or were taken for one between two pitches) are slurs
    for (symbols, taken), (_page, system, found) in zip(tie_curves, per_system, strict=True):
        ties = {
            id(curve)
            for curve, head, ending in taken
            if (head.tied_from if ending else head.tied_to) is not None
        }
        read_slurs(system, [c for c in symbols.curves if id(c) not in ties], found)
    lyric_fonts: set[tuple[str, float]] = set()
    readings = []
    for page, system, found in per_system:
        on_page = [s for _p, s, _f in per_system if s.page == page.number]
        margins = (min(s.x0 for s in on_page), max(s.x1 for s in on_page))
        readings.extend(lyric_rows(page, system, found, margins, on_page))
    lyric_problems, goes_on = place_lyrics(readings)
    notes.extend(lyric_problems)
    goes_on.extend(_lines_going_on(per_system))
    _continue_words(events)
    lyric_fonts = _lyric_fonts(per_system)
    for page, system, found in per_system:
        directions.extend(read_directions(page, system, found, lyric_fonts))
        read_fermatas(page, system, found, [s for _p, s, _f in per_system if s.page == page.number])
    resolve_returns(directions)
    _number_measures(measures, per_system)
    notes.extend(read_endings({p.number: p for p in pages}, measures))
    first_page, first_system, _f = per_system[0]
    title, subtitle, composer, arranger = _titles(first_page, first_system)
    parts = _parts(first_page, first_system)
    _line_lengths(events, measures, [s for _p, s, _f in per_system], goes_on)
    return ReadScore(
        title=title,
        subtitle=subtitle,
        composer=composer,
        arranger=arranger,
        parts=parts,
        measures=measures,
        events=events,
        directions=directions,
        staff_count=staff_count,
        notes=notes,
        clef_at=dict(clef_at),
        key_at=dict(key_at),
    )


def _lyric_fonts(per_system: list[tuple[Page, System, list[Event]]]) -> set[tuple[str, float]]:
    """The fonts the words were found in (other text in them is not a direction)."""
    fonts: set[tuple[str, float]] = set()
    for page, system, found in per_system:
        texts = {lyric.text for e in found for lyric in e.lyrics}
        if not texts:
            continue
        for g in page.glyphs:
            if (
                is_plain_text(g)
                and system.bottom - 16 * system.space <= g.y <= system.top + 12 * system.space
            ):
                fonts.add((g.font, round(g.size, 1)))
    # only the font the most lyric text uses
    return fonts


def _parts(page: Page, system: System) -> list[PartInfo]:
    names = _part_names(page, system)
    braced: dict[int, int] = {}
    for a, b in system.braced:
        for k in range(a, b + 1):
            braced[k] = a
    parts: list[PartInfo] = []
    for staff in system.staves:
        start = braced.get(staff.index, staff.index)
        if start != staff.index and parts:
            parts[-1].staves.append(staff.index)
            continue
        parts.append(PartInfo(f"P{len(parts) + 1}", names[staff.index], [staff.index]))
    return parts


def _printed_numbers(per_system: list[tuple[Page, System, list[Event]]]) -> dict[int, int]:
    """The measure numbers printed at the start of systems: {index of the system: number}.

    A notation program writes the number of the first measure of each system (but the first)
    in small italic digits over the start of the top staff.
    """
    found: dict[int, int] = {}
    for k, (page, system, _found) in enumerate(per_system):
        sp = system.space
        top = system.staves[0].top
        digits = sorted(
            (
                g
                for g in page.glyphs
                if g.text.isdigit()
                and "italic" in g.font.lower()
                and system.x0 - 2 <= g.x <= system.x0 + 6 * sp
                and top <= g.y <= top + 6 * sp
            ),
            key=lambda g: g.x,
        )
        if not digits:
            continue
        row = [g for g in digits if abs(g.y - digits[0].y) < 0.5]
        found[k] = int("".join(g.text for g in row))
    return found


def _number_measures(
    measures: list[MeasureInfo], per_system: list[tuple[Page, System, list[Event]]]
) -> None:
    """Number the measures as the score does: from the numbers printed at the start of its
    systems; without them, from 1, a short first measure (a pickup) being 0."""
    printed = _printed_numbers(per_system)
    first_of: dict[int, int] = {}
    for m in measures:
        for k, (_p, system, _f) in enumerate(per_system):
            if m.system is system and k not in first_of:
                first_of[k] = m.index
    base: int | None = None
    for k, number in sorted(printed.items()):
        if k in first_of:
            base = number - first_of[k]
            break
    if base is None:
        base = 0 if measures and measures[0].length < measures[0].nominal else 1
    for m in measures:
        m.number = m.index + base
    for k, number in sorted(printed.items()):  # a system's own number wins from there on
        if k not in first_of:
            continue
        shift = number - measures[first_of[k]].number
        if shift:
            for m in measures[first_of[k] :]:
                m.number += shift


def _ordered_voice(events: list[Event]) -> dict[tuple[int, int], list[Event]]:
    lines: dict[tuple[int, int], list[Event]] = defaultdict(list)
    for e in events:
        lines[(e.staff.index, e.voice)].append(e)
    for group in lines.values():
        group.sort(key=lambda e: (e.measure, e.onset))
    return lines


def _join_broken_ties(events: list[Event]) -> None:
    """Join a tie that runs over a line break: its halves end at the end of one system and begin
    at the start of the next, on the same line or space of the same voice."""
    for group in _ordered_voice(events).values():
        for k, a in enumerate(group):
            for h in a.heads:
                if not h.tie_start or h.tied_to is not None:
                    continue
                later = next((e for e in group[k + 1 :] if not e.is_rest), None)
                if later is None or later.system is a.system:
                    continue
                position = h.staff.position(h.y)
                match = next(
                    (
                        g
                        for g in later.heads
                        if g.tie_stop and g.tied_from is None and g.staff.position(g.y) == position
                    ),
                    None,
                )
                if match is not None:
                    h.tied_to, match.tied_from = match, h


def _pair_ties(events: list[Event]) -> None:
    """Keep only ties that join two notes of one pitch; a curve between two pitches is a slur,
    and half a tie whose other half was not found (a slur that runs over a line break) is none."""
    for e in events:
        for h in e.heads:
            other = h.tied_to
            if other is not None and other.midi != h.midi:
                h.tied_to = other.tied_from = None
    for e in events:
        for h in e.heads:
            h.tie_start = h.tied_to is not None
            h.tie_stop = h.tied_from is not None


def _continue_words(events: list[Event]) -> None:
    """A syllable after one that a hyphen continues is part of the same word (over a line break)."""
    rows: dict[tuple[int, int, int], list[tuple[Event, int]]] = defaultdict(list)
    for e in events:
        for i, lyric in enumerate(e.lyrics):
            rows[(e.staff.index, e.voice, lyric.number)].append((e, i))
    for group in rows.values():
        group.sort(key=lambda p: (p[0].measure, p[0].onset))
        open_word = False
        for e, i in group:
            lyric = e.lyrics[i]
            if open_word and lyric.syllabic in ("single", "begin"):
                lyric.syllabic = "end" if lyric.syllabic == "single" else "middle"
            open_word = lyric.syllabic in ("begin", "middle")


def _lines_going_on(per_system: list[tuple[Page, System, list[Event]]]) -> list[LineGoesOn]:
    """Underscore lines that start a system (a held syllable of the system before goes on):
    horizontal lines from the start of the music, away from the staff lines, under or over a
    staff."""
    found: list[LineGoesOn] = []
    for page, system, events in per_system:
        sp = system.space
        for staff in system.staves:
            mine = [e.x for e in events if e.staff is staff]
            if not mine:
                continue
            first = min(mine)
            for s in page.segments:
                if abs(s.y0 - s.y1) > 0.01:
                    continue
                a, b = sorted((s.x0, s.x1))
                # it starts before the first note (a line after that note's syllable starts after)
                if not (system.x0 <= a <= first - 0.2 * sp) or b - a < 2 * sp:
                    continue
                if staff.bottom - 0.5 * sp <= s.y0 <= staff.top + 0.5 * sp:
                    continue  # on the staff: a staff or ledger line
                above = s.y0 > staff.top
                offset = (s.y0 - staff.top) if above else (staff.bottom - s.y0)
                if offset > 14 * sp:
                    continue
                found.append(LineGoesOn(system, staff.index, above, offset, b))
    return found


def _line_lengths(
    events: list[Event],
    measures: list[MeasureInfo],
    systems: list[System],
    goes_on: list[LineGoesOn],
) -> None:
    """How far each underscore line runs, in quarter notes from its syllable's note to the start
    of the last note it is drawn under (as MuseScore keeps it). A line that reaches the end of a
    system goes on at the start of the next one, as far as that part of it is drawn; a line under
    no further note is MuseScore's one tick."""
    starts: list[Fraction] = []
    t = Fraction(0)
    for m in measures:
        starts.append(t)
        t += m.length
    order = {id(s): i for i, s in enumerate(systems)}
    lines = _ordered_voice(events)
    for group in lines.values():
        for k, e in enumerate(group):
            for lyric in e.lyrics:
                here = starts[e.measure] + e.onset
                if lyric.extend_to is None and _last_of_system(e, group, k):
                    # on the last note of a system, a line too short to draw before the break
                    # shows only at the start of the next system
                    nxt = order.get(id(e.system), -1) + 1
                    if nxt < len(systems) and any(
                        g.system is systems[nxt]
                        and g.staff_index == e.staff.index
                        and g.above == lyric.above
                        and abs(g.offset - lyric.offset) < 1.0 * e.system.space
                        for g in goes_on
                    ):
                        lyric.extend_to = e.system.x1
                if lyric.extend_to is None:
                    if lyric.left_aligned:  # held over the next note, its line not drawn
                        following = next((g for g in group[k + 1 :] if not g.is_rest), None)
                        if following is not None and not following.lyrics:
                            lyric.line = starts[following.measure] + following.onset - here
                    continue
                last = e
                system, reach = e.system, lyric.extend_to
                while True:
                    for later in group[k + 1 :]:
                        if later.system is not system:
                            continue
                        if later.is_rest or later.x + 0.3 * later.heads[0].w > reach:
                            if later.x > reach:
                                break
                            continue
                        if (starts[later.measure] + later.onset) > (
                            starts[last.measure] + last.onset
                        ):
                            last = later
                    last_x = max((g.x for g in events if g.system is system), default=system.x0)
                    if reach < system.music_end(last_x) - 3 * system.space:
                        break
                    index = order.get(id(system), -1) + 1
                    if index >= len(systems):
                        break
                    system = systems[index]
                    on = [
                        g
                        for g in goes_on
                        if g.system is system
                        and g.staff_index == e.staff.index
                        and g.above == lyric.above
                        and abs(g.offset - lyric.offset) < 3 * system.space
                    ]
                    if not on:
                        break
                    reach = min(on, key=lambda g: abs(g.offset - lyric.offset)).to
                if last is e:
                    lyric.line = Fraction(1, 480)  # a line under no further note: one tick
                else:
                    lyric.line = starts[last.measure] + last.onset - here


def _last_of_system(e: Event, group: list[Event], k: int) -> bool:
    """Whether ``e`` is the last note of its voice in its system."""
    return not any(g.system is e.system and not g.is_rest for g in group[k + 1 :])


__all__ = ["NotNotationPdf", "read_score"]
