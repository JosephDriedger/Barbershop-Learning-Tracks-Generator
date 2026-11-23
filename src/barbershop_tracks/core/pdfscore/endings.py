"""First and second endings (volta brackets) of a score PDF.

An ending is a bracket over the top staff: a hook down at its start, a line along the top, and a
hook down at its end when the ending is closed (a last ending is often left open). Its numbers
("1.", "2.", "1, 2") are written just inside the start, in bold. A bracket that runs over a line
break goes on at the start of the next system, without its numbers.
"""

import re
from dataclasses import dataclass

from barbershop_tracks.core.pdfscore.layout import System
from barbershop_tracks.core.pdfscore.model import MeasureInfo
from barbershop_tracks.core.pdfscore.pdf import Page


@dataclass(slots=True)
class _Bracket:
    system: System
    x0: float
    x1: float
    y: float
    closed: bool
    numbers: str


def _brackets(page: Page, system: System) -> list[_Bracket]:
    sp = system.space
    top = system.staves[0].top
    horizontals = [
        s
        for s in page.segments
        if abs(s.y0 - s.y1) < 0.01
        and top + 0.8 * sp < s.y0 < top + 10 * sp
        and abs(s.x1 - s.x0) > 2 * sp
    ]
    verticals = [s for s in page.segments if abs(s.x0 - s.x1) < 0.01]
    found: list[_Bracket] = []
    for h in horizontals:
        a, b = sorted((h.x0, h.x1))
        y = h.y0

        def hook(x: float, y: float = y) -> bool:
            return any(
                abs(v.x0 - x) < 0.5
                and abs(max(v.y0, v.y1) - y) < 0.5
                and 1.0 * sp < abs(v.y1 - v.y0) < 4 * sp
                for v in verticals
            )

        starts_here = hook(a)
        continues = a <= system.x0 + 12 * sp and not starts_here
        if not starts_here and not continues:
            continue
        glyphs = sorted(
            (
                g
                for g in page.glyphs
                if a < g.x < a + 6 * sp
                and y - 3 * sp < g.y < y
                and "bold" in g.font.lower()
                and (g.text.isdigit() or g.text in ",.")
            ),
            key=lambda g: g.x,
        )
        text = "".join(g.text for g in glyphs)
        digits = re.findall(r"\d+", text)
        if starts_here and not digits:
            continue
        found.append(_Bracket(system, a, b, y, hook(b), ", ".join(digits)))
    return found


def read_endings(pages: dict[int, Page], measures: list[MeasureInfo]) -> list[str]:
    """Mark the measures that start and end each ending. Returns what could not be read."""
    problems: list[str] = []
    systems: list[System] = []
    for m in measures:
        if not systems or systems[-1] is not m.system:
            systems.append(m.system)
    open_numbers: str | None = None
    for system in systems:
        here = [m for m in measures if m.system is system]
        for bracket in sorted(_brackets(pages[system.page], system), key=lambda b: b.x0):
            covered = [
                m
                for m in here
                if min(m.x1, bracket.x1) - max(m.x0, bracket.x0) > 0.5 * (m.x1 - m.x0)
            ]
            if not covered:
                continue
            if bracket.numbers:
                numbers = bracket.numbers
                covered[0].ending_start = numbers
            elif open_numbers is not None:
                numbers = open_numbers  # an ending going on from the system before
            else:
                continue
            runs_on = not bracket.closed and bracket.x1 >= system.x1 - system.space
            if runs_on:
                open_numbers = numbers
                continue
            open_numbers = None
            covered[-1].ending_stop = (numbers, "stop" if bracket.closed else "discontinue")
    if open_numbers is not None:
        problems.append("an ending bracket runs to the end of the score without closing")
    return problems


__all__ = ["read_endings"]
