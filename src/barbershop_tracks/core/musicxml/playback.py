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
from barbershop_tracks.core.musicxml.fermata_tails import tempo_changes_heard, with_fermata_tails
from barbershop_tracks.core.musicxml.midi_tempo import (
    MidiTempoError,
    read_length,
    read_tempo_changes,
)
from barbershop_tracks.core.musicxml.parser import ParseResult
from barbershop_tracks.models import TempoChange

_AGREE = Fraction(1, 100)  # beats per minute: the most a mark and the playback may differ by
# quarter notes: the most the length of the score and the length of MuseScore's playback may differ
# by; a different number of beats (a pickup read as a whole bar) puts every tempo change on the
# wrong notes
_SAME_LENGTH = Fraction(1, 2)


@dataclass(frozen=True, slots=True)
class PlaybackTempo:
    """What was done with MuseScore's playback tempo (said to the person, kept in the package)."""

    applied: bool  # the performance's tempo is MuseScore's playback tempo
    changes: int  # how many tempo changes it makes after the opening one
    note: str  # said to the person; empty when there is nothing to say
    # where the playback tempo came from: MuseScore's own export, or the score's marks played
    # by MuseScore's rules (``marked_playback.py``)
    source: str = "MuseScore MIDI export"

    def as_record(self) -> dict[str, object]:
        return {
            "source": self.source,
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


def _agrees(changes: Sequence[TempoChange], mark: TempoChange) -> bool:
    """MuseScore plays ``mark`` at its place: at that tempo, or as a fermata stretch of it.

    A tempo mark on a note with a fermata is played slower for the length of the fermata, and the
    stretch begins exactly at the mark. That is the mark being followed, if the first faster tempo
    after the stretch is the mark's own.
    """
    playing = _bpm_at(changes, mark.position)
    if abs(playing - mark.bpm) <= _AGREE:
        return True
    if playing >= mark.bpm or not any(c.position == mark.position for c in changes):
        return False
    for change in changes:
        if change.position > mark.position and change.bpm > playing:
            return abs(change.bpm - mark.bpm) <= _AGREE
    return False


def apply_playback_tempo(
    parsed: ParseResult, changes: Sequence[TempoChange], length: Fraction | None = None
) -> tuple[ParseResult, PlaybackTempo]:
    """``parsed`` with the playback tempo as its tempo, if it can be trusted; with what was done.

    ``length`` is how long MuseScore's playback is, in quarter notes: the tempo changes are at
    MuseScore's positions, so they are only used if the score is as long as MuseScore plays it.
    """
    performed = parsed.performed
    if performed is None or not performed.tempo_events or not changes:
        return parsed, NOT_USED  # a score with no tempo of its own stays blocked, not given one
    if changes[0].position != 0:
        return parsed, NOT_USED
    if length is not None:
        ours = performed.plan.end if performed.plan.played else performed.song.duration
        if abs(ours - length) > _SAME_LENGTH:
            return parsed, PlaybackTempo(
                False,
                0,
                f"MuseScore's playback is {float(length):g} quarter notes long but the score read "
                f"here is {float(ours):g}, so its tempo changes would fall on the wrong notes: the "
                "score's own tempo marks are used and a ritardando or fermata is not followed.",
            )
    for mark in performed.tempo_events:
        if not _agrees(changes, mark):
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
    heard = tempo_changes_heard(changes)
    done = PlaybackTempo(
        True,
        heard,
        f"The tempo follows MuseScore's playback: {heard} tempo "
        f"change{'' if heard == 1 else 's'} (a ritardando, a fermata or a return to the "
        "first tempo, as MuseScore plays them).",
    )
    shaped = with_fermata_tails(changes)
    opening = min(performed.tempo_events, key=lambda mark: mark.position).bpm
    return replace(
        parsed, performed=replace(performed, tempo_events=shaped, opening_bpm=opening)
    ), done


def _follow_marks(opened: OpenedScore, parsed: ParseResult) -> tuple[ParseResult, PlaybackTempo]:
    from barbershop_tracks.core.errors import ScoreLoadError
    from barbershop_tracks.core.musicxml.marked_playback import marked_tempo_changes
    from barbershop_tracks.core.musicxml.source import load_musicxml_source

    try:
        root = load_musicxml_source(opened.parse_path).root
    except (ScoreLoadError, OSError, ValueError):
        return parsed, NOT_USED
    changes = marked_tempo_changes(root, parsed)
    if not changes:
        return parsed, NOT_USED
    result, done = apply_playback_tempo(parsed, changes)
    if not done.applied:
        return parsed, NOT_USED
    heard = done.changes
    return result, replace(
        done,
        source="the score's fermatas and tempo lines, played as MuseScore plays them",
        note=(
            f"The tempo follows the score's fermatas and tempo lines as MuseScore plays them: "
            f"{heard} tempo change{'' if heard == 1 else 's'} (a fermata, a ritardando or a "
            "return to the first tempo)."
        ),
    )


def parse_with_playback_tempo(
    opened: OpenedScore, parse: Callable[[Path], ParseResult]
) -> tuple[ParseResult, PlaybackTempo]:
    """Parse the score of ``opened`` and follow MuseScore's playback tempo if it is at hand."""
    return follow_playback_tempo(opened, parse(opened.parse_path))


def follow_playback_tempo(
    opened: OpenedScore, parsed: ParseResult
) -> tuple[ParseResult, PlaybackTempo]:
    """``parsed`` with MuseScore's playback tempo, if ``opened`` has it and it can be trusted.

    Without a playback (a MusicXML file, a PDF), the tempo MuseScore would play is worked out from
    the score's fermatas and tempo lines, so the song sounds as it does from its project.
    """
    if opened.playback_midi is None:
        return _follow_marks(opened, parsed)
    try:
        data = opened.playback_midi.read_bytes()
        changes = read_tempo_changes(data)
        length = read_length(data)
    except (OSError, MidiTempoError):
        return parsed, NOT_USED
    return apply_playback_tempo(parsed, changes, length)
