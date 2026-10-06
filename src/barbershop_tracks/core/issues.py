"""Collecting validation issues while parsing or analyzing."""

from fractions import Fraction

from barbershop_tracks.models import Severity, ValidationIssue, ValidationResult


class IssueCollector:
    """Accumulates located issues. Parsing never raises for problems in the music."""

    def __init__(self) -> None:
        self._issues: list[ValidationIssue] = []

    def error(
        self,
        code: str,
        message: str,
        *,
        part_id: str | None = None,
        measure: int | None = None,
        beat: Fraction | None = None,
    ) -> None:
        self._add(Severity.ERROR, code, message, part_id, measure, beat)

    def warning(
        self,
        code: str,
        message: str,
        *,
        part_id: str | None = None,
        measure: int | None = None,
        beat: Fraction | None = None,
    ) -> None:
        self._add(Severity.WARNING, code, message, part_id, measure, beat)

    def extend(self, result: ValidationResult) -> None:
        self._issues.extend(result.issues)

    def result(self) -> ValidationResult:
        return ValidationResult.of(self._issues)

    def _add(
        self,
        severity: Severity,
        code: str,
        message: str,
        part_id: str | None,
        measure: int | None,
        beat: Fraction | None,
    ) -> None:
        self._issues.append(
            ValidationIssue(
                severity=severity,
                code=code,
                message=message,
                part_id=part_id,
                measure=measure,
                beat=beat,
            )
        )
