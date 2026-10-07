"""Lyric readiness: capability lyric policies, never a hard-coded Lead."""

from dataclasses import replace

import pytest

from barbershop_tracks.core.readiness import (
    QUARTET_VOCAL,
    TEST_TONE,
    Capability,
    Disposition,
    LyricPolicy,
    assess_readiness,
)
from barbershop_tracks.models import Lyric, Melisma, Note, Pitch, VoiceRole
from readiness_builders import (
    LINE_IDS,
    PITCHES,
    melody,
    note,
    parsed_of,
    quartet_assignments,
    quartet_lines,
    song_of,
)

LA = Lyric(text="la")
ALL_LINES = replace(
    QUARTET_VOCAL, name="all-lines", lyric_policy=LyricPolicy.ALL_ASSIGNED_LINES_COMPLETE
)


def sung(role: VoiceRole, count: int = 8, *, skip: int = 0) -> list[Note]:
    """``count`` quarter notes with a lyric on each except the last ``skip``."""
    pitch: Pitch = PITCHES[role]
    return [note(i, 1, pitch, lyrics=() if i >= count - skip else (LA,)) for i in range(count)]


def assess(capability: Capability, **lines: list[Note]):  # type: ignore[no-untyped-def]
    parsed = parsed_of(song_of(quartet_lines(**lines)))
    return assess_readiness(parsed, quartet_assignments(), capability)


def codes(report) -> set[str]:  # type: ignore[no-untyped-def]
    return {f.code for f in report.findings if f.origin.value == "readiness"}


def test_one_complete_line_is_enough_and_it_need_not_be_the_lead() -> None:
    for role in VoiceRole:
        report = assess(QUARTET_VOCAL, **{role.value: sung(role)})
        assert report.ready, role
        assert not {c for c in codes(report) if c.startswith("LYRIC_")}


def test_no_line_with_lyrics_blocks() -> None:
    report = assess(QUARTET_VOCAL)
    assert "LYRIC_SOURCE_MISSING" in codes(report)
    assert not report.ready


def test_only_partial_lyrics_blocks_and_nothing_is_filled_in() -> None:
    report = assess(QUARTET_VOCAL, lead=sung(VoiceRole.LEAD, skip=2))
    assert "LYRIC_SOURCE_INCOMPLETE" in codes(report)
    finding = report.by_code("LYRIC_SOURCE_INCOMPLETE")[0]
    assert "2 of 8" in finding.issue.message
    assert finding.disposition is Disposition.BLOCKING
    assert finding.location is not None  # the first gap
    assert not report.ready


def test_a_complete_line_makes_partial_harmony_lines_irrelevant() -> None:
    report = assess(
        QUARTET_VOCAL,
        lead=sung(VoiceRole.LEAD),
        tenor=sung(VoiceRole.TENOR, skip=3),
    )
    assert report.ready
    assert "LYRIC_SOURCE_INCOMPLETE" not in codes(report)


def test_a_configured_source_role_must_itself_be_complete() -> None:
    from_tenor = QUARTET_VOCAL.with_lyric_source(VoiceRole.TENOR)
    # lead is complete but the configured source (tenor) has nothing
    missing = assess(from_tenor, lead=sung(VoiceRole.LEAD))
    assert "LYRIC_SOURCE_MISSING" in codes(missing)
    assert missing.by_code("LYRIC_SOURCE_MISSING")[0].role is VoiceRole.TENOR
    assert not missing.ready
    # the configured source is partial
    partial = assess(from_tenor, tenor=sung(VoiceRole.TENOR, skip=1), lead=sung(VoiceRole.LEAD))
    assert "LYRIC_SOURCE_INCOMPLETE" in codes(partial)
    # the configured source is complete (the lead has none): ready
    ok = assess(from_tenor, tenor=sung(VoiceRole.TENOR))
    assert ok.ready


def test_lead_is_only_the_source_when_the_capability_says_so() -> None:
    from_lead = QUARTET_VOCAL.with_lyric_source(VoiceRole.LEAD)
    assert not assess(from_lead, bass=sung(VoiceRole.BASS)).ready  # lyrics elsewhere do not count
    assert assess(from_lead, lead=sung(VoiceRole.LEAD)).ready
    assert QUARTET_VOCAL.lyric_source_role is None  # the preset does not hard-code Lead


def test_an_unassigned_configured_source_role_is_reported() -> None:
    from_bass = QUARTET_VOCAL.with_lyric_source(VoiceRole.BASS)
    entries = tuple(
        (r, line) for r, line in quartet_assignments().entries if r is not VoiceRole.BASS
    )
    from barbershop_tracks.core.readiness import RoleAssignments

    parsed = parsed_of(song_of(quartet_lines(bass=sung(VoiceRole.BASS))))
    report = assess_readiness(parsed, RoleAssignments(entries=entries), from_bass)
    assert "LYRIC_SOURCE_MISSING" in codes(report)


def test_a_melisma_continuation_counts_as_a_resolved_lyric() -> None:
    held = Lyric(text="la", melisma=Melisma.UNTYPED)
    lead = [note(0, 1, PITCHES[VoiceRole.LEAD], lyrics=(held,))] + [
        note(i, 1, PITCHES[VoiceRole.LEAD]) for i in range(1, 8)
    ]
    assert assess(QUARTET_VOCAL, lead=lead).ready


def test_all_assigned_lines_policy_requires_every_line() -> None:
    complete = {role.value: sung(role) for role in VoiceRole}
    assert assess(ALL_LINES, **complete).ready
    one_missing = dict(complete, bass=melody(PITCHES[VoiceRole.BASS]))
    missing = assess(ALL_LINES, **one_missing)
    assert codes(missing) >= {"LYRIC_LINE_MISSING"}
    assert missing.by_code("LYRIC_LINE_MISSING")[0].role is VoiceRole.BASS
    assert not missing.ready
    partial = dict(complete, baritone=sung(VoiceRole.BARITONE, skip=1))
    report = assess(ALL_LINES, **partial)
    assert "LYRIC_LINE_INCOMPLETE" in codes(report)
    assert not report.ready


def test_a_capability_without_a_lyric_policy_is_not_asked_for_lyrics() -> None:
    report = assess(TEST_TONE)
    assert report.ready
    assert not {c for c in codes(report) if c.startswith("LYRIC_")}


@pytest.mark.parametrize("policy", list(LyricPolicy))
def test_the_policy_is_read_from_the_capability_not_its_name(policy: LyricPolicy) -> None:
    capability = replace(QUARTET_VOCAL, name="whatever", lyric_policy=policy)
    report = assess(capability)  # nobody has lyrics
    assert report.ready is (policy is LyricPolicy.NONE)


def test_lyric_readiness_findings_carry_role_and_line() -> None:
    report = assess(
        ALL_LINES, **{role.value: sung(role) for role in VoiceRole if role is not VoiceRole.BASS}
    )
    finding = report.by_code("LYRIC_LINE_MISSING")[0]
    assert finding.line_id == LINE_IDS[VoiceRole.BASS]
    assert finding.role is VoiceRole.BASS


# --- completeness is measured on performed sounding attacks, never on elapsed time ---


def test_a_rest_or_gap_between_sung_attacks_does_not_make_a_line_incomplete() -> None:
    pitch = PITCHES[VoiceRole.LEAD]
    lead = [
        note(0, 1, pitch, lyrics=(LA,)),
        note(1, 1, None),  # a rest
        note(3, 1, pitch, lyrics=(LA,)),  # and a gap at beat 2
        note(5, 1, pitch, lyrics=(LA,)),
    ]
    report = assess(QUARTET_VOCAL, lead=lead)
    assert report.ready
    assert not {c for c in codes(report) if c.startswith("LYRIC_")}


def test_a_melisma_continuation_between_sung_attacks_can_be_complete() -> None:
    pitch = PITCHES[VoiceRole.LEAD]
    held = Lyric(text="la", melisma=Melisma.UNTYPED)
    lead = [
        note(0, 1, pitch, lyrics=(LA,)),
        note(1, 1, pitch, lyrics=(held,)),
        note(2, 1, pitch),  # continuation: no text of its own
        note(3, 1, pitch, lyrics=(LA,)),
    ]
    assert assess(QUARTET_VOCAL, lead=lead).ready


def test_a_tie_merged_attack_needs_only_one_lyric() -> None:
    pitch = PITCHES[VoiceRole.LEAD]
    lead = [
        note(0, 1, pitch, to=True, lyrics=(LA,)),
        note(1, 1, pitch, frm=True),  # same performed attack: no second lyric required
        note(2, 1, pitch, lyrics=(LA,)),
    ]
    assert assess(QUARTET_VOCAL, lead=lead).ready


def test_a_genuinely_unlyricked_attack_still_makes_the_line_incomplete() -> None:
    pitch = PITCHES[VoiceRole.LEAD]
    lead = [
        note(0, 1, pitch, lyrics=(LA,)),
        note(1, 1, None),
        note(2, 1, pitch),  # a new sounding attack with no lyric and no melisma
    ]
    assert "LYRIC_SOURCE_INCOMPLETE" in codes(assess(QUARTET_VOCAL, lead=lead))
