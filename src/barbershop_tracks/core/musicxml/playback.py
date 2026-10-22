"""Following the tempo a notation program plays, for the scores it can export a playback of.

A MuseScore project exported to MusicXML keeps its tempo marks (a metronome mark, a tempo text with
a number) as ``<sound tempo>``, and its ritardando, accelerando and fermata only as words or not at
all, so BLT would sing straight through them at the opening tempo. MuseScore itself plays them, and
its MIDI export says how: a ritardando as small steps, a fermata as a slower stretch, "a tempo" as
the return (``midi_tempo.py``). When that export is at hand, the tempo of the performance is taken
from it, which is exactly what the person hears in MuseScore, with nothing guessed.

It is used only if it can be trusted: the score must state a tempo of its own, and MuseScore's
playback must agree with every tempo mark BLT reads from the score, at the place it is written. If
anything disagrees (a different reading of the repeats, a tempo mark played at another speed) the
playback is left unused, BLT says so, and the score's own tempo marks decide as they always did.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from fractions import Fraction
from pathlib import Path

from barbershop_tracks.core.musicxml.convert import OpenedScore
from barbershop_tracks.core.musicxml.midi_tempo import MidiTempoError, read_tempo_changes
from barbershop_tracks.core.musicxml.parser import ParseResult
from barbershop_tracks.models import TempoChange

_AGREE = Fraction(1, 100)  # beats per minute: the most a mark and the playback may differ by


@dataclass(frozen=True, slots=True)
class PlaybackTempo:
    """What was done with MuseScore's playback tempo (said to the person, kept in the package)."""

    applied: bool  # the performance's tempo is MuseScore's playback tempo
    changes: int  # how many tempo changes it makes after the opening one
    note: str  # said to the person; empty when there is nothing to say

    def as_record(self) -> dict[str, object]:
        return {
            "source": "MuseScore MIDI export",
            "applied": self.applied,
            "changes": self.changes,
            "note": self.note,
        }


NOT_USED = PlaybackTempo(False, 0, "")


def _bpm_at(changes: Sequence[TempoChange], position: Fraction) -> Fraction:
    playing = changes[0].bpm
    for change in changes:
        if change.position <= position:
            playing = change.bpm
        else:
            break
    return playing


def apply_playback_tempo(
    parsed: ParseResult, changes: Sequence[TempoChange]
) -> tuple[ParseResult, PlaybackTempo]:
    """``parsed`` with the playback tempo as its tempo, if it can be trusted; with what was done."""
    performed = parsed.performed
    if performed is None or not performed.tempo_events or not changes:
        return parsed, NOT_USED  # a score with no tempo of its own stays blocked, not given one
    if changes[0].position != 0:
        return parsed, NOT_USED
    for mark in performed.tempo_events:
        if abs(_bpm_at(changes, mark.position) - mark.bpm) > _AGREE:
            return parsed, PlaybackTempo(
                False,
                0,
                "MuseScore's playback does not agree with the tempo marks of the score (around "
                f"quarter note {float(mark.position):g}), so the score's own tempo marks are used "
                "and a ritardando or fermata is not followed.",
            )
    own = tuple((t.position, t.bpm) for t in performed.tempo_events)
    if own == tuple((t.position, t.bpm) for t in changes):
        return parsed, NOT_USED  # nothing but the marks: nothing to follow
    done = PlaybackTempo(
        True,
        len(changes) - 1,
        f"The tempo follows MuseScore's playback: {len(changes) - 1} tempo "
        f"change{'' if len(changes) == 2 else 's'} (a ritardando, a fermata or a return to the "
        "first tempo, as MuseScore plays them).",
    )
    return replace(parsed, performed=replace(performed, tempo_events=tuple(changes))), done


def parse_with_playback_tempo(
    opened: OpenedScore, parse: Callable[[Path], ParseResult]
) -> tuple[ParseResult, PlaybackTempo]:
    """Parse the score of ``opened`` and follow MuseScore's playback tempo if it is at hand."""
    return follow_playback_tempo(opened, parse(opened.parse_path))


def follow_playback_tempo(
    opened: OpenedScore, parsed: ParseResult
) -> tuple[ParseResult, PlaybackTempo]:
    """``parsed`` with MuseScore's playback tempo, if ``opened`` has it and it can be trusted."""
    if opened.playback_midi is None:
        return parsed, NOT_USED
    try:
        changes = read_tempo_changes(opened.playback_midi.read_bytes())
    except (OSError, MidiTempoError):
        return parsed, NOT_USED
    return apply_playback_tempo(parsed, changes)
