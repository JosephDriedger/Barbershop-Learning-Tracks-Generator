"""Pure rendering of readiness reports and line listings: text and JSON.

Readiness computation, text rendering, JSON serialization and CLI argument handling are separate
concerns. These functions only turn already-built, immutable results into strings; a UI can reuse
them or ignore them. Source severity and readiness disposition are both always shown.

JSON is versioned (``schema``), uses semantic fields rather than prose (the ``message`` is only one
field among them), and writes exact fractions as strings (``"7/2"``). Key order is fixed so that
snapshots are stable; it carries no meaning, and within a schema version the format only grows by
adding fields.
"""

import json
from fractions import Fraction
from typing import Any

from barbershop_tracks.core.readiness.findings import (
    Disposition,
    LineSummary,
    ReadinessFinding,
    ReadinessReport,
)
from barbershop_tracks.core.readiness.lines import LineInfo
from barbershop_tracks.models import PerformanceLocation

READINESS_SCHEMA = "barbershop-tracks.readiness/1"
LINES_SCHEMA = "barbershop-tracks.lines/1"


def _fraction(value: Fraction | None) -> str | None:
    return None if value is None else str(value)


def _location_json(location: PerformanceLocation | None) -> dict[str, Any] | None:
    if location is None:
        return None
    return {
        "measure_index": location.measure_index,
        "number": location.number,
        "visit": location.visit,
        "repeat_pass": location.repeat_pass,
        "endings": list(location.endings),
        "performed_position": _fraction(location.performed_position),
        "performed_measure_index": location.performed_measure_index,
    }


def _finding_json(finding: ReadinessFinding) -> dict[str, Any]:
    issue = finding.issue
    return {
        "disposition": finding.disposition.value,
        "severity": issue.severity.name.lower(),
        "code": issue.code,
        "origin": finding.origin.value,
        "role": None if finding.role is None else finding.role.value,
        "line_id": finding.line_id,
        "measure": issue.measure,
        "beat": _fraction(issue.beat),
        "location": _location_json(finding.location),
        "superseded_by": finding.superseded_by,
        "message": issue.message,
    }


def _line_json(line: LineSummary) -> dict[str, Any]:
    return {
        "line_id": line.line_id,
        "role": None if line.role is None else line.role.value,
        "ignored": line.ignored,
        "sounding_attacks": line.sounding_attacks,
        "first_start": _fraction(line.first_start),
        "end": _fraction(line.end),
    }


def report_to_dict(report: ReadinessReport, *, strict: bool = False) -> dict[str, Any]:
    """The JSON-ready structure of ``report``. ``passed`` honours ``strict``."""
    capability = report.capability
    counts = report.counts
    passed = report.clean if strict else report.ready
    return {
        "schema": READINESS_SCHEMA,
        "capability": {
            "name": capability.name,
            "required_roles": sorted(role.value for role in capability.required_roles),
            "lyric_policy": capability.lyric_policy.value,
            "lyric_source_role": (
                None if capability.lyric_source_role is None else capability.lyric_source_role.value
            ),
        },
        "ready": report.ready,
        "clean": report.clean,
        "outcome": {"strict": strict, "passed": passed},
        "counts": {d.value: counts[d] for d in Disposition},
        "performed_length": _fraction(report.performed_length),
        "lines": [_line_json(line) for line in report.lines],
        "findings": [_finding_json(f) for f in report.findings],
    }


def render_json(report: ReadinessReport, *, strict: bool = False) -> str:
    return json.dumps(report_to_dict(report, strict=strict), indent=2) + "\n"


def _where(finding: ReadinessFinding) -> str:
    parts: list[str] = []
    if finding.role is not None:
        parts.append(finding.role.display_name)
    if finding.line_id is not None:
        parts.append(finding.line_id)
    if finding.location is not None:
        parts.append(finding.location.describe())
    elif finding.issue.measure is not None:
        parts.append(f"measure {finding.issue.measure}")
    return f" ({', '.join(parts)})" if parts else ""


def render_text(
    report: ReadinessReport, *, strict: bool = False, show_superseded: bool = False
) -> str:
    """A human-readable report. Findings that a stronger finding supersedes are folded unless
    ``show_superseded``; readiness never depends on what is folded."""
    capability = report.capability
    verdict = "READY" if report.ready else "NOT READY"
    if report.ready and strict and not report.clean:
        verdict = "READY, but not clean (--strict)"
    counts = report.counts
    out = [
        f"Readiness for {capability.name}: {verdict}",
        f"  {counts[Disposition.BLOCKING]} blocking, {counts[Disposition.ADVISORY]} advisory, "
        f"{counts[Disposition.INFO]} info; performed length {report.performed_length} quarters",
    ]
    hidden = 0
    for disposition, title in (
        (Disposition.BLOCKING, "Blocking"),
        (Disposition.ADVISORY, "Advisory"),
        (Disposition.INFO, "Info"),
    ):
        shown = []
        for finding in report.findings:
            if finding.disposition is not disposition:
                continue
            if finding.superseded_by and not show_superseded:
                hidden += 1
                continue
            shown.append(finding)
        if not shown:
            continue
        out.append("")
        out.append(f"{title}:")
        for finding in shown:
            issue = finding.issue
            out.append(f"  {issue.severity.name} {issue.code}{_where(finding)}: {issue.message}")
    if hidden:
        out.append("")
        out.append(f"({hidden} redundant finding(s) folded; they are explained by a stronger one)")
    if report.lines:
        out.append("")
        out.append("Lines:")
        for line in report.lines:
            role = (
                "ignored"
                if line.ignored
                else (line.role.display_name if line.role else "unassigned")
            )
            out.append(f"  {line.line_id}: {role}, {line.sounding_attacks} sounding attacks")
    return "\n".join(out) + "\n"


def _info_json(info: LineInfo) -> dict[str, Any]:
    suggestion = info.suggestion
    return {
        "line_id": info.line_id,
        "part_name": info.part_name,
        "source_name": info.source_name,
        "staff": info.staff,
        "voice": info.voice,
        "sounding_attacks": info.sounding_attacks,
        "has_lyrics": info.has_lyrics,
        "first_measure": info.first_measure,
        "last_measure": info.last_measure,
        "suggestion": {
            "role": None if suggestion.role is None else suggestion.role.value,
            "basis": suggestion.basis.value,
            "confirmed": suggestion.confirmed,
            "note": suggestion.note,
        },
    }


def render_lines_json(infos: tuple[LineInfo, ...], *, error_count: int = 0) -> str:
    payload = {
        "schema": LINES_SCHEMA,
        "errors": error_count,
        "lines": [_info_json(info) for info in infos],
    }
    return json.dumps(payload, indent=2) + "\n"


def render_lines_text(infos: tuple[LineInfo, ...], *, error_count: int = 0) -> str:
    out = ["Source lines (copy an identifier into --assign ROLE=LINE or --ignore LINE):"]
    for info in infos:
        suggestion = info.suggestion
        hint = "no suggestion"
        if suggestion.role is not None:
            hint = f"suggested {suggestion.role.value} ({suggestion.basis.value}, unconfirmed)"
        span = (
            "no notes"
            if info.first_measure is None
            else f"measures {info.first_measure}-{info.last_measure}"
        )
        lyrics = "lyrics" if info.has_lyrics else "no lyrics"
        out.append(
            f"  {info.line_id}  {info.part_name!r}  {info.sounding_attacks} attacks, {span}, "
            f"{lyrics}; {hint}"
        )
    if not infos:
        out.append("  (no lines)")
    if error_count:
        out.append(f"The score has {error_count} error(s); run `check` for details.")
    return "\n".join(out) + "\n"
