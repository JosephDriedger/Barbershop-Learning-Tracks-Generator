"""The facts the readiness checks read, gathered once from a performed score."""

from dataclasses import dataclass
from fractions import Fraction

from barbershop_tracks.core.readiness.assignments import RoleAssignments
from barbershop_tracks.core.readiness.capability import Capability
from barbershop_tracks.core.readiness.findings import (
    Disposition,
    FindingOrigin,
    ReadinessFinding,
)
from barbershop_tracks.core.readiness.policy import classify
from barbershop_tracks.models import (
    Note,
    PerformanceNote,
    PerformedSong,
    Severity,
    ValidationIssue,
    VoiceRole,
)


@dataclass(frozen=True, slots=True)
class LineFacts:
    """One performed line: its sounding (non-rest), tie-merged attacks in order."""

    line_id: str
    attacks: tuple[PerformanceNote, ...]

    @property
    def has_notes(self) -> bool:
        return bool(self.attacks)


@dataclass(frozen=True, slots=True)
class Facts:
    performed: PerformedSong
    capability: Capability
    assignments: RoleAssignments
    lines: tuple[LineFacts, ...]

    @classmethod
    def gather(
        cls, performed: PerformedSong, assignments: RoleAssignments, capability: Capability
    ) -> "Facts":
        lines = tuple(
            LineFacts(
                line_id=line.part_id,
                attacks=tuple(a for a in merged if not a.is_rest),
            )
            for line, merged in zip(performed.lines, performed.merged, strict=True)
        )
        return cls(performed, capability, assignments, lines)

    @property
    def line_ids(self) -> frozenset[str]:
        return frozenset(line.line_id for line in self.lines)

    def line(self, line_id: str) -> LineFacts | None:
        return next((line for line in self.lines if line.line_id == line_id), None)

    @property
    def assigned_lines(self) -> tuple[LineFacts, ...]:
        """Existing lines that were assigned a role, once each, in score order."""
        assigned = {line for _, line in self.assignments.entries}
        return tuple(line for line in self.lines if line.line_id in assigned)

    @property
    def extent(self) -> Fraction:
        """The performed length in quarter notes."""
        plan = self.performed.plan
        return plan.end if plan.played else self.performed.song.duration

    def role_of(self, line_id: str) -> VoiceRole | None:
        return self.assignments.role_of(line_id)


def make_finding(
    capability: Capability,
    severity: Severity,
    code: str,
    message: str,
    *,
    facts: Facts | None = None,
    role: VoiceRole | None = None,
    line_id: str | None = None,
    note: Note | None = None,
) -> ReadinessFinding:
    """A readiness-origin finding, classified exactly like any other issue."""
    issue = ValidationIssue(
        severity=severity,
        code=code,
        message=message,
        role=role,
        part_id=line_id,
        measure=None if note is None else note.measure,
        beat=None if note is None else note.beat,
    )
    location = None if note is None or facts is None else facts.performed.location_of(note)
    return ReadinessFinding(
        issue=issue,
        origin=FindingOrigin.READINESS,
        disposition=classify(issue, capability).disposition,
        role=role,
        line_id=line_id,
        location=location,
    )


__all__ = ["Disposition", "Facts", "LineFacts", "make_finding"]
