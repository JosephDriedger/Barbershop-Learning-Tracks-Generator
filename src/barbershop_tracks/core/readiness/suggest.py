"""Read-only role suggestions for source lines. They are never applied.

A suggestion carries its *basis* and is always unconfirmed: readiness uses only the assignments
the caller states explicitly. Two bases exist:

* ``NAME``: the part name contains exactly one voice word (tenor, lead, baritone/bari, bass) and no
  other line suggests the same role from its name;
* ``ORDER``: exactly four lines, none with a name suggestion, listed top to bottom as Tenor, Lead,
  Baritone, Bass (the usual TTBB score order). A weaker guess, flagged as such.

Anything else (no name match, several voice words, the same role named twice) gets no suggestion.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from barbershop_tracks.models import Part, VoiceRole

_WORDS = {
    "tenor": VoiceRole.TENOR,
    "lead": VoiceRole.LEAD,
    "baritone": VoiceRole.BARITONE,
    "bari": VoiceRole.BARITONE,
    "bass": VoiceRole.BASS,
}
_ORDER = (VoiceRole.TENOR, VoiceRole.LEAD, VoiceRole.BARITONE, VoiceRole.BASS)


class SuggestionBasis(Enum):
    NAME = "name"
    ORDER = "order"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class RoleSuggestion:
    """A suggested role for one line. ``confirmed`` is always False: a suggestion is not an
    assignment."""

    line_id: str
    role: VoiceRole | None
    basis: SuggestionBasis
    note: str
    confirmed: bool = False


def _roles_in(name: str) -> set[VoiceRole]:
    words = re.findall(r"[a-z]+", name.lower())
    return {_WORDS[word] for word in words if word in _WORDS}


def suggest_roles(parts: Sequence[Part]) -> tuple[RoleSuggestion, ...]:
    """Suggestions for ``parts`` (the source lines), in the same order. Pure and deterministic."""
    named: list[VoiceRole | None] = []
    for part in parts:
        found: set[VoiceRole] = set()
        for text in (part.source_name, part.name):
            if text:
                found |= _roles_in(text)
        named.append(next(iter(found)) if len(found) == 1 else None)
    counts = {role: named.count(role) for role in set(named) if role is not None}
    suggestions: list[RoleSuggestion] = []
    any_name = False
    for part, role in zip(parts, named, strict=True):
        if role is not None and counts[role] == 1:
            any_name = True
            suggestions.append(
                RoleSuggestion(
                    part.part_id, role, SuggestionBasis.NAME, f"the part name says {role.value}"
                )
            )
        elif role is not None:
            suggestions.append(
                RoleSuggestion(
                    part.part_id,
                    None,
                    SuggestionBasis.NONE,
                    f"{counts[role]} lines are named {role.value}; no suggestion",
                )
            )
        else:
            suggestions.append(RoleSuggestion(part.part_id, None, SuggestionBasis.NONE, ""))
    if not any_name and len(parts) == 4 and all(r is None for r in named):
        return tuple(
            RoleSuggestion(
                part.part_id,
                role,
                SuggestionBasis.ORDER,
                f"line {index + 1} of 4 in score order (unconfirmed guess)",
            )
            for index, (part, role) in enumerate(zip(parts, _ORDER, strict=True))
        )
    return tuple(suggestions)
