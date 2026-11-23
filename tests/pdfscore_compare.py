"""Comparing two readings of one score, as BLT parses them: the lines, notes, words and tempo.

Used by the tests of the PDF reader: a PDF exported from a score has to give the same reading as
the MusicXML exported from the same score.
"""

from dataclasses import dataclass, field
from fractions import Fraction

from barbershop_tracks.core.musicxml.parser import ParseResult
from barbershop_tracks.models import LyricKind, Note


@dataclass(slots=True)
class Comparison:
    differences: list[str] = field(default_factory=list)
    notes_compared: int = 0
    notes_equal: int = 0
    lyrics_compared: int = 0
    lyrics_equal: int = 0

    @property
    def same(self) -> bool:
        return not self.differences

    def summary(self) -> str:
        return (
            f"notes {self.notes_equal}/{self.notes_compared}, "
            f"lyrics {self.lyrics_equal}/{self.lyrics_compared}, "
            f"{len(self.differences)} differences"
        )


def _sounding(note: Note) -> int | None:
    if note.written_pitch is None:
        return None
    return note.transform.apply(note.written_pitch).midi_note


def _lyric(note: Note) -> str:
    found = []
    for lyric in note.lyrics:
        if lyric.kind is LyricKind.TEXT and lyric.verse in (None, "1"):
            found.append(f"{lyric.text}/{lyric.syllabic.value}")
    return " ".join(found)


def _describe(note: Note) -> str:
    pitch = _sounding(note)
    tie = ("~" if note.tied_from_previous else "") + ("~" if note.tied_to_next else "")
    tie += ")" * note.slurs_closed + "(" * note.slurs_opened
    return (
        f"m{note.measure} b{note.beat} {'rest' if pitch is None else pitch}{tie} "
        f"len {note.duration} '{_lyric(note)}'"
    )


def compare(expected: ParseResult, actual: ParseResult, *, limit: int = 12) -> Comparison:
    result = Comparison()
    diff = result.differences
    a, b = expected.song, actual.song
    if a is None or b is None:
        diff.append("a score could not be read")
        return result
    if len(a.measures) != len(b.measures):
        diff.append(f"measures: {len(a.measures)} != {len(b.measures)}")
    ta = [(t.position, t.bpm) for t in a.tempo_map]
    tb = [(t.position, t.bpm) for t in b.tempo_map]
    if ta != tb:
        diff.append(f"tempo: {ta} != {tb}")
    ma = [(m.position, m.beats, m.beat_type) for m in a.time_signatures]
    mb = [(m.position, m.beats, m.beat_type) for m in b.time_signatures]
    if ma != mb:
        diff.append(f"meter: {ma} != {mb}")
    if a.key_signature != b.key_signature:
        diff.append(f"key: {a.key_signature} != {b.key_signature}")
    pa, pb = expected.performed, actual.performed
    if pa is not None and pb is not None:
        # the order the music is sung in: repeats, endings and jumps expanded
        if pa.plan.end != pb.plan.end:
            diff.append(f"performed length: {pa.plan.end} != {pb.plan.end}")
        order_a = [(m.source_index, m.visit) for m in pa.plan.played]
        order_b = [(m.source_index, m.visit) for m in pb.plan.played]
        if order_a != order_b:
            diff.append(f"performed order: {order_a} != {order_b}")
        sung_a = {
            line.part.part_id: [(n.start, n.duration, _sounding(n)) for n in line.part.events]
            for line in pa.lines
        }
        sung_b = {
            line.part.part_id: [(n.start, n.duration, _sounding(n)) for n in line.part.events]
            for line in pb.lines
        }
        for line_id in sorted(set(sung_a) & set(sung_b)):
            if sung_a[line_id] != sung_b[line_id]:
                diff.append(f"{line_id}: the performed notes differ")
    lines_a = {p.part_id: p for p in a.parts}
    lines_b = {p.part_id: p for p in b.parts}
    if set(lines_a) != set(lines_b):
        diff.append(f"lines: {sorted(lines_a)} != {sorted(lines_b)}")
    for line in sorted(set(lines_a) & set(lines_b)):
        ea = list(lines_a[line].events)
        eb = list(lines_b[line].events)
        shown = 0
        for i in range(max(len(ea), len(eb))):
            na = ea[i] if i < len(ea) else None
            nb = eb[i] if i < len(eb) else None
            if na is not None and na.written_pitch is not None:
                result.notes_compared += 1
                if _lyric(na):
                    result.lyrics_compared += 1
            if na is None or nb is None:
                diff.append(f"{line}: {len(ea)} events != {len(eb)} events")
                break
            same_note = (
                na.start == nb.start
                and na.measure == nb.measure
                and na.beat == nb.beat
                and na.duration == nb.duration
                and _sounding(na) == _sounding(nb)
                and na.tied_to_next == nb.tied_to_next
                and na.tied_from_previous == nb.tied_from_previous
                and (na.slurs_opened, na.slurs_closed) == (nb.slurs_opened, nb.slurs_closed)
            )
            if same_note and na.written_pitch is not None:
                result.notes_equal += 1
            same_words = _lyric(na) == _lyric(nb)
            if same_words and _lyric(na):
                result.lyrics_equal += 1
            if not (same_note and same_words):
                if shown < limit:
                    diff.append(f"{line} #{i}: {_describe(na)}  |  {_describe(nb)}")
                shown += 1
                if na.start != nb.start:
                    diff.append(f"{line}: out of step from event {i}; the rest is not compared")
                    break
    return result


def same_tempo(a: ParseResult, b: ParseResult) -> bool:
    pa, pb = a.performed, b.performed
    if pa is None or pb is None:
        return False
    return [(t.position, t.bpm) for t in pa.tempo_events] == [
        (t.position, t.bpm) for t in pb.tempo_events
    ]


__all__ = ["Comparison", "Fraction", "compare", "same_tempo"]
