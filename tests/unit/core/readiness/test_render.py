"""Pure rendering: text and JSON, both severity and disposition visible, exact fractions."""

import json
from fractions import Fraction

from barbershop_tracks.core.readiness import TEST_TONE, ReadinessReport, assess_readiness
from barbershop_tracks.core.readiness.render import (
    LINES_SCHEMA,
    READINESS_SCHEMA,
    render_json,
    render_text,
    report_to_dict,
)
from barbershop_tracks.models import Pitch, Step
from readiness_builders import (
    QUARTET_STRUCTURE,
    note,
    parsed_of,
    quartet_assignments,
    quartet_lines,
    ready_parsed,
    song_of,
)

C4 = Pitch(Step.C, 4)
D4 = Pitch(Step.D, 4)


def overlapping_report() -> ReadinessReport:
    lines = quartet_lines(lead=[note(0, 2, C4), note(1, 1, D4)])
    return assess_readiness(parsed_of(song_of(lines)), quartet_assignments(), QUARTET_STRUCTURE)


def test_schema_names_are_versioned() -> None:
    assert READINESS_SCHEMA.endswith("/1")
    assert LINES_SCHEMA.endswith("/1")


def test_json_shows_both_source_severity_and_readiness_disposition() -> None:
    data = json.loads(render_json(overlapping_report()))
    lyric = next(f for f in data["findings"] if f["code"] == "LYRIC_SIMULTANEOUS_ATTACKS")
    assert lyric["severity"] == "error"  # the lower layer's own severity
    assert lyric["disposition"] == "info"  # lyrics are not consumed by this capability
    assert lyric["superseded_by"] == "LINE_OVERLAPPING_NOTES"  # kept, with both visible
    overlap = next(f for f in data["findings"] if f["code"] == "LINE_OVERLAPPING_NOTES")
    assert overlap["origin"] == "readiness"
    assert overlap["role"] == "lead"
    assert overlap["location"]["performed_position"] == "1"
    assert data["ready"] is False


def test_fractions_are_exact_strings_never_floats() -> None:
    lines = quartet_lines(lead=[note(Fraction(1, 3), Fraction(1, 3), C4)])
    report = assess_readiness(parsed_of(song_of(lines)), quartet_assignments(), QUARTET_STRUCTURE)
    data = report_to_dict(report)
    lead = next(line for line in data["lines"] if line["role"] == "lead")
    assert lead["first_start"] == "1/3"
    assert lead["end"] == "2/3"
    assert data["performed_length"] == "16"


def test_the_text_report_folds_a_superseded_finding_but_readiness_does_not_depend_on_it() -> None:
    report = overlapping_report()
    folded = render_text(report)
    shown = render_text(report, show_superseded=True)
    assert "LYRIC_SIMULTANEOUS_ATTACKS" not in folded
    assert "folded" in folded
    assert "LYRIC_SIMULTANEOUS_ATTACKS" in shown
    assert "LINE_OVERLAPPING_NOTES" in folded
    assert not report.ready  # unchanged by what a renderer hides
    assert any(f.code == "LYRIC_SIMULTANEOUS_ATTACKS" for f in report.findings)


def test_text_report_verdicts() -> None:
    ready = assess_readiness(ready_parsed(), quartet_assignments(), QUARTET_STRUCTURE)
    assert "READY" in render_text(ready).splitlines()[0]
    assert "NOT READY" not in render_text(ready)
    assert "not clean" in render_text(ready, strict=True) or ready.clean
    assert "NOT READY" in render_text(overlapping_report())


def test_the_outcome_follows_strictness_not_readiness() -> None:
    report = assess_readiness(ready_parsed(), quartet_assignments(), TEST_TONE)
    plain = report_to_dict(report)
    strict = report_to_dict(report, strict=True)
    assert plain["outcome"] == {"strict": False, "passed": report.ready}
    assert strict["outcome"] == {"strict": True, "passed": report.clean}
    assert plain["ready"] == strict["ready"]


def test_json_is_deterministic_and_parses() -> None:
    report = overlapping_report()
    assert render_json(report) == render_json(report)
    assert json.loads(render_json(report))["schema"] == READINESS_SCHEMA


def test_rendering_does_not_mutate_the_report() -> None:
    report = overlapping_report()
    before = (report.findings, report.lines, report.counts)
    render_text(report)
    render_json(report)
    assert (report.findings, report.lines, report.counts) == before
