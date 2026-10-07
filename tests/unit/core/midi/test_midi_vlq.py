"""Variable-length quantity bounds: canonical bytes, typed failure, deltas not absolute ticks."""

from dataclasses import replace

import pytest

from barbershop_tracks.core.midi import EventKind, MidiEvent, MidiExportError, encode_midi
from barbershop_tracks.core.midi.encode import vlq
from midi_builders import decode, exported

VLQ_MAX = 0x0FFFFFFF


@pytest.mark.parametrize(
    ("value", "encoded"),
    [
        (0, "00"),
        (127, "7f"),
        (128, "8100"),
        (16_383, "ff7f"),
        (16_384, "818000"),
        (2_097_151, "ffff7f"),
        (2_097_152, "81808000"),
        (VLQ_MAX, "ffffff7f"),  # the largest four-byte quantity
    ],
)
def test_representable_values_have_one_canonical_encoding(value: int, encoded: str) -> None:
    assert vlq(value).hex() == encoded


@pytest.mark.parametrize("value", [VLQ_MAX + 1, 2**32, -1, -128])
def test_unrepresentable_or_negative_values_are_typed_errors_never_truncated(value: int) -> None:
    with pytest.raises(MidiExportError) as info:
        vlq(value)
    assert info.value.code == "MIDI_DELTA_OUT_OF_RANGE"


def with_voice_events(*events: MidiEvent, end_tick: int):  # type: ignore[no-untyped-def]
    plan = exported().plan
    voice = replace(
        plan.tracks[1],
        events=(
            MidiEvent(0, EventKind.TRACK_NAME, None, (), "Tenor"),
            *events,
            MidiEvent(end_tick, EventKind.END_OF_TRACK),
        ),
    )
    return replace(plan, tracks=(plan.tracks[0], voice, *plan.tracks[2:]))


def note(tick: int, kind: EventKind) -> MidiEvent:
    return MidiEvent(tick, kind, 0, (60, 80 if kind is EventKind.NOTE_ON else 64))


def test_an_absolute_tick_beyond_one_delta_is_fine_when_every_delta_fits() -> None:
    a, b, c = 200_000_000, 400_000_000, 600_000_000  # each step < VLQ_MAX, absolutes exceed it
    assert c > VLQ_MAX
    plan = with_voice_events(
        note(a, EventKind.NOTE_ON),
        note(b, EventKind.NOTE_OFF),
        end_tick=c,
    )
    track = encode_midi(plan).split(b"MTrk")[2]  # the Tenor chunk
    assert vlq(a) in track
    assert vlq(b - a) in track
    assert vlq(c - b) in track


def test_a_single_gap_over_the_maximum_fails_including_the_gap_to_the_end_of_track() -> None:
    ok = with_voice_events(note(10, EventKind.NOTE_OFF), end_tick=10 + VLQ_MAX)
    encode_midi(ok)  # the empty trailing region before EOT is exactly representable
    with pytest.raises(MidiExportError) as trailing:
        encode_midi(with_voice_events(note(10, EventKind.NOTE_OFF), end_tick=10 + VLQ_MAX + 1))
    assert trailing.value.code == "MIDI_DELTA_OUT_OF_RANGE"
    with pytest.raises(MidiExportError) as leading:
        encode_midi(with_voice_events(note(VLQ_MAX + 1, EventKind.NOTE_ON), end_tick=VLQ_MAX + 2))
    assert leading.value.code == "MIDI_DELTA_OUT_OF_RANGE"


def test_a_long_trailing_silence_round_trips_through_an_independent_read() -> None:
    # a real export whose last note ends well before the song end: the gap to EOT is a delta
    result = exported()
    tail = decode(result.data).tracks[2][-1]
    assert tail.type == "end_of_track"
    assert tail.time >= 0


def test_deltas_are_never_negative_because_the_order_is_enforced() -> None:
    plan = with_voice_events(note(20, EventKind.NOTE_ON), note(10, EventKind.NOTE_OFF), end_tick=30)
    with pytest.raises(MidiExportError) as info:
        encode_midi(plan)
    assert info.value.code == "MIDI_EVENT_ORDER"
