"""Writing what was read from a score PDF as MusicXML, in the shape MuseScore's own export has.

One part per staff (or per braced group of staves), the upper voice of a staff as voice 1 and the
lower as voice 2 (5 and 6 on a part's second staff), the written pitch with the octave of an
octave clef in the clef, lyrics with their verse number and ``placement="above"`` when they stand
over the staff, and a pickup as measure 0. Reading the result therefore gives the same lines, the
same line identifiers and the same words as the MusicXML of the project the PDF was made from.
"""

import math
import xml.etree.ElementTree as ET
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

from barbershop_tracks.core.musicxml.parser import PDF_READER_SOFTWARE
from barbershop_tracks.core.pdfscore.lyrics import UNDERTIE
from barbershop_tracks.core.pdfscore.model import Direction, Event, MeasureInfo, ReadScore

_TYPES = {
    Fraction(16): "long",
    Fraction(8): "breve",
    Fraction(4): "whole",
    Fraction(2): "half",
    Fraction(1): "quarter",
    Fraction(1, 2): "eighth",
    Fraction(1, 4): "16th",
    Fraction(1, 8): "32nd",
    Fraction(1, 16): "64th",
    Fraction(1, 32): "128th",
}


def _sub(parent: ET.Element, tag: str, text: str | None = None, **attrs: str) -> ET.Element:
    element = ET.SubElement(parent, tag, attrs)
    if text is not None:
        element.text = text
    return element


def _divisions(score: ReadScore) -> int:
    lcm = 1
    for e in score.events:
        for value in (e.onset, e.duration):
            lcm = math.lcm(lcm, value.denominator)
    for m in score.measures:
        lcm = math.lcm(lcm, m.length.denominator)
    for d in score.directions:
        lcm = math.lcm(lcm, d.onset.denominator)
    return lcm


def _beat_unit(unit: Fraction) -> tuple[str, bool]:
    if unit in _TYPES:
        return _TYPES[unit], False
    plain = unit * Fraction(2, 3)
    return _TYPES.get(plain, "quarter"), True


def write_musicxml(score: ReadScore, target: Path) -> None:
    divisions = _divisions(score)
    root = ET.Element("score-partwise", version="4.0")
    if score.title:
        work = _sub(root, "work")
        _sub(work, "work-title", score.title)
    ident = _sub(root, "identification")
    if score.composer:
        _sub(ident, "creator", score.composer, type="composer")
    if score.arranger:
        _sub(ident, "creator", score.arranger, type="arranger")
    encoding = _sub(ident, "encoding")
    _sub(encoding, "software", PDF_READER_SOFTWARE)
    part_list = _sub(root, "part-list")
    for part in score.parts:
        sp = _sub(part_list, "score-part", id=part.id)
        _sub(sp, "part-name", part.name)
    by_cell: dict[tuple[int, int], list[Event]] = defaultdict(list)
    for e in score.events:
        if bool(e.heads) and all(h.small for h in e.heads):
            continue
        by_cell[(e.measure, e.staff.index)].append(e)
    for part in score.parts:
        element = _sub(root, "part", id=part.id)
        clef_seen: dict[int, tuple[str, int, int] | None] = {}
        key_seen: int | None = None
        for m in score.measures:
            measure = _sub(element, "measure", number=str(m.number))
            if m.number == 0:
                measure.set("implicit", "yes")
            _attributes(score, measure, m, part.staves, divisions, clef_seen, key_seen)
            keys = score.key_at.get(part.staves[0], [])
            for km, fifths in keys:
                if km == m.index:
                    key_seen = fifths
            if m.repeat_start or m.ending_start:
                bar = _sub(measure, "barline", location="left")
                if m.repeat_start:
                    _sub(bar, "bar-style", "heavy-light")
                if m.ending_start:
                    _sub(bar, "ending", number=m.ending_start, type="start")
                if m.repeat_start:
                    _sub(bar, "repeat", direction="forward")
            first_staff = True
            for k, staff_index in enumerate(part.staves):
                voices: dict[int, list[Event]] = defaultdict(list)
                for e in by_cell.get((m.index, staff_index), []):
                    voices[e.voice].append(e)
                if not voices:
                    voices[1] = []
                for v in sorted(voices):
                    if not first_staff:
                        _sub(_sub(measure, "backup"), "duration", str(int(m.length * divisions)))
                    first_staff = False
                    number = k * 4 + v
                    t = Fraction(0)
                    pending = (
                        [
                            d
                            for d in score.directions
                            if d.measure == m.index and _direction_part(score, d) == part.id
                        ]
                        if (k == 0 and v == min(voices))
                        else []
                    )
                    ordered = sorted(voices[v], key=lambda e: e.onset)
                    for j, e in enumerate(ordered):
                        for d in [d for d in pending if d.onset <= e.onset]:
                            _direction(measure, d, d.onset - t, divisions)
                            pending.remove(d)
                        if e.onset > t:
                            _sub(
                                _sub(measure, "forward"),
                                "duration",
                                str(int((e.onset - t) * divisions)),
                            )
                            t = e.onset
                        group = e.tuplet_group
                        bounds = (
                            group != 0 and (j == 0 or ordered[j - 1].tuplet_group != group),
                            group != 0
                            and (j + 1 == len(ordered) or ordered[j + 1].tuplet_group != group),
                        )
                        _note(measure, e, number, k + 1, len(part.staves) > 1, divisions, bounds)
                        t += e.duration
                    for d in pending:
                        _direction(measure, d, d.onset - t, divisions)
                    if t < m.length:
                        _sub(
                            _sub(measure, "forward"),
                            "duration",
                            str(int((m.length - t) * divisions)),
                        )
            if m.repeat_end or m.barline_end in ("final", "double") or m.ending_stop:
                bar = _sub(measure, "barline", location="right")
                if m.repeat_end or m.barline_end in ("final", "double"):
                    final = m.repeat_end or m.barline_end == "final"
                    _sub(bar, "bar-style", "light-heavy" if final else "light-light")
                if m.ending_stop:
                    _sub(bar, "ending", number=m.ending_stop[0], type=m.ending_stop[1])
                if m.repeat_end:
                    _sub(bar, "repeat", direction="backward")
    ET.indent(root)
    data = ET.tostring(root, encoding="unicode")
    target.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" '
        '"http://www.musicxml.org/dtds/partwise.dtd">\n' + data + "\n",
        encoding="utf-8",
    )


def _direction_part(score: ReadScore, d: Direction) -> str:
    if d.tempo is not None or d.dashes:
        return score.parts[0].id
    for part in score.parts:
        if d.staff_index in part.staves:
            return part.id
    return score.parts[0].id


def _attributes(
    score: ReadScore,
    measure: ET.Element,
    m: MeasureInfo,
    staves: list[int],
    divisions: int,
    clef_seen: dict[int, tuple[str, int, int] | None],
    key_seen: int | None,
) -> None:
    attrs = ET.Element("attributes")
    if m.index == 0:
        _sub(attrs, "divisions", str(divisions))
    fifths = None
    for km, value in score.key_at.get(staves[0], []):
        if km == m.index:
            fifths = value
    if fifths is None and m.index == 0:
        fifths = 0
    if fifths is not None and fifths != key_seen:
        key = _sub(attrs, "key")
        _sub(key, "fifths", str(fifths))
    if m.time is not None:
        time = _sub(attrs, "time")
        if m.time_symbol:
            time.set("symbol", m.time_symbol)
        _sub(time, "beats", str(m.time[0]))
        _sub(time, "beat-type", str(m.time[1]))
    elif m.index == 0:
        time = _sub(attrs, "time")
        _sub(time, "beats", "4")
        _sub(time, "beat-type", "4")
    if m.index == 0 and len(staves) > 1:
        _sub(attrs, "staves", str(len(staves)))
    for k, staff_index in enumerate(staves):
        here = [c for (cm, _x, c) in score.clef_at.get(staff_index, []) if cm == m.index]
        if not here:
            if m.index == 0:
                here = [("G", 2, 0)]
            else:
                continue
        clef = here[0] if m.index == 0 or clef_seen.get(staff_index) is None else here[-1]
        if clef_seen.get(staff_index) == clef:
            continue
        clef_seen[staff_index] = clef
        element = _sub(attrs, "clef")
        if len(staves) > 1:
            element.set("number", str(k + 1))
        _sub(element, "sign", clef[0])
        _sub(element, "line", str(clef[1]))
        if clef[2]:
            _sub(element, "clef-octave-change", str(clef[2]))
    if len(attrs):
        measure.append(attrs)


def _direction(measure: ET.Element, d: Direction, offset: Fraction, divisions: int) -> None:
    element = _sub(measure, "direction", placement="above" if d.above else "below")
    if d.words:
        dt = _sub(element, "direction-type")
        words = _sub(dt, "words", d.words)
        if d.bold:
            words.set("font-weight", "bold")
    if d.dashes:
        _sub(_sub(element, "direction-type"), "dashes", type=d.dashes, number="1")
    if d.beat_unit is not None and d.per_minute:
        dt = _sub(element, "direction-type")
        metronome = _sub(dt, "metronome", parentheses="no")
        unit, dotted = _beat_unit(d.beat_unit)
        _sub(metronome, "beat-unit", unit)
        if dotted:
            _sub(metronome, "beat-unit-dot")
        _sub(metronome, "per-minute", d.per_minute)
    if len(element) == 0:
        measure.remove(element)
        return
    if offset:
        _sub(element, "offset", str(int(offset * divisions)), sound="yes")
    if d.tempo is not None:
        tempo = d.tempo
        value = str(int(tempo)) if tempo.denominator == 1 else f"{float(tempo):g}"
        _sub(element, "sound", tempo=value)


def _note(
    measure: ET.Element,
    e: Event,
    voice: int,
    staff: int,
    many: bool,
    divisions: int,
    tuplet_bounds: tuple[bool, bool] = (False, False),
) -> None:
    """One note (or a chord, or a rest). ``tuplet_bounds``: whether it starts and whether it
    ends its tuplet group (a program reading the MusicXML makes one tuplet of the notes between,
    not one of each note)."""
    duration = str(int(e.duration * divisions))
    if e.is_rest:
        note = _sub(measure, "note")
        rest = _sub(note, "rest")
        if e.measure_rest:
            rest.set("measure", "yes")
        _sub(note, "duration", duration)
        _sub(note, "voice", str(voice))
        if not e.measure_rest:
            _type_and_dots(note, e)
        _time_modification(note, e)
        if many:
            _sub(note, "staff", str(staff))
        _tuplet_marks(note, ET.Element("notations"), tuplet_bounds, e)
        return
    heads = sorted(e.heads, key=lambda h: h.diatonic)
    for i, h in enumerate(heads):
        note = _sub(measure, "note")
        if i:
            _sub(note, "chord")
        pitch = _sub(note, "pitch")
        _sub(pitch, "step", h.step)
        if h.alter:
            _sub(pitch, "alter", str(h.alter))
        _sub(pitch, "octave", str(h.octave))
        _sub(note, "duration", duration)
        if h.tie_stop:
            _sub(note, "tie", type="stop")
        if h.tie_start:
            _sub(note, "tie", type="start")
        _sub(note, "voice", str(voice))
        _type_and_dots(note, e)
        if h.accidental is not None:
            _sub(
                note,
                "accidental",
                {-2: "flat-flat", -1: "flat", 0: "natural", 1: "sharp", 2: "double-sharp"}[
                    h.accidental
                ],
            )
        _time_modification(note, e)
        if e.stem:
            _sub(note, "stem", "up" if e.stem == 1 else "down")
        if many:
            _sub(note, "staff", str(staff))
        notations = ET.Element("notations")
        if h.tie_stop:
            _sub(notations, "tied", type="stop")
        if h.tie_start:
            _sub(notations, "tied", type="start")
        if i == 0:
            for _ in range(e.slur_stops):
                _sub(notations, "slur", type="stop")
            for _ in range(e.slur_starts):
                _sub(notations, "slur", type="start")
        if e.fermata and i == 0:
            _sub(notations, "fermata", type="upright" if e.voice % 2 == 1 else "inverted")
        _tuplet_marks(note, notations, tuplet_bounds if i == 0 else (False, False), e)
        if i == 0:
            for lyric in sorted(e.lyrics, key=lambda ly: ly.number):
                el = _sub(note, "lyric", number=str(lyric.number))
                if lyric.above:
                    el.set("placement", "above")
                pieces = lyric.text.split(UNDERTIE)
                for j, piece in enumerate(pieces):
                    if j:
                        _sub(el, "elision", UNDERTIE)  # two syllables sung on one note
                    _sub(el, "syllabic", lyric.syllabic if len(pieces) == 1 else "single")
                    _sub(el, "text", piece)
                if lyric.extend_to is not None or lyric.line is not None:
                    _sub(el, "extend")  # held: a line drawn, or set at its note (too short)


def _time_modification(note: ET.Element, e: Event) -> None:
    if e.tuplet_shown is None:
        return
    # the ratio in the notes' own value: a triplet of eighths is 3 in the time of 2; Finale's duplet
    # of quarters in the time of three eighths is 4 quarters in the time of 3. MuseScore takes a
    # tuplet's value from its notes and ignores <normal-type>, so it is said this way, which every
    # program reads alike; the number printed over the notes is kept on the tuplet (_tuplet_marks)
    tm = _sub(note, "time-modification")
    _sub(tm, "actual-notes", str(e.tuplet.denominator))
    _sub(tm, "normal-notes", str(e.tuplet.numerator))


def _tuplet_marks(
    note: ET.Element, notations: ET.Element, bounds: tuple[bool, bool], e: Event | None = None
) -> None:
    """Add the start and stop of a tuplet group, then the notations if there are any."""
    starts, stops = bounds
    if starts:
        mark = _sub(notations, "tuplet", type="start", bracket="yes")
        if e is not None and e.tuplet_shown is not None:
            shown = e.tuplet_shown
            if shown != (e.tuplet.denominator, e.tuplet.numerator):
                # the number printed over the notes ("2"), not the ratio written above ("4")
                mark.set("show-number", "actual")
                actual = _sub(mark, "tuplet-actual")
                _sub(actual, "tuplet-number", str(shown[0]))
                normal = _sub(mark, "tuplet-normal")
                _sub(normal, "tuplet-number", str(shown[1]))
    if stops:
        _sub(notations, "tuplet", type="stop")
    if len(notations):
        note.append(notations)


def _type_and_dots(note: ET.Element, e: Event) -> None:
    base = (e.rest if e.rest is not None else e.heads[0].base) / (2**e.halvings)
    _sub(note, "type", _TYPES.get(base, "quarter"))
    for _ in range(e.dots):
        _sub(note, "dot")


__all__ = ["write_musicxml"]
