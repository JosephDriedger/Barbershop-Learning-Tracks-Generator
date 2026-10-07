"""Voice-assignment checks (M4a): explicit roles, never inferred."""

import pytest

from barbershop_tracks.core.readiness import (
    QUARTET_VOCAL,
    TEST_TONE,
    Disposition,
    RoleAssignments,
    assess_readiness,
)
from barbershop_tracks.models import Pitch, Step, VoiceRole
from readiness_builders import (
    LINE_IDS,
    melody,
    parsed_of,
    quartet_assignments,
    quartet_lines,
    ready_parsed,
    rest,
    song_of,
)

EXTRA = "P5/s1/v1"


def codes(report) -> list[str]:  # type: ignore[no-untyped-def]
    return [f.code for f in report.findings if f.origin.value == "readiness"]


def test_all_four_roles_correctly_assigned_is_ready() -> None:
    report = assess_readiness(ready_parsed(), quartet_assignments(), QUARTET_VOCAL)
    assert report.ready
    assert codes(report) == []
    assert [line.role for line in report.lines] == list(VoiceRole)


def test_a_missing_required_role() -> None:
    entries = tuple(
        (r, line) for r, line in quartet_assignments().entries if r is not VoiceRole.BASS
    )
    report = assess_readiness(ready_parsed(), RoleAssignments(entries=entries), QUARTET_VOCAL)
    assert not report.ready
    assert "ROLE_MISSING" in codes(report)
    missing = report.by_code("ROLE_MISSING")[0]
    assert missing.role is VoiceRole.BASS
    assert missing.disposition is Disposition.BLOCKING
    assert "LINE_UNASSIGNED" in codes(report)  # the bass line has notes and no role


def test_a_duplicate_role() -> None:
    entries = (*quartet_assignments().entries, (VoiceRole.LEAD, LINE_IDS[VoiceRole.TENOR]))
    report = assess_readiness(ready_parsed(), RoleAssignments(entries=entries), QUARTET_VOCAL)
    assert "ROLE_DUPLICATE" in codes(report)
    assert "LINE_ASSIGNED_TWICE" in codes(report)  # the tenor line now has two roles
    assert not report.ready


def test_an_unknown_line() -> None:
    report = assess_readiness(ready_parsed(), quartet_assignments(lead="P9/s1/v1"), QUARTET_VOCAL)
    assert "ROLE_LINE_UNKNOWN" in codes(report)
    assert not report.ready
    assert report.by_code("ROLE_LINE_UNKNOWN")[0].line_id == "P9/s1/v1"


def test_the_same_line_assigned_twice() -> None:
    same = LINE_IDS[VoiceRole.TENOR]
    report = assess_readiness(ready_parsed(), quartet_assignments(lead=same), QUARTET_VOCAL)
    assert "LINE_ASSIGNED_TWICE" in codes(report)
    assert "LINE_UNASSIGNED" in codes(report)  # the real lead line is now unaccounted for
    assert not report.ready


def test_an_unassigned_musical_line_blocks_unless_ignored() -> None:
    lines = quartet_lines()
    lines[EXTRA] = melody(Pitch(Step.D, 4))
    parsed = parsed_of(song_of(lines))
    report = assess_readiness(parsed, quartet_assignments(), QUARTET_VOCAL)
    assert "LINE_UNASSIGNED" in codes(report)
    assert not report.ready


def test_an_ignored_musical_line_is_recorded_not_discarded_silently() -> None:
    lines = quartet_lines()
    lines[EXTRA] = melody(Pitch(Step.D, 4))
    parsed = parsed_of(song_of(lines))
    assigned = RoleAssignments(entries=quartet_assignments().entries, ignored=(EXTRA,))
    report = assess_readiness(parsed, assigned, QUARTET_VOCAL)
    assert report.ready
    ignored = report.by_code("LINE_IGNORED")
    assert len(ignored) == 1
    assert ignored[0].disposition is Disposition.INFO
    assert next(s for s in report.lines if s.line_id == EXTRA).ignored


def test_an_assigned_line_with_no_sounding_notes_is_an_error() -> None:
    lines = quartet_lines(bass=[rest(0, 4), rest(4, 4)])
    report = assess_readiness(parsed_of(song_of(lines)), quartet_assignments(), QUARTET_VOCAL)
    assert "ROLE_LINE_EMPTY" in codes(report)
    assert report.by_code("ROLE_LINE_EMPTY")[0].role is VoiceRole.BASS
    assert not report.ready


def test_an_ignored_empty_line_causes_no_error() -> None:
    lines = quartet_lines()
    lines[EXTRA] = [rest(0, 4)]
    assigned = RoleAssignments(entries=quartet_assignments().entries, ignored=(EXTRA,))
    report = assess_readiness(parsed_of(song_of(lines)), assigned, QUARTET_VOCAL)
    assert report.ready
    assert "LINE_IGNORED" not in codes(report)  # nothing musical was excluded


def test_an_unknown_ignored_line_and_a_line_both_assigned_and_ignored() -> None:
    tenor = LINE_IDS[VoiceRole.TENOR]
    assigned = RoleAssignments(entries=quartet_assignments().entries, ignored=("P9/s1/v1", tenor))
    report = assess_readiness(ready_parsed(), assigned, QUARTET_VOCAL)
    assert "IGNORED_LINE_UNKNOWN" in codes(report)
    assert "LINE_ASSIGNED_AND_IGNORED" in codes(report)
    assert not report.ready


def test_roles_are_a_capability_requirement_not_a_universal_rule() -> None:
    # test-tone requires no roles and does not insist every musical line is accounted for
    lines = quartet_lines()
    lines[EXTRA] = melody(Pitch(Step.D, 4))
    parsed = parsed_of(song_of(lines))
    report = assess_readiness(parsed, RoleAssignments(), TEST_TONE)
    assert report.ready
    assert codes(report) == []


def test_assignments_are_never_inferred_from_the_score() -> None:
    parsed = ready_parsed()
    assert parsed.song is not None
    assert all(part.role is None for part in parsed.song.parts)
    report = assess_readiness(parsed, RoleAssignments(), QUARTET_VOCAL)
    assert codes(report).count("ROLE_MISSING") == 4
    assert codes(report).count("LINE_UNASSIGNED") == 4


@pytest.mark.parametrize("role", list(VoiceRole))
def test_each_required_role_is_checked_independently(role: VoiceRole) -> None:
    entries = tuple((r, line) for r, line in quartet_assignments().entries if r is not role)
    report = assess_readiness(ready_parsed(), RoleAssignments(entries=entries), QUARTET_VOCAL)
    assert [f.role for f in report.by_code("ROLE_MISSING")] == [role]
