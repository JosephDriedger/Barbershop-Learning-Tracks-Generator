"""``assess_readiness``: can this capability safely generate from this performed score?

Pure. It wraps the issues the lower layers already produced (never altering them), runs the
lyric analysis once over the performed traversal, and adds only the generation-specific checks.
"""

from dataclasses import replace
from fractions import Fraction

from barbershop_tracks.core.lyrics import analyze_song_lyrics
from barbershop_tracks.core.musicxml import ParseResult
from barbershop_tracks.core.readiness.assignments import RoleAssignments
from barbershop_tracks.core.readiness.capability import Capability
from barbershop_tracks.core.readiness.context import Facts, make_finding
from barbershop_tracks.core.readiness.findings import (
    FindingOrigin,
    LineSummary,
    ReadinessFinding,
    ReadinessReport,
)
from barbershop_tracks.core.readiness.lyric_policy import check_lyrics
from barbershop_tracks.core.readiness.policy import classify
from barbershop_tracks.core.readiness.roles import check_roles
from barbershop_tracks.core.readiness.sounding import (
    check_monophony,
    check_pitch,
    check_tempo,
    check_timeline,
)
from barbershop_tracks.models import (
    LocatedIssue,
    PerformanceLocation,
    Severity,
    ValidationIssue,
)

# A lower-layer finding that a stronger readiness finding explains (the lower layer's own severity
# is untouched; renderers may fold it).
_SUPERSEDED_BY = {
    "LYRIC_SIMULTANEOUS_ATTACKS": ("LINE_SIMULTANEOUS_NOTES", "LINE_OVERLAPPING_NOTES"),
}


def assess_readiness(
    parsed: ParseResult,
    assignments: RoleAssignments,
    capability: Capability,
    *,
    verse: str | None = None,
) -> ReadinessReport:
    """Assess ``parsed`` for ``capability`` with the caller's explicit ``assignments``."""
    performed = parsed.performed
    findings: list[ReadinessFinding] = []
    located_pool = list(performed.located_issues) if performed is not None else []
    for issue in parsed.issues:
        match = next((i for i, located in enumerate(located_pool) if located.issue == issue), None)
        if match is None:
            findings.append(_wrap(issue, FindingOrigin.PARSE, None, capability, assignments))
        else:
            located = located_pool.pop(match)
            findings.append(
                _wrap(issue, FindingOrigin.PERFORMANCE, located.location, capability, assignments)
            )
    if performed is None:
        findings.append(
            make_finding(
                capability,
                Severity.ERROR,
                "NO_PERFORMANCE",
                "no performed score could be built, so nothing can be generated",
            )
        )
        return ReadinessReport(capability=capability, findings=tuple(findings))

    facts = Facts.gather(performed, assignments, capability)
    analysis = analyze_song_lyrics(performed, verse=verse)
    for issue in analysis.issues:
        findings.append(_wrap(issue, FindingOrigin.LYRICS, None, capability, assignments))
    for line in analysis.lines:
        for located in line.located:
            findings.append(
                _wrap(
                    located.issue, FindingOrigin.LYRICS, located.location, capability, assignments
                )
            )
    metronome = any(f.code == "METRONOME_WITHOUT_SOUND" for f in findings)
    findings += check_roles(facts)
    findings += check_lyrics(facts, analysis)
    findings += check_monophony(facts)
    findings += check_pitch(facts)
    findings += check_tempo(facts, metronome_hint=metronome)
    findings += check_timeline(facts)
    return ReadinessReport(
        capability=capability,
        findings=tuple(_mark_superseded(findings)),
        lines=_summaries(facts),
        performed_length=facts.extent,
    )


def _wrap(
    issue: ValidationIssue,
    origin: FindingOrigin,
    location: PerformanceLocation | None,
    capability: Capability,
    assignments: RoleAssignments,
) -> ReadinessFinding:
    line_id = issue.part_id
    return ReadinessFinding(
        issue=issue,
        origin=origin,
        disposition=classify(issue, capability).disposition,
        role=assignments.role_of(line_id) if line_id is not None else issue.role,
        line_id=line_id,
        location=location,
    )


def _mark_superseded(findings: list[ReadinessFinding]) -> list[ReadinessFinding]:
    strong = {(f.line_id, f.code) for f in findings if f.origin is FindingOrigin.READINESS}
    marked: list[ReadinessFinding] = []
    for finding in findings:
        by = next(
            (
                code
                for code in _SUPERSEDED_BY.get(finding.code, ())
                if (finding.line_id, code) in strong
            ),
            None,
        )
        marked.append(replace(finding, superseded_by=by) if by is not None else finding)
    return marked


def _summaries(facts: Facts) -> tuple[LineSummary, ...]:
    ignored = set(facts.assignments.ignored)
    summaries = []
    for line in facts.lines:
        starts = [a.start for a in line.attacks]
        ends = [a.end for a in line.attacks]
        summaries.append(
            LineSummary(
                line_id=line.line_id,
                role=facts.role_of(line.line_id),
                ignored=line.line_id in ignored,
                sounding_attacks=len(line.attacks),
                first_start=min(starts) if starts else None,
                end=max(ends) if ends else None,
            )
        )
    return tuple(summaries)


__all__ = ["Fraction", "LocatedIssue", "assess_readiness"]
