"""Readiness findings and the report. Pure, frozen, derived.

A finding *wraps* a ``ValidationIssue``; the issue is never changed. Source severity (what the
producing layer said) and readiness disposition (what that means for a capability) are different
things and both are kept.
"""

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from fractions import Fraction

from barbershop_tracks.core.readiness.capability import Capability
from barbershop_tracks.models import PerformanceLocation, ValidationIssue, VoiceRole


class Disposition(Enum):
    """What a finding means for generation with a given capability."""

    BLOCKING = "blocking"
    ADVISORY = "advisory"
    INFO = "info"


class FindingOrigin(Enum):
    """The layer that produced the wrapped issue."""

    PARSE = "parse"
    PERFORMANCE = "performance"
    LYRICS = "lyrics"
    READINESS = "readiness"


@dataclass(frozen=True, slots=True)
class ReadinessFinding:
    """An issue plus its disposition, origin, role and performance location.

    ``superseded_by`` names a stronger readiness code that explains the same fact (so a renderer may
    fold the lower-layer finding); the wrapped issue keeps its own severity regardless.
    """

    issue: ValidationIssue
    origin: FindingOrigin
    disposition: Disposition
    role: VoiceRole | None = None
    line_id: str | None = None
    location: PerformanceLocation | None = None
    superseded_by: str | None = None

    @property
    def code(self) -> str:
        return self.issue.code


@dataclass(frozen=True, slots=True, kw_only=True)
class LineSummary:
    """Facts about one performed line, for a report or a UI."""

    line_id: str
    role: VoiceRole | None
    ignored: bool
    sounding_attacks: int
    first_start: Fraction | None
    end: Fraction | None


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    """The outcome of assessing a performed score for one capability.

    Everything is derived from ``findings``: there is no stored ``ready`` flag that could disagree
    with them.
    """

    capability: Capability
    findings: tuple[ReadinessFinding, ...] = ()
    lines: tuple[LineSummary, ...] = ()
    performed_length: Fraction = field(default=Fraction(0))

    def _with(self, disposition: Disposition) -> tuple[ReadinessFinding, ...]:
        return tuple(f for f in self.findings if f.disposition is disposition)

    @property
    def blocking(self) -> tuple[ReadinessFinding, ...]:
        return self._with(Disposition.BLOCKING)

    @property
    def advisory(self) -> tuple[ReadinessFinding, ...]:
        return self._with(Disposition.ADVISORY)

    @property
    def info(self) -> tuple[ReadinessFinding, ...]:
        return self._with(Disposition.INFO)

    @property
    def ready(self) -> bool:
        """True if nothing blocks generation with this capability."""
        return not self.blocking

    @property
    def clean(self) -> bool:
        """True if there is neither a blocking nor an advisory finding (what ``--strict`` asks)."""
        return not self.blocking and not self.advisory

    @property
    def counts(self) -> dict[Disposition, int]:
        counted = Counter(f.disposition for f in self.findings)
        return {disposition: counted.get(disposition, 0) for disposition in Disposition}

    def by_code(self, code: str) -> tuple[ReadinessFinding, ...]:
        return tuple(f for f in self.findings if f.code == code)

    def by_role(self, role: VoiceRole) -> tuple[ReadinessFinding, ...]:
        return tuple(f for f in self.findings if f.role is role)
