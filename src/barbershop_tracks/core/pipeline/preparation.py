"""Readiness and plan building, shared by ``generate`` and by anything that wants a preview.

``prepare`` never raises for a score that simply is not ready; it returns what it found so a
GUI can show it while the user is still choosing. ``generate`` turns the same outcome into the
errors the CLI reports, so there is one implementation of "is this score ready, and what is left".
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from barbershop_tracks.core.musicxml import ParseResult
from barbershop_tracks.core.pipeline.lyric_files import review_report
from barbershop_tracks.core.readiness import MIDI_QUARTET, RoleAssignments, assess_readiness
from barbershop_tracks.core.readiness.findings import ReadinessReport
from barbershop_tracks.core.synthesis import (
    LyricApproval,
    SourceIdentity,
    SynthesisPlan,
    VoiceEngineRef,
    build_synthesis_plan,
)
from barbershop_tracks.models import VoiceRole


@dataclass(frozen=True, slots=True)
class Preparation:
    report: ReadinessReport | None  # None when no performed score exists
    plan: SynthesisPlan | None  # None while the score or the mapping blocks planning
    review: dict[str, Any] | None  # the lyric review report when the plan has undecided notes

    @property
    def source_ready(self) -> bool:
        return self.report is not None and self.report.ready

    @property
    def generatable(self) -> bool:
        return self.plan is not None and self.plan.is_ready


def blocking_details(report: ReadinessReport) -> list[dict[str, Any]]:
    out = []
    for finding in report.blocking:
        out.append(
            {
                "code": finding.code,
                "message": finding.issue.message,
                "voice": finding.role.value if finding.role else None,
                "line": finding.line_id,
                "where": finding.location.describe() if finding.location else None,
            }
        )
    return out


def prepare(
    parsed: ParseResult,
    assignments: RoleAssignments,
    *,
    identity: SourceIdentity,
    engine_refs: Mapping[VoiceRole, VoiceEngineRef],
    verse: str | None = None,
    approvals: Sequence[LyricApproval] = (),
) -> Preparation:
    if parsed.performed is None or parsed.song is None:
        return Preparation(None, None, None)
    report = assess_readiness(parsed, assignments, MIDI_QUARTET, verse=verse)
    if not report.ready:
        return Preparation(report, None, None)
    plan = build_synthesis_plan(
        parsed.performed,
        assignments,
        source=identity,
        engine_refs=engine_refs,
        verse=verse,
        approvals=approvals,
    )
    return Preparation(report, plan, None if plan.is_ready else review_report(plan))
