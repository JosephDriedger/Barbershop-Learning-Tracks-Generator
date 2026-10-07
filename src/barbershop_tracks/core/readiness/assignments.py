"""Explicit source-line to role assignments.

Roles are never inferred. The caller supplies exact source-line identifiers (``P1/s1/v1``) and
roles; raw entries are kept so that mistakes (an unknown line, a role given twice, one line
given two roles, a line both assigned and ignored) become *findings* in the readiness report
instead of exceptions. There is no fuzzy matching.
"""

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from barbershop_tracks.models import VoiceRole


@dataclass(frozen=True, slots=True)
class RoleAssignments:
    """``entries`` are ``(role, line_id)`` pairs as given; ``ignored`` lines are left out."""

    entries: tuple[tuple[VoiceRole, str], ...] = ()
    ignored: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        entries = tuple((role, line) for role, line in self.entries)
        for role, line in entries:
            if not isinstance(role, VoiceRole):
                raise TypeError("an assignment needs a VoiceRole")
            if not isinstance(line, str) or not line:
                raise TypeError("a line identifier must be a non-empty string")
        object.__setattr__(self, "entries", entries)
        object.__setattr__(self, "ignored", tuple(self.ignored))

    @classmethod
    def of(
        cls, mapping: Mapping[VoiceRole, str], *, ignored: Iterable[str] = ()
    ) -> "RoleAssignments":
        """Assignments from a role -> line mapping (a role can then appear only once)."""
        return cls(entries=tuple(mapping.items()), ignored=tuple(ignored))

    def lines_for(self, role: VoiceRole) -> tuple[str, ...]:
        return tuple(line for assigned, line in self.entries if assigned is role)

    def roles_for(self, line: str) -> tuple[VoiceRole, ...]:
        return tuple(role for role, assigned in self.entries if assigned == line)

    def role_of(self, line: str) -> VoiceRole | None:
        """The role of ``line`` (the first one if it was given several, which is reported)."""
        roles = self.roles_for(line)
        return roles[0] if roles else None

    @property
    def duplicate_roles(self) -> tuple[VoiceRole, ...]:
        counts = Counter(role for role, _ in self.entries)
        return tuple(role for role, count in counts.items() if count > 1)

    @property
    def lines_assigned_twice(self) -> tuple[str, ...]:
        counts = Counter(line for _, line in self.entries)
        return tuple(line for line, count in counts.items() if count > 1)
