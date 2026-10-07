"""Monophony, pitch fitness, tempo and timeline checks (M4a)."""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from fractions import Fraction
from typing import Any

import pytest

from barbershop_tracks.core.readiness import (
    QUARTET_VOCAL,
    TEST_TONE,
    Capability,
    Disposition,
    ReadinessReport,
    RoleAssignments,
    assess_readiness,
)
from barbershop_tracks.models import Note, Pitch, Step, VoiceRole
from readiness_builders import (
    LINE_IDS,
    melody,
    note,
    parsed_of,
    quartet_assignments,
    quartet_lines,
    rest,
    song_of,
    tempo_at,
)

C4 = Pitch(Step.C, 4)
D4 = Pitch(Step.D, 4)
LEAD = LINE_IDS[VoiceRole.LEAD]


def run(
    lines: Mapping[str, Sequence[Note]],
    capability: Capability = QUARTET_VOCAL,
    **kw: Any,
) -> ReadinessReport:
    song = song_of(lines, **kw)
    return assess_readiness(parsed_of(song), quartet_assignments(), capability)


def codes(report: ReadinessReport) -> list[str]:
    return [f.code for f in report.findings if f.origin.value == "readiness"]


def with_lead(notes: list[Note], **kw: Any) -> ReadinessReport:
    return run(quartet_lines(lead=notes), **kw)


# --- monophony -------------------------------------------------------------------------------


def test_simultaneous_attacks_are_a_chord_and_are_reported_not_repaired() -> None:
    report = with_lead([note(0, 1, C4), note(0, 1, D4), note(1, 1, C4)])
    assert codes(report) == ["LINE_SIMULTANEOUS_NOTES"]
    finding = report.by_code("LINE_SIMULTANEOUS_NOTES")[0]
    assert finding.disposition is Disposition.BLOCKING
    assert finding.role is VoiceRole.LEAD
    assert finding.line_id == LEAD
    assert finding.location is not None
    assert finding.location.performed_position == 0


def test_overlapping_attacks() -> None:
    report = with_lead([note(0, 2, C4), note(1, 1, D4)])
    assert codes(report) == ["LINE_OVERLAPPING_NOTES"]
    assert not report.ready


def test_adjacent_attacks_rests_and_gaps_are_allowed() -> None:
    notes = [note(0, 1, C4), note(1, 1, D4), rest(2, 1), note(5, 1, C4)]
    assert codes(with_lead(notes)) == []


def test_a_tie_merged_sustain_does_not_overlap_itself() -> None:
    notes = [note(0, 2, C4, to=True), note(2, 2, C4, frm=True), note(4, 1, D4)]
    report = with_lead(notes)
    assert codes(report) == []
    assert next(s for s in report.lines if s.line_id == LEAD).sounding_attacks == 2


def test_exact_fraction_boundaries_decide_overlap() -> None:
    adjacent = [note(0, 1, C4), note(Fraction(1), 1, D4)]
    assert codes(with_lead(adjacent)) == []
    just_before = [note(0, 1, C4), note(Fraction(99, 100), 1, D4)]
    assert codes(with_lead(just_before)) == ["LINE_OVERLAPPING_NOTES"]
    third = Fraction(1, 3)
    triplet = [note(0, third, C4), note(third, third, D4), note(2 * third, third, C4)]
    assert codes(with_lead(triplet)) == []


def test_a_chord_is_aggregated_per_line_with_a_count() -> None:
    notes = [note(i, 1, C4) for i in range(3)] + [note(i, 1, D4) for i in range(3)]
    report = with_lead(sorted(notes, key=lambda n: n.start))
    finding = report.by_code("LINE_SIMULTANEOUS_NOTES")
    assert len(finding) == 1
    assert "3 attack(s)" in finding[0].issue.message


def test_monophony_is_a_capability_requirement() -> None:
    chord = [note(0, 1, C4), note(0, 1, D4)]
    relaxed = replace(QUARTET_VOCAL, name="relaxed", monophony_required=False)
    assert codes(with_lead(chord, capability=relaxed)) == []


def test_unassigned_lines_are_not_checked_for_monophony() -> None:
    lines = quartet_lines()
    lines["P5/s1/v1"] = [note(0, 1, C4), note(0, 1, D4)]
    assigned = RoleAssignments(entries=quartet_assignments().entries, ignored=("P5/s1/v1",))
    report = assess_readiness(parsed_of(song_of(lines)), assigned, QUARTET_VOCAL)
    assert "LINE_SIMULTANEOUS_NOTES" not in codes(report)


# --- pitch -----------------------------------------------------------------------------------


MICRO = Pitch(Step.C, 4, Fraction(1, 2))


def test_integral_sounding_pitch_is_accepted() -> None:
    assert codes(with_lead(melody(C4))) == []


def test_a_microtonal_pitch_blocks_a_capability_that_needs_integral_pitch() -> None:
    report = with_lead([note(0, 1, C4), note(1, 1, MICRO)])
    assert codes(report) == ["PITCH_NOT_INTEGRAL"]
    assert "not rounded" in report.by_code("PITCH_NOT_INTEGRAL")[0].issue.message
    assert not report.ready


def test_a_capability_without_the_requirement_accepts_microtones() -> None:
    free = Capability(name="free", monophony_required=True)
    assert codes(with_lead([note(0, 1, MICRO)], capability=free)) == []
    assert codes(with_lead([note(0, 1, MICRO)], capability=TEST_TONE)) == []


def test_the_sounding_pitch_is_authoritative_not_the_written_one() -> None:
    from barbershop_tracks.models import PitchTransform

    written = Note(
        start=Fraction(0),
        duration=Fraction(1),
        measure=1,
        beat=Fraction(1),
        written_pitch=Pitch(Step.C, 4),
        transform=PitchTransform(diatonic=0, chromatic=0, octave_change=0),
    )
    assert written.sounding_pitch == Pitch(Step.C, 4)
    assert codes(with_lead([written])) == []


def test_pitches_outside_the_capability_midi_range_are_errors_for_integral_pitch() -> None:
    narrow = replace(QUARTET_VOCAL, name="narrow", midi_range=(50, 70), typical_ranges=None)
    report = with_lead(
        [note(0, 1, Pitch(Step.C, 2)), note(1, 1, C4), note(2, 1, Pitch(Step.C, 6))],
        capability=narrow,
    )
    lead = [f for f in report.by_code("PITCH_OUT_OF_MIDI_RANGE") if f.role is VoiceRole.LEAD]
    assert len(lead) == 1  # one aggregated finding for the lead line
    assert "2 attack(s)" in lead[0].issue.message
    assert not report.ready


def test_microtonal_pitch_below_and_above_the_midi_range() -> None:
    ranged = Capability(name="ranged", midi_range=(0, 127))
    low = Pitch(Step.C, -1, Fraction(-1, 2))
    high = Pitch(Step.G, 9, Fraction(1, 2))
    assert low.absolute_semitones < 0
    assert high.absolute_semitones > 127
    report = with_lead([note(0, 1, low), note(1, 1, high)], capability=ranged)
    assert codes(report) == ["PITCH_OUT_OF_MIDI_RANGE"]


def test_an_unusual_range_is_advisory_only_and_never_changes_pitch() -> None:
    high_bass = melody(Pitch(Step.E, 5))  # E5 = 76, well above a bass range
    report = run(quartet_lines(bass=high_bass))
    unusual = report.by_code("VOICE_RANGE_UNUSUAL")
    assert len(unusual) == 1
    assert unusual[0].disposition is Disposition.ADVISORY
    assert unusual[0].role is VoiceRole.BASS
    assert report.ready  # an advisory finding never blocks
    assert not report.clean


def test_the_range_heuristic_is_off_when_the_capability_has_none() -> None:
    relaxed = replace(QUARTET_VOCAL, name="x", typical_ranges=None)
    assert "VOICE_RANGE_UNUSUAL" not in codes(
        run(quartet_lines(bass=melody(Pitch(Step.E, 5))), capability=relaxed)
    )


# --- tempo -----------------------------------------------------------------------------------


def test_no_tempo_at_all() -> None:
    report = run(quartet_lines(), tempos=[])
    assert codes(report) == ["TEMPO_MISSING"]
    assert not report.ready


def test_the_first_tempo_after_position_zero() -> None:
    report = run(quartet_lines(), tempos=[tempo_at(4, 90)])
    assert codes(report) == ["TEMPO_INITIAL_MISSING"]  # exactly one, never both
    assert "quarter note 4" in report.by_code("TEMPO_INITIAL_MISSING")[0].issue.message


def test_a_tempo_at_zero_is_enough() -> None:
    assert codes(run(quartet_lines(), tempos=[tempo_at(0, 80), tempo_at(8, 100)])) == []


def test_tempo_is_a_capability_requirement() -> None:
    silent = replace(QUARTET_VOCAL, name="x", tempo_required=False)
    assert codes(run(quartet_lines(), capability=silent, tempos=[])) == []


# --- timeline --------------------------------------------------------------------------------


def test_an_empty_song_has_no_length() -> None:
    parsed = parsed_of(song_of({}, measures=0, tempos=[]))
    report = assess_readiness(parsed, RoleAssignments(), TEST_TONE)
    assert "SONG_EMPTY" in codes(report)
    assert not report.ready


def test_an_attack_beyond_the_performed_extent_is_reported() -> None:
    report = with_lead([*melody(C4), note(40, 1, D4)])
    assert codes(report) == ["EVENT_OUTSIDE_TIMELINE"]
    assert report.performed_length == 16


def test_an_attack_before_zero_cannot_even_be_built() -> None:
    with pytest.raises(ValueError, match="negative"):
        note(-1, 1, C4)
