from dataclasses import fields
from fractions import Fraction

import pytest

from barbershop_tracks.models import Severity, ValidationIssue, ValidationResult, VoiceRole
from barbershop_tracks.models.note import Note
from barbershop_tracks.models.part import Part
from barbershop_tracks.models.song import Song


def _issue(severity: Severity, code: str = "SOME_CODE", **kwargs: object) -> ValidationIssue:
    return ValidationIssue(severity=severity, code=code, message="msg", **kwargs)  # type: ignore[arg-type]


def test_severity_has_info_warning_error_in_increasing_order() -> None:
    assert [s.name for s in Severity] == ["INFO", "WARNING", "ERROR"]
    assert Severity.INFO < Severity.WARNING < Severity.ERROR


def test_issue_carries_machine_readable_fields() -> None:
    issue = ValidationIssue(
        severity=Severity.ERROR,
        code="NO_LYRIC",
        message="Note has no lyric",
        role=VoiceRole.LEAD,
        part_id="P2",
        measure=7,
        beat=Fraction(5, 2),
    )
    assert issue.severity is Severity.ERROR
    assert issue.code == "NO_LYRIC"
    assert issue.role is VoiceRole.LEAD
    assert issue.part_id == "P2"
    assert issue.measure == 7
    assert issue.beat == Fraction(5, 2)
    assert "Lead" in str(issue)
    assert "measure 7" in str(issue)


def test_issue_location_is_optional() -> None:
    issue = _issue(Severity.INFO)
    assert issue.role is None
    assert issue.part_id is None
    assert issue.measure is None
    assert issue.beat is None


@pytest.mark.parametrize("code", ["", "lower", "Has Space", "1STARTS_WITH_DIGIT", "X-Y"])
def test_issue_code_must_be_upper_snake_case(code: str) -> None:
    with pytest.raises(ValueError, match="code"):
        _issue(Severity.INFO, code=code)


def test_issue_requires_message() -> None:
    with pytest.raises(ValueError, match="message"):
        ValidationIssue(severity=Severity.INFO, code="X", message="")


def test_issue_rejects_float_beat() -> None:
    with pytest.raises(TypeError, match="Fraction or int"):
        _issue(Severity.INFO, beat=1.5)


def test_issue_holds_no_references_to_mutable_model_objects() -> None:
    forbidden = (Song, Part, Note)
    for field in fields(ValidationIssue):
        annotation = str(field.type)
        assert not any(model.__name__ in annotation for model in forbidden), field.name


def test_empty_result_has_no_errors() -> None:
    result = ValidationResult()
    assert not result.has_errors
    assert not result.has_warnings
    assert len(result) == 0


def test_has_errors_only_for_error_severity() -> None:
    assert not ValidationResult.of([_issue(Severity.INFO), _issue(Severity.WARNING)]).has_errors
    assert ValidationResult.of([_issue(Severity.INFO), _issue(Severity.ERROR)]).has_errors


def test_filtering_by_severity() -> None:
    info = _issue(Severity.INFO, "I")
    warn = _issue(Severity.WARNING, "W")
    err1 = _issue(Severity.ERROR, "E1")
    err2 = _issue(Severity.ERROR, "E2")
    result = ValidationResult.of([err1, info, warn, err2])
    assert result.by_severity(Severity.ERROR) == (err1, err2)
    assert result.errors == (err1, err2)
    assert result.warnings == (warn,)
    assert result.infos == (info,)
    assert result.at_least(Severity.WARNING) == (err1, warn, err2)
    assert result.at_least(Severity.INFO) == (err1, info, warn, err2)
    assert result.by_code("E2") == (err2,)
    assert result.has_warnings


def test_result_is_immutable_and_combinable() -> None:
    a = _issue(Severity.INFO, "A")
    b = _issue(Severity.ERROR, "B")
    first = ValidationResult.of([a])
    extended = first.with_issue(b)
    assert len(first) == 1  # original unchanged
    assert list(extended) == [a, b]
    merged = first.merged(ValidationResult.of([b]), ValidationResult())
    assert merged.issues == (a, b)
    with pytest.raises(AttributeError):
        first.issues = ()  # type: ignore[misc]


def test_result_rejects_non_issues() -> None:
    with pytest.raises(TypeError, match="ValidationIssue"):
        ValidationResult(("oops",))  # type: ignore[arg-type]
