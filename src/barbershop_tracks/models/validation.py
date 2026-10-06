"""Validation issues and results.

Issues are plain immutable data with machine-readable identifiers. They never hold
references to ``Song``, ``Part`` or ``Note`` objects.
"""

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from enum import IntEnum
from fractions import Fraction

from barbershop_tracks.models.timing import require_int, to_fraction
from barbershop_tracks.models.voice import VoiceRole

_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


class Severity(IntEnum):
    """Issue severity, ordered so ``Severity.ERROR > Severity.WARNING``."""

    INFO = 1
    WARNING = 2
    ERROR = 3


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidationIssue:
    """One finding. ``code`` is a stable UPPER_SNAKE_CASE identifier, e.g. ``NO_LYRIC``."""

    severity: Severity
    code: str
    message: str
    role: VoiceRole | None = None
    part_id: str | None = None
    measure: int | None = None
    beat: Fraction | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.severity, Severity):
            raise TypeError("severity must be a Severity")
        if not _CODE_PATTERN.match(self.code):
            raise ValueError("code must be UPPER_SNAKE_CASE")
        if not self.message:
            raise ValueError("message must not be empty")
        if self.measure is not None:
            require_int(self.measure, name="measure")
        if self.beat is not None:
            object.__setattr__(self, "beat", to_fraction(self.beat, name="beat"))

    def __str__(self) -> str:
        where = []
        if self.role is not None:
            where.append(self.role.display_name)
        elif self.part_id is not None:
            where.append(f"part {self.part_id}")
        if self.measure is not None:
            where.append(f"measure {self.measure}")
        if self.beat is not None:
            where.append(f"beat {self.beat}")
        location = f" ({', '.join(where)})" if where else ""
        return f"{self.severity.name} {self.code}{location}: {self.message}"


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """An immutable, ordered collection of issues."""

    issues: tuple[ValidationIssue, ...] = ()

    def __post_init__(self) -> None:
        issues = tuple(self.issues)
        if not all(isinstance(issue, ValidationIssue) for issue in issues):
            raise TypeError("issues must contain only ValidationIssue objects")
        object.__setattr__(self, "issues", issues)

    @classmethod
    def of(cls, issues: Iterable[ValidationIssue]) -> "ValidationResult":
        return cls(tuple(issues))

    def __iter__(self) -> Iterator[ValidationIssue]:
        return iter(self.issues)

    def __len__(self) -> int:
        return len(self.issues)

    def with_issue(self, issue: ValidationIssue) -> "ValidationResult":
        """Return a new result with ``issue`` appended."""
        return ValidationResult((*self.issues, issue))

    def merged(self, *others: "ValidationResult") -> "ValidationResult":
        """Return a new result with the issues of ``others`` appended, in order."""
        combined = list(self.issues)
        for other in others:
            combined.extend(other.issues)
        return ValidationResult(tuple(combined))

    def by_severity(self, severity: Severity) -> tuple[ValidationIssue, ...]:
        """Issues with exactly this severity."""
        return tuple(issue for issue in self.issues if issue.severity is severity)

    def at_least(self, severity: Severity) -> tuple[ValidationIssue, ...]:
        """Issues with this severity or higher."""
        return tuple(issue for issue in self.issues if issue.severity >= severity)

    def by_code(self, code: str) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.code == code)

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return self.by_severity(Severity.ERROR)

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return self.by_severity(Severity.WARNING)

    @property
    def infos(self) -> tuple[ValidationIssue, ...]:
        return self.by_severity(Severity.INFO)

    @property
    def has_errors(self) -> bool:
        return any(issue.severity is Severity.ERROR for issue in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(issue.severity is Severity.WARNING for issue in self.issues)
