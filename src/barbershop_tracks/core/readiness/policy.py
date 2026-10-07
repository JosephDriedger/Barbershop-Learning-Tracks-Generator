"""The issue-policy registry: every issue code the code base can emit, and what it means.

Source severity (what the producing layer says) and readiness disposition (what that means for a
capability) are separate. The rules are small and fixed:

* a structural **ERROR** (parsing, timeline, pitch, repeat/ending planning, ties, navigation)
  blocks every capability; an ERROR in a *domain* (today: lyrics) blocks the capabilities that
  consume that domain and is INFO for the others. The wrapped issue keeps severity ERROR either
  way: severity says how serious the diagnostic is, disposition says whether this capability may
  generate;
* a **WARNING** gets its disposition from its ``WarningPolicy``: a default, optionally overridden
  by a capability *feature* (for example lyric hygiene drops to INFO when a capability does not use
  lyrics);
* an **INFO** stays INFO;
* a WARNING with no policy fails safe and **blocks**. There is no "unknown warnings are allowed"
  fallback; a test makes every new code get an explicit decision here.

This module is data plus one small function. It contains no checks.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum

from barbershop_tracks.core.readiness.capability import Capability, Feature
from barbershop_tracks.core.readiness.findings import Disposition, FindingOrigin
from barbershop_tracks.models import Severity, ValidationIssue


@dataclass(frozen=True, slots=True)
class Override:
    """Replace the disposition when ``(feature in capability.features) == active``."""

    feature: Feature
    active: bool
    disposition: Disposition


@dataclass(frozen=True, slots=True)
class WarningPolicy:
    default: Disposition
    overrides: tuple[Override, ...] = ()
    reason: str = ""

    def disposition_for(self, capability: Capability) -> Disposition:
        features = capability.features
        for override in self.overrides:
            if (override.feature in features) == override.active:
                return override.disposition
        return self.default


class Domain(Enum):
    """The kind of fact an issue is about, as registry data (never inferred from a code's name).

    A ``STRUCTURE`` error means we cannot trust which notes are performed, when, or how the score
    is traversed. A ``LYRICS`` error means the lyric interpretation is unusable; the notes may be
    perfectly trustworthy.
    """

    STRUCTURE = "structure"
    LYRICS = "lyrics"


@dataclass(frozen=True, slots=True)
class CodePolicy:
    """One known issue code: origin layer, domain, severity, and (for warnings) its policy."""

    origin: FindingOrigin
    severity: Severity
    warning: WarningPolicy | None = None
    domain: Domain = Domain.STRUCTURE


_ADVISORY = WarningPolicy(Disposition.ADVISORY, reason="shown prominently, does not block")
_LYRIC_HYGIENE = WarningPolicy(
    Disposition.ADVISORY,
    overrides=(Override(Feature.LYRICS_USED, False, Disposition.INFO),),
    reason="matters only to a capability that uses lyrics; text is never rewritten",
)


def _errors(
    origin: FindingOrigin, *codes: str, domain: Domain = Domain.STRUCTURE
) -> dict[str, CodePolicy]:
    return {code: CodePolicy(origin, Severity.ERROR, domain=domain) for code in codes}


def _warnings(origin: FindingOrigin, policy: WarningPolicy, *codes: str) -> dict[str, CodePolicy]:
    domain = Domain.LYRICS if policy is _LYRIC_HYGIENE else Domain.STRUCTURE
    return {code: CodePolicy(origin, Severity.WARNING, policy, domain) for code in codes}


_P, _F, _L, _R = (
    FindingOrigin.PARSE,
    FindingOrigin.PERFORMANCE,
    FindingOrigin.LYRICS,
    FindingOrigin.READINESS,
)

ISSUE_POLICY: Mapping[str, CodePolicy] = {
    # --- parse errors ---
    **_errors(
        _P,
        "BACKUP_BEFORE_MEASURE_START",
        "CHORD_WITHOUT_PRECEDING_NOTE",
        "DIVISIONS_INVALID",
        "DIVISIONS_MISSING",
        "ENDING_BARLINE_PLACEMENT",
        "ENDING_MID_MEASURE",
        "ENDING_NUMBER_INVALID",
        "ENDING_NUMBER_MISMATCH",
        "ENDING_NUMBER_UNSPECIFIED",
        "ENDING_OVERLAP",
        "ENDING_STOP_WITHOUT_START",
        "ENDING_TYPE_INVALID",
        "ENDING_UNCLOSED",
        "MEASURE_DURATION_MISMATCH",
        "MEASURE_LENGTH_MISMATCH_ACROSS_PARTS",
        "MOVE_DURATION_INVALID",
        "NOTE_DURATION_INVALID",
        "NOTE_DURATION_MISSING",
        "NOTE_WITHOUT_PITCH",
        "NO_PARTS",
        "PART_ID_INVALID",
        "PART_MEASURE_COUNT_MISMATCH",
        "PART_NOT_IN_PART_LIST",
        "PITCH_INVALID",
        "PITCH_OUT_OF_RANGE",
        "REPEAT_AFTER_JUMP_UNSUPPORTED",
        "REPEAT_BARLINE_PLACEMENT",
        "REPEAT_DIRECTION_INVALID",
        "REPEAT_MID_MEASURE",
        "REPEAT_STRUCTURE_CONFLICT",
        "REPEAT_TIMES_EXCESSIVE",
        "REPEAT_TIMES_INVALID",
        "STAFF_INVALID",
        "TEMPO_CONFLICT",
        "TEMPO_INVALID",
        "TEMPO_OFFSET_OUT_OF_MEASURE",
        "TIED_WITHOUT_TIE",
        "TIE_TIED_MISMATCH",
        "TIE_TYPE_INVALID",
        "TIME_SIGNATURE_CHANGE_MID_MEASURE",
        "TIME_SIGNATURE_CONFLICT",
        "TIME_SIGNATURE_MISSING",
        "TIME_SIGNATURE_UNSUPPORTED",
        "TRANSPOSE_DOUBLE_UNSUPPORTED",
        "TRANSPOSE_INVALID",
        "TRANSPOSE_NOT_SPELLABLE",
        "UNSUPPORTED_GRACE_NOTE",
        "UNSUPPORTED_JUMP",
        "UNSUPPORTED_UNPITCHED_NOTE",
        "VOICE_MISSING",
    ),
    # --- parse errors in the lyric domain (the notes themselves are still trustworthy) ---
    **_errors(
        _P,
        "LYRIC_DUPLICATE_VERSE",
        "LYRIC_EXTEND_TYPE_INVALID",
        "LYRIC_NUMBER_INVALID",
        "LYRIC_ON_CUE_NOTE",
        "LYRIC_ON_GRACE_NOTE",
        "LYRIC_ON_REST",
        "LYRIC_ON_UNPITCHED_NOTE",
        "LYRIC_TEXT_STRUCTURE_UNSUPPORTED",
        "LYRIC_TIME_ONLY_UNSUPPORTED",
        domain=Domain.LYRICS,
    ),
    # --- performance errors (repeat/ending planning, tie merging, expansion) ---
    **_errors(
        _F,
        "ENDING_PASS_DUPLICATE",
        "ENDING_PASS_MISSING",
        "ENDING_STRUCTURE_UNSUPPORTED",
        "ENDING_WITHOUT_REPEAT",
        "NOTE_OUTSIDE_MEASURES",
        "REPEAT_EXPANSION_TOO_LARGE",
        "REPEAT_NESTED_UNSUPPORTED",
        "REPEAT_START_AMBIGUOUS",
        "REPEAT_TIMES_ENDINGS_CONFLICT",
        "TIE_AMBIGUOUS",
        "TIE_PITCH_MISMATCH",
        "TIE_UNMATCHED_START",
        "TIE_UNMATCHED_STOP",
    ),
    # --- lyric-analysis errors ---
    **_errors(
        _L,
        "LYRIC_EXTEND_SEQUENCE_INVALID",
        "LYRIC_EXTEND_WITHOUT_START",
        "LYRIC_SIMULTANEOUS_ATTACKS",
        "LYRIC_TIE_CONFLICT",
        "LYRIC_VERSE_NOT_FOUND",
        "LYRIC_WORD_AMBIGUOUS",
        "LYRIC_WORD_UNCLOSED",
        "LYRIC_WORD_UNOPENED",
        domain=Domain.LYRICS,
    ),
    # --- warnings that are advisory for every capability ---
    **_warnings(
        _P,
        _ADVISORY,
        "CLEF_INVALID",
        "CUE_NOTE_SKIPPED",
        "DURATION_TYPE_MISMATCH",
        "MEASURE_INCOMPLETE",
        "MEASURE_NUMBER_NONNUMERIC",
        "METRONOME_WITHOUT_SOUND",
        "REPEAT_TIMES_IGNORED",
        "REPEAT_TIMES_ONE",
        "TEMPO_ZERO_UNRESOLVED",
        "TIE_WITHOUT_TIED",
    ),
    **_warnings(
        _F,
        _ADVISORY,
        "REPEAT_FORWARD_UNUSED",
        "TIE_BROKEN_BY_DISCONTINUITY",
        "TIE_BROKEN_BY_ENDING",
        "TIE_BROKEN_BY_REPEAT",
    ),
    # --- lyric warnings: advisory, INFO when the capability does not use lyrics ---
    **_warnings(_P, _LYRIC_HYGIENE, "LYRIC_EMPTY"),
    **_warnings(
        _L,
        _LYRIC_HYGIENE,
        "LYRIC_ELIDED",
        "LYRIC_LINE_EMPTY",
        "LYRIC_MELISMA_INTERRUPTED",
        "LYRIC_MELISMA_UNCLOSED",
        "LYRIC_MISSING_SUMMARY",
        "LYRIC_MULTIPLE_VERSES",
        "LYRIC_SYLLABIC_MISSING",
        "LYRIC_TEXT_INNER_SPACE",
        "LYRIC_TEXT_RESERVED_CHARACTERS",
        "LYRIC_TEXT_TRAILING_HYPHEN",
        "LYRIC_TEXT_WHITESPACE",
        "LYRIC_TIE_REPEATED",
        "LYRIC_VERSE_MIXED_NUMBERING",
    ),
    # --- readiness's own findings ---
    **_errors(
        _R,
        "EVENT_OUTSIDE_TIMELINE",
        "IGNORED_LINE_UNKNOWN",
        "LINE_ASSIGNED_AND_IGNORED",
        "LINE_ASSIGNED_TWICE",
        "LINE_OVERLAPPING_NOTES",
        "LINE_SIMULTANEOUS_NOTES",
        "LINE_UNASSIGNED",
        "NO_PERFORMANCE",
        "PITCH_NOT_INTEGRAL",
        "PITCH_OUT_OF_MIDI_RANGE",
        "ROLE_DUPLICATE",
        "ROLE_LINE_EMPTY",
        "ROLE_LINE_UNKNOWN",
        "ROLE_MISSING",
        "SONG_EMPTY",
        "TEMPO_INITIAL_MISSING",
        "TEMPO_MISSING",
    ),
    **_warnings(_R, _ADVISORY, "VOICE_RANGE_UNUSUAL"),
    "LINE_IGNORED": CodePolicy(_R, Severity.INFO),
}


@dataclass(frozen=True, slots=True)
class Classification:
    """The result of classifying one issue: its disposition and why."""

    disposition: Disposition
    reason: str = field(default="")


def classify(issue: ValidationIssue, capability: Capability) -> Classification:
    """The readiness disposition of ``issue`` for ``capability``.

    * a structural ERROR blocks; an unknown ERROR blocks (fail safe);
    * a lyric-domain ERROR blocks only a capability that uses lyrics, otherwise it is INFO (it has
      no effect on what that capability generates; the issue itself stays severity ERROR);
    * INFO stays INFO;
    * a WARNING uses its registered policy and, if it has none, blocks (fail safe).
    """
    policy = ISSUE_POLICY.get(issue.code)
    if issue.severity is Severity.ERROR:
        if (
            policy is not None
            and policy.domain is Domain.LYRICS
            and Feature.LYRICS_USED not in capability.features
        ):
            return Classification(
                Disposition.INFO,
                f"a lyric error, but {capability.name} does not use lyrics, so it cannot "
                "affect what is generated",
            )
        return Classification(Disposition.BLOCKING, "a structural error blocks generation")
    if issue.severity is Severity.INFO:
        return Classification(Disposition.INFO)
    if policy is None or policy.warning is None:
        return Classification(
            Disposition.BLOCKING,
            f"the warning {issue.code} has no readiness policy, so it blocks (fail safe)",
        )
    return Classification(policy.warning.disposition_for(capability), policy.warning.reason)
