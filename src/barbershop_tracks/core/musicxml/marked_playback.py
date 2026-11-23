"""The tempo MuseScore plays, worked out from the marks of a score that comes without a playback.

For a MuseScore project BLT asks MuseScore for its MIDI export and follows the tempo it plays
(``playback.py``). A MusicXML file, or a PDF that BLT read, has no playback, but it has the marks
MuseScore plays from, and MuseScore plays them by fixed rules:

* a **fermata** halves the tempo marked at it (MuseScore's default stretch) from its note until one
  tick before the next note of the score starts, then the marked tempo returns (also after a
  ritardando: the return is to the tempo mark, not to the slowed tempo);
* a **ritardando** or **rallentando** line ("rit." with a dashed line) slows the marked tempo in
  eight equal steps to three quarters of it at the end of the line, an **accelerando** line
  ("accel.") speeds it up in eight steps to four thirds; the tempo then stays there until the next
  tempo mark;
* a tempo mark (a metronome mark, "a tempo") sets the tempo, as BLT already reads it.

Worked out here, the tempo is the one MuseScore's MIDI export of the same score carries (the same
steps at the same ticks, rounded as a MIDI tempo is), so a song sounds the same from its project,
its MusicXML and its PDF. It is used only where BLT reads the score in written order (no repeats);
otherwise the score's own tempo marks decide as before.
"""

import re
import xml.etree.ElementTree as ET
from fractions import Fraction

from barbershop_tracks.core.musicxml.parser import ParseResult
from barbershop_tracks.models import TempoChange

_TICK = Fraction(1, 480)  # MuseScore's MIDI resolution, in quarter notes
_STEPS = 8
_FACTORS = (
    (
        re.compile(r"^\s*(rit|ritard|ritardando|rall|rallentando)\b\.?", re.IGNORECASE),
        Fraction(3, 4),
    ),
    (re.compile(r"^\s*(accel|accelerando)\b\.?", re.IGNORECASE), Fraction(4, 3)),
)
_STEP = 1024  # as midi_tempo rounds a MIDI tempo


def _int(text: str | None, default: int = 0) -> int:
    try:
        return int((text or "").strip())
    except ValueError:
        return default


def _marks(
    root: ET.Element,
) -> tuple[list[Fraction], list[Fraction], list[tuple[Fraction, Fraction, Fraction]]]:
    """(onsets of every note and rest, positions of fermatas, (start, end, factor) of tempo
    lines), in written quarter notes from the start, over all parts."""
    onsets: set[Fraction] = set()
    fermatas: set[Fraction] = set()
    open_lines: dict[str, tuple[Fraction, Fraction]] = {}
    lines: list[tuple[Fraction, Fraction, Fraction]] = []
    for part in root.findall("part"):
        divisions = 1
        start = Fraction(0)
        for measure in part.findall("measure"):
            cursor = Fraction(0)
            longest = Fraction(0)
            last_onset = Fraction(0)
            for element in measure:
                tag = element.tag
                if tag == "attributes" and element.find("divisions") is not None:
                    divisions = max(1, _int(element.findtext("divisions"), 1))
                elif tag == "note":
                    if element.find("grace") is not None or element.find("cue") is not None:
                        continue
                    duration = Fraction(_int(element.findtext("duration")), divisions)
                    if element.find("chord") is not None:
                        at = last_onset
                    else:
                        at = cursor
                        last_onset = at
                        cursor += duration
                        longest = max(longest, cursor)
                    onsets.add(start + at)
                    if element.find("notations/fermata") is not None:
                        fermatas.add(start + at)
                elif tag == "backup":
                    cursor -= Fraction(_int(element.findtext("duration")), divisions)
                elif tag == "forward":
                    cursor += Fraction(_int(element.findtext("duration")), divisions)
                    longest = max(longest, cursor)
                elif tag == "direction":
                    offset = Fraction(_int(element.findtext("offset")), divisions)
                    at = start + cursor + offset
                    words = " ".join((w.text or "") for w in element.iter("words"))
                    factor = next((f for rx, f in _FACTORS if rx.match(words)), None)
                    for dashes in element.iter("dashes"):
                        number = dashes.get("number", "1")
                        if dashes.get("type") == "start" and factor is not None:
                            open_lines[number] = (at, factor)
                        elif dashes.get("type") == "stop" and number in open_lines:
                            begin, line_factor = open_lines.pop(number)
                            if at > begin:
                                lines.append((begin, at, line_factor))
            start += longest
    return sorted(onsets), sorted(fermatas), sorted(set(lines))


def _rounded(bpm: Fraction) -> Fraction:
    """``bpm`` as a MIDI file holds it (whole microseconds per quarter note) and BLT reads it."""
    microseconds = round(Fraction(60_000_000) / bpm)
    return Fraction(round(Fraction(60_000_000, microseconds) * _STEP), _STEP)


def marked_tempo_changes(root: ET.Element, parsed: ParseResult) -> tuple[TempoChange, ...] | None:
    """The tempo changes MuseScore would play for this score, or None when there is nothing to
    add to its tempo marks (no fermata, no tempo line) or it cannot be worked out here."""
    performed = parsed.performed
    if performed is None or not performed.tempo_events or not performed.plan.is_identity:
        return None
    onsets, fermatas, lines = _marks(root)
    if not fermatas and not lines:
        return None
    marks = sorted((t.position, t.bpm) for t in performed.tempo_events)

    def marked(at: Fraction) -> Fraction:
        bpm = marks[0][1]
        for position, value in marks:
            if position <= at:
                bpm = value
        return bpm

    # (position, priority, bpm): at one position the higher priority wins, as in MuseScore's
    # tempo map a fermata's stretch is applied over the tempo there
    events: list[tuple[Fraction, int, Fraction]] = [(p, 0, b) for p, b in marks]
    for begin, end, factor in lines:
        base = marked(begin)
        for k in range(1, _STEPS + 1):
            events.append(
                (
                    begin + (end - begin) * k / _STEPS,
                    1,
                    base * (1 + (factor - 1) * Fraction(k, _STEPS)),
                )
            )
    for at in fermatas:
        base = marked(at)
        events.append((at, 2, base / 2))
        later = [o for o in onsets if o > at]
        if later:
            events.append((min(later) - _TICK, 2, base))
    by_position: dict[Fraction, tuple[int, Fraction]] = {}
    for position, priority, bpm in sorted(events):
        held = by_position.get(position)
        if held is None or priority >= held[0]:
            by_position[position] = (priority, bpm)
    changes: list[TempoChange] = []
    for position in sorted(by_position):
        bpm = _rounded(by_position[position][1])
        if changes and changes[-1].bpm == bpm:
            continue
        changes.append(TempoChange(position=position, bpm=bpm))
    return tuple(changes)


__all__ = ["marked_tempo_changes"]
