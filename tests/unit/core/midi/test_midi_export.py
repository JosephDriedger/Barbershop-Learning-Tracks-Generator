"""The pure MIDI export: layout, ordering, safety checks, determinism, read-back."""

from dataclasses import replace
from fractions import Fraction
from types import SimpleNamespace

import mido
import pytest

from barbershop_tracks.core.midi import (
    CONDUCTOR_NAME,
    NOTE_OFF_VELOCITY,
    NOTE_ON_VELOCITY,
    VOICE_CHANNELS,
    VOICE_ORDER,
    EventKind,
    MidiExportError,
    MidiVerificationError,
    build_midi_plan,
    encode_midi,
    verify_midi_bytes,
)
from barbershop_tracks.core.midi.build import _midi_pitch
from barbershop_tracks.core.readiness import RoleAssignments
from barbershop_tracks.models import (
    Note,
    PerformedSong,
    Pitch,
    Step,
    TempoChange,
    TimeSignature,
    VoiceRole,
)
from barbershop_tracks.models.pitch_transform import PitchTransform
from midi_builders import decode, exported, performed_of, quartet_assignments, tempo_at
from readiness_builders import PITCHES, melody, note, quartet_lines

C4 = Pitch(Step.C, 4)
D4 = Pitch(Step.D, 4)


def refuses(code: str, **kwargs) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(MidiExportError) as info:
        exported(**kwargs)
    assert info.value.code == code


def voice_messages(data: bytes, index: int) -> list[tuple[int, mido.Message]]:
    """(absolute tick, message) of one track, read independently with mido."""
    tick, out = 0, []
    for message in decode(data).tracks[index]:
        tick += message.time
        out.append((tick, message))
    return out


# --- the file layout ---


def test_five_tracks_in_fixed_order_with_stable_names_and_channels() -> None:
    result = exported()
    mid = decode(result.data)
    assert mid.type == 1
    assert mid.ticks_per_beat == 480
    names = [t[0].name for t in mid.tracks]
    assert names == [CONDUCTOR_NAME, "Tenor", "Lead", "Baritone", "Bass"]
    assert [role.display_name for role in VOICE_ORDER] == names[1:]
    for index, role in enumerate(VOICE_ORDER, start=1):
        channels = {m.channel for m in mid.tracks[index] if hasattr(m, "channel")}
        assert channels == {VOICE_CHANNELS[role]}
    assert 9 not in VOICE_CHANNELS.values()  # never the percussion channel


def test_voice_order_is_the_role_not_the_source_order() -> None:
    lines = quartet_lines()
    reversed_lines = dict(reversed(list(lines.items())))
    result = exported(performed_of(reversed_lines))
    names = [t.name for t in result.plan.tracks]
    assert names == [CONDUCTOR_NAME, "Tenor", "Lead", "Baritone", "Bass"]
    first_tenor_note = voice_messages(result.data, 1)[1][1]
    assert first_tenor_note.note == PITCHES[VoiceRole.TENOR].midi_note  # tenor, not line 1 = bass


def test_note_events_are_exact_ticks_with_real_note_offs_and_constant_velocity() -> None:
    lead = [note(0, 1, C4), note(1, Fraction(1, 3), D4), note(2, 2, C4)]
    result = exported(performed_of(quartet_lines(lead=lead)))
    events = [(t, m) for t, m in voice_messages(result.data, 2) if m.type.startswith("note")]
    assert [(t, m.type, m.note) for t, m in events] == [
        (0, "note_on", 60),
        (480, "note_off", 60),
        (480, "note_on", 62),
        (640, "note_off", 62),
        (960, "note_on", 60),
        (1920, "note_off", 60),
    ]
    assert {m.velocity for _, m in events if m.type == "note_on"} == {NOTE_ON_VELOCITY}
    assert {m.velocity for _, m in events if m.type == "note_off"} == {NOTE_OFF_VELOCITY}
    assert NOTE_OFF_VELOCITY != 0  # never note-on with velocity zero as the encoding


def test_every_track_ends_at_exactly_the_performed_song_end() -> None:
    result = exported()  # 4 measures of 4 beats
    assert result.plan.end_tick == 16 * 480
    for index in range(5):
        messages = voice_messages(result.data, index)
        assert messages[-1][1].type == "end_of_track"
        assert messages[-1][0] == 16 * 480


def test_a_voice_that_stops_early_keeps_trailing_silence_before_the_end_of_track() -> None:
    result = exported(performed_of(quartet_lines(lead=[note(0, 4, C4)])))
    messages = voice_messages(result.data, 2)
    off = next(t for t, m in messages if m.type == "note_off")
    assert off == 4 * 480
    assert messages[-1][0] == 16 * 480


def test_the_end_follows_the_performed_timeline_with_repeats() -> None:
    result = exported(performed_of(backward_repeat_at=1))  # measures 0..1 played twice
    assert result.plan.end_position == 24
    assert result.plan.end_tick == 24 * 480
    lead_ons = [t for t, m in voice_messages(result.data, 2) if m.type == "note_on"]
    # the melody fills measures 0..1 (8 quarters); the repeat plays it twice, then the silence
    assert lead_ons == [480 * i for i in range(16)]


def test_no_lyric_program_change_or_other_events_are_written() -> None:
    allowed = {
        "track_name",
        "set_tempo",
        "time_signature",
        "note_on",
        "note_off",
        "end_of_track",
    }
    mid = decode(exported().data)
    assert {m.type for track in mid.tracks for m in track} <= allowed


# --- same-tick ordering ---


def test_note_off_precedes_note_on_at_the_same_tick_even_for_the_same_pitch() -> None:
    lead = [note(0, 1, C4), note(1, 1, C4)]  # same pitch, back to back, not tied
    result = exported(performed_of(quartet_lines(lead=lead)))
    kinds = [(t, m.type) for t, m in voice_messages(result.data, 2) if m.type.startswith("note")]
    assert kinds == [(0, "note_on"), (480, "note_off"), (480, "note_on"), (960, "note_off")]


def test_the_total_event_priority_at_one_tick() -> None:
    result = exported(
        performed_of(signatures=[TimeSignature(position=Fraction(0), beats=4, beat_type=4)])
    )
    conductor = [type(m).__name__ + ":" + m.type for _, m in voice_messages(result.data, 0)]
    assert conductor == [
        "MetaMessage:track_name",
        "MetaMessage:time_signature",
        "MetaMessage:set_tempo",
        "MetaMessage:end_of_track",
    ]
    voice = [m.type for t, m in voice_messages(result.data, 2) if t == 0]
    assert voice == ["track_name", "note_on"]
    assert [e.value for e in EventKind] == sorted(e.value for e in EventKind)
    assert EventKind.NOTE_OFF.value < EventKind.NOTE_ON.value < EventKind.END_OF_TRACK.value


def test_a_final_note_off_and_the_end_of_track_share_a_tick_in_the_right_order() -> None:
    result = exported(performed_of(quartet_lines(lead=[note(12, 4, C4)])))
    tail = [(t, m.type) for t, m in voice_messages(result.data, 2)][-2:]
    assert tail == [(16 * 480, "note_off"), (16 * 480, "end_of_track")]


# --- sounding pitch, rests, ties ---


def test_the_performed_sounding_pitch_is_exported_not_the_written_one() -> None:
    octave_down = Note(
        start=Fraction(0),
        duration=Fraction(4),
        measure=1,
        beat=Fraction(1),
        written_pitch=C4,
        transform=PitchTransform(octave_change=-1),
    )
    result = exported(performed_of(quartet_lines(lead=[octave_down])))
    on = next(m for _, m in voice_messages(result.data, 2) if m.type == "note_on")
    assert on.note == 48  # C3 sounds; the written C4 (60) is not exported


def test_rests_emit_nothing_and_tied_notes_are_one_attack() -> None:
    lead = [note(0, 1, C4, to=True), note(1, 1, C4, frm=True), note(2, 1, None), note(3, 1, D4)]
    result = exported(performed_of(quartet_lines(lead=lead)))
    notes = [
        (t, m.type, m.note) for t, m in voice_messages(result.data, 2) if m.type.startswith("note")
    ]
    assert notes == [
        (0, "note_on", 60),
        (960, "note_off", 60),
        (1440, "note_on", 62),
        (1920, "note_off", 62),
    ]
    assert result.plan.roles[1].attacks == 2


# --- tempo and meter in the file ---


def test_tempo_events_are_exported_with_their_records() -> None:
    result = exported(performed_of(tempos=[tempo_at(0, 100), tempo_at(8, 90)]))
    tempos = [(t, m.tempo) for t, m in voice_messages(result.data, 0) if m.type == "set_tempo"]
    assert tempos == [(0, 600000), (8 * 480, 666667)]
    record = result.plan.tempo[1]
    assert record.bpm == 90
    assert record.exact_us_per_quarter == Fraction(2000000, 3)
    assert record.encoded_us_per_quarter == 666667
    assert record.error_us_per_quarter == Fraction(1, 3)
    assert [w.code for w in result.warnings] == ["MIDI_TEMPO_QUANTIZED", "METER_NONE_EMITTED"]


def test_a_missing_tempo_is_an_error_and_120_is_never_invented() -> None:
    refuses("MIDI_TEMPO_MISSING", performed=performed_of(tempos=[]))
    refuses("MIDI_TEMPO_MISSING", performed=performed_of(tempos=[tempo_at(4, 100)]))


def with_tempos(*changes: TempoChange) -> PerformedSong:
    """A performed song whose tempo events are set directly (the Song model forbids duplicates)."""
    return replace(performed_of(), tempo_events=tuple(changes))


def test_identical_same_tick_tempos_are_emitted_once_and_conflicting_ones_fail() -> None:
    once = exported(with_tempos(tempo_at(0, 100), tempo_at(0, 100)))
    assert sum(1 for _, m in voice_messages(once.data, 0) if m.type == "set_tempo") == 1
    refuses("MIDI_TEMPO_CONFLICT", performed=with_tempos(tempo_at(0, 100), tempo_at(0, 120)))


def test_identical_tempos_at_different_ticks_are_preserved() -> None:
    result = exported(performed_of(tempos=[tempo_at(0, 100), tempo_at(8, 100)]))
    assert sum(1 for _, m in voice_messages(result.data, 0) if m.type == "set_tempo") == 2


def test_an_unrepresentable_tempo_is_an_export_error() -> None:
    refuses("MIDI_TEMPO_UNREPRESENTABLE", performed=performed_of(tempos=[tempo_at(0, 3)]))


def test_a_tempo_off_the_tick_grid_is_an_error() -> None:
    refuses(
        "MIDI_TICK_NOT_INTEGRAL",
        performed=performed_of(tempos=[tempo_at(0, 100), tempo_at(Fraction(1, 7), 90)]),
    )


def test_explicit_meters_are_written_with_the_documented_auxiliary_fields() -> None:
    signatures = [
        TimeSignature(position=Fraction(0), beats=4, beat_type=4),
        TimeSignature(position=Fraction(8), beats=6, beat_type=8),
    ]
    result = exported(performed_of(signatures=signatures))
    meters = [(t, m) for t, m in voice_messages(result.data, 0) if m.type == "time_signature"]
    assert [(t, m.numerator, m.denominator) for t, m in meters] == [(0, 4, 4), (8 * 480, 6, 8)]
    assert {(m.clocks_per_click, m.notated_32nd_notes_per_beat) for _, m in meters} == {(24, 8)}
    assert all(r.written for r in result.plan.meter)
    assert "METER_NONE_EMITTED" not in {w.code for w in result.warnings}


def test_no_meter_is_synthesised_from_the_effective_context() -> None:
    result = exported()
    assert not any(m.type == "time_signature" for _, m in voice_messages(result.data, 0))
    assert result.plan.meter == ()
    assert "METER_NONE_EMITTED" in {w.code for w in result.warnings}


def test_an_unrepresentable_meter_is_omitted_with_a_warning_and_recorded() -> None:
    signatures = [
        TimeSignature(position=Fraction(0), beats=4, beat_type=4),
        TimeSignature(position=Fraction(8), beats=256, beat_type=4),
    ]
    result = exported(performed_of(signatures=signatures))
    meters = [m for _, m in voice_messages(result.data, 0) if m.type == "time_signature"]
    assert len(meters) == 1  # the 256/4 is omitted, never approximated
    omitted = [r for r in result.plan.meter if not r.written]
    assert len(omitted) == 1
    assert omitted[0].reason is not None
    assert "MIDI_METER_NOT_REPRESENTABLE" in {w.code for w in result.warnings}


# --- defensive checks (the exporter does not trust the caller) ---


def test_a_roles_must_resolve_to_four_distinct_present_lines() -> None:
    partial = RoleAssignments(entries=tuple(quartet_assignments().entries[:3]))
    with pytest.raises(MidiExportError) as info:
        build_midi_plan(performed_of(), partial)
    assert info.value.code == "MIDI_ROLE_MISSING"
    twice = RoleAssignments(entries=(*quartet_assignments().entries, (VoiceRole.LEAD, "P1/s1/v1")))
    with pytest.raises(MidiExportError) as info:
        build_midi_plan(performed_of(), twice)
    assert info.value.code == "MIDI_ROLE_DUPLICATE"
    refuses("MIDI_LINE_UNKNOWN", lead="P9/s1/v1")
    refuses("MIDI_LINE_SHARED", lead="P1/s1/v1")


def test_overlapping_notes_and_chords_are_refused_without_readiness() -> None:
    refuses(
        "MIDI_VOICE_OVERLAP",
        performed=performed_of(quartet_lines(lead=[note(0, 2, C4), note(1, 1, D4)])),
    )
    refuses(
        "MIDI_VOICE_OVERLAP",
        performed=performed_of(quartet_lines(lead=[note(0, 1, C4), note(0, 1, D4)])),
    )


def test_an_empty_voice_is_refused() -> None:
    refuses("MIDI_VOICE_EMPTY", performed=performed_of(quartet_lines(lead=[note(0, 4, None)])))


def test_microtonal_pitches_are_refused() -> None:
    quarter_sharp = Pitch(Step.C, 4, alter=Fraction(1, 2))
    lead = [note(0, 4, quarter_sharp)]
    refuses("MIDI_PITCH_NOT_INTEGRAL", performed=performed_of(quartet_lines(lead=lead)))


def test_the_midi_range_is_checked_by_the_exporter_even_though_pitch_checks_it_too() -> None:
    top = [note(0, 4, Pitch(Step.G, 9))]  # MIDI 127, the highest
    assert exported(performed_of(quartet_lines(lead=top))).plan.roles[1].highest_midi == 127
    for height in (128, -1):  # a Pitch cannot be built out of range; a stand-in can
        stand_in = SimpleNamespace(
            start=Fraction(0),
            pitch=SimpleNamespace(absolute_semitones=Fraction(height), __str__=lambda s: "x"),
        )
        with pytest.raises(MidiExportError) as info:
            _midi_pitch(stand_in)  # type: ignore[arg-type]
        assert info.value.code == "MIDI_PITCH_OUT_OF_RANGE"


def test_a_note_off_the_tick_grid_is_refused_never_rounded() -> None:
    lead = [note(0, Fraction(1, 7), C4), *melody(C4)[1:]]
    refuses("MIDI_TICK_NOT_INTEGRAL", performed=performed_of(quartet_lines(lead=lead)))
    # the same score is fine at a PPQ that holds sevenths
    assert exported(performed_of(quartet_lines(lead=lead)), ppq=840).plan.ppq == 840


def test_the_ppq_is_validated() -> None:
    refuses("MIDI_PPQ_INVALID", ppq=0)
    refuses("MIDI_PPQ_INVALID", ppq=0x8000)


def test_the_song_end_must_be_on_the_grid_too() -> None:
    lead = [note(0, 4, C4)]
    # a performed end of 4 beats * measures is always on the grid; check the ppq-1 case instead
    result = exported(performed_of(quartet_lines(lead=lead)), ppq=1)
    assert result.plan.end_tick == 16


def test_the_exporter_rejects_a_plan_whose_events_are_out_of_order() -> None:
    plan = exported().plan
    track = plan.tracks[1]
    broken = replace(track, events=tuple(reversed(track.events)))
    with pytest.raises(MidiExportError) as info:
        encode_midi(replace(plan, tracks=(plan.tracks[0], broken, *plan.tracks[2:])))
    assert info.value.code == "MIDI_EVENT_ORDER"


# --- determinism and golden bytes ---


def tiny_performed() -> PerformedSong:
    lines = {
        line_id: [note(0, 4, PITCHES[role])]
        for role, line_id in zip(
            VOICE_ORDER, ("P1/s1/v1", "P2/s1/v1", "P3/s1/v1", "P4/s1/v1"), strict=True
        )
    }
    return performed_of(lines, measures=1)


GOLDEN_TINY = (
    # MThd, length 6, format 1, 5 tracks, division 480
    "4d546864000000060001000501e0"
    # MTrk conductor: 100 BPM, EOT 1920
    "4d54726b0000001900ff0309436f6e647563746f7200ff51030927c08f00ff2f00"
    # MTrk Tenor: ch0 E4 vel 80, off vel 64
    "4d54726b0000001600ff030554656e6f72009040508f0080404000ff2f00"
    # MTrk Lead: ch1 C4
    "4d54726b0000001500ff03044c65616400913c508f00813c4000ff2f00"
    # MTrk Baritone: ch2 G3
    "4d54726b0000001900ff030842617269746f6e65009237508f0082374000ff2f00"
    # MTrk Bass: ch3 C3
    "4d54726b0000001500ff030442617373009330508f0083304000ff2f00"
)
GOLDEN_FULL_SHA = "1fe6dab38a264da5017058ebed674c074035f48642b678643f698be1fc6456e3"


def full_case() -> PerformedSong:
    lead = [
        note(0, 1, C4),
        note(1, Fraction(1, 3), D4),
        note(Fraction(4, 3) + 1, Fraction(2, 3), C4),
        note(3, 1, None),
    ]
    lines = quartet_lines(lead=lead)
    return performed_of(
        lines,
        tempos=[tempo_at(0, 100), tempo_at(8, 90)],
        signatures=[TimeSignature(position=Fraction(0), beats=4, beat_type=4)],
        backward_repeat_at=1,
    )


def test_the_export_is_byte_identical_across_runs() -> None:
    first = exported(full_case())
    second = exported(full_case())
    assert first.data == second.data
    assert first.sha256 == second.sha256
    assert first.plan == second.plan


def test_golden_bytes_of_a_tiny_score() -> None:
    result = exported(tiny_performed())
    assert result.data.hex() == GOLDEN_TINY


def test_golden_hash_of_a_larger_case() -> None:
    assert exported(full_case()).sha256 == GOLDEN_FULL_SHA


# --- read-back verification compares semantics, not just "mido can open it" ---


def test_the_verifier_accepts_what_the_encoder_wrote() -> None:
    result = exported(full_case())
    verify_midi_bytes(result.data, result.plan)


def test_the_verifier_rejects_a_changed_pitch() -> None:
    result = exported(tiny_performed())
    data = bytearray(result.data)
    index = data.index(bytes([0x91, PITCHES[VoiceRole.LEAD].midi_note]))
    data[index + 1] += 1
    with pytest.raises(MidiVerificationError, match="Lead"):
        verify_midi_bytes(bytes(data), result.plan)


def test_the_verifier_rejects_a_wrong_ppq_a_wrong_track_count_and_garbage() -> None:
    result = exported(tiny_performed())
    with pytest.raises(MidiVerificationError, match="ppq"):
        verify_midi_bytes(result.data, replace(result.plan, ppq=960))
    with pytest.raises(MidiVerificationError, match="tracks"):
        verify_midi_bytes(result.data, replace(result.plan, tracks=result.plan.tracks[:4]))
    with pytest.raises(MidiVerificationError):
        verify_midi_bytes(b"not a midi file", result.plan)


def test_the_verifier_rejects_a_changed_end_of_track() -> None:
    result = exported(tiny_performed())
    shorter = replace(result.plan, end_tick=result.plan.end_tick - 1)
    with pytest.raises(MidiVerificationError):
        verify_midi_bytes(result.data, shorter)


def test_the_verifier_rejects_an_unexpected_message_type() -> None:
    result = exported(tiny_performed())
    mid = decode(result.data)
    mid.tracks[1].insert(1, mido.MetaMessage("lyrics", text="la"))
    import io

    buffer = io.BytesIO()
    mid.save(file=buffer)
    with pytest.raises(MidiVerificationError, match="lyrics"):
        verify_midi_bytes(buffer.getvalue(), result.plan)
