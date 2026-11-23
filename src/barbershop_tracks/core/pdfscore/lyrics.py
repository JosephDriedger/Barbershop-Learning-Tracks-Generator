"""Reading the words: which syllable is sung on which note, how words are split, how long lines run.

A notation program centres each syllable on its note, draws a hyphen between the syllables of one
word (shortened, but drawn, when the space is tight) and an underscore line after a syllable that
is held over several notes. The words of one row are text on one baseline. Where two syllables
touch (the program had no room for a gap), the row is split where it puts each syllable under a
note, so "thecoun" under two notes becomes "the" and "coun"; with no hyphen between them they are
two words.
"""

import unicodedata
from collections import defaultdict
from dataclasses import dataclass

from barbershop_tracks.core.pdfscore.layout import Staff, System
from barbershop_tracks.core.pdfscore.model import Event, LineGoesOn, LyricOut
from barbershop_tracks.core.pdfscore.pdf import Glyph, Page, Segment
from barbershop_tracks.core.pdfscore.symbols import is_music_symbol


@dataclass(slots=True)
class Row:
    y: float
    size: float
    font: str
    glyphs: list[Glyph]
    hyphens: list[Segment]
    lines: list[Segment]  # underscore lines


@dataclass(slots=True)
class _Group:
    chars: list[Glyph]
    hyphen_after: bool = False
    hyphen_before: bool = False
    extend_to: float | None = None
    whole: bool = False  # written as one text of its own: one syllable, never split
    spaced: bool = False  # one text with a space in it (several words)

    @property
    def x0(self) -> float:
        return self.chars[0].x

    @property
    def x1(self) -> float:
        return self.chars[-1].x + self.chars[-1].width

    @property
    def center(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def text(self) -> str:
        # ligatures (ﬁ, ﬂ) as the letters they join; an elision as the undertie
        text = "".join(UNDERTIE if c.text in ELISIONS else c.text for c in self.chars)
        return unicodedata.normalize("NFKC", text)


# an elision (two syllables sung on one note, "the" and "ir" joined by an undertie):
# SMuFL's lyrics elisions and the undertie character
UNDERTIE = chr(0x203F)
ELISIONS = frozenset({chr(0xE550), chr(0xE551), chr(0xE552), UNDERTIE})


def is_plain_text(g: Glyph) -> bool:
    name = g.font.lower()
    if g.text in ELISIONS:
        return True
    return not is_music_symbol(g.text) and "bold" not in name and "italic" not in name


def _band_distance(system: System, y: float) -> float:
    if system.bottom <= y <= system.top:
        return 0.0
    return min(abs(y - system.top), abs(y - system.bottom))


def text_rows(page: Page, system: System, systems: list[System] | None = None) -> list[Row]:
    """The rows of plain text that belong to ``system``: near it, and nearer it than any other
    of ``systems`` (the systems of the page)."""
    sp = system.space
    others = [s for s in (systems or []) if s is not system]
    found: dict[tuple[float, str, float], list[Glyph]] = defaultdict(list)
    for g in page.glyphs:
        if not is_plain_text(g):
            continue
        if not (system.x0 - 2 <= g.x <= system.x1 + 2):
            continue
        if not (system.bottom - 16 * sp <= g.y <= system.top + 12 * sp):
            continue
        if any(_band_distance(o, g.y) < _band_distance(system, g.y) - 12 * sp for o in others):
            continue  # much nearer another system
        # one row: one font and size, baselines within a fraction of a point (a program can
        # place the words of one row a little higher in one measure than in the next)
        key = next(
            (
                k
                for k in found
                if (g.text in ELISIONS or (k[1] == g.font and k[2] == round(g.size, 1)))
                and abs(k[0] - g.y) < 0.6
            ),
            (g.y, g.font, round(g.size, 1)),
        )
        found[key].append(g)
    rows: list[Row] = []
    for (_y, font, size), glyphs in found.items():
        glyphs.sort(key=lambda g: g.x)
        y = sorted(g.y for g in glyphs)[len(glyphs) // 2]
        hyphens: list[Segment] = []
        lines: list[Segment] = []
        for s in page.segments:
            if abs(s.y0 - s.y1) > 0.01 or not (system.x0 - 2 <= min(s.x0, s.x1) <= system.x1):
                continue
            dy = s.y0 - y
            length = abs(s.x1 - s.x0)
            if 0.1 * size <= dy <= 0.42 * size and length <= 1.1 * size:
                hyphens.append(s)
            elif -0.2 * size <= dy <= 0.1 * size and length >= 0.2 * size:
                lines.append(s)
        rows.append(Row(y, size, font, glyphs, hyphens, lines))
    return rows


def _tokens(row: Row) -> list[_Group]:
    groups: list[_Group] = []
    # a notation program writes each syllable as a text of its own; when the row is made of
    # several, they are the syllables (the spacing is only a fallback for a PDF that writes a
    # whole line as one text)
    by_run = len({g.run for g in row.glyphs if g.text not in ELISIONS}) > 1
    marks = sorted(
        [(min(h.x0, h.x1), max(h.x0, h.x1), "-") for h in row.hyphens]
        + [(min(s.x0, s.x1), max(s.x0, s.x1), "_") for s in row.lines]
    )
    for g in row.glyphs:
        # a hyphen (hyphen-minus, hyphen, en dash) or a line written as a character
        if g.text in ("-", chr(0x2010), chr(0x2013), "_"):
            marks.append((g.x, g.x + g.width, "-" if g.text != "_" else "_"))
            continue
        if g.text in ELISIONS and groups:
            groups[-1].chars.append(g)
            continue
        if groups and groups[-1].chars[-1].text in ELISIONS:
            groups[-1].chars.append(g)
            continue
        if groups:
            last = groups[-1].chars[-1]
            gap = g.x - (last.x + last.width)
            between = [m for m in marks if m[0] >= last.x + last.width - 0.5 and m[1] <= g.x + 0.5]
            # letters of one syllable are set edge to edge by the font (kerning moves them a
            # few hundredths of the size); two syllables that the layout put side by side
            # almost never meet so exactly
            together = (g.run == last.run) if by_run else (gap <= 0.045 * row.size)
            if together and not between:
                groups[-1].chars.append(g)
                if by_run and gap > 0.2 * row.size:
                    groups[-1].spaced = True
                continue
        groups.append(_Group([g], whole=by_run))
    marks.sort()
    for i, group in enumerate(groups):
        # after the last syllable of a row, only a mark right after it (a hyphen carrying the
        # word over the line break, a held syllable's line) is its own
        nxt = groups[i + 1].x0 if i + 1 < len(groups) else group.x1 + 3 * row.size
        for a, b, kind in marks:
            # a mark after this syllable and before the next: its middle lies between them (a
            # font with wide letter spacing makes it overlap the edges of their text a little)
            middle = (a + b) / 2
            if kind == "-":
                after = group.x1 - 0.5 <= middle <= nxt + 0.5
            else:
                after = a >= group.x1 - 1.0 and a <= nxt + 0.5
            if after:
                if kind == "-":
                    group.hyphen_after = True
                    if i + 1 < len(groups):
                        groups[i + 1].hyphen_before = True
                else:
                    group.extend_to = max(group.extend_to or b, b)
    return groups


def _has_vowel(chars: list[Glyph]) -> bool:
    """Whether text can be a syllable on its own: it has a vowel, or it is a contraction
    (n't, 's)."""
    for c in chars:
        if c.text in ("'", chr(0x2019)):
            return True
        base = unicodedata.normalize("NFKD", c.text)[:1].lower()
        if base in "aeiouyæøœ" or (
            c.text.isalpha() and not c.text.isascii() and not base.isascii()
        ):
            return True
    return False


@dataclass(slots=True)
class _Note:
    cx: float  # the centre of its column
    event: Event
    x: float  # the left of its column
    tied: bool = False  # tied on: its syllable starts at the note instead of being centred


def _notes(events: list[Event], staff: Staff) -> list[_Note]:
    notes = []
    for e in events:
        if e.staff is not staff or not e.heads or (bool(e.heads) and all(h.small for h in e.heads)):
            continue
        if all(h.tie_stop for h in e.heads):
            continue  # a note tied from the one before sings no new syllable
        head = min(e.heads, key=lambda h: abs(h.x - e.x))
        notes.append(_Note(e.x + head.w / 2, e, e.x, any(h.tie_start for h in e.heads)))
    notes.sort(key=lambda n: n.cx)
    return notes


def _align(
    groups: list[_Group], notes: list[_Note], sp: float, prefer: int
) -> tuple[float, list[tuple[_Group, _Note | None]]]:
    """Split the row into syllables, each under its own note, at the least cost."""
    pieces: list[tuple[_Group, int]] = []  # (group, index of the token it came from)
    for t, g in enumerate(groups):
        pieces.append((g, t))
    # dynamic programming over (characters consumed, last note used)
    chars: list[tuple[Glyph, int]] = [(c, t) for g, t in pieces for c in g.chars]
    token_end = {sum(len(g.chars) for g in groups[: t + 1]) - 1: t for t in range(len(groups))}
    n_chars = len(chars)
    inf = float("inf")
    best: dict[tuple[int, int], tuple[float, tuple[int, int] | None, int | None]] = {
        (0, -1): (0.0, None, None)
    }
    frontier = {(0, -1)}
    while frontier:
        next_frontier: set[tuple[int, int]] = set()
        for state in sorted(frontier):
            i, j = state
            cost0 = best[state][0]
            if i >= n_chars:
                continue
            token = chars[i][1]
            for end in range(i, n_chars):
                if chars[end][1] != token:
                    break
                inner_split = end not in token_end
                chunk = [c for c, _t in chars[i : end + 1]]
                x0, x1 = chunk[0].x, chunk[-1].x + chunk[-1].width
                center = (x0 + x1) / 2
                # a syllable held under a line starts at its note instead of being centred on it
                held = not inner_split and groups[token].extend_to is not None
                # a cut inside touching text is allowed only where both pieces sit under notes,
                # and each piece is a syllable (it has a vowel)
                inner = inner_split or (i > 0 and chars[i - 1][1] == token)
                if inner and (groups[token].whole or not _has_vowel(chunk)):
                    continue
                split_cost = 1.0 if inner_split else 0.0
                # text that runs over the columns of other notes is probably several syllables
                covered = {round(n.cx) for n in notes if x0 + 0.3 * sp < n.cx < x1 - 0.3 * sp}
                placed = False
                for k in range(j + 1, len(notes)):
                    d = (notes[k].cx - center) / sp
                    lean = 0.0
                    left = (notes[k].x - x0) / sp
                    if abs(left) < abs(d):
                        # a syllable sung over several notes starts at its note (its line may
                        # be too short to draw); centring is the likelier reading otherwise
                        d, lean = left, (0.0 if held else 0.15 if notes[k].tied else 0.3)
                    if d < -2.5:
                        continue
                    if d > 2.5:
                        break
                    if inner and abs(d) > 0.5:
                        continue
                    over = len(covered - {round(notes[k].cx)})
                    cost = cost0 + abs(d) + lean + split_cost + (0 if held else 0.6 * over)
                    if notes[k].event.voice != prefer:
                        cost += 0.8  # the side of the staff says whose words they are
                    key = (end + 1, k)
                    if key not in best or cost < best[key][0]:
                        best[key] = (cost, state, k)
                        next_frontier.add(key)
                    placed = True
                if not placed and not inner_split:
                    key = (end + 1, j)
                    cost = cost0 + 6.0 + split_cost
                    if key not in best or cost < best[key][0]:
                        best[key] = (cost, state, None)
                        next_frontier.add(key)
        frontier = next_frontier
    finals = [(v[0], k) for k, v in best.items() if k[0] == n_chars]
    if not finals:
        return inf, []
    total, key = min(finals)
    # walk back
    cuts: list[tuple[int, int, int | None]] = []
    walk: tuple[int, int] | None = key
    while walk is not None and best[walk][1] is not None:
        _c, prev, note = best[walk]
        assert prev is not None
        cuts.append((prev[0], walk[0], note))
        walk = prev
    cuts.reverse()
    result: list[tuple[_Group, _Note | None]] = []
    for start, stop, note in cuts:
        chunk = [c for c, _t in chars[start:stop]]
        token = chars[start][1]
        source = groups[token]
        first_of_token = start == 0 or chars[start - 1][1] != token
        last_of_token = stop - 1 in token_end
        piece = _Group(
            chunk,
            hyphen_after=source.hyphen_after if last_of_token else False,
            hyphen_before=source.hyphen_before if first_of_token else False,
            extend_to=source.extend_to if last_of_token else None,
        )
        result.append((piece, notes[note] if note is not None else None))
    return total, result


@dataclass(slots=True)
class RowReading:
    """The ways a row of words can be read: under which staff, and on which side of it."""

    system: System
    row: Row
    # (cost, staff, above, the syllables and their notes), the cheapest first
    options: list[tuple[float, Staff, bool, list[tuple[_Group, _Note | None]]]]

    @property
    def clear(self) -> bool:
        """Whether one reading is clearly better than the others."""
        return len(self.options) == 1 or self.options[1][0] - self.options[0][0] > 0.4


def lyric_rows(
    page: Page,
    system: System,
    events: list[Event],
    margins: tuple[float, float],
    systems: list[System],
) -> list[RowReading]:
    """The rows of words of ``system`` with the ways each can be read.

    ``margins``: the left and right edges of the music on the page; a line of text over the top
    staff that starts or ends exactly there is a credit (composer, lyricist), not words.
    """
    sp = system.space
    found: list[RowReading] = []
    rows = text_rows(page, system, systems)
    # a program that writes each syllable as a text of its own writes a title or a credit as one
    # text of several words
    per_syllable = any(len({g.run for g in r.glyphs}) > 1 for r in rows)
    for row in rows:
        groups = _tokens(row)
        if not groups:
            continue
        if per_syllable and len(groups) > 1 and len({g.run for g in row.glyphs}) == 1:
            continue
        # without a text of its own for each syllable, a credit is known by standing at a margin
        # (a held syllable can run to the margin too, so this is only the fallback)
        if (
            not per_syllable
            and row.y > system.top
            and (abs(groups[0].x0 - margins[0]) < 0.6 or abs(groups[-1].x1 - margins[1]) < 0.6)
        ):
            continue
        if any(g.spaced for g in groups):
            continue  # a text with a space in it is a title or a credit: a syllable has none
        options: list[tuple[float, Staff, bool, list[tuple[_Group, _Note | None]]]] = []
        for staff in system.staves:
            if row.y < staff.bottom - 0.5 * sp:
                above = False
                distance = staff.bottom - row.y
            elif row.y > staff.top + 0.5 * sp:
                above = True
                distance = row.y - staff.top
            else:
                continue
            if distance > 14 * sp:
                continue
            notes = _notes(events, staff)
            if not notes:
                continue
            two_voices = len({n.event.voice for n in notes}) > 1
            prefer = 1 if above or not two_voices else 2
            cost, aligned = _align(groups, notes, sp, prefer)
            matched = sum(1 for _g, n in aligned if n is not None)
            if matched < max(1, 0.6 * len(aligned)):
                continue
            off = [
                min(abs(n.cx - g.center), abs(n.x - g.x0)) / sp for g, n in aligned if n is not None
            ]
            if sum(off) / len(off) > 0.6:
                continue  # not words centred under notes (a title, a staff text)
            # words belong to the nearer staff when they fit both equally well
            options.append(
                (cost / max(1, len(aligned)) + 0.1 * distance / sp, staff, above, aligned)
            )
        if options:
            options.sort(key=lambda o: o[0])
            found.append(RowReading(system, row, options))
    return found


def _stacked_side(
    r: RowReading,
    close: list[tuple[float, Staff, bool, list[tuple[_Group, _Note | None]]]],
    readings: list[RowReading],
    votes: dict[tuple[int, bool], int],
    usual_above: dict[int, float],
) -> tuple[float, Staff, bool, list[tuple[_Group, _Note | None]]] | None:
    """For a row between two staves that other rows there overlap: the upper row is the words
    under the upper staff; a lower row is the words over the lower staff when that staff has
    words over it elsewhere in the score at about this height, and otherwise a further verse
    under the upper staff."""
    below_upper = next((o for o in close if not o[2]), None)
    above_lower = next((o for o in close if o[2]), None)
    if below_upper is None or above_lower is None:
        return None
    upper, lower = below_upper[1], above_lower[1]
    x0, x1 = r.row.glyphs[0].x, r.row.glyphs[-1].x
    stack = [
        o
        for o in readings
        if o.system is r.system
        and o is not r
        and lower.top < o.row.y < upper.bottom
        and o.row.glyphs[0].x < x1
        and o.row.glyphs[-1].x > x0
    ]
    if not stack:
        return None
    higher = sum(1 for o in stack if o.row.y > r.row.y + 0.3 * r.row.size)
    lower_rows = sum(1 for o in stack if o.row.y < r.row.y - 0.3 * r.row.size)
    if higher == 0 and lower_rows > 0:
        return below_upper
    if lower_rows == 0 and higher > 0:
        above_it = min(
            (o.row.y - r.row.y for o in stack if o.row.y > r.row.y + 0.3 * r.row.size),
            default=None,
        )
        if above_it is not None and 1.05 * r.row.size <= above_it <= 1.45 * r.row.size:
            return below_upper  # one text line under the row above: a further verse of it
        if votes.get((lower.index, True), 0) == 0:
            return below_upper  # no words over that staff anywhere: a further verse
        usual = usual_above.get(lower.index)
        if usual is not None and r.row.y - lower.top > usual + 4 * lower.space:
            return below_upper
        return above_lower
    return None


def _one_line_under(
    r: RowReading, readings: list[RowReading]
) -> tuple[float, Staff, bool, list[tuple[_Group, _Note | None]]] | None:
    """A row between two staves one text line under a row of words of the upper staff that it
    overlaps is a further verse of that staff, whatever its notes fit."""
    below_upper = next((o for o in r.options if not o[2]), None)
    if below_upper is None or not any(o[2] for o in r.options):
        return None
    upper = below_upper[1]
    size = r.row.size
    x0, x1 = r.row.glyphs[0].x, r.row.glyphs[-1].x
    for o in readings:
        if o.system is not r.system or o is r:
            continue
        if not (o.row.glyphs[0].x < x1 and o.row.glyphs[-1].x > x0):
            continue
        first = o.options[0]
        if first[1] is not upper or first[2]:
            continue
        if 1.05 * size <= o.row.y - r.row.y <= 1.45 * size and _under(r.row, o.row):
            return below_upper
    return None


def _under(lower: Row, upper: Row) -> bool:
    """Whether most syllables of ``lower`` stand under the words of ``upper`` (a syllable of it
    or the line of one it holds): a further verse is sung on the notes of the one above it."""
    spans = [(g.x0, g.x1) for g in _tokens(upper)]
    spans += [(min(s.x0, s.x1), max(s.x0, s.x1)) for s in upper.lines]
    margin = 0.5 * upper.size
    groups = _tokens(lower)
    inside = sum(1 for g in groups if any(a - margin <= g.center <= b + margin for a, b in spans))
    return inside >= 0.75 * len(groups)


def _usual_side(
    r: RowReading,
    close: list[tuple[float, Staff, bool, list[tuple[_Group, _Note | None]]]],
    usual: dict[tuple[int, bool], float],
) -> tuple[float, Staff, bool, list[tuple[_Group, _Note | None]]] | None:
    """Of the sides a row fits about equally, the one whose rows usually stand at this distance
    from their staff (a program places the words of one voice at much the same distance on every
    line); None when that does not decide."""
    scored = []
    for o in close:
        staff, above = o[1], o[2]
        known = usual.get((staff.index, above))
        if known is None:
            continue
        distance = abs(r.row.y - (staff.top if above else staff.bottom)) / staff.space
        scored.append((abs(distance - known), o))
    if not scored:
        return None
    scored.sort(key=lambda s: s[0])
    if len(scored) == 1:
        return scored[0][1] if len(close) > 1 else None
    if scored[1][0] - scored[0][0] < 1.0:
        return None
    return scored[0][1]


def place_lyrics(readings: list[RowReading]) -> tuple[list[str], list[LineGoesOn]]:
    """Give the notes their words. A row that fits two staves about equally (midway between
    them) goes to the side of the staff the clear rows of the score are on."""
    # a row near two systems is read with the one its syllables fit best
    best: dict[int, RowReading] = {}
    for r in readings:
        key = id(r.row.glyphs[0])
        if key not in best or r.options[0][0] < best[key].options[0][0]:
            best[key] = r
    readings = [r for r in readings if best[id(r.row.glyphs[0])] is r]
    votes: dict[tuple[int, bool], int] = defaultdict(int)
    for r in readings:
        if r.clear:
            # each side counts the syllables of its clear rows (the words a voice sings)
            _c, staff, above, aligned = r.options[0]
            votes[(staff.index, above)] += sum(1 for _g, n in aligned if n is not None)
    above_heights: dict[int, list[float]] = defaultdict(list)
    for r in readings:
        if r.clear and r.options[0][2]:
            staff = r.options[0][1]
            above_heights[staff.index].append(r.row.y - staff.top)
    usual_above = {k: sorted(v)[len(v) // 2] for k, v in above_heights.items()}
    # how far from its staff each side's clear rows usually stand, in spaces
    side_distances: dict[tuple[int, bool], list[float]] = defaultdict(list)
    for r in readings:
        if r.clear:
            _c, staff, above, _a = r.options[0]
            edge = staff.top if above else staff.bottom
            side_distances[(staff.index, above)].append(abs(r.row.y - edge) / staff.space)
    usual = {k: sorted(v)[len(v) // 2] for k, v in side_distances.items()}
    problems: list[str] = []
    goes_on: list[LineGoesOn] = []
    by_system: dict[int, list[tuple[Row, Staff, bool, list[tuple[_Group, _Note | None]]]]] = (
        defaultdict(list)
    )
    for r in readings:
        option = r.options[0]
        stacked_under = _one_line_under(r, readings)
        if stacked_under is not None:
            option = stacked_under
        elif not r.clear:
            close = [o for o in r.options if o[0] - r.options[0][0] <= 0.4]
            stacked = _stacked_side(r, close, readings, votes, usual_above)
            if stacked is not None:
                option = stacked
            else:
                option = _usual_side(r, close, usual) or max(
                    close, key=lambda o: (votes[(o[1].index, o[2])], -o[0])
                )
        _c, staff, above, aligned = option
        by_system[id(r.system)].append((r.row, staff, above, aligned))
        offset = abs(r.row.y - (staff.top if above else staff.bottom))
        first_word = r.row.glyphs[0].x
        for s in r.row.lines:
            a, b = sorted((s.x0, s.x1))
            if a < first_word - 0.5 and a <= r.system.x0 + 12 * r.system.space:
                goes_on.append(LineGoesOn(r.system, staff.index, above, offset, b))
    for placed_rows in by_system.values():
        # verse numbers: in each measure, the rows of words on one side of a staff, the nearest
        # the staff first (a program moves the words of a measure away from low or high notes,
        # so a row is not at one height over the whole system)
        heights: dict[tuple[int, bool, int], list[float]] = defaultdict(list)
        for row, staff, above, aligned in placed_rows:
            for _group, note in aligned:
                if note is not None:
                    heights[(staff.index, above, note.event.measure)].append(row.y)
        for row, staff, above, aligned in placed_rows:
            for group, note in aligned:
                number = 1
                if note is not None:
                    levels: list[float] = []
                    for y in sorted(
                        heights[(staff.index, above, note.event.measure)],
                        key=lambda y: abs(y - staff.middle),
                    ):
                        if not levels or abs(y - levels[-1]) > 0.3 * row.size:
                            levels.append(y)
                    number = 1 + sum(
                        1
                        for y in levels
                        if abs(y - staff.middle) < abs(row.y - staff.middle) - 0.3 * row.size
                    )
                if note is None:
                    problems.append(
                        f"page {staff.page}: the words '{group.text}' are under no note and "
                        "were left out"
                    )
                    continue
                syllabic = (
                    ("middle" if group.hyphen_after else "end")
                    if group.hyphen_before
                    else ("begin" if group.hyphen_after else "single")
                )
                note.event.lyrics.append(
                    LyricOut(
                        group.text,
                        syllabic,
                        number,
                        above,
                        extend_to=group.extend_to,
                        offset=abs(row.y - (staff.top if above else staff.bottom)),
                        left_aligned=(
                            not group.hyphen_after  # a word's last syllable is the one held
                            and abs(note.x - group.x0) < 0.25 * staff.space
                            and abs(note.cx - group.center) > 0.35 * staff.space
                        ),
                    )
                )
    return problems, goes_on


__all__ = ["RowReading", "lyric_rows", "place_lyrics", "text_rows"]
