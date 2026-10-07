"""``PerformedSong`` + role assignments -> ``MidiPlan``, with the serializer's own safety checks.

This does not re-run the readiness framework; it checks the invariants the file itself relies on.
"""

from collections.abc import Iterable
from fractions import Fraction

from barbershop_tracks.core.midi.errors import MidiExportError
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
    MidiPlan,
    MidiTrack,
    MidiWarning,
    RoleSummary,
    TempoRecord,
)
from barbershop_tracks.core.midi.tempo import encode_tempo
from barbershop_tracks.core.midi.ticks import DEFAULT_PPQ, to_ticks, validate_ppq
from barbershop_tracks.core.readiness.assignments import RoleAssignments
from barbershop_tracks.models import PerformanceNote, PerformedSong, VoiceRole


def _sorted(events: Iterable[MidiEvent]) -> tuple[MidiEvent, ...]:
    return tuple(sorted(events, key=lambda event: event.sort_key))


def _resolve_lines(performed: PerformedSong, assignments: RoleAssignments) -> dict[VoiceRole, str]:
    chosen: dict[VoiceRole, str] = {}
    for role in VOICE_ORDER:
        lines = assignments.lines_for(role)
        if not lines:
            raise MidiExportError("MIDI_ROLE_MISSING", f"{role.display_name} has no assigned line")
        if len(lines) > 1:
            raise MidiExportError(
                "MIDI_ROLE_DUPLICATE",
                f"{role.display_name} is assigned {len(lines)} lines: {', '.join(lines)}",
            )
        if performed.line(lines[0]) is None:
            raise MidiExportError(
                "MIDI_LINE_UNKNOWN", f"{role.display_name} is assigned unknown line {lines[0]}"
            )
        chosen[role] = lines[0]
    values = list(chosen.values())
    shared = sorted({line for line in values if values.count(line) > 1})
    if shared:
        raise MidiExportError(
            "MIDI_LINE_SHARED", f"one line is assigned to several roles: {', '.join(shared)}"
        )
    return chosen


def _midi_pitch(note: PerformanceNote) -> int:
    pitch = note.pitch  # the performed SOUNDING pitch, never the written one
    if pitch is None:
        raise MidiExportError("MIDI_PITCH_MISSING", f"a sounding note at {note.start} has no pitch")
    height = pitch.absolute_semitones
    if height.denominator != 1:
        raise MidiExportError(
            "MIDI_PITCH_NOT_INTEGRAL", f"{pitch} at {note.start} is not an equal-tempered pitch"
        )
    if not 0 <= height <= 127:
        raise MidiExportError(
            "MIDI_PITCH_OUT_OF_RANGE", f"{pitch} at {note.start} is outside MIDI notes 0..127"
        )
    return int(height)


def _voice_events(
    role: VoiceRole, line_id: str, performed: PerformedSong, ppq: int, end_tick: int
) -> tuple[list[MidiEvent], RoleSummary]:
    channel = VOICE_CHANNELS[role]
    attacks = sorted(
        (a for a in performed.attacks(line_id) if not a.is_rest),
        key=lambda a: (a.start, a.end),
    )
    if not attacks:
        raise MidiExportError("MIDI_VOICE_EMPTY", f"{role.display_name} has no sounding notes")
    events: list[MidiEvent] = []
    pitches: list[int] = []
    previous: PerformanceNote | None = None
    for attack in attacks:
        if attack.duration <= 0:
            raise MidiExportError(
                "MIDI_NOTE_DURATION_INVALID", f"a note at {attack.start} has no positive duration"
            )
        if previous is not None and attack.start < previous.end:
            raise MidiExportError(
                "MIDI_VOICE_OVERLAP",
                f"{role.display_name} sounds two notes at once around {attack.start}",
            )
        pitch = _midi_pitch(attack)
        start = to_ticks(attack.start, ppq, what=f"{role.display_name} note start")
        stop = to_ticks(attack.end, ppq, what=f"{role.display_name} note end")
        if stop > end_tick:
            raise MidiExportError(
                "MIDI_NOTE_AFTER_END", f"{role.display_name} note at {attack.start} passes the end"
            )
        events.append(MidiEvent(start, EventKind.NOTE_ON, channel, (pitch, NOTE_ON_VELOCITY)))
        events.append(MidiEvent(stop, EventKind.NOTE_OFF, channel, (pitch, NOTE_OFF_VELOCITY)))
        pitches.append(pitch)
        previous = attack
    line = performed.line(line_id)
    if line is None:  # unreachable after _resolve_lines; keeps the types honest
        raise MidiExportError("MIDI_LINE_UNKNOWN", f"unknown line {line_id}")
    summary = RoleSummary(
        role=role,
        track_name=role.display_name,
        channel=channel,
        line_id=line_id,
        part_name=line.part.name,
        attacks=len(attacks),
        lowest_midi=min(pitches),
        highest_midi=max(pitches),
    )
    return events, summary


def _tempo(
    performed: PerformedSong, ppq: int, end_tick: int
) -> tuple[list[MidiEvent], list[TempoRecord], list[MidiWarning]]:
    ordered = sorted(
        ((to_ticks(t.position, ppq, what="tempo event"), t) for t in performed.tempo_events),
        key=lambda pair: pair[0],  # stable: performed order decides among equal ticks
    )
    by_tick: dict[int, TempoRecord] = {}
    for tick, change in ordered:
        if tick > end_tick:
            raise MidiExportError(
                "MIDI_EVENT_AFTER_END", f"a tempo event at {change.position} is after the end"
            )
        encoding = encode_tempo(change.bpm)
        encoded = encoding.encoded_us_per_quarter
        earlier = by_tick.get(tick)
        if earlier is not None:
            if earlier.encoded_us_per_quarter != encoded:
                raise MidiExportError(
                    "MIDI_TEMPO_CONFLICT",
                    f"different tempos at {change.position}: {earlier.bpm} and {change.bpm} BPM",
                )
            continue  # an identical event at the same tick is emitted once
        by_tick[tick] = TempoRecord(
            position=change.position,
            tick=tick,
            bpm=change.bpm,
            exact_us_per_quarter=encoding.exact_us_per_quarter,
            encoded_us_per_quarter=encoded,
            error_us_per_quarter=encoding.error_us_per_quarter,
            bpm_error=encoding.bpm_error,
        )
    if 0 not in by_tick:
        raise MidiExportError("MIDI_TEMPO_MISSING", "no tempo is declared at position zero")
    records = [by_tick[tick] for tick in sorted(by_tick)]
    events = [
        MidiEvent(r.tick, EventKind.TEMPO, None, (r.encoded_us_per_quarter,)) for r in records
    ]
    warnings = [
        MidiWarning(
            "MIDI_TEMPO_QUANTIZED",
            f"{r.bpm} BPM at {r.position} needs {r.exact_us_per_quarter} us per quarter; "
            f"{r.encoded_us_per_quarter} was written (error {r.error_us_per_quarter} us)",
        )
        for r in records
        if r.error_us_per_quarter != 0
    ]
    return events, records, warnings


def _meter(
    performed: PerformedSong, ppq: int, end_tick: int
) -> tuple[list[MidiEvent], list[MeterRecord], list[MidiWarning]]:
    chosen: dict[int, tuple[int, int]] = {}
    records: list[MeterRecord] = []
    events: list[MidiEvent] = []
    warnings: list[MidiWarning] = []
    declared = sorted(
        (
            (to_ticks(e.signature.position, ppq, what="meter event"), e.signature)
            for e in performed.meter_events
        ),
        key=lambda pair: pair[0],
    )
    for tick, signature in declared:
        if tick > end_tick:
            raise MidiExportError(
                "MIDI_EVENT_AFTER_END", f"a meter event at {signature.position} is after the end"
            )
        meter = (signature.beats, signature.beat_type)
        if tick in chosen:
            if chosen[tick] != meter:
                raise MidiExportError(
                    "MIDI_METER_CONFLICT", f"different meters at {signature.position}"
                )
            continue
        chosen[tick] = meter
        encoding = encode_meter(signature)
        if isinstance(encoding, MeterEncoding):
            records.append(
                MeterRecord(signature.position, tick, signature.beats, signature.beat_type, True)
            )
            data = (
                encoding.numerator,
                encoding.denominator_exponent,
                METER_CLICK_CLOCKS,
                METER_32NDS_PER_QUARTER,
            )
            events.append(MidiEvent(tick, EventKind.TIME_SIGNATURE, None, data))
        else:
            records.append(
                MeterRecord(
                    signature.position, tick, signature.beats, signature.beat_type, False, encoding
                )
            )
            warnings.append(
                MidiWarning(
                    "MIDI_METER_NOT_REPRESENTABLE",
                    f"{signature.beats}/{signature.beat_type} at {signature.position} was omitted: "
                    f"{encoding}",
                )
            )
    if not records:
        warnings.append(
            MidiWarning(
                "METER_NONE_EMITTED",
                "the score declares no meter, so no time signature is written "
                "(MIDI readers assume 4/4)",
            )
        )
    return events, records, warnings


def build_midi_plan(
    performed: PerformedSong, assignments: RoleAssignments, *, ppq: int = DEFAULT_PPQ
) -> MidiPlan:
    ppq = validate_ppq(ppq)
    played = performed.plan
    end: Fraction = played.end if played.played else performed.song.duration
    end_tick = to_ticks(end, ppq, what="song end")
    lines = _resolve_lines(performed, assignments)

    tempo_events, tempo_records, tempo_warnings = _tempo(performed, ppq, end_tick)
    meter_events, meter_records, meter_warnings = _meter(performed, ppq, end_tick)

    conductor = [
        MidiEvent(0, EventKind.TRACK_NAME, None, (), CONDUCTOR_NAME),
        *meter_events,
        *tempo_events,
        MidiEvent(end_tick, EventKind.END_OF_TRACK),
    ]
    tracks = [MidiTrack(CONDUCTOR_NAME, None, _sorted(conductor))]
    summaries: list[RoleSummary] = []
    for role in VOICE_ORDER:
        notes, summary = _voice_events(role, lines[role], performed, ppq, end_tick)
        summaries.append(summary)
        voice = [
            MidiEvent(0, EventKind.TRACK_NAME, None, (), role.display_name),
            *notes,
            MidiEvent(end_tick, EventKind.END_OF_TRACK),
        ]
        tracks.append(MidiTrack(role.display_name, VOICE_CHANNELS[role], _sorted(voice)))
    return MidiPlan(
        ppq=ppq,
        end_position=end,
        end_tick=end_tick,
        tracks=tuple(tracks),
        roles=tuple(summaries),
        tempo=tuple(tempo_records),
        meter=tuple(meter_records),
        warnings=tuple(tempo_warnings + meter_warnings),
    )
