"""Read the encoded bytes back through ``mido`` and compare the decoded semantics to the plan.

"mido can open it" is not the test: every track's decoded events (ticks, kinds, channels, data,
names) must equal the intended ones, in order, and nothing else (no lyrics, no program changes, no
running-status surprises) may appear.
"""

import io

import mido

from barbershop_tracks.core.midi.errors import MidiVerificationError
from barbershop_tracks.core.midi.model import EventKind, MidiEvent, MidiPlan

_Decoded = tuple[int, EventKind, int | None, tuple[int, ...], str]


def _decode(message: mido.Message | mido.MetaMessage, tick: int) -> _Decoded:
    kind = message.type
    if kind == "track_name":
        return (tick, EventKind.TRACK_NAME, None, (), message.name)
    if kind == "set_tempo":
        return (tick, EventKind.TEMPO, None, (message.tempo,), "")
    if kind == "time_signature":
        exponent = message.denominator.bit_length() - 1
        data = (
            message.numerator,
            exponent,
            message.clocks_per_click,
            message.notated_32nd_notes_per_beat,
        )
        return (tick, EventKind.TIME_SIGNATURE, None, data, "")
    if kind == "end_of_track":
        return (tick, EventKind.END_OF_TRACK, None, (), "")
    if kind == "note_on" and message.velocity > 0:
        return (tick, EventKind.NOTE_ON, message.channel, (message.note, message.velocity), "")
    if kind == "note_off":
        return (tick, EventKind.NOTE_OFF, message.channel, (message.note, message.velocity), "")
    raise MidiVerificationError(f"unexpected {kind} message at tick {tick}")


def _expected(event: MidiEvent) -> _Decoded:
    return (event.tick, event.kind, event.channel, event.data, event.text)


def verify_midi_bytes(data: bytes, plan: MidiPlan) -> None:
    """Raise ``MidiVerificationError`` unless ``data`` decodes to exactly ``plan``."""
    try:
        decoded = mido.MidiFile(file=io.BytesIO(data))
    except Exception as error:  # mido raises a variety of types on malformed data
        raise MidiVerificationError(f"the encoded bytes cannot be read back: {error}") from error
    if decoded.type != 1:
        raise MidiVerificationError(f"expected MIDI format 1, read {decoded.type}")
    if decoded.ticks_per_beat != plan.ppq:
        raise MidiVerificationError(f"expected ppq {plan.ppq}, read {decoded.ticks_per_beat}")
    if len(decoded.tracks) != len(plan.tracks):
        raise MidiVerificationError(
            f"expected {len(plan.tracks)} tracks, read {len(decoded.tracks)}"
        )
    for track, read in zip(plan.tracks, decoded.tracks, strict=True):
        tick = 0
        events: list[_Decoded] = []
        for message in read:
            tick += message.time
            events.append(_decode(message, tick))
        intended = [_expected(event) for event in track.events]
        if events != intended:
            first = next(
                (i for i, (a, b) in enumerate(zip(events, intended, strict=False)) if a != b),
                min(len(events), len(intended)),
            )
            raise MidiVerificationError(
                f"track {track.name}: event {first} differs (read "
                f"{events[first] if first < len(events) else 'nothing'}, expected "
                f"{intended[first] if first < len(intended) else 'nothing'})"
            )
        last = events[-1]
        if last[1] is not EventKind.END_OF_TRACK or last[0] != plan.end_tick:
            raise MidiVerificationError(
                f"track {track.name} must end at tick {plan.end_tick}, ends at {last[0]}"
            )
