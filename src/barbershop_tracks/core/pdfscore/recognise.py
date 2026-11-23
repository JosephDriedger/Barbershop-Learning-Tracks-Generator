"""Reading the music of a score PDF: notes, rests, rhythm, voices, pitch, ties and signatures.

Everything is read from where the notation program put each symbol (see ``pdf.py``): a notehead's
pitch is its staff position under the clef, key signature and the accidentals before it in the
measure; its length is the notehead, the flags or beams at the end of its stem, its dots and a
tuplet number over its group. On a staff that two voices share, the stems say which voice a note
belongs to (up: the upper voice) and rests are moved up or down out of each other's way; whatever
the drawing leaves open (a whole note, a rest in the middle) is settled by the rhythm, since each
voice has to fill its measure and simultaneous notes stand in one column.
"""

import itertools
from collections import defaultdict
from dataclasses import replace
from fractions import Fraction

from barbershop_tracks.core.pdfscore.layout import Staff, System, stem_width
from barbershop_tracks.core.pdfscore.model import Event, Head, MeasureInfo
from barbershop_tracks.core.pdfscore.pdf import Glyph, Page, Segment, Shape
from barbershop_tracks.core.pdfscore.symbols import (
    ACCIDENTALS,
    AUGMENTATION_DOT,
    CLEF_REFERENCE,
    CLEFS,
    FLAGS,
    NOTEHEADS,
    RESTS,
    STEPS,
    TIME_COMMON,
    TIME_CUT,
    TIME_DIGITS,
    TUPLET_DIGITS,
    WHOLE_REST,
    diatonic,
    is_music_symbol,
)

Clef = tuple[str, int, int]


class SystemSymbols:
    """The music symbols of one system, each given to the staff it belongs to."""

    def __init__(self, page: Page, system: System, all_systems: list[System]) -> None:
        self.page = page
        self.system = system
        self.glyphs: dict[int, list[Glyph]] = defaultdict(list)
        # digits in an italic text face: a tuplet number as most programs write it (or a
        # measure number, which stands over no beamed group)
        self.digits: dict[int, list[Glyph]] = defaultdict(list)
        staves = [s for sys_ in all_systems for s in sys_.staves]
        for g in page.glyphs:
            italic_digit = g.text.isdigit() and "italic" in g.font.lower()
            if not is_music_symbol(g.text) and not italic_digit:
                continue
            staff = _nearest_staff(staves, g.x, g.y)
            if staff is not None and staff in system.staves:
                (self.digits if italic_digit else self.glyphs)[staff.index].append(g)
        thin = stem_width(page)
        sp = system.space
        self.stems = [
            s
            for s in page.segments
            if abs(s.x0 - s.x1) < 0.01
            and abs(s.width - thin) < 0.12
            and abs(s.y1 - s.y0) >= 1.2 * sp
            and system.x0 <= s.x0 <= system.x1
            and system.bottom - 12 * sp <= min(s.y0, s.y1) <= system.top + 12 * sp
        ]
        self.beams = [
            sh
            for sh in page.shapes
            if sh.filled
            and not sh.curved
            and system.x0 <= sh.bbox[0] <= system.x1
            and system.bottom - 12 * sp <= sh.bbox[1] <= system.top + 12 * sp
            and (sh.bbox[2] - sh.bbox[0]) > 1.0 * sp
        ]
        self.curves = [
            sh
            for sh in page.shapes
            if sh.curved
            and system.x0 - 2 <= sh.bbox[0] <= system.x1 + 2
            and system.bottom - 12 * sp <= sh.bbox[1] <= system.top + 12 * sp
        ]


def _nearest_staff(staves: list[Staff], x: float, y: float) -> Staff | None:
    best: Staff | None = None
    best_d = 1e9
    for s in staves:
        if not (s.x0 - 40 <= x <= s.x1 + 20):
            continue
        d = 0.0 if s.bottom <= y <= s.top else min(abs(y - s.top), abs(y - s.bottom))
        if d < best_d:
            best, best_d = s, d
    return best


def _vertical_extent(shape: Shape, x: float) -> tuple[float, float] | None:
    """Where the outline of ``shape`` crosses the vertical line at ``x`` (lowest, highest)."""
    ys: list[float] = []
    pts = shape.points
    for (ax, ay), (bx, by) in itertools.pairwise(pts):
        if ax == bx:
            if abs(ax - x) < 0.05:
                ys.extend((ay, by))
            continue
        lo, hi = sorted((ax, bx))
        if lo - 0.3 <= x <= hi + 0.3:
            t = min(1.0, max(0.0, (x - ax) / (bx - ax)))
            ys.append(ay + t * (by - ay))
    if not ys:
        return None
    return (min(ys), max(ys))


# --- notes, stems and rests ----------------------------------------------------------------------


def read_events(symbols: SystemSymbols, notes: list[str]) -> list[Event]:
    system = symbols.system
    sp = system.space
    events: list[Event] = []
    for staff in system.staves:
        glyphs = symbols.glyphs[staff.index]
        sizes = sorted(g.size for g in glyphs if g.text in NOTEHEADS)
        normal = sizes[len(sizes) // 2] if sizes else 4 * sp
        heads = [
            Head(g, staff, NOTEHEADS[g.text], g.size < 0.85 * normal)
            for g in glyphs
            if g.text in NOTEHEADS
        ]
        stems = [s for s in symbols.stems if _nearest_staff_for_stem(system, s) is staff]
        attached: dict[int, list[Head]] = defaultdict(list)
        used: set[int] = set()
        directions: dict[int, tuple[int, float]] = {}
        candidates: dict[int, list[tuple[int, Head]]] = {}
        roots: dict[int, Head] = {}
        for k, stem in enumerate(stems):
            lo, hi = sorted((stem.y0, stem.y1))
            beside = [
                (i, h)
                for i, h in enumerate(heads)
                if lo - 0.7 * sp <= h.y <= hi + 0.7 * sp
                and (
                    abs(stem.x0 - h.x) <= max(0.5, 0.18 * h.w)
                    or abs(stem.x0 - (h.x + h.w)) <= max(0.5, 0.18 * h.w)
                )
            ]
            if not beside:
                continue
            # the end of the stem at a notehead is its root; the other end is its tip
            near_lo = min(abs(h.y - lo) for _i, h in beside)
            near_hi = min(abs(h.y - hi) for _i, h in beside)
            if near_lo <= near_hi:
                direction, tip, root = 1, hi, lo
            else:
                direction, tip, root = -1, lo, hi
            if min(near_lo, near_hi) > 0.6 * sp:
                continue  # no notehead at either end: not a stem (a line of something else)
            candidates[k] = [
                (i, h)
                for i, h in beside
                if (
                    (root - 0.45 * sp <= h.y <= tip)
                    if direction == 1
                    else (tip <= h.y <= root + 0.45 * sp)
                )
            ]
            roots[k] = min(beside, key=lambda p: abs(p[1].y - root))[1]
            directions[k] = (direction, tip)
        for k, found_heads in candidates.items():
            # two voices with their stems the same way in one column draw two stems over each
            # other; a notehead at the root of another stem there is that stem's
            others = {
                id(roots[j])
                for j in candidates
                if j != k
                and abs(stems[j].x0 - stems[k].x0) < 0.3
                and directions[j][0] == directions[k][0]
            }
            for i, h in found_heads:
                if id(h) in others and h is not roots[k]:
                    continue
                attached[k].append(h)
                used.add(i)
        # a unison of two voices is drawn as two noteheads on top of each other, one for each
        # stem: give each stem one of them
        taken: set[int] = set()
        for k in sorted(attached, key=lambda k: stems[k].x0):
            unique: dict[tuple[float, float], Head] = {}
            for h in attached[k]:
                spot = (round(h.x, 1), round(h.y, 1))
                if spot not in unique or (id(unique[spot]) in taken and id(h) not in taken):
                    unique[spot] = h
            chosen = []
            for h in unique.values():
                if id(h) in taken:
                    h = replace(h)  # both stems on one drawn notehead: a copy for this one
                taken.add(id(h))
                chosen.append(h)
            attached[k] = chosen
        for k, group in attached.items():
            stem = stems[k]
            direction, tip = directions[k]
            # the column: where the notehead on the usual side of the stem is
            usual = [h for h in group if (h.x < stem.x0 - 0.2 * h.w) == (direction == 1)]
            ref = usual or group
            x = min(h.x for h in ref)
            ev = Event(system, staff, x, heads=sorted(group, key=lambda h: h.y))
            ev.stem, ev.stem_x, ev.tip = direction, stem.x0, tip
            ev.voice_hint = 1 if direction == 1 else 2
            events.append(ev)
        for i, h in enumerate(heads):
            if i in used:
                continue
            if h.base < 4:
                notes.append(
                    f"page {system.page}: a notehead with no stem at x={h.x:.0f} was read as it is"
                )
            events.append(Event(system, staff, h.x, heads=[h]))
        for g in glyphs:
            if g.text in RESTS:
                ev = Event(system, staff, g.x, rest=RESTS[g.text], rest_glyph=g)
                ev.measure_rest = g.text == WHOLE_REST
                ev.voice_hint = _rest_hint(g, staff)
                events.append(ev)
    _flags_and_beams(symbols, events)
    _dots(symbols, events)
    _tuplets(symbols, events)
    _shared_columns(events)
    return events


def _shared_columns(events: list[Event]) -> None:
    """Put a chord moved aside for a neighbour's notehead back in the column it stands in.

    Where two voices of a staff sing a second (or a unison of different noteheads) apart, the
    notation program moves one of them a notehead to the side; its syllable and its time are
    still those of the column.
    """
    chords = [e for e in events if e.heads and e.stem]
    for a in chords:
        for b in chords:
            if a is b or a.staff is not b.staff or a.stem != 1 or b.stem != -1:
                continue
            w = a.heads[0].w
            gap = b.x - a.x
            if not (0.5 * w <= abs(gap) <= 1.3 * w):
                continue
            near = min(abs(ha.y - hb.y) for ha in a.heads for hb in b.heads)
            crossed = max(hb.y for hb in b.heads) > min(ha.y for ha in a.heads)
            if near > 0.55 * a.staff.space and not crossed:
                continue
            column = min(a.x, b.x)
            a.x = b.x = column


def _nearest_staff_for_stem(system: System, stem: Segment) -> Staff:
    mid = (stem.y0 + stem.y1) / 2
    lo, hi = sorted((stem.y0, stem.y1))
    best = system.staves[0]
    best_d = 1e9
    for s in system.staves:
        # the end of the stem at a notehead is the nearer to the staff
        d = min(
            0.0 if s.bottom <= y <= s.top else min(abs(y - s.top), abs(y - s.bottom))
            for y in (lo, hi, mid)
        )
        if d < best_d:
            best, best_d = s, d
    return best


def _rest_hint(g: Glyph, staff: Staff) -> int:
    sp = staff.space
    usual = staff.lines[1] if g.text == WHOLE_REST else staff.middle
    if g.text == "":  # a half rest sits on the middle line
        usual = staff.middle
    offset = g.y - usual
    if offset >= 0.9 * sp:
        return 1
    if offset <= -0.9 * sp:
        return 2
    return 0


def _flags_and_beams(symbols: SystemSymbols, events: list[Event]) -> None:
    sp = symbols.system.space
    # a flag is found by its stem, wherever it is (one high over the staff can be nearer the
    # system above)
    flags = [g for g in symbols.page.glyphs if g.text in FLAGS]
    for ev in events:
        if not ev.stem:
            continue
        for g in flags:
            count, _up = FLAGS[g.text]
            if abs(g.x - ev.stem_x) <= 0.8 and abs(g.y - ev.tip) <= 1.2 * sp:
                ev.halvings = max(ev.halvings, count)
        found = 0
        for k, beam in enumerate(symbols.beams):
            x0, _y0, x1, _y1 = beam.bbox
            if not (x0 - 0.4 <= ev.stem_x <= x1 + 0.4):
                continue
            extent = _vertical_extent(beam, ev.stem_x)
            if extent is None or extent[1] - extent[0] > 1.2 * sp:
                continue
            lo, hi = extent
            if (ev.stem == 1 and ev.tip - 3.6 * sp <= lo and hi <= ev.tip + 0.4 * sp) or (
                ev.stem == -1 and ev.tip - 0.4 * sp <= lo and hi <= ev.tip + 3.6 * sp
            ):
                found += 1
                ev.beams.append(k)
        ev.halvings = max(ev.halvings, found)


def _dots(symbols: SystemSymbols, events: list[Event]) -> None:
    sp = symbols.system.space
    for staff in symbols.system.staves:
        dots = sorted(
            (g for g in symbols.glyphs[staff.index] if g.text == AUGMENTATION_DOT),
            key=lambda g: g.x,
        )
        owners: list[tuple[float, float, Event, Head | None]] = []
        for ev in events:
            if ev.staff is not staff:
                continue
            if ev.rest_glyph is not None:
                g = ev.rest_glyph
                owners.append((g.x + g.width, g.y, ev, None))
            for h in ev.heads:
                owners.append((h.x + h.w, h.y, ev, h))
        # dots in a column right of notes (the first dot of each); a further dot of a double dot
        # stands right of one of them at the same height
        firsts = [
            d
            for d in dots
            if not any(0 < d.x - o.x <= 1.3 * sp and abs(o.y - d.y) < 0.1 for o in dots)
        ]
        columns: list[list[Glyph]] = []
        for d in sorted(firsts, key=lambda d: d.x):
            if columns and d.x - columns[-1][0].x <= 0.5 * sp:
                columns[-1].append(d)
            else:
                columns.append([d])
        owner_of: dict[int, tuple[Event, Head | None]] = {}
        for column in columns:
            options = [_dot_owners(d, owners, sp) for d in column]
            best_cost = float("inf")
            best_pick: list[tuple[Event, Head | None] | None] = []
            for pick in itertools.product(*[[*o, None] for o in options]):
                chosen = [p for p in pick if p is not None]
                keys = [id(p[2]) if p[2] is not None else id(p[1]) for p in chosen]
                if len(keys) != len(set(keys)):
                    continue  # one note, one dot in a column
                cost = sum(p[0] if p is not None else 5.0 for p in pick)
                if cost < best_cost:
                    best_cost = cost
                    best_pick = [None if p is None else (p[1], p[2]) for p in pick]
            for d, p in zip(column, best_pick, strict=False):
                if p is not None:
                    owner_of[id(d)] = p
        for d in sorted(dots, key=lambda d: d.x):
            if id(d) not in owner_of:
                left = [
                    o
                    for o in dots
                    if 0 < d.x - o.x <= 1.3 * sp and abs(o.y - d.y) < 0.1 and id(o) in owner_of
                ]
                if not left:
                    continue
                owner_of[id(d)] = owner_of[id(max(left, key=lambda o: o.x))]
            ev, head = owner_of[id(d)]
            if head is not None:
                head.dots += 1
            else:
                ev.dots += 1
        # a notehead both voices sing is drawn once, with one set of dots for both
        spots: dict[tuple[float, float], int] = {}
        for ev in events:
            if ev.staff is staff:
                for h in ev.heads:
                    spot = (round(h.x, 1), round(h.y, 1))
                    spots[spot] = max(spots.get(spot, 0), h.dots)
        for ev in events:
            if ev.staff is staff and ev.heads:
                for h in ev.heads:
                    h.dots = spots[(round(h.x, 1), round(h.y, 1))]
                ev.dots = max(h.dots for h in ev.heads)


def _dot_owners(
    d: Glyph, owners: list[tuple[float, float, Event, Head | None]], sp: float
) -> list[tuple[float, Event, Head | None]]:
    """The notes (or rests) a dot can belong to, with how well it fits each."""
    found: list[tuple[float, Event, Head | None]] = []
    for right, y, ev, head in owners:
        dx = d.x - right
        dy = abs(d.y - y)
        if head is not None:
            # a dot is level with a note in a space; for a note on a line it is in the space
            # above, or below for the lower voice (a stem down) of two
            on_line = head.staff.position(head.y) % 2 == 0
            signed = d.y - head.y
            if on_line:
                prefer = -0.5 * sp if ev.stem == -1 else 0.5 * sp
                miss = min(abs(signed - prefer), abs(signed + prefer) + 0.2 * sp)
            else:
                miss = abs(signed)
            if miss > 0.3 * sp or not (-0.2 <= dx <= 3.5 * sp):
                continue
            found.append((4 * miss / sp + 0.2 * dx / sp, ev, head))
        else:
            if dy > 2.5 * sp or not (-0.2 <= dx <= 2.2 * sp):
                continue
            found.append((1.0 + 0.2 * dx / sp, ev, head))
    return sorted(found, key=lambda f: f[0])[:4]


def _tuplets(symbols: SystemSymbols, events: list[Event]) -> None:
    sp = symbols.system.space
    for staff in symbols.system.staves:
        # (x, y, the number, written as text); digits side by side make one number
        digits = sorted(
            [(g, False) for g in symbols.glyphs[staff.index] if g.text in TUPLET_DIGITS]
            + [(g, True) for g in symbols.digits[staff.index]],
            key=lambda p: p[0].x,
        )
        numbers: list[tuple[float, float, int, bool]] = []
        for g, text in digits:
            value = int(g.text) if text else TUPLET_DIGITS[g.text]
            if (
                numbers
                and abs(numbers[-1][1] - g.y) < 0.2
                and g.x - numbers[-1][0] < 1.5 * sp
                and numbers[-1][3] == text
            ):
                x, y, n, _t = numbers[-1]
                numbers[-1] = (x, y, n * 10 + value, text)
            else:
                numbers.append((g.x, g.y, value, text))
        for x, y, n, text in numbers:
            members = _tuplet_members(symbols, events, staff, x, y, beamed_only=text)
            if not members or n < 2:
                continue
            normal = {2: 3, 3: 2, 4: 3, 5: 4, 6: 4, 7: 4, 9: 8, 10: 8, 11: 8, 12: 8}.get(n, 2)
            if n == 4 and len(members) != 4:
                normal = 3
            for ev in members:
                ev.tuplet = Fraction(normal, n)
                ev.tuplet_shown = (n, normal)


def _tuplet_members(
    symbols: SystemSymbols,
    events: list[Event],
    staff: Staff,
    x: float,
    y: float,
    *,
    beamed_only: bool = False,
) -> list[Event]:
    sp = staff.space
    near = [ev for ev in events if ev.staff is staff]
    above = [ev for ev in near if ev.stem == 1 and y >= ev.tip - sp]
    below = [ev for ev in near if ev.stem == -1 and y <= ev.tip + sp]
    for group in (above, below):
        for ev in group:
            for k in ev.beams:
                beam = symbols.beams[k]
                if beam.bbox[0] - sp <= x <= beam.bbox[2] + sp and (
                    abs(y - beam.bbox[1]) < 3 * sp or abs(y - beam.bbox[3]) < 3 * sp
                ):
                    members = [e for e in group if k in e.beams]
                    if len(members) >= 2:
                        return sorted(members, key=lambda e: e.x)
    if beamed_only:
        return []
    # a bracket: lines at the number's height on both sides of it (not staff lines)
    staff_lines = [ln for s in symbols.system.staves for ln in s.lines]
    left = right = x
    for s in symbols.page.segments:
        if abs(s.y0 - y) > 1.5 * sp and abs(s.y1 - y) > 1.5 * sp:
            continue
        if abs(s.y0 - s.y1) < 0.01 and any(abs(s.y0 - ln) < 0.1 for ln in staff_lines):
            continue
        a, b = sorted((s.x0, s.x1))
        if b - a < 0.2 * sp:
            continue
        if a < x and x - b < 4 * sp:
            left = min(left, a)
        if b > x and a - x < 4 * sp:
            right = max(right, b)
    if right - left > 2 * sp:
        side = above if y > staff.middle else below
        pool = side or near
        return sorted(
            (ev for ev in pool if left - 0.5 * sp <= ev.x <= right + 0.5 * sp),
            key=lambda e: e.x,
        )
    return []


# --- measures, voices and time ----------------------------------------------------------------


def measure_of(boundaries_x: list[float], x: float) -> int | None:
    for i in range(len(boundaries_x) - 1):
        if boundaries_x[i] < x < boundaries_x[i + 1]:
            return i
    return None


def assign_voices(
    events: list[Event], target: Fraction, head_width: float
) -> tuple[Fraction, float, list[Event]]:
    """Give each event of one staff in one measure its voice and onset.

    Returns (the length the voices fill, the cost of the best reading: 0 when everything fits,
    the events added for a notehead both voices sing).
    """
    music = [e for e in events if not (bool(e.heads) and all(h.small for h in e.heads))]
    for e in events:
        if e not in music:
            e.voice = e.voice_hint or 1
    if not music:
        return target, 0, []
    options: list[tuple[float, Fraction, list[int]]] = []
    two = _best_two_voice(music, target, head_width)
    if two is not None:
        options.append(two)
    one = _single_voice(music, target, head_width)
    if one is not None:
        options.append(one)
    cost, length, voices = min(options, key=lambda o: o[0])
    added: list[Event] = []
    final: list[Event] = []
    final_voices: list[int] = []
    for e, v in zip(music, voices, strict=True):
        if v == 3:
            twin = replace(e, heads=[replace(h) for h in e.heads], lyrics=[], beams=list(e.beams))
            e.voice, twin.voice = 1, 2
            added.append(twin)
            final.extend((e, twin))
            final_voices.extend((1, 2))
        else:
            e.voice = v
            final.append(e)
            final_voices.append(v)
    _set_onsets(final, final_voices, length, head_width)
    return length, cost, added


def _length(e: Event, measure: Fraction) -> Fraction:
    return measure if e.measure_rest else e.written()


def _same_column(a: Event, b: Event, hw: float) -> bool:
    """Whether two events stand in one column: at one x, or moved a notehead aside because
    their noteheads would touch (a second or a unison on one staff)."""
    if abs(a.x - b.x) < 0.3 * hw:
        return True
    if a.staff is not b.staff or not a.heads or not b.heads:
        return False
    if not (0.5 * hw <= abs(a.x - b.x) <= 1.3 * hw):
        return False
    sp = a.staff.space
    return min(abs(ha.y - hb.y) for ha in a.heads for hb in b.heads) <= 0.55 * sp


def _timeline(
    group: list[Event], measure: Fraction, full: list[tuple[Event, Fraction]], hw: float
) -> tuple[list[Fraction], int]:
    """Onsets of a voice's events (in x order), and the cost of the timing.

    A voice that does not fill its measure has a gap where its rest was left out (a notation
    program lets a voice begin later or pause without drawing a rest); its notes then stand in
    the columns of the voice that does fill the measure, and take their times from there.
    """
    onsets: list[Fraction] = []
    cost = 0
    t = Fraction(0)
    missing = measure - sum((_length(e, measure) for e in group), Fraction(0))
    for e in group:
        match = next((ft for f, ft in full if _same_column(f, e, hw)), None)
        if match is not None:
            if match > t:
                missing -= match - t
                t = match
            elif match < t:
                cost += 3
        elif missing > 0:
            # standing right of a column of time t, it is later than t: the left-out rest is
            # before it
            before = [(f.x, ft) for f, ft in full if f.x < e.x - 0.3 * hw and ft >= t]
            if before:
                _x, at = max(before)
                later = [ft for f, ft in full if f.x > e.x + 0.6 * hw and ft > at]
                rest = sum((_length(g, measure) for g in group[group.index(e) :]), Fraction(0))
                gap = min(
                    [missing, measure - rest - at, *[ft - at - _length(e, measure) for ft in later]]
                )
                if gap > 0:
                    missing -= at + gap - t
                    t = at + gap
        onsets.append(t)
        t += _length(e, measure)
    if t > measure or (t < measure and not full):
        cost += 10
    elif t < measure:
        cost += 1
    return onsets, cost


def _voices_timed(
    events: list[Event], voices: list[int], measure: Fraction, hw: float
) -> tuple[dict[int, list[tuple[Event, Fraction]]], int]:
    groups = {v: _voice_events(events, voices, v) for v in (1, 2)}
    sums = {v: sum((_length(e, measure) for e in g), Fraction(0)) for v, g in groups.items() if g}
    timed: dict[int, list[tuple[Event, Fraction]]] = {}
    cost = 0
    full_voices = [v for v, s in sums.items() if s == measure]
    for v in full_voices:
        onsets, c = _timeline(groups[v], measure, [], hw)
        timed[v] = list(zip(groups[v], onsets, strict=True))
        cost += c
    reference = [p for v in full_voices for p in timed[v]]
    for v, g in groups.items():
        if not g or v in timed:
            continue
        onsets, c = _timeline(g, measure, reference, hw)
        timed[v] = list(zip(g, onsets, strict=True))
        cost += c
    return timed, cost


def retime_short_voices(events: list[Event], measure: Fraction, hw: float) -> None:
    """Time again each voice of a measure that does not fill it, by the columns of every voice
    that does on any staff of the system (a staff holding one long note has no other columns)."""
    lines: dict[tuple[int, int], list[Event]] = defaultdict(list)
    for e in events:
        if not (bool(e.heads) and all(h.small for h in e.heads)):
            lines[(e.staff.index, e.voice)].append(e)
    full: list[tuple[Event, Fraction]] = []
    short: list[list[Event]] = []
    for group in lines.values():
        group.sort(key=lambda e: e.x)
        total = sum((e.duration for e in group), Fraction(0))
        if total == measure:
            full.extend((e, e.onset) for e in group)
        elif total < measure:
            short.append(group)
    for group in short:
        onsets, _cost = _timeline(group, measure, full, hw)
        for e, t in zip(group, onsets, strict=True):
            e.onset = t


def _set_onsets(events: list[Event], voices: list[int], measure: Fraction, hw: float) -> None:
    timed, _cost = _voices_timed(events, voices, measure, hw)
    for pairs in timed.values():
        for e, t in pairs:
            e.onset = t
            e.duration = _length(e, measure)


def _single_voice(
    events: list[Event], target: Fraction, hw: float
) -> tuple[float, Fraction, list[int]] | None:
    ordered = sorted(events, key=lambda e: e.x)
    cost = 0
    for a, b in itertools.pairwise(ordered):
        if abs(a.x - b.x) < 0.45 * hw:
            cost += 20  # two things in one column: not one voice
    total = sum((_length(e, target) for e in events), Fraction(0))
    if total != target:
        cost += 8
    return cost + 1, total, [1] * len(events)


def _partnered(e: Event, events: list[Event], hw: float) -> bool:
    """Whether the other voice stands in the same column (its stem the other way): only then
    does the stem say which voice a note is in; elsewhere a program turns the stems of a voice
    by the pitch, as for a single voice."""
    return any(
        f is not e and f.voice_hint and f.voice_hint != e.voice_hint and _same_column(e, f, hw)
        for f in events
    )


def _best_two_voice(
    events: list[Event], target: Fraction, hw: float
) -> tuple[float, Fraction, list[int]] | None:
    unknown = [i for i, e in enumerate(events) if not e.voice_hint]
    soft = [i for i, e in enumerate(events) if e.voice_hint and not _partnered(e, events, hw)]
    if len(unknown) + len(soft) > 10:
        soft = []  # too many to try: the stems decide
    unknown = unknown[:9]
    free = unknown + soft
    best: tuple[float, Fraction, list[int]] | None = None
    options = [
        (1, 2, 3)
        if i in unknown and not (events[i].is_rest and not events[i].measure_rest)
        else (1, 2)
        for i in free
    ]
    for choice in itertools.product(*options):
        voices = [e.voice_hint or 1 for e in events]
        against = 0.0
        for i, v in zip(free, choice, strict=True):
            voices[i] = v
            if events[i].voice_hint and v != events[i].voice_hint:
                against += 0.6  # a stem against its voice: allowed where no other voice sounds
        if all(v == 2 for v in voices):
            against += 2  # a voice 2 alone is one voice
        for length in _candidate_lengths(events, voices, target):
            cost = _two_voice_cost(events, voices, length, hw) + against
            if length != target:
                cost += 1
            if best is None or cost < best[0]:
                best = (cost, length, voices)
    return best


def _voice_events(events: list[Event], voices: list[int], voice: int) -> list[Event]:
    return sorted(
        (e for e, v in zip(events, voices, strict=True) if v == voice or v == 3),
        key=lambda e: e.x,
    )


def _candidate_lengths(events: list[Event], voices: list[int], target: Fraction) -> list[Fraction]:
    found = [target]
    for voice in (1, 2):
        group = _voice_events(events, voices, voice)
        if group and not any(e.measure_rest for e in group):
            total = sum((e.written() for e in group), Fraction(0))
            if total not in found and 0 < total < target:
                found.append(total)
    return found


def _two_voice_cost(events: list[Event], voices: list[int], measure: Fraction, hw: float) -> int:
    cost = 0
    for voice in (1, 2):
        group = _voice_events(events, voices, voice)
        for a, b in itertools.pairwise(group):
            if abs(a.x - b.x) < 0.45 * hw:
                cost += 20
    by_voice, timing_cost = _voices_timed(events, voices, measure, hw)
    cost += timing_cost
    timed = [(e, t, v) for v, pairs in by_voice.items() for e, t in pairs]
    for (a, ta, va), (b, tb, vb) in itertools.combinations(timed, 2):
        if va == vb or a is b:
            continue
        same_column = abs(a.x - b.x) < 0.6 * hw
        if (same_column and ta != tb) or (
            not same_column and (a.x < b.x) != (ta < tb) and ta != tb
        ):
            cost += 3
        elif not same_column and ta == tb and abs(a.x - b.x) > 1.6 * hw:
            cost += 1
    return cost


# --- signatures and pitch ----------------------------------------------------------------------


def read_clefs(glyphs: list[Glyph], staff: Staff) -> list[tuple[float, Clef]]:
    found: list[tuple[float, Clef]] = []
    for g in glyphs:
        if g.text not in CLEFS:
            continue
        sign, _line, octave = CLEFS[g.text]
        line = round((g.y - staff.bottom) / staff.space) + 1  # the line the clef stands on
        found.append((g.x, (sign, line, octave)))
    return sorted(found)


def read_times(glyphs: list[Glyph], staff: Staff) -> list[tuple[float, tuple[int, int], str]]:
    sp = staff.space
    items = sorted(
        (g for g in glyphs if g.text in TIME_DIGITS or g.text in (TIME_COMMON, TIME_CUT)),
        key=lambda g: g.x,
    )
    groups: list[list[Glyph]] = []
    for g in items:
        if groups and g.x - max(h.x + h.width for h in groups[-1]) < 0.8 * sp:
            groups[-1].append(g)
        else:
            groups.append([g])
    result: list[tuple[float, tuple[int, int], str]] = []
    for group in groups:
        x = min(g.x for g in group)
        if any(g.text == TIME_COMMON for g in group):
            result.append((x, (4, 4), "common"))
            continue
        if any(g.text == TIME_CUT for g in group):
            result.append((x, (2, 2), "cut"))
            continue
        top = sorted((g for g in group if g.y > staff.middle), key=lambda g: g.x)
        bottom = sorted((g for g in group if g.y <= staff.middle), key=lambda g: g.x)
        if not top or not bottom:
            continue
        num = int("".join(str(TIME_DIGITS[g.text]) for g in top))
        den = int("".join(str(TIME_DIGITS[g.text]) for g in bottom))
        if num > 0 and den in (1, 2, 4, 8, 16, 32):
            result.append((x, (num, den), ""))
    return result


# staff positions (half spaces above the bottom line) of the accidentals of a key signature, in
# the order they are written, on a treble staff; a bass staff has them two positions lower
_KEY_FLATS = (4, 7, 3, 6, 2, 5, 1)
_KEY_SHARPS = (8, 5, 9, 6, 3, 7, 4)


def key_accidentals(
    glyphs: list[Glyph],
    heads: list[Head],
    staff: Staff,
    clef: tuple[str, int, int],
    firsts: list[tuple[float, float, float]],
) -> list[Glyph]:
    """The accidentals of key signatures: before the first note of a measure, in the order and
    at the staff positions a key signature has (a chord's own accidentals can stand there too)."""
    if clef[0] == "G":
        shift = 2 * (clef[1] - 2)
    elif clef[0] == "F":
        shift = 2 * (clef[1] - 4) - 2
    else:
        shift = None
    found: list[Glyph] = []
    for start, _end, first in firsts:
        before = sorted(
            (
                g
                for g in glyphs
                if g.text in ACCIDENTALS
                and ACCIDENTALS[g.text] != 99
                and start <= g.x < first
                and not _right_before_a_note(g, heads, staff.space)
                and not _in_parentheses(g, glyphs, staff.space)
            ),
            key=lambda g: g.x,
        )
        index = {"flat": 0, "sharp": 0}
        last_x: float | None = None
        for g in before:
            alter = ACCIDENTALS[g.text]
            if last_x is not None and g.x - last_x > 1.8 * staff.space:
                break  # a gap: what follows belongs to a note
            position = staff.position(g.y)
            if alter == 0:
                if shift is None or any(
                    position - shift in (pattern[i], pattern[i] - 7)
                    for pattern in (_KEY_FLATS, _KEY_SHARPS)
                    for i in range(7)
                ):
                    found.append(g)
                    last_x = g.x
                    continue
                break
            kind = "flat" if alter == -1 else "sharp" if alter == 1 else None
            if kind is None or index[kind] >= 7:
                break
            pattern = _KEY_FLATS if kind == "flat" else _KEY_SHARPS
            if shift is not None and position - shift not in (
                pattern[index[kind]],
                pattern[index[kind]] - 7,
                pattern[index[kind]] + 7,
            ):
                break
            index[kind] += 1
            found.append(g)
            last_x = g.x
    return found


def _in_parentheses(g: Glyph, glyphs: list[Glyph], sp: float) -> bool:
    """A courtesy accidental in parentheses, which belongs to a note (a key signature has
    none)."""
    return any(
        ACCIDENTALS.get(p.text) == 99 and abs(p.y - g.y) <= 0.5 * sp and abs(p.x - g.x) <= 1.2 * sp
        for p in glyphs
    )


def _right_before_a_note(g: Glyph, heads: list[Head], sp: float) -> bool:
    return any(
        abs(h.y - g.y) <= 0.3 * sp and -0.3 <= h.x - (g.x + g.width) <= 0.6 * sp for h in heads
    )


def attach_accidentals(glyphs: list[Glyph], heads: list[Head], staff: Staff) -> None:
    """Give each accidental to the notehead it stands in front of."""
    sp = staff.space
    for g in sorted(glyphs, key=lambda g: -g.x):  # the nearest column first
        alter = ACCIDENTALS.get(g.text)
        if alter is None or alter == 99:
            continue
        best: Head | None = None
        for h in heads:
            gap = h.x - (g.x + g.width)
            if abs(h.y - g.y) > 0.3 * sp or not (-0.3 <= gap <= 4.5 * sp):
                continue
            if best is None or h.x < best.x:
                best = h
        if best is not None and best.accidental is None:
            best.accidental = alter


def key_from(accidentals: list[Glyph]) -> int | None:
    sharps = sum(1 for g in accidentals if ACCIDENTALS[g.text] == 1)
    flats = sum(1 for g in accidentals if ACCIDENTALS[g.text] == -1)
    naturals = sum(1 for g in accidentals if ACCIDENTALS[g.text] == 0)
    if sharps and not flats:
        return min(7, sharps)
    if flats and not sharps:
        return -min(7, flats)
    if naturals and not sharps and not flats:
        return 0
    return None


_SHARP_ORDER = "FCGDAEB"


def key_alter(fifths: int, step: str) -> int:
    if fifths > 0 and step in _SHARP_ORDER[:fifths]:
        return 1
    if fifths < 0 and step in _SHARP_ORDER[::-1][:-fifths]:
        return -1
    return 0


def pitch_of(head: Head, clef: Clef) -> tuple[str, int]:
    """(step, octave) of a notehead under ``clef``, before accidentals.

    An octave clef (the tenor's treble clef with an 8 below) moves the pitch an octave from where
    the note is drawn; MusicXML has the pitch so moved, with the clef's octave change beside it.
    """
    sign, line, octave_change = clef
    if sign not in CLEF_REFERENCE:
        sign, line = "G", 2
    step, octave = CLEF_REFERENCE[sign]
    clef_position = (line - 1) * 2
    d = diatonic(step, octave) + head.staff.position(head.y) - clef_position + 7 * octave_change
    return STEPS[d % 7], d // 7


def spell(
    events: list[Event],
    measures: list[MeasureInfo],
    clef_at: dict[int, list[tuple[int, float, Clef]]],
    key_at: dict[int, list[tuple[int, int]]],
) -> None:
    """Give every notehead its pitch: clef, key signature and the accidentals of its measure."""
    by_staff: dict[int, list[Event]] = defaultdict(list)
    for e in events:
        if e.heads:
            by_staff[e.staff.index].append(e)
    for staff_index, group in by_staff.items():
        group.sort(key=lambda e: (e.measure, e.x))
        clefs = clef_at.get(staff_index, [])
        keys = key_at.get(staff_index, [])
        state: dict[int, int] = {}
        current = -1
        for e in group:
            if e.measure != current:
                state = {}
                current = e.measure
            clef = _clef_for(clefs, e.measure, e.x)
            fifths = 0
            for m, k in keys:
                if m <= e.measure:
                    fifths = k
            for h in sorted(e.heads, key=lambda h: h.x):
                step, octave = pitch_of(h, clef)
                h.step, h.octave = step, octave
                d = h.diatonic
                if h.accidental is not None:
                    state[d] = h.accidental
                    h.alter = h.accidental
                elif h.tied_from is not None and h.tied_from.diatonic == d:
                    # a note tied over the barline keeps its accidental, and so does the line
                    # or space it is on for the rest of the measure
                    h.alter = h.tied_from.alter
                    state[d] = h.alter
                elif d in state:
                    h.alter = state[d]
                else:
                    h.alter = key_alter(fifths, step)
    del measures


def _clef_for(clefs: list[tuple[int, float, Clef]], measure: int, x: float) -> Clef:
    chosen: Clef = ("G", 2, 0)
    for m, cx, clef in clefs:
        if (m, cx) <= (measure, x):
            chosen = clef
    return chosen


# --- ties ---------------------------------------------------------------------------------------


def read_ties(
    symbols: SystemSymbols, events: list[Event], reach: float = 0.95
) -> list[tuple[Shape, Head, bool]]:
    """Mark the ties among the curves of the system. Returns each curve read as a tie with the
    notehead it was given to and whether it is the end of the tie there (whether it stays a tie is
    known once the pitches are)."""
    system = symbols.system
    taken: list[tuple[Shape, Head, bool]] = []
    halves: dict[int, tuple[float, Shape]] = {}
    last_x = max((e.x for e in events if e.system is system), default=system.x0)
    half_heads: dict[int, Head] = {}
    sp = system.space
    heads = [(h, e) for e in events if e.system is system for h in e.heads]
    for curve in symbols.curves:
        pts = curve.points
        left = min(pts, key=lambda p: p[0])
        right = max(pts, key=lambda p: p[0])
        if right[0] - left[0] < 0.8 * sp:
            continue
        # a tie is flat, its two ends level; a slur rises between notes of different heights
        if abs(left[1] - right[1]) > 0.35 * sp:
            continue
        a = _head_near(heads, left, sp, start=True, reach=reach)
        b = _head_near(heads, right, sp, start=False, reach=reach)
        if a is not None and (
            b is None or b[0].staff.position(b[0].y) != a[0].staff.position(a[0].y)
        ):
            # a note moved aside (voices crossing) leaves the end of its tie short of it
            position = a[0].staff.position(a[0].y)
            ahead = [
                (h, e)
                for h, e in heads
                if h.staff is a[0].staff
                and h.staff.position(h.y) == position
                and right[0] - sp <= h.x <= right[0] + 4 * sp
                and h.x > a[0].x
            ]
            if ahead:
                b = min(ahead, key=lambda p: p[0].x)
        if a is not None and b is not None:
            if (
                a[0].staff is b[0].staff
                and a[0].staff.position(a[0].y) == b[0].staff.position(b[0].y)
                and b[0].x > a[0].x
            ):
                a[0].tie_start = True
                b[0].tie_stop = True
                a[0].tied_to, b[0].tied_from = b[0], a[0]
                taken.append((curve, a[0], False))
        elif a is not None and right[0] >= system.music_end(last_x) - 2.5 * sp:
            a[0].tie_start = True
            taken.append((curve, a[0], False))
            continue
        if a is None and b is None and left[0] <= system.x0 + 20 * sp:
            # the second half of a tie whose note is moved aside (voices crossing) ends short of
            # it: the note at its height just after its end
            ahead = [
                (h, e)
                for h, e in heads
                if abs(h.y - right[1]) <= 0.95 * sp and right[0] - sp <= h.x <= right[0] + 3 * sp
            ]
            if ahead:
                # a tie lies about three quarters of a space off its notehead, never on it
                b = min(
                    ahead,
                    key=lambda p: (
                        abs(abs(p[0].y - right[1]) / sp - 0.73) + 0.05 * (p[0].x - right[0]) / sp
                    ),
                )
        if (
            a is None
            and b is not None
            and left[0] <= _first_content_x(system, events, b[1].staff) + sp
        ):
            # the second half of a tie over a line break; a slur going on from the line before
            # can end at the same note: the curve nearer the notehead is the tie
            hug = abs(right[1] - b[0].y)
            if hug < halves.get(id(b[0]), (1e9, curve))[0]:
                halves[id(b[0])] = (hug, curve)
                half_heads[id(b[0])] = b[0]
    for key, (_hug, curve) in halves.items():
        half_heads[key].tie_stop = True
        taken.append((curve, half_heads[key], True))
    return taken


def _first_content_x(system: System, events: list[Event], staff: Staff) -> float:
    xs = [e.x for e in events if e.system is system and e.staff is staff]
    return min(xs) if xs else system.x0


def tie_reach(symbols: SystemSymbols, events: list[Event]) -> float:
    """How far from its noteheads a tie may end, in spaces: a little more than the farthest tie
    of this system lies (a font's ties lie at their own distance: three quarters of a space for
    Leland, up to one and a fifth for a hand-written style such as Petaluma); at least 0.95."""
    sp = symbols.system.space
    heads = [(h, e) for e in events if e.system is symbols.system for h in e.heads]
    found: list[float] = []
    for curve in symbols.curves:
        left = min(curve.points, key=lambda p: p[0])
        right = max(curve.points, key=lambda p: p[0])
        if right[0] - left[0] < 0.8 * sp or abs(left[1] - right[1]) > 0.35 * sp:
            continue
        a = _head_near(heads, left, sp, start=True, reach=1.6)
        b = _head_near(heads, right, sp, start=False, reach=1.6)
        if a is None or b is None or a[0].staff is not b[0].staff:
            continue
        if a[0].staff.position(a[0].y) != b[0].staff.position(b[0].y):
            continue
        found.append((abs(left[1] - a[0].y) + abs(right[1] - b[0].y)) / 2 / sp)
    if not found:
        return 0.95
    # ties come at one or two distances (over a line or in a space); a slur ends two spaces or
    # more off its notes
    return max(0.95, min(1.5, max(found) + 0.15))


def _head_near(
    heads: list[tuple[Head, Event]],
    point: tuple[float, float],
    sp: float,
    *,
    start: bool,
    reach: float = 0.95,
) -> tuple[Head, Event] | None:
    best: tuple[float, Head, Event] | None = None
    for h, e in heads:
        dy = abs(h.y - point[1])
        if dy > reach * sp:  # a tie ends close to its notehead; a slur ends further off
            continue
        if start:
            dx = point[0] - (h.x + h.w / 2)
            ok = -0.2 * h.w <= dx <= h.w / 2 + 1.2 * sp
        else:
            dx = (h.x + h.w / 2) - point[0]
            ok = -0.2 * h.w <= dx <= h.w / 2 + 1.2 * sp
        if not ok:
            continue
        score = abs(dx) + 2 * dy
        if best is None or score < best[0]:
            best = (score, h, e)
    return None if best is None else (best[1], best[2])


__all__ = [
    "SystemSymbols",
    "assign_voices",
    "attach_accidentals",
    "key_accidentals",
    "key_from",
    "measure_of",
    "read_clefs",
    "read_events",
    "read_ties",
    "read_times",
    "spell",
    "tie_reach",
]
