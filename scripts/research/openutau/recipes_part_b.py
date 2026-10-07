"""Part B recipes: deliberately tiny *experimental* MIDI files with lyric meta events.

These are research inputs only, never BLT Music Generator output: they are written with ``mido``
directly and the production exporter is not involved. A lyric event sits at the note's own tick,
before its note-on. ``lyric=None`` means no lyric event at all for that note.
"""

import io
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import mido

PPQ = 480
BPM = 100
QUARTER = PPQ
_CHANNELS = {"Tenor": 0, "Lead": 1, "Baritone": 2, "Bass": 3}
_PRIORITY = {"lyrics": 0, "note_off": 1, "note_on": 2, "end_of_track": 9}


@dataclass(frozen=True, slots=True)
class LyricNote:
    start: int  # tick
    duration: int  # ticks
    pitch: int
    lyric: str | None


@dataclass(frozen=True, slots=True)
class LyricTrack:
    name: str
    notes: tuple[LyricNote, ...]


@dataclass(frozen=True, slots=True)
class LyricExperiment:
    experiment_id: str
    description: str
    tracks: tuple[LyricTrack, ...]


def _melody(pitches: Sequence[int], lyrics: Sequence[str | None]) -> tuple[LyricNote, ...]:
    return tuple(
        LyricNote(i * QUARTER, QUARTER, pitch, lyric)
        for i, (pitch, lyric) in enumerate(zip(pitches, lyrics, strict=True))
    )


def _single(
    experiment_id: str, description: str, pitches: list[int], lyrics: list[str | None]
) -> LyricExperiment:
    return LyricExperiment(
        experiment_id, description, (LyricTrack("Lead", _melody(pitches, lyrics)),)
    )


def _experiments() -> list[LyricExperiment]:
    c = 60
    out = [
        _single(
            "B01_SYLLABLES",
            "one syllable per note; a multisyllable word; a repeated word; punctuation",
            [c, c + 2, c + 4, c + 5, c + 7, c + 5, c + 4, c + 2, c, c + 2, c + 4, c + 5],
            ["love", "is", "a", "won", "der", "ful", "thing", "la", "la", "hi,", "you", "now."],
        ),
        _single(
            "B02_MISSING_LYRIC",
            "a note with no lyric event between lyric-bearing notes",
            [c, c + 2, c + 4, c + 5],
            ["la", None, "la", None],
        ),
        _single("B03_PLUS", "literal + as the continuation", [c, c + 2, c + 4], ["la", "+", "+"]),
        _single(
            "B04_PLUS_TILDE",
            "literal +~ as the continuation",
            [c, c + 2, c + 4],
            ["la", "+~", "+~"],
        ),
        _single(
            "B05_MELISMA_PLUS",
            "a word over three notes: first syllable, then +, +",
            [c, c + 2, c + 4],
            ["won", "+", "+"],
        ),
        _single(
            "B05_MELISMA_PLUS_TILDE",
            "a word over three notes: first syllable, then +~, +~",
            [c, c + 2, c + 4],
            ["won", "+~", "+~"],
        ),
        _single(
            "B05_MELISMA_MIXED",
            "a word over three notes: first syllable, then +, +~",
            [c, c + 2, c + 4],
            ["won", "+", "+~"],
        ),
        _single(
            "B05_MELISMA_HYPHEN",
            "a word over three notes: first syllable, then -, -",
            [c, c + 2, c + 4],
            ["won", "-", "-"],
        ),
        LyricExperiment(
            "B06_PITCH_CONTINUATION",
            "continuation after a same pitch (Tenor), changed pitches (Lead), repeated adjacent "
            "pitches (Baritone)",
            (
                LyricTrack("Tenor", _melody([64, 64, 64], ["la", "+", "+"])),
                LyricTrack("Lead", _melody([60, 62, 64], ["la", "+", "+"])),
                LyricTrack("Baritone", _melody([55, 55, 57, 57], ["la", "+", "la", "+"])),
            ),
        ),
        LyricExperiment(
            "B07_FOUR_TRACKS",
            "lyric events on all four voice tracks, each track with its own words",
            tuple(
                LyricTrack(name, _melody([base, base + 2, base + 4], words))
                for name, base, words in (
                    ("Tenor", 64, ["ten", "or", "one"]),
                    ("Lead", 60, ["lead", "is", "two"]),
                    ("Baritone", 55, ["bar", "i", "three"]),
                    ("Bass", 48, ["bass", "is", "four"]),
                )
            ),
        ),
        LyricExperiment(
            "B08_ONE_SOURCE_TRACK",
            "lyrics only on the Lead track; Tenor, Baritone and Bass carry notes without lyrics",
            (
                LyricTrack("Tenor", _melody([64, 66, 68], [None, None, None])),
                LyricTrack("Lead", _melody([60, 62, 64], ["lead", "is", "alone"])),
                LyricTrack("Baritone", _melody([55, 57, 59], [None, None, None])),
                LyricTrack("Bass", _melody([48, 50, 52], [None, None, None])),
            ),
        ),
        _single(
            "B09_TEXT",
            "characters that occur in lyrics: apostrophe, hyphen, comma, period, ? and !",
            [c, c + 2, c + 4, c + 5, c + 7, c + 9],
            ["don't", "well-", "come,", "home.", "why?", "oh!"],
        ),
    ]
    return out


EXPERIMENTS: dict[str, LyricExperiment] = {e.experiment_id: e for e in _experiments()}


def build_midi(experiment: LyricExperiment) -> bytes:
    """Format 1: a conductor (tempo, 4/4) and the experiment's voice tracks, deterministic."""
    end = max(n.start + n.duration for t in experiment.tracks for n in t.notes) + QUARTER
    mid = mido.MidiFile(type=1, ticks_per_beat=PPQ)
    conductor = mido.MidiTrack()
    conductor.append(mido.MetaMessage("track_name", name="Conductor", time=0))
    conductor.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    conductor.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(BPM), time=0))
    conductor.append(mido.MetaMessage("end_of_track", time=end))
    mid.tracks.append(conductor)
    for track in experiment.tracks:
        events: list[tuple[int, int, Any]] = []
        channel = _CHANNELS[track.name]
        for note in track.notes:
            if note.lyric is not None:
                events.append(
                    (note.start, _PRIORITY["lyrics"], mido.MetaMessage("lyrics", text=note.lyric))
                )
            events.append(
                (
                    note.start,
                    _PRIORITY["note_on"],
                    mido.Message("note_on", channel=channel, note=note.pitch, velocity=80),
                )
            )
            events.append(
                (
                    note.start + note.duration,
                    _PRIORITY["note_off"],
                    mido.Message("note_off", channel=channel, note=note.pitch, velocity=64),
                )
            )
        events.sort(key=lambda e: (e[0], e[1]))
        voice = mido.MidiTrack()
        voice.append(mido.MetaMessage("track_name", name=track.name, time=0))
        last = 0
        for tick, _, message in events:
            voice.append(message.copy(time=tick - last))
            last = tick
        voice.append(mido.MetaMessage("end_of_track", time=end - last))
        mid.tracks.append(voice)
    buffer = io.BytesIO()
    mid.save(file=buffer)
    return buffer.getvalue()


def expected_events(experiment: LyricExperiment) -> list[dict[str, Any]]:
    """What the file contains, per note: the exact lyric text sent (or ``None``)."""
    return [
        {
            "track": track.name,
            "kind": "lyric_note",
            "pitch": note.pitch,
            "start_tick": note.start,
            "end_tick": note.start + note.duration,
            "lyric": note.lyric,
        }
        for track in experiment.tracks
        for note in track.notes
    ]
