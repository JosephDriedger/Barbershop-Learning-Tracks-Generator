"""Slurs: the curves that are not ties, from the note they start at to the note they end at.

A slur says that the notes under it are sung on one syllable (a melisma), so a note under a slur
needs no syllable of its own. A notation program draws it from near the first note (its notehead,
or its stem end) to near the last, arching over the notes: above the upper voice of a staff, below
the lower. A slur that runs over a line break is drawn in two halves, the first to the end of the
system and the second from its start.
"""

from barbershop_tracks.core.pdfscore.layout import System
from barbershop_tracks.core.pdfscore.model import Event
from barbershop_tracks.core.pdfscore.pdf import Shape


def _reach(e: Event) -> tuple[float, float]:
    """The heights an event covers: its noteheads and its stem."""
    ys = [h.y for h in e.heads]
    if e.stem:
        ys.append(e.tip)
    return min(ys), max(ys)


def _end_cost(e: Event, point: tuple[float, float], sp: float, above: bool) -> float | None:
    cx = e.x + e.heads[0].w / 2
    dx = abs(cx - point[0])
    if dx > 2.2 * sp:
        return None
    lo, hi = _reach(e)
    # how far outside the band of the note (its noteheads and stem, and a space and a half
    # around them) the end of the slur is
    dy = max(0.0, lo - 1.5 * sp - point[1], point[1] - hi - 1.5 * sp)
    if dy > 2.0 * sp:
        return None
    upper = e.voice % 2 == 1
    return dx / sp + 3 * dy / sp + (0.0 if upper == above else 1.5)


def read_slurs(system: System, curves: list[Shape], events: list[Event]) -> None:
    sp = system.space
    notes = [e for e in events if e.system is system and e.heads]
    if not notes:
        return
    last_x = max(e.x for e in notes)
    for curve in curves:
        pts = curve.points
        left = min(pts, key=lambda p: p[0])
        right = max(pts, key=lambda p: p[0])
        if right[0] - left[0] < 0.8 * sp:
            continue
        _x0, _y0, _x1, y1 = curve.bbox
        above = y1 > max(left[1], right[1]) + 0.3 * sp
        # the second half of a slur over a line break starts left of the system's first note
        starts = left[0] <= min(e.x for e in notes) - 0.5 * sp
        ends = right[0] >= system.music_end(last_x) - 1.5 * sp  # the first half
        best: tuple[float, Event | None, Event | None] | None = None
        for voice_staff in {(e.staff.index, e.voice) for e in notes}:
            pool = [e for e in notes if (e.staff.index, e.voice) == voice_staff]
            a = None if starts else _best(pool, left, sp, above)
            b = None if ends else _best(pool, right, sp, above)
            if (a is None and not starts) or (b is None and not ends):
                continue
            if a is not None and b is not None and (a[1] is b[1] or a[1].x >= b[1].x):
                continue
            cost = (a[0] if a else 0.0) + (b[0] if b else 0.0)
            if best is None or cost < best[0]:
                best = (cost, a[1] if a else None, b[1] if b else None)
        if best is None:
            continue
        _cost, first, last = best
        if first is not None:
            first.slur_starts += 1
        if last is not None:
            last.slur_stops += 1


def _best(
    pool: list[Event], point: tuple[float, float], sp: float, above: bool
) -> tuple[float, Event] | None:
    found: tuple[float, Event] | None = None
    for e in pool:
        cost = _end_cost(e, point, sp, above)
        if cost is not None and (found is None or cost < found[0]):
            found = (cost, e)
    return found


__all__ = ["read_slurs"]
