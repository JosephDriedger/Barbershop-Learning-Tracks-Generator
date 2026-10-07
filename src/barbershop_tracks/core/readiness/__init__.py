"""Generation-readiness validation: can a capability safely generate from a performed score?

Pure and immutable. M3 answered what the score contains and how it is performed; this layer
answers whether a given capability can generate from it. Lower-layer issues are wrapped, never
changed; the only new checks are the ones generation needs (roles, monophony, pitch fitness, tempo,
timeline). No Qt, no I/O, no formatting.
"""

from barbershop_tracks.core.readiness.assess import assess_readiness
from barbershop_tracks.core.readiness.assignments import RoleAssignments
from barbershop_tracks.core.readiness.capability import (
    CAPABILITIES,
    DEFAULT_TYPICAL_RANGES,
    QUARTET_VOCAL,
    TEST_TONE,
    Capability,
    Feature,
    LyricPolicy,
)
from barbershop_tracks.core.readiness.findings import (
    Disposition,
    FindingOrigin,
    LineSummary,
    ReadinessFinding,
    ReadinessReport,
)
from barbershop_tracks.core.readiness.policy import (
    ISSUE_POLICY,
    CodePolicy,
    Domain,
    Override,
    WarningPolicy,
    classify,
)

__all__ = [
    "CAPABILITIES",
    "DEFAULT_TYPICAL_RANGES",
    "ISSUE_POLICY",
    "QUARTET_VOCAL",
    "TEST_TONE",
    "Capability",
    "CodePolicy",
    "Disposition",
    "Domain",
    "Feature",
    "FindingOrigin",
    "LineSummary",
    "LyricPolicy",
    "Override",
    "ReadinessFinding",
    "ReadinessReport",
    "RoleAssignments",
    "WarningPolicy",
    "assess_readiness",
    "classify",
]
