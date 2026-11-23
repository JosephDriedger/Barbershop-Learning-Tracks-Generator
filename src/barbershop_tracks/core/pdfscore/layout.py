"""Staves, systems and barlines of a score page, found in what the page draws.

A staff is five horizontal lines at one spacing over the same width. A system is a run of staves
that a line at their left edge joins (or that a bracket or brace spans); a staff that nothing joins
to another is a system of its own. A barline is a vertical line, thicker than a stem, that runs from
the top line of a staff to its bottom line.
"""

from collections import Counter
from dataclasses import dataclass, field

from barbershop_tracks.core.pdfscore.pdf import Glyph, Page, Segment
from barbershop_tracks.core.pdfscore.symbols import BRACE, REPEAT_DOT, REPEAT_DOTS


@dataclass(slots=True)
class Staff:
    page: int
    lines: tuple[float, ...]  # y of the five lines, top first
    x0: float
    x1: float
    index: int = 0  # in its system, from the top

    @property
    def top(self) -> float:
        return self.lines[0]

    @property
    def bottom(self) -> float:
        return self.lines[-1]

    @property
    def space(self) -> float:
        return (self.top - self.bottom) / 4

    @property
    def middle(self) -> float:
        return (self.top + self.bottom) / 2

    def position(self, y: float) -> int:
        """The staff position of ``y`` in half spaces above the bottom line (0: the bottom line)."""
        return round((y - self.bottom) / (self.space / 2))


@dataclass(slots=True)
class Boundary:
    x: float
    kind: str = "regular"  # regular, double, final, start (the left edge of the system)
    repeat_before: bool = False  # dots on its left: the end of a repeated passage
    repeat_after: bool = False  # dots on its right: the start of one


@dataclass(slots=True)
class System:
    page: int
    staves: list[Staff]
    boundaries: list[Boundary] = field(default_factory=list)
    braced: list[tuple[int, int]] = field(default_factory=list)  # staff index ranges a brace joins

    @property
    def x0(self) -> float:
        return min(s.x0 for s in self.staves)

    @property
    def x1(self) -> float:
        return max(s.x1 for s in self.staves)

    def music_end(self, notes_x: float) -> float:
        """Where the music of the system ends: the barline after its last note (a courtesy key or
        time signature can stand after it, before the end of the staves)."""
        after = [b.x for b in self.boundaries if b.x > notes_x]
        return min(after) if after else self.x1

    @property
    def top(self) -> float:
        return self.staves[0].top

    @property
    def bottom(self) -> float:
        return self.staves[-1].bottom

    @property
    def space(self) -> float:
        return self.staves[0].space


def _horizontal_lines(segments: list[Segment]) -> list[tuple[float, float, float, float]]:
    """(y, x0, x1, width) of horizontal lines, pieces that continue one another joined."""
    rows: dict[float, list[tuple[float, float, float]]] = {}
    exact: dict[float, float] = {}
    for s in segments:
        if abs(s.y0 - s.y1) > 0.01:
            continue
        a, b = sorted((s.x0, s.x1))
        key = round(s.y0, 1)
        rows.setdefault(key, []).append((a, b, s.width))
        exact.setdefault(key, s.y0)
    joined: list[tuple[float, float, float, float]] = []
    for key, pieces in rows.items():
        y = exact[key]
        pieces.sort()
        start, end, width = pieces[0]
        for a, b, w in pieces[1:]:
            if a <= end + 1.0 and abs(w - width) < 0.05:
                end = max(end, b)
            else:
                joined.append((y, start, end, width))
                start, end, width = a, b, w
        joined.append((y, start, end, width))
    return joined


def find_staves(page: Page) -> list[Staff]:
    lines = [ln for ln in _horizontal_lines(page.segments) if ln[2] - ln[1] >= 40]
    lines.sort(key=lambda ln: -ln[0])
    used: set[int] = set()
    staves: list[Staff] = []
    for i, first in enumerate(lines):
        if i in used:
            continue
        for j in range(i + 1, len(lines)):
            if j in used:
                continue
            gap = first[0] - lines[j][0]
            if gap < 2.0:
                continue
            if gap > 20.0:
                break
            if not _overlaps(first, lines[j]):
                continue
            chosen = [i, j]
            for k in range(2, 4 + 1):
                want = first[0] - k * gap
                match = next(
                    (
                        m
                        for m in range(j + 1, len(lines))
                        if m not in used
                        and abs(lines[m][0] - want) <= max(0.3, gap * 0.06)
                        and _overlaps(first, lines[m])
                        and abs(lines[m][3] - first[3]) < 0.05
                    ),
                    None,
                )
                if match is None:
                    break
                chosen.append(match)
            if len(chosen) == 5:
                group = [lines[c] for c in chosen]
                used.update(chosen)
                staves.append(
                    Staff(
                        page.number,
                        tuple(g[0] for g in group),
                        min(g[1] for g in group),
                        max(g[2] for g in group),
                    )
                )
                break
    staves.sort(key=lambda s: -s.top)
    return staves


def _overlaps(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    lo, hi = max(a[1], b[1]), min(a[2], b[2])
    return hi - lo >= 0.8 * min(a[2] - a[1], b[2] - b[1])


def _verticals(page: Page) -> list[Segment]:
    return [s for s in page.segments if abs(s.x0 - s.x1) < 0.01 and abs(s.y0 - s.y1) > 0.5]


def stem_width(page: Page) -> float:
    widths = Counter(round(s.width, 2) for s in _verticals(page) if abs(s.y0 - s.y1) < 60)
    return widths.most_common(1)[0][0] if widths else 0.5


def find_systems(page: Page, staves: list[Staff]) -> list[System]:
    verticals = _verticals(page)
    systems: list[System] = []
    for staff in staves:
        if systems and _joined(systems[-1].staves[-1], staff, verticals, page.glyphs):
            systems[-1].staves.append(staff)
        else:
            systems.append(System(page.number, [staff]))
    thin = stem_width(page)
    for system in systems:
        for i, staff in enumerate(system.staves):
            staff.index = i
        system.boundaries = _boundaries(page, system, verticals, thin)
        system.braced = _braces(page.glyphs, system)
    return systems


def _joined(upper: Staff, lower: Staff, verticals: list[Segment], glyphs: list[Glyph]) -> bool:
    left = min(upper.x0, lower.x0)
    if abs(upper.x0 - lower.x0) > 30 and abs(upper.x1 - lower.x1) > 1:
        return False
    for v in verticals:
        lo, hi = sorted((v.y0, v.y1))
        if abs(v.x0 - left) <= 12 and lo <= lower.top + 0.5 and hi >= upper.bottom - 0.5:
            return True
    for g in glyphs:  # a brace drawn as one glyph that reaches over both staves
        if (
            g.text == BRACE
            and g.x < left
            and lower.bottom - 1 <= g.y <= lower.top + 1
            and g.y + g.size >= upper.bottom
        ):
            return True
    return False


def _braces(glyphs: list[Glyph], system: System) -> list[tuple[int, int]]:
    found: list[tuple[int, int]] = []
    for g in glyphs:
        if g.text != BRACE or g.x > system.x0:
            continue
        top = g.y + g.size  # a brace glyph is scaled to its height; its origin is at the bottom
        covered = [s.index for s in system.staves if s.bottom >= g.y - 1 and s.top <= top + 1]
        if len(covered) >= 2:
            found.append((covered[0], covered[-1]))
    return found


def _boundaries(
    page: Page, system: System, verticals: list[Segment], thin: float
) -> list[Boundary]:
    xs: list[tuple[float, str]] = []
    for staff in system.staves:
        sp = staff.space
        for v in verticals:
            lo, hi = sorted((v.y0, v.y1))
            if not (system.x0 - 1 <= v.x0 <= system.x1 + 1):
                continue
            spans_staff = lo <= staff.bottom + 0.35 * sp and hi >= staff.top - 0.35 * sp
            if spans_staff and (v.width >= thin * 1.3 or (hi - lo) > 6 * sp):
                xs.append((v.x0, "thin"))
        for shape in page.shapes:
            if not shape.filled or shape.curved:
                continue
            x0, y0, x1, y1 = shape.bbox
            if (
                x1 - x0 < 1.2 * sp
                and x1 - x0 > 0.2 * sp
                and y0 <= staff.bottom + 0.35 * sp
                and y1 >= staff.top - 0.35 * sp
                and system.x0 - 1 <= x0 <= system.x1 + 1
            ):
                xs.append(((x0 + x1) / 2, "thick"))
    xs.sort()
    sp = system.space
    groups: list[list[tuple[float, str]]] = []
    for x, kind in xs:
        if groups and x - groups[-1][-1][0] <= 1.2 * sp:
            groups[-1].append((x, kind))
        else:
            groups.append([(x, kind)])
    result: list[Boundary] = []
    for group in groups:
        kinds = {k for _x, k in group}
        distinct = sorted({round(x, 1) for x, _k in group})
        x = max(x for x, _k in group)
        kind = "final" if "thick" in kinds else ("double" if len(distinct) > 1 else "regular")
        result.append(Boundary(x, kind))
    if not result or result[0].x > system.x0 + 2:
        result.insert(0, Boundary(system.x0, "start"))
    else:
        result[0].kind = "start"
        result[0].x = system.x0
    if system.x1 - result[-1].x > 2 * sp:
        result.append(Boundary(system.x1, "regular"))
    _repeat_dots(page.glyphs, system, result)
    return result


def _repeat_dots(glyphs: list[Glyph], system: System, boundaries: list[Boundary]) -> None:
    sp = system.space
    for g in glyphs:
        if g.text not in (REPEAT_DOT, REPEAT_DOTS):
            continue
        if not (system.bottom - sp <= g.y <= system.top + sp):
            continue
        for b in boundaries:
            if b.x - 2.5 * sp <= g.x < b.x - 0.1 * sp:
                b.repeat_before = True
                break
            if b.x - 0.6 * sp <= g.x <= b.x + 2.5 * sp:
                b.repeat_after = True
                break


def page_systems(page: Page) -> list[System]:
    return find_systems(page, find_staves(page))
