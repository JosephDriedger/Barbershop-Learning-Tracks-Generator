"""The pure tie-merging helper, tested on hand-built source notes (no XML)."""

from fractions import Fraction

import pytest

from barbershop_tracks.core.timeline import TieMergeResult, merge_tied_notes
from barbershop_tracks.models import (
    Lyric,
    Note,
    PerformanceNote,
    Pitch,
    PitchTransform,
    Severity,
    Step,
)

F = Fraction
LINE = "P1/s1/v1"
MIDDLE_C = Pitch(Step.C, 4)


def n(
    start: F | int,
    duration: F | int = 1,
    pitch: Pitch | None = MIDDLE_C,
    *,
    to: bool = False,
    frm: bool = False,
    measure: int = 1,
    transform: PitchTransform | None = None,
    lyrics: tuple[Lyric, ...] = (),
) -> Note:
    return Note(
        start=F(start),
        duration=F(duration),
        measure=measure,
        beat=F(1) + F(start),
        written_pitch=pitch,
        transform=transform or PitchTransform(),
        tied_to_next=to,
        tied_from_previous=frm,
        lyrics=lyrics,
    )


def merge(*notes: Note) -> TieMergeResult:
    return merge_tied_notes(notes, part_id=LINE)


def codes(result: TieMergeResult) -> list[str]:
    return [issue.code for issue in result.issues]


C4, D4, E4, G4 = (Pitch(Step.C, 4), Pitch(Step.D, 4), Pitch(Step.E, 4), Pitch(Step.G, 4))
C_SHARP4 = Pitch(Step.C, 4, F(1))
D_FLAT4 = Pitch(Step.D, 4, F(-1))


# --- merging --------------------------------------------------------------------------


def test_untied_notes_pass_through_one_to_one() -> None:
    notes = (n(0, pitch=C4), n(1, pitch=D4), n(2, pitch=None))
    result = merge(*notes)
    assert not result.issues
    assert [p.source for p in result.notes] == [(notes[0],), (notes[1],), (notes[2],)]
    assert result.notes[2].is_rest


def test_simple_tie_merges_into_one_attack() -> None:
    first, second = n(0, 1, to=True), n(1, 2, frm=True)
    result = merge(first, second)
    assert not result.issues
    (merged,) = result.notes
    assert merged.source == (first, second)
    assert (merged.start, merged.duration, merged.end) == (F(0), F(3), F(3))
    assert merged.pitch == C4
    assert merged.is_tied_group


def test_chain_of_three() -> None:
    a, b, c = n(0, to=True), n(1, to=True, frm=True), n(2, frm=True)
    (merged,) = merge(a, b, c).notes
    assert merged.source == (a, b, c)
    assert merged.duration == 3


def test_tie_across_a_barline_and_a_following_note() -> None:
    a, b = n(3, to=True, measure=1), n(4, 2, frm=True, measure=2)
    after = n(6, pitch=D4, measure=2)
    result = merge(a, b, after)
    assert not result.issues
    assert [(p.start, p.duration) for p in result.notes] == [(F(3), F(3)), (F(6), F(1))]
    assert result.notes[0].measure == 1  # located at the first source note


def test_durations_are_exact_thirds() -> None:
    third = F(1, 3)
    a, b, c = (
        n(0, third, to=True),
        n(third, third, to=True, frm=True),
        n(2 * third, third, frm=True),
    )
    (merged,) = merge(a, b, c).notes
    assert merged.duration == 1  # exactly, with no float drift


def test_tie_across_a_divisions_change_is_just_exact_arithmetic() -> None:
    # 1/2 quarter (divisions 2) tied to 1/3 quarter (divisions 3), positions exact.
    a, b = n(0, F(1, 2), to=True), n(F(1, 2), F(1, 3), frm=True)
    (merged,) = merge(a, b).notes
    assert merged.duration == F(5, 6)


def test_merged_note_keeps_first_pitch_spelling_and_lyric() -> None:
    lyric = Lyric(text="la")
    a = n(0, pitch=C_SHARP4, to=True, lyrics=(lyric,))
    b = n(1, pitch=D_FLAT4, frm=True)
    (merged,) = merge(a, b).notes
    assert str(merged.pitch) == "C#4"
    assert merged.lyrics == (lyric,)
    assert [str(p.written_pitch) for p in merged.source] == ["C#4", "Db4"]  # both preserved


def test_enharmonic_group_has_one_sounding_pitch_while_sources_keep_their_spellings() -> None:
    first = n(0, pitch=C_SHARP4, to=True)
    second = n(1, pitch=D_FLAT4, frm=True)
    snapshot = (first, second)
    result = merge(first, second)
    (merged,) = result.notes

    # 1. the source spellings remain different
    assert first.written_pitch == C_SHARP4
    assert second.written_pitch == D_FLAT4
    assert first.written_pitch != second.written_pitch
    assert [str(s.written_pitch) for s in merged.source] == ["C#4", "Db4"]

    # 2. the merged performance event has one sounding pitch (absolute semitone 61)
    assert merged.pitch is not None
    assert merged.pitch.absolute_semitones == 61
    assert {s.sounding_pitch.absolute_semitones for s in merged.source if s.sounding_pitch} == {61}
    assert str(merged.pitch) == "C#4"  # the representative is the first note's sounding pitch

    # 3. no source Note was mutated (same objects, same values, flags intact)
    assert (first, second) == snapshot
    assert merged.source[0] is first
    assert merged.source[1] is second
    assert first.tied_to_next
    assert second.tied_from_previous
    assert first.start == 0
    assert first.duration == 1


def test_performance_pitch_is_the_sounding_pitch_not_the_written_pitch() -> None:
    octave_down = PitchTransform(octave_change=-1)
    written = n(0, pitch=Pitch(Step.C, 5), to=True, transform=octave_down)  # written C5, sounds C4
    cont = n(1, pitch=Pitch(Step.C, 4), frm=True)
    (merged,) = merge(written, cont).notes
    assert merged.pitch == Pitch(Step.C, 4)
    assert merged.source[0].written_pitch == Pitch(Step.C, 5)  # still available, unchanged


def test_source_notes_are_not_modified() -> None:
    a, b = n(0, to=True), n(1, frm=True)
    before = (a, b)
    result = merge(a, b)
    assert (a, b) == before
    assert a.tied_to_next
    assert result.notes[0].source[0] is a
    assert result.notes[0].source[1] is b


def test_every_source_note_appears_exactly_once() -> None:
    notes = (n(0, to=True), n(1, frm=True), n(2, pitch=D4), n(3, pitch=None), n(4, to=True))
    result = merge(*notes)
    flat = [s for p in result.notes for s in p.source]
    assert sorted(flat, key=lambda x: x.start) == sorted(notes, key=lambda x: x.start)
    assert len(flat) == len(notes)


def test_output_is_ordered_by_start() -> None:
    result = merge(n(2, pitch=D4), n(0, to=True), n(1, frm=True))
    assert [p.start for p in result.notes] == [0, 2]


# --- enharmonic, microtonal, transposed ------------------------------------------------


def test_enharmonic_tie_merges() -> None:
    result = merge(n(0, pitch=C_SHARP4, to=True), n(1, pitch=D_FLAT4, frm=True))
    assert not result.issues
    assert len(result.notes) == 1


def test_enharmonic_spellings_remain_unequal_as_pitches() -> None:
    assert C_SHARP4 != D_FLAT4
    assert C_SHARP4.absolute_semitones == D_FLAT4.absolute_semitones


def test_microtonal_equal_pitches_merge_exactly() -> None:
    quarter_flat = Pitch(Step.E, 4, F(-1, 2))
    result = merge(n(0, pitch=quarter_flat, to=True), n(1, pitch=quarter_flat, frm=True))
    assert not result.issues
    assert len(result.notes) == 1


def test_microtonal_near_miss_is_a_mismatch() -> None:
    a = Pitch(Step.E, 4, F(-1, 2))
    b = Pitch(Step.E, 4, F(-1, 4))
    result = merge(n(0, pitch=a, to=True), n(1, pitch=b, frm=True))
    assert codes(result) == ["TIE_PITCH_MISMATCH"]


def test_microtonal_is_not_confused_with_the_nearest_equal_tempered_pitch() -> None:
    quarter_flat = Pitch(Step.E, 4, F(-1, 2))
    result = merge(n(0, pitch=quarter_flat, to=True), n(1, pitch=Pitch(Step.E, 4, F(-1)), frm=True))
    assert codes(result) == ["TIE_PITCH_MISMATCH"]


def test_matching_uses_sounding_pitch_after_transposition() -> None:
    octave_down = PitchTransform(octave_change=-1)
    a = n(0, pitch=Pitch(Step.C, 5), to=True, transform=octave_down)  # sounds C4
    b = n(1, pitch=Pitch(Step.C, 4), frm=True)  # sounds C4 (written differently)
    assert not merge(a, b).issues


def test_same_written_pitch_but_different_sounding_pitch_is_a_mismatch() -> None:
    octave_down = PitchTransform(octave_change=-1)
    a = n(0, pitch=C4, to=True, transform=octave_down)  # sounds C3
    b = n(1, pitch=C4, frm=True)  # sounds C4
    assert codes(merge(a, b)) == ["TIE_PITCH_MISMATCH"]


# --- chords ----------------------------------------------------------------------------


def test_chord_members_pair_by_pitch_not_by_order() -> None:
    c1, e1 = n(0, pitch=C4, to=True), n(0, pitch=E4, to=True)
    e2, c2 = n(1, pitch=E4, frm=True), n(1, pitch=C4, frm=True)  # reversed order
    result = merge(c1, e1, e2, c2)
    assert not result.issues
    by_pitch = {str(p.pitch): p.source for p in result.notes}
    assert by_pitch["C4"] == (c1, c2)
    assert by_pitch["E4"] == (e1, e2)


def test_chord_with_only_one_member_tied() -> None:
    c1, e1 = n(0, pitch=C4, to=True), n(0, pitch=E4)
    c2, e2 = n(1, pitch=C4, frm=True), n(1, pitch=E4)
    result = merge(c1, e1, c2, e2)
    assert not result.issues
    assert sorted((str(p.pitch), len(p.source)) for p in result.notes) == [
        ("C4", 2),
        ("E4", 1),
        ("E4", 1),
    ]


# --- diagnostics and their precedence ------------------------------------------------


def test_unmatched_start_at_the_end_of_the_line() -> None:
    result = merge(n(0, to=True), n(1, pitch=D4))
    assert codes(result) == ["TIE_UNMATCHED_START"]
    issue = result.issues.issues[0]
    assert issue.part_id == LINE
    assert issue.measure == 1
    assert issue.beat == 1
    assert len(result.notes) == 2  # nothing is lost


def test_unmatched_start_when_the_next_note_does_not_follow_immediately() -> None:
    result = merge(n(0, to=True), n(2, pitch=D4))
    assert codes(result) == ["TIE_UNMATCHED_START"]


def test_unmatched_start_is_reported_once_at_the_very_end() -> None:
    assert codes(merge(n(0, to=True))) == ["TIE_UNMATCHED_START"]


def test_unrelated_stop_is_unmatched_stop_never_a_pitch_mismatch() -> None:
    result = merge(n(0, pitch=D4), n(1, pitch=C4, frm=True))
    assert codes(result) == ["TIE_UNMATCHED_STOP"]
    assert "leads into" in result.issues.issues[0].message


def test_stop_with_no_open_tie_anywhere_is_unmatched_stop() -> None:
    assert codes(merge(n(0, frm=True))) == ["TIE_UNMATCHED_STOP"]


def test_wrong_pitch_where_a_tie_arrives_is_a_pitch_mismatch_and_consumes_the_start() -> None:
    result = merge(n(0, pitch=C4, to=True), n(1, pitch=D4, frm=True))
    assert codes(result) == ["TIE_PITCH_MISMATCH"]  # one mistake, one diagnostic
    assert "C4" in result.issues.issues[0].message
    assert "D4" in result.issues.issues[0].message
    assert [len(p.source) for p in result.notes] == [1, 1]


def test_a_tie_across_a_rest_gives_unmatched_start_and_unmatched_stop() -> None:
    result = merge(n(0, to=True), n(1, pitch=None), n(2, frm=True))
    assert codes(result) == ["TIE_UNMATCHED_START", "TIE_UNMATCHED_STOP"]


def test_two_unison_open_ties_make_the_stop_ambiguous() -> None:
    a, b = n(0, pitch=C4, to=True), n(0, pitch=C4, to=True)
    stop = n(1, pitch=C4, frm=True)
    result = merge(a, b, stop)
    assert codes(result) == ["TIE_AMBIGUOUS"]  # no guess, no extra unmatched-start noise
    assert all(len(p.source) == 1 for p in result.notes)  # nothing was paired


def test_ambiguity_is_reported_once_for_the_same_position_and_pitch() -> None:
    a, b = n(0, pitch=C4, to=True), n(0, pitch=C4, to=True)
    stops = (n(1, pitch=C4, frm=True), n(1, pitch=C4, frm=True))
    assert codes(merge(a, b, *stops)) == ["TIE_AMBIGUOUS"]


def test_precedence_ambiguous_beats_paired_and_mismatch() -> None:
    # Two C4 ties arrive (ambiguous). A D4 stop at the same place is a mismatch (not ambiguous).
    notes = (
        n(0, pitch=C4, to=True),
        n(0, pitch=C4, to=True),
        n(1, pitch=C4, frm=True),
        n(1, pitch=D4, frm=True),
    )
    assert codes(merge(*notes)) == ["TIE_AMBIGUOUS", "TIE_PITCH_MISMATCH"]


def test_mismatch_with_two_candidates_reports_once() -> None:
    notes = (
        n(0, pitch=C4, to=True),
        n(0, pitch=E4, to=True),
        n(1, pitch=G4, frm=True),  # neither C4 nor E4
    )
    result = merge(*notes)
    assert codes(result) == ["TIE_PITCH_MISMATCH"]
    assert "C4" in result.issues.issues[0].message
    assert "E4" in result.issues.issues[0].message


def test_mismatch_does_not_consume_a_start_that_another_stop_will_pair() -> None:
    # C4 and E4 are tied; the next chord has E4 (pairs) and G4 (mismatch against the C4 tie).
    notes = (
        n(0, pitch=C4, to=True),
        n(0, pitch=E4, to=True),
        n(1, pitch=G4, frm=True),
        n(1, pitch=E4, frm=True),
    )
    result = merge(*notes)
    assert codes(result) == ["TIE_PITCH_MISMATCH"]  # C4's start is covered by this; E4 paired
    assert sorted(len(p.source) for p in result.notes) == [1, 1, 2]


def test_all_tie_diagnostics_are_errors_with_the_line_and_position() -> None:
    result = merge(n(0, to=True), n(2, frm=True, measure=3))
    assert {i.code for i in result.issues} == {"TIE_UNMATCHED_START", "TIE_UNMATCHED_STOP"}
    assert all(i.severity is Severity.ERROR and i.part_id == LINE for i in result.issues)
    assert result.issues.has_errors


def test_input_order_does_not_matter() -> None:
    a, b = n(0, to=True), n(1, frm=True)
    assert merge(b, a).notes == merge(a, b).notes


def test_empty_input() -> None:
    result = merge_tied_notes((), part_id=LINE)
    assert result.notes == ()
    assert not result.issues


def test_rests_are_never_tied() -> None:
    result = merge(n(0, pitch=None), n(1, pitch=None))
    assert [p.is_rest for p in result.notes] == [True, True]
    assert all(not p.is_tied_group for p in result.notes)


def test_performance_notes_are_immutable_and_hold_no_back_references() -> None:
    (merged,) = merge(n(0, to=True), n(1, frm=True)).notes
    with pytest.raises(AttributeError):
        merged.source = ()  # type: ignore[misc]
    assert isinstance(merged, PerformanceNote)
