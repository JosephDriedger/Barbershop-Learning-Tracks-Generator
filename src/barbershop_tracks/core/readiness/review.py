"""The bars of a score that a person should look at, found from what the parser could not accept.

Music recognised from a PDF is wrong in places, and BLT cannot see the PDF. What it can see is
where the recognised music does not add up: a bar short of notes, a voice split in two, a tie that
changes pitch, an ending that never closes. This module collects those findings *per bar*, with
the page the bar is on, so that a person can go through them one by one against the original. It
says what is suspect, never what the music should be, and it cannot find a wrong note that still
adds up: checking the music against the PDF stays the person's job.

A bar with an **error** must be corrected in a notation program (the score cannot be used until it
is). A bar with only **warnings** can be looked at and acknowledged.
"""

import re
import xml.etree.ElementTree as ET
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from barbershop_tracks.core.musicxml import ParseResult
from barbershop_tracks.core.readiness.lines import LineInfo
from barbershop_tracks.core.readiness.suggest import shared_staff_positions
from barbershop_tracks.models import Severity

_FRACTION = re.compile(r"\b(\d+)/(\d+)\b")
_STRAY = (
    "a few stray notes were split off into a voice of their own here, which usually means the "
    "recognition lost track of whose notes they are: check every note in this bar"
)


@dataclass(frozen=True, slots=True)
class SuspectBar:
    measure: int
    page: int | None
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def must_fix(self) -> bool:
        return bool(self.errors)

    @property
    def where(self) -> str:
        return f"Bar {self.measure}" + (f", page {self.page}" if self.page else "")


@dataclass(frozen=True, slots=True)
class BarReview:
    bars: tuple[SuspectBar, ...]
    general: tuple[str, ...]  # problems that belong to no bar (the tempo, say)
    total_bars: int

    @property
    def must_fix(self) -> int:
        return sum(1 for bar in self.bars if bar.must_fix) + len(self.general)

    def pending(self, acknowledged: Collection[int]) -> int:
        """Bars still to deal with: those that must be fixed, and the others not yet looked at."""
        return self.must_fix + sum(
            1 for bar in self.bars if not bar.must_fix and bar.measure not in acknowledged
        )

    @property
    def clean(self) -> bool:
        return not self.bars and not self.general


def measure_pages(root: ET.Element) -> dict[int, int]:
    """Bar number to page number, from the page breaks of the first part (page 1 if none)."""
    first = root.find("part")
    if first is None:
        return {}
    pages: dict[int, int] = {}
    page = 1
    for bar in first.findall("measure"):
        for print_element in bar.findall("print"):
            if print_element.get("new-page") == "yes" and pages:
                page += 1
        number = bar.get("number", "")
        if number.isdigit():
            pages.setdefault(int(number), page)
    return pages


def _plainly(text: str) -> str:
    """The same sentence with exact fractions as decimals ("5/2" as "2.5")."""

    def decimal(found: re.Match[str]) -> str:
        value = Fraction(int(found.group(1)), int(found.group(2)))
        return f"{float(value):g}"

    text = _FRACTION.sub(decimal, text)
    return text[:1].upper() + text[1:]


def _staff_names(lines: Iterable[LineInfo]) -> dict[str, str]:
    names: dict[str, str] = {}
    for info in lines:
        source = info.line_id.split("/")[0]
        label = info.position.split(" staff")[0] + " staff" if info.position else info.part_name
        names.setdefault(source, label)
    return names


def build_review(
    parsed: ParseResult, lines: Sequence[LineInfo], pages: Mapping[int, int] | None = None
) -> BarReview:
    """The bars of ``parsed`` that do not add up, with the reasons, in bar order."""
    song = parsed.song
    if song is None:
        return BarReview((), (), 0)
    pages = pages or {}
    staves = _staff_names(lines)
    errors: dict[int, list[str]] = {}
    warnings: dict[int, list[str]] = {}
    general: list[str] = []
    for issue in parsed.issues.issues:
        if issue.severity not in (Severity.ERROR, Severity.WARNING):
            continue
        text = _plainly(issue.message)
        if issue.part_id is not None:
            owner = staves.get(issue.part_id.split("/")[0], issue.part_id)
            text = f"{owner}: {text}"
        if issue.measure is None:
            if issue.severity is Severity.ERROR and text not in general:
                general.append(text)
            continue
        bucket = errors if issue.severity is Severity.ERROR else warnings
        if text not in bucket.setdefault(issue.measure, []):
            bucket[issue.measure].append(text)
    for part in song.parts:
        position = shared_staff_positions(song.parts).get(part.part_id)
        if position is not None and position.upper is None:
            label = f"{position.staff_label} staff: voice {position.voice}"
            for bar in sorted({note.measure for note in part.sounding_notes}):
                text = f"{label}: {_STRAY}"
                if text not in warnings.setdefault(bar, []):
                    warnings[bar].append(text)
    total = len({note.measure for part in song.parts for note in part.events})
    bars = tuple(
        SuspectBar(
            measure=measure,
            page=pages.get(measure),
            errors=tuple(errors.get(measure, ())),
            warnings=tuple(warnings.get(measure, ())),
        )
        for measure in sorted(set(errors) | set(warnings))
    )
    return BarReview(bars, tuple(general), total)
