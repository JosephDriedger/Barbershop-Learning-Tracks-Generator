"""The issue-policy registry: every code decided, errors always block, no permissive fallback."""

import re
from dataclasses import replace
from pathlib import Path

import pytest

from barbershop_tracks.core.readiness import (
    ISSUE_POLICY,
    QUARTET_VOCAL,
    TEST_TONE,
    Capability,
    Disposition,
    Domain,
    Feature,
    Override,
    WarningPolicy,
    classify,
)
from barbershop_tracks.models import Severity, ValidationIssue

SRC = Path(__file__).resolve().parents[4] / "src" / "barbershop_tracks"
LITERAL = re.compile(r'"([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)"')


def codes_in_source() -> set[str]:
    found: set[str] = set()
    for path in SRC.rglob("*.py"):
        if path.name == "__init__.py":
            continue  # only ``__all__`` lists of names live there, never issue codes
        if path.name == "policy.py" and path.parent.name == "readiness":
            continue  # the registry itself is not a producer of codes
        if path.relative_to(SRC).parts[:2] == ("core", "midi"):
            # Narrow on purpose: M5 serialization failures are typed ``MidiExportError`` codes
            # ("can this be serialized safely?"), not ValidationIssues ("can capability X use this
            # score?"). Every other module is still scanned, so an unclassified issue still fails.
            continue
        found |= set(LITERAL.findall(path.read_text(encoding="utf-8")))
    return found


def issue(code: str, severity: Severity) -> ValidationIssue:
    return ValidationIssue(severity=severity, code=code, message="m")


def test_every_code_in_the_source_has_a_policy_decision_and_none_is_stale() -> None:
    known = codes_in_source()
    assert known == set(ISSUE_POLICY), {
        "undecided": sorted(known - set(ISSUE_POLICY)),
        "stale": sorted(set(ISSUE_POLICY) - known),
    }


def test_every_warning_code_has_an_explicit_warning_policy() -> None:
    for code, policy in ISSUE_POLICY.items():
        if policy.severity is Severity.WARNING:
            assert policy.warning is not None, code
        else:
            assert policy.warning is None, code


@pytest.mark.parametrize("capability", [QUARTET_VOCAL, TEST_TONE])
def test_a_structural_error_blocks_every_capability(capability: Capability) -> None:
    structural = [
        c
        for c, p in ISSUE_POLICY.items()
        if p.severity is Severity.ERROR and p.domain is Domain.STRUCTURE
    ]
    assert structural
    for code in structural:
        assert classify(issue(code, Severity.ERROR), capability).disposition is Disposition.BLOCKING


def test_a_lyric_domain_error_blocks_only_a_capability_that_uses_lyrics() -> None:
    lyric_errors = [
        c
        for c, p in ISSUE_POLICY.items()
        if p.severity is Severity.ERROR and p.domain is Domain.LYRICS
    ]
    assert {"LYRIC_WORD_UNCLOSED", "LYRIC_ON_REST", "LYRIC_TIE_CONFLICT"} <= set(lyric_errors)
    for code in lyric_errors:
        error = issue(code, Severity.ERROR)
        assert classify(error, QUARTET_VOCAL).disposition is Disposition.BLOCKING
        verdict = classify(error, TEST_TONE)
        assert verdict.disposition is Disposition.INFO, code
        assert "does not use lyrics" in verdict.reason
        assert error.severity is Severity.ERROR  # the source severity is untouched


def test_the_domain_is_registry_data_not_a_naming_convention() -> None:
    # structural codes that merely mention lyrics in their text stay structural; every domain is
    # declared explicitly, and the lyric-domain set contains the parser's lyric errors too
    assert ISSUE_POLICY["UNSUPPORTED_GRACE_NOTE"].domain is Domain.STRUCTURE
    assert ISSUE_POLICY["LYRIC_ON_GRACE_NOTE"].domain is Domain.LYRICS
    assert ISSUE_POLICY["LYRIC_ON_GRACE_NOTE"].origin.value == "parse"
    assert ISSUE_POLICY["LYRIC_WORD_UNCLOSED"].origin.value == "lyrics"


def test_an_unknown_error_fails_safe_and_blocks_every_capability() -> None:
    unknown = issue("A_BRAND_NEW_ERROR", Severity.ERROR)
    for capability in (QUARTET_VOCAL, TEST_TONE):
        assert classify(unknown, capability).disposition is Disposition.BLOCKING


def test_an_unknown_warning_fails_safe_and_blocks() -> None:
    unknown = issue("A_BRAND_NEW_WARNING", Severity.WARNING)
    result = classify(unknown, QUARTET_VOCAL)
    assert result.disposition is Disposition.BLOCKING
    assert "no readiness policy" in result.reason


def test_an_info_issue_stays_info() -> None:
    assert (
        classify(issue("LINE_IGNORED", Severity.INFO), QUARTET_VOCAL).disposition
        is Disposition.INFO
    )


def test_a_known_warning_is_advisory_and_can_differ_by_capability() -> None:
    hygiene = issue("LYRIC_TEXT_WHITESPACE", Severity.WARNING)
    assert classify(hygiene, QUARTET_VOCAL).disposition is Disposition.ADVISORY  # uses lyrics
    assert classify(hygiene, TEST_TONE).disposition is Disposition.INFO  # lyrics are unused
    always = issue("MEASURE_INCOMPLETE", Severity.WARNING)
    assert classify(always, QUARTET_VOCAL).disposition is Disposition.ADVISORY
    assert classify(always, TEST_TONE).disposition is Disposition.ADVISORY


def test_incomplete_measures_and_meter_warnings_are_advisory_not_blocking() -> None:
    for code in ("MEASURE_INCOMPLETE", "METRONOME_WITHOUT_SOUND", "TEMPO_ZERO_UNRESOLVED"):
        assert (
            classify(issue(code, Severity.WARNING), QUARTET_VOCAL).disposition
            is Disposition.ADVISORY
        )


def test_the_navigation_tie_warnings_never_block() -> None:
    for code in ("TIE_BROKEN_BY_REPEAT", "TIE_BROKEN_BY_ENDING", "TIE_BROKEN_BY_DISCONTINUITY"):
        assert (
            classify(issue(code, Severity.WARNING), QUARTET_VOCAL).disposition
            is Disposition.ADVISORY
        )


def test_source_severity_is_never_changed_by_classification() -> None:
    original = issue("LYRIC_TEXT_WHITESPACE", Severity.WARNING)
    classify(original, TEST_TONE)
    assert original.severity is Severity.WARNING  # disposition is a separate concept


def test_a_warning_policy_override_follows_the_capability_features() -> None:
    policy = WarningPolicy(
        Disposition.ADVISORY, overrides=(Override(Feature.TEMPO, True, Disposition.BLOCKING),)
    )
    assert policy.disposition_for(QUARTET_VOCAL) is Disposition.BLOCKING
    assert (
        policy.disposition_for(replace(QUARTET_VOCAL, name="x", tempo_required=False))
        is Disposition.ADVISORY
    )


def test_capability_features_are_derived_from_its_requirements() -> None:
    assert QUARTET_VOCAL.features == {
        Feature.MONOPHONY,
        Feature.INTEGRAL_PITCH,
        Feature.TEMPO,
        Feature.LYRICS_USED,
    }
    assert TEST_TONE.features == {Feature.MONOPHONY, Feature.TEMPO}


def test_a_capability_is_immutable_and_validated() -> None:
    with pytest.raises(ValueError, match="needs a name"):
        Capability(name="")
    with pytest.raises(ValueError, match="lyric source role"):
        Capability(name="x", lyric_source_role=next(iter(QUARTET_VOCAL.required_roles)))
    with pytest.raises(ValueError, match="low <= high"):
        Capability(name="x", midi_range=(10, 1))
    configured = QUARTET_VOCAL.with_lyric_source(next(iter(QUARTET_VOCAL.required_roles)))
    assert configured.lyric_source_role is not None
    assert QUARTET_VOCAL.lyric_source_role is None  # the preset is untouched
