"""Names, the manifest, in-memory package verification and the MIDI_QUARTET capability."""

import json
from dataclasses import replace
from fractions import Fraction

import pytest

from barbershop_tracks.core.handoff import (
    LYRICS_STATUS,
    MANIFEST_NAME,
    PACKAGE_TYPE,
    SCHEMA,
    HandoffError,
    sanitize_name,
    verify_package_files,
)
from barbershop_tracks.core.readiness import (
    CAPABILITIES,
    MIDI_QUARTET,
    LyricPolicy,
    assess_readiness,
)
from barbershop_tracks.core.readiness.capability import Feature
from barbershop_tracks.models import Pitch, Step, TimeSignature, VoiceRole
from handoff_builders import prepare, prepared
from readiness_builders import (
    note,
    parsed_of,
    quartet_assignments,
    quartet_lines,
    ready_parsed,
    song_of,
    tempo_at,
)

# --- names ---


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Song Title", "Song_Title"),
        ("a/b\\c:d", "a_b_c_d"),
        ("  x-y_z  ", "x-y_z"),
        ("Café", "Caf"),
    ],
)
def test_names_are_ascii_and_safe(text: str, expected: str) -> None:
    assert sanitize_name(text) == expected


@pytest.mark.parametrize("text", ["", "   ", "///", "...", "CON", "nul", "com1", "LPT9", ".", ".."])
def test_unusable_names_are_refused(text: str) -> None:
    with pytest.raises(HandoffError) as info:
        sanitize_name(text)
    assert info.value.code == "HANDOFF_NAME_INVALID"


def test_long_names_are_capped() -> None:
    assert len(sanitize_name("x" * 500)) == 64


# --- the MIDI_QUARTET capability ---


def test_midi_quartet_is_a_registered_capability_that_needs_no_lyrics() -> None:
    assert CAPABILITIES["quartet-midi"] is MIDI_QUARTET
    assert MIDI_QUARTET.lyric_policy is LyricPolicy.NONE
    assert Feature.LYRICS_USED not in MIDI_QUARTET.features
    assert MIDI_QUARTET.required_roles == frozenset(VoiceRole)
    assert MIDI_QUARTET.monophony_required
    assert MIDI_QUARTET.integral_midi_pitch_required
    assert MIDI_QUARTET.midi_range == (0, 127)
    assert MIDI_QUARTET.tempo_required
    assert MIDI_QUARTET.all_musical_lines_accounted_for
    assert MIDI_QUARTET.assigned_lines_must_sound


def test_a_lyric_free_quartet_is_ready_for_the_midi_handoff() -> None:
    assert assess_readiness(ready_parsed(), quartet_assignments(), MIDI_QUARTET).ready


def test_the_midi_capability_still_needs_all_four_roles_and_a_tempo() -> None:
    three = replace(quartet_assignments(), entries=quartet_assignments().entries[:3])
    assert not assess_readiness(ready_parsed(), three, MIDI_QUARTET).ready
    no_tempo = parsed_of(song_of(quartet_lines(), tempos=[]))
    assert not assess_readiness(no_tempo, quartet_assignments(), MIDI_QUARTET).ready


# --- preparing a package ---


def test_a_ready_score_prepares_a_verified_package_with_three_files() -> None:
    handoff = prepared("demo")
    assert list(handoff.files) == ["demo.mid", "OPENUTAU-STEPS.txt", MANIFEST_NAME]
    verify_package_files(handoff.files, handoff.midi)
    assert handoff.dirname == "demo.handoff"
    # no source MusicXML, voicebank, OpenUtau project or audio file is part of the package
    assert not [
        n for n in handoff.files if n.endswith((".musicxml", ".xml", ".mxl", ".ustx", ".wav"))
    ]


def test_a_not_ready_score_prepares_nothing() -> None:
    parsed = parsed_of(song_of(quartet_lines(), tempos=[]))
    outcome = prepare(parsed)
    assert outcome.handoff is None
    assert outcome.export_error is None
    assert not outcome.report.ready


def test_an_exporter_failure_is_reported_separately_from_readiness() -> None:
    # readiness accepts a note off the 480 grid; the exporter refuses to round it
    lead = [note(0, Fraction(1, 7), Pitch(Step.C, 4)), note(1, 3, Pitch(Step.C, 4))]
    outcome = prepare(parsed_of(song_of(quartet_lines(lead=lead))))
    assert outcome.report.ready
    assert outcome.handoff is None
    assert outcome.export_error is not None
    assert outcome.export_error.code == "MIDI_TICK_NOT_INTEGRAL"
    assert prepare(parsed_of(song_of(quartet_lines(lead=lead))), ppq=840).handoff is not None


def test_strict_refuses_when_advisory_findings_exist_and_not_otherwise() -> None:
    high = quartet_lines(lead=[note(i, 1, Pitch(Step.C, 7)) for i in range(8)])
    parsed = parsed_of(song_of(high))
    plain = prepare(parsed)
    strict = prepare(parsed, strict=True)
    assert plain.report.advisory
    assert plain.handoff is not None
    assert strict.handoff is None
    assert strict.export_error is None


# --- the manifest ---


def manifest_of(name: str = "demo") -> dict:  # type: ignore[type-arg]
    return prepared(name).manifest


def test_the_manifest_has_the_required_identifiers_and_fields() -> None:
    m = manifest_of()
    assert m["schema"] == SCHEMA == "barbershop-tracks.handoff/1"
    assert m["package_type"] == PACKAGE_TYPE
    assert m["generator"]["name"] == "barbershop-learning-tracks"
    assert m["generator"]["version"]
    assert m["source"] == {"display_name": "demo.musicxml", "sha256": "0" * 64}
    assert m["midi"]["file"] == "demo.mid"
    assert m["midi"]["format"] == 1
    assert m["midi"]["ppq"] == 480
    assert [t["name"] for t in m["midi"]["tracks"]] == [
        "Conductor",
        "Tenor",
        "Lead",
        "Baritone",
        "Bass",
    ]
    assert (m["midi"]["note_on_velocity"], m["midi"]["note_off_velocity"]) == (80, 64)
    assert m["timing"] == {"performed_length_quarters": "16", "end_tick": 7680}
    assert [r["role"] for r in m["roles"]] == ["tenor", "lead", "baritone", "bass"]
    assert m["roles"][1]["line_id"] == "P2/s1/v1"
    assert m["roles"][1]["lowest_midi"] == m["roles"][1]["highest_midi"] == 60
    assert m["lyrics"] == LYRICS_STATUS
    assert m["lyrics"]["status"] == "not_exported"
    assert m["limitations"]
    assert m["readiness"]["capability"] == "quartet-midi"


def test_the_manifest_records_exact_and_encoded_tempo_and_the_error() -> None:
    parsed = parsed_of(song_of(quartet_lines(), tempos=[tempo_at(0, 90)]))
    event = prepare(parsed).handoff.manifest["tempo"]["events"][0]  # type: ignore[union-attr]
    assert event["bpm"] == "90"
    assert event["exact_us_per_quarter"] == "2000000/3"
    assert event["encoded_us_per_quarter"] == 666667
    assert event["error_us_per_quarter"] == "1/3"
    assert Fraction(event["bpm_error"]) < 0
    codes = {w["code"] for w in prepare(parsed).handoff.manifest["warnings"]}  # type: ignore[union-attr]
    assert "MIDI_TEMPO_QUANTIZED" in codes


def test_the_manifest_records_written_and_omitted_meters_and_the_auxiliary_fields() -> None:
    signatures = (
        TimeSignature(position=Fraction(0), beats=4, beat_type=4),
        TimeSignature(position=Fraction(8), beats=256, beat_type=4),
    )
    song = replace(song_of(quartet_lines()), time_signatures=signatures)
    handoff = prepare(parsed_of(song)).handoff
    assert handoff is not None
    meter = handoff.manifest["meter"]
    assert [m["beats"] for m in meter["written"]] == [4]
    assert [(m["beats"], m["position"]) for m in meter["omitted"]] == [(256, "8")]
    assert meter["omitted"][0]["reason"]
    assert meter["auxiliary_fields"]["clocks_per_click"] == 24
    assert meter["auxiliary_fields"]["notated_32nds_per_quarter"] == 8
    assert "not facts from the score" in meter["auxiliary_fields"]["note"]
    assert "MIDI_METER_NOT_REPRESENTABLE" in {w["code"] for w in handoff.manifest["warnings"]}


def test_the_manifest_lists_every_other_file_with_size_and_hash_and_no_timestamps_or_paths() -> (
    None
):
    handoff = prepared()
    m = handoff.manifest
    assert [f["name"] for f in m["files"]] == ["demo.mid", "OPENUTAU-STEPS.txt"]
    text = handoff.files[MANIFEST_NAME].decode("ascii")
    assert json.loads(text) == m
    for forbidden in ("\\\\", ":/", "Users", "tmp", "T00:", "2026", "timestamp"):
        assert forbidden not in text, forbidden


def test_the_package_is_byte_deterministic() -> None:
    first, second = prepared(), prepared()
    assert first.files == second.files
    assert list(first.files) == list(second.files)


# --- in-memory verification ---


def test_package_verification_rejects_tampering() -> None:
    handoff = prepared()
    for name in ("demo.mid", "OPENUTAU-STEPS.txt"):
        bad = dict(handoff.files)
        bad[name] = bad[name] + b"x"
        with pytest.raises(HandoffError) as info:
            verify_package_files(bad, handoff.midi)
        assert info.value.code == "HANDOFF_VERIFY_FAILED"
    extra = dict(handoff.files)
    extra["extra.txt"] = b"x"
    with pytest.raises(HandoffError):
        verify_package_files(extra, handoff.midi)
    missing = {k: v for k, v in handoff.files.items() if k != MANIFEST_NAME}
    with pytest.raises(HandoffError):
        verify_package_files(missing, handoff.midi)
