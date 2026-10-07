"""``assess_readiness``: wrapping the lower layers, locations, supersession, immutability."""

import copy
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from barbershop_tracks.core.musicxml import ParseResult, parse_musicxml
from barbershop_tracks.core.readiness import (
    QUARTET_VOCAL,
    TEST_TONE,
    Disposition,
    FindingOrigin,
    RoleAssignments,
    assess_readiness,
)
from barbershop_tracks.models import (
    Lyric,
    Pitch,
    Severity,
    Step,
    Syllabic,
    ValidationIssue,
    ValidationResult,
    VoiceRole,
)
from readiness_builders import (
    LINE_IDS,
    note,
    parsed_of,
    quartet_assignments,
    quartet_lines,
    ready_parsed,
    song_of,
)
from xml_builders import (
    attributes,
    measure,
    parse_text,
    score,
    tie_xml,
    tied_xml,
)
from xml_builders import note as xml_note

pytestmark = pytest.mark.usefixtures("no_network")

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "musicxml"
C4 = Pitch(Step.C, 4)
D4 = Pitch(Step.D, 4)


def code_set(report) -> set[str]:  # type: ignore[no-untyped-def]
    return {f.code for f in report.findings}


# --- lower-layer issues are wrapped, never changed ----------------------------------------------


def test_a_parser_error_always_blocks_and_the_issue_is_the_same_object() -> None:
    error = ValidationIssue(severity=Severity.ERROR, code="UNSUPPORTED_JUMP", message="no jumps")
    parsed = parsed_of(song_of(quartet_lines()), ValidationResult.of([error]))
    report = assess_readiness(parsed, quartet_assignments(), QUARTET_VOCAL)
    wrapped = report.by_code("UNSUPPORTED_JUMP")[0]
    assert wrapped.issue is error  # untouched: same object, same severity
    assert wrapped.issue.severity is Severity.ERROR
    assert wrapped.disposition is Disposition.BLOCKING
    assert wrapped.origin is FindingOrigin.PARSE
    assert not report.ready
    assert not assess_readiness(parsed, RoleAssignments(), TEST_TONE).ready  # every capability


def test_a_parser_warning_gets_its_registered_disposition() -> None:
    warning = ValidationIssue(
        severity=Severity.WARNING, code="MEASURE_INCOMPLETE", message="short", part_id="P1"
    )
    parsed = parsed_of(song_of(quartet_lines()), ValidationResult.of([warning]))
    report = assess_readiness(parsed, quartet_assignments(), QUARTET_VOCAL)
    finding = report.by_code("MEASURE_INCOMPLETE")[0]
    assert finding.disposition is Disposition.ADVISORY
    assert finding.issue.severity is Severity.WARNING
    assert report.ready
    assert not report.clean  # what --strict will ask


def test_an_unclassified_warning_blocks() -> None:
    odd = ValidationIssue(severity=Severity.WARNING, code="SOMETHING_NEW", message="?")
    parsed = parsed_of(song_of(quartet_lines()), ValidationResult.of([odd]))
    report = assess_readiness(parsed, quartet_assignments(), QUARTET_VOCAL)
    assert report.by_code("SOMETHING_NEW")[0].disposition is Disposition.BLOCKING


def test_no_performed_score_is_not_ready() -> None:
    parsed = ParseResult(song=None, issues=ValidationResult())
    report = assess_readiness(parsed, quartet_assignments(), QUARTET_VOCAL)
    assert code_set(report) == {"NO_PERFORMANCE"}
    assert not report.ready


# --- the report is derived ---------------------------------------------------------------------


def test_ready_is_derived_from_findings_and_cannot_be_set() -> None:
    report = assess_readiness(ready_parsed(), quartet_assignments(), QUARTET_VOCAL)
    assert report.ready
    with pytest.raises((AttributeError, TypeError)):  # a derived property, not a stored flag
        report.ready = False  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        report.findings = ()  # type: ignore[misc]
    counts = report.counts
    assert counts[Disposition.BLOCKING] == 0
    assert sum(counts.values()) == len(report.findings)


def test_counts_and_views_agree() -> None:
    lines = quartet_lines(lead=[note(0, 1, C4), note(0, 1, D4)])
    report = assess_readiness(parsed_of(song_of(lines)), quartet_assignments(), QUARTET_VOCAL)
    assert len(report.blocking) == report.counts[Disposition.BLOCKING] > 0
    assert len(report.advisory) == report.counts[Disposition.ADVISORY]
    assert len(report.info) == report.counts[Disposition.INFO]
    assert report.by_role(VoiceRole.LEAD)


def test_the_source_song_is_never_changed() -> None:
    parsed = ready_parsed()
    assert parsed.song is not None
    before = copy.deepcopy(parsed.song)
    assess_readiness(parsed, quartet_assignments(), QUARTET_VOCAL)
    assess_readiness(parsed, RoleAssignments(), TEST_TONE)
    assert parsed.song == before


# --- lyric analysis findings -------------------------------------------------------------------


def unclosed_word_song() -> ParseResult:
    """The same performed score every time: the lead begins a word it never ends."""
    begin = Lyric(text="ba", syllabic=Syllabic.BEGIN)
    lead = [note(0, 1, C4, lyrics=(begin,)), *[note(i, 1, C4) for i in range(1, 8)]]
    return parsed_of(song_of(quartet_lines(lead=lead)))


def test_a_lyric_error_blocks_a_capability_that_uses_lyrics_and_carries_a_location() -> None:
    report = assess_readiness(unclosed_word_song(), quartet_assignments(), QUARTET_VOCAL)
    unclosed = report.by_code("LYRIC_WORD_UNCLOSED")
    assert len(unclosed) == 1
    assert unclosed[0].origin is FindingOrigin.LYRICS
    assert unclosed[0].disposition is Disposition.BLOCKING
    assert unclosed[0].location is not None
    assert unclosed[0].location.number == 1
    assert not report.ready


def test_source_severity_is_not_capability_disposition() -> None:
    parsed = unclosed_word_song()
    vocal = assess_readiness(parsed, quartet_assignments(), QUARTET_VOCAL)
    tone = assess_readiness(parsed, quartet_assignments(), TEST_TONE)
    for report in (vocal, tone):
        finding = report.by_code("LYRIC_WORD_UNCLOSED")[0]
        assert finding.issue.severity is Severity.ERROR  # preserved, whatever the capability
        assert finding.issue.code == "LYRIC_WORD_UNCLOSED"
    assert vocal.by_code("LYRIC_WORD_UNCLOSED")[0].disposition is Disposition.BLOCKING
    assert tone.by_code("LYRIC_WORD_UNCLOSED")[0].disposition is Disposition.INFO
    assert not vocal.ready
    assert tone.ready  # nothing else blocks the capability that ignores lyrics


def test_a_lyric_error_never_hides_a_structural_one_for_a_lyric_free_capability() -> None:
    structural = ValidationIssue(severity=Severity.ERROR, code="UNSUPPORTED_JUMP", message="no")
    parsed = parsed_of(unclosed_word_song().song, ValidationResult.of([structural]))  # type: ignore[arg-type]
    tone = assess_readiness(parsed, RoleAssignments(), TEST_TONE)
    assert tone.by_code("LYRIC_WORD_UNCLOSED")[0].disposition is Disposition.INFO
    assert tone.by_code("UNSUPPORTED_JUMP")[0].disposition is Disposition.BLOCKING
    assert not tone.ready


def test_a_parser_lyric_error_is_also_non_blocking_for_a_lyric_free_capability() -> None:
    lyric_error = ValidationIssue(
        severity=Severity.ERROR, code="LYRIC_ON_REST", message="a rest carries a lyric"
    )
    parsed = parsed_of(song_of(quartet_lines()), ValidationResult.of([lyric_error]))
    tone = assess_readiness(parsed, quartet_assignments(), TEST_TONE)
    finding = tone.by_code("LYRIC_ON_REST")[0]
    assert finding.origin is FindingOrigin.PARSE
    assert finding.disposition is Disposition.INFO
    assert finding.issue is lyric_error
    assert tone.ready
    assert not assess_readiness(parsed, quartet_assignments(), QUARTET_VOCAL).ready


def test_the_lyric_simultaneous_error_never_replaces_the_monophony_check() -> None:
    overlapping = quartet_lines(lead=[note(0, 2, C4), note(1, 1, D4)])
    parsed = parsed_of(song_of(overlapping))
    tone = assess_readiness(parsed, quartet_assignments(), TEST_TONE)
    lyric = tone.by_code("LYRIC_SIMULTANEOUS_ATTACKS")[0]
    assert lyric.issue.severity is Severity.ERROR
    assert lyric.disposition is Disposition.INFO  # lyrics are not consumed ...
    assert lyric.superseded_by == "LINE_OVERLAPPING_NOTES"
    assert (
        tone.by_code("LINE_OVERLAPPING_NOTES")[0].disposition is Disposition.BLOCKING
    )  # ... but M4 still blocks
    assert not tone.ready


def test_a_tie_warning_is_located_by_performance_not_by_message(tmp_path: Path) -> None:
    fwd = '<barline location="left"><repeat direction="forward"/></barline>'
    back = '<barline location="right"><repeat direction="backward"/></barline>'
    start = xml_note("C", 4, 8, tie=tie_xml("start"), notations=tied_xml("start"))
    stop = xml_note("C", 4, 8, tie=tie_xml("stop"), notations=tied_xml("stop"))
    body = (
        measure(1, fwd + xml_note("D", 4, 8), attrs=attributes())
        + measure(2, start + back)
        + measure(3, stop)
    )
    parsed = parse_text(tmp_path, score(body))
    report = assess_readiness(parsed, RoleAssignments(), TEST_TONE)
    broken = report.by_code("TIE_BROKEN_BY_REPEAT")[0]
    assert broken.origin is FindingOrigin.PERFORMANCE
    assert broken.disposition is Disposition.ADVISORY
    assert broken.location is not None
    assert (broken.location.number, broken.location.visit, broken.location.repeat_pass) == (2, 1, 1)


def test_a_lower_layer_finding_superseded_by_monophony_keeps_its_severity() -> None:
    lines = quartet_lines(lead=[note(0, 2, C4), note(1, 1, D4)])
    report = assess_readiness(parsed_of(song_of(lines)), quartet_assignments(), QUARTET_VOCAL)
    lyric = report.by_code("LYRIC_SIMULTANEOUS_ATTACKS")
    assert lyric
    assert lyric[0].issue.severity is Severity.ERROR  # the lower layer's own severity
    assert lyric[0].superseded_by == "LINE_OVERLAPPING_NOTES"  # explained by a stronger finding
    assert report.by_code("LINE_OVERLAPPING_NOTES")[0].superseded_by is None


# --- real fixtures through the whole pipeline -----------------------------------------------------


def ttbb_assignments(parsed: ParseResult) -> RoleAssignments:
    assert parsed.performed is not None
    ids = [line.part_id for line in parsed.performed.lines]
    return RoleAssignments(entries=tuple(zip(list(VoiceRole), ids, strict=True)))


def test_ttbb_fixture_with_a_tempo_is_ready_for_the_quartet() -> None:
    parsed = parse_musicxml(FIXTURES / "ttbb" / "inputs" / "ttbb_layout_shared_tempo.musicxml")
    report = assess_readiness(parsed, ttbb_assignments(parsed), QUARTET_VOCAL)
    assert report.ready
    assert "LYRIC_LINE_EMPTY" in code_set(report)  # lyric-less lines are advisory here
    assert report.by_code("LYRIC_LINE_EMPTY")[0].disposition is Disposition.ADVISORY


def test_ttbb_fixture_without_a_tempo_is_not_ready_for_a_real_time_capability() -> None:
    parsed = parse_musicxml(FIXTURES / "ttbb" / "inputs" / "ttbb_layout.musicxml")
    report = assess_readiness(parsed, ttbb_assignments(parsed), QUARTET_VOCAL)
    assert not report.ready
    assert "TEMPO_MISSING" in code_set(report)  # and 120 BPM is never assumed


def test_lines_pair_with_roles_only_when_the_caller_says_so() -> None:
    parsed = parse_musicxml(FIXTURES / "ttbb" / "inputs" / "ttbb_layout_shared_tempo.musicxml")
    report = assess_readiness(parsed, RoleAssignments(), QUARTET_VOCAL)
    assert not report.ready
    assert [s.role for s in report.lines] == [None, None, None, None]
    assert LINE_IDS  # the builders' ids are unrelated to the parsed fixture's
