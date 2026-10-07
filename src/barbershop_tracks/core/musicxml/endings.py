"""Reading endings (voltas) from ``<barline>`` elements: marks, then validated spans.

Two steps, and nothing is repaired between them:

1. ``read_ending`` turns one ``<ending>`` into an ``EndingMark`` (the literal marker) or reports why
   it cannot (bad number, bad type, bad placement);
2. ``build_spans`` pairs each ``start`` mark with the mark that closes it into an ``EndingSpan``.

MusicXML 4.0: ``number`` is a comma-separated list of positive integers without leading zeros
(or only spaces when the software could not tell); ranges, zero and leading zeros are invalid.
``start`` belongs to the left barline of the first measure of an ending; ``stop`` and
``discontinue`` (a downward jog or none) belong to the right barline of its last measure and both
close the span. The element text and ``print-object`` are display only and ignored. Where a
marker sits is never reinterpreted (MuseScore attaches it to the containing measure; we refuse).
"""

import re
import xml.etree.ElementTree as ET
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from barbershop_tracks.core.issues import IssueCollector
from barbershop_tracks.models import EndingClose, EndingSpan

_NUMBER = re.compile(r"[1-9][0-9]*(, ?[1-9][0-9]*)*")

Report = Callable[[str, str], None]  # (code, message)


@dataclass(frozen=True, slots=True)
class EndingMark:
    """One ``<ending>`` element exactly as found (a literal source marker)."""

    kind: str  # "start", "stop" or "discontinue"
    measure_index: int
    numbers: tuple[int, ...]
    raw_number: str


def parse_ending_number(raw: str | None) -> tuple[tuple[int, ...] | None, str | None]:
    """``(numbers, problem)``: ``problem`` is an issue code when ``raw`` is not usable."""
    if raw is None:
        return None, "ENDING_NUMBER_INVALID"
    text = raw.strip()
    if not text:
        return None, "ENDING_NUMBER_UNSPECIFIED"
    if _NUMBER.fullmatch(text) is None:
        return None, "ENDING_NUMBER_INVALID"
    numbers = [int(part) for part in text.split(",")]
    if len(set(numbers)) != len(numbers):
        return None, "ENDING_NUMBER_INVALID"
    return tuple(sorted(numbers)), None


def read_ending(
    barline: ET.Element,
    *,
    measure_index: int,
    content_before: bool,
    error: Report,
) -> EndingMark | None:
    """The ending mark on ``barline``, or ``None`` (reported) if it cannot be interpreted.

    ``content_before`` says whether notes, rests or moves already occurred in the measure.
    """
    ending = barline.find("ending")
    if ending is None:
        return None
    kind = ending.get("type")
    if kind not in ("start", "stop", "discontinue"):
        error("ENDING_TYPE_INVALID", f"an <ending> has type {kind!r}")
        return None
    raw = ending.get("number")
    numbers, problem = parse_ending_number(raw)
    if numbers is None:
        if problem == "ENDING_NUMBER_UNSPECIFIED":
            error(problem, "an <ending> has no number (only spaces), so its passes are unknown")
        else:
            error(
                "ENDING_NUMBER_INVALID",
                f"ending number {raw!r} is not a comma-separated list of positive whole "
                "numbers without leading zeros (ranges are not valid)",
            )
        return None
    location = barline.get("location", "right")
    if location not in ("left", "right"):
        error("ENDING_MID_MEASURE", "an ending marker in the middle of a measure is not supported")
        return None
    wanted = "left" if kind == "start" else "right"
    if location != wanted:
        error(
            "ENDING_BARLINE_PLACEMENT",
            f"an ending '{kind}' is at the {location} barline (the default is 'right'); a "
            "'start' belongs to the left barline of the first measure of the ending and a "
            "'stop' or 'discontinue' to the right barline of its last measure",
        )
        return None
    if location == "left" and content_before:
        error("ENDING_MID_MEASURE", "an ending start after the notes of a measure is not allowed")
        return None
    return EndingMark(kind=kind, measure_index=measure_index, numbers=numbers, raw_number=raw or "")


def build_spans(
    marks: Sequence[EndingMark],
    measure_numbers: Sequence[int],
    part_id: str,
    issues: IssueCollector,
) -> tuple[tuple[EndingSpan, ...], bool]:
    """Pair marks into spans. ``(spans, ok)``; ``ok`` is False if any pairing was an error."""
    spans: list[EndingSpan] = []
    ok = True
    open_mark: EndingMark | None = None

    def fail(code: str, message: str, mark: EndingMark) -> None:
        nonlocal ok
        ok = False
        issues.error(code, message, part_id=part_id, measure=measure_numbers[mark.measure_index])

    for mark in sorted(marks, key=lambda m: (m.measure_index, m.kind != "start")):
        if mark.kind == "start":
            if open_mark is not None:
                fail(
                    "ENDING_OVERLAP",
                    f"an ending starts before the ending that started at measure "
                    f"{measure_numbers[open_mark.measure_index]} was closed",
                    mark,
                )
                continue
            open_mark = mark
        elif open_mark is None:
            fail("ENDING_STOP_WITHOUT_START", f"an ending '{mark.kind}' closes no ending", mark)
        elif open_mark.numbers != mark.numbers:
            fail(
                "ENDING_NUMBER_MISMATCH",
                f"an ending starting with number {open_mark.raw_number!r} is closed with "
                f"number {mark.raw_number!r}",
                mark,
            )
            open_mark = None
        else:
            spans.append(
                EndingSpan(
                    start_index=open_mark.measure_index,
                    end_index=mark.measure_index,
                    numbers=open_mark.numbers,
                    closing=EndingClose(mark.kind),
                    raw_number=open_mark.raw_number,
                )
            )
            open_mark = None
    if open_mark is not None:
        fail("ENDING_UNCLOSED", "an ending is started but never closed", open_mark)
    return tuple(spans), ok
