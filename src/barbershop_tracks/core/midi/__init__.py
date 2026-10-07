"""Deterministic quartet MIDI: exact ticks, a fixed track layout, bytes verified by read-back.

Pure and in memory; the handoff package (file names, manifest, filesystem) is a later layer.
"""

from barbershop_tracks.core.midi.build import build_midi_plan
from barbershop_tracks.core.midi.encode import encode_midi
from barbershop_tracks.core.midi.errors import MidiExportError, MidiVerificationError
from barbershop_tracks.core.midi.export import export_midi
from barbershop_tracks.core.midi.meter import (
    METER_32NDS_PER_QUARTER,
    METER_CLICK_CLOCKS,
    MeterEncoding,
    encode_meter,
)
from barbershop_tracks.core.midi.model import (
    CONDUCTOR_NAME,
    NOTE_OFF_VELOCITY,
    NOTE_ON_VELOCITY,
    VOICE_CHANNELS,
    VOICE_ORDER,
    EventKind,
    MeterRecord,
    MidiEvent,
    MidiExport,
    MidiPlan,
    MidiTrack,
    MidiWarning,
    RoleSummary,
    TempoRecord,
)
from barbershop_tracks.core.midi.tempo import TempoEncoding, encode_tempo
from barbershop_tracks.core.midi.ticks import DEFAULT_PPQ, MAX_PPQ, MIN_PPQ, to_ticks, validate_ppq
from barbershop_tracks.core.midi.verify import verify_midi_bytes

__all__ = [
    "CONDUCTOR_NAME",
    "DEFAULT_PPQ",
    "MAX_PPQ",
    "METER_32NDS_PER_QUARTER",
    "METER_CLICK_CLOCKS",
    "MIN_PPQ",
    "NOTE_OFF_VELOCITY",
    "NOTE_ON_VELOCITY",
    "VOICE_CHANNELS",
    "VOICE_ORDER",
    "EventKind",
    "MeterEncoding",
    "MeterRecord",
    "MidiEvent",
    "MidiExport",
    "MidiExportError",
    "MidiPlan",
    "MidiTrack",
    "MidiVerificationError",
    "MidiWarning",
    "RoleSummary",
    "TempoEncoding",
    "TempoRecord",
    "build_midi_plan",
    "encode_meter",
    "encode_midi",
    "encode_tempo",
    "export_midi",
    "to_ticks",
    "validate_ppq",
    "verify_midi_bytes",
]
