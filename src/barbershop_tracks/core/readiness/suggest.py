"""Read-only role suggestions for source lines. They are never applied.

A suggestion carries its *basis* and is always unconfirmed: readiness uses only the assignments
the caller states explicitly. Two bases exist:

* ``NAME``: the part name contains exactly one voice word (tenor, lead, baritone/bari, bass) and no
  other line suggests the same role from its name;
* ``ORDER``: exactly four lines, none with a name suggestion, listed top to bottom as Tenor, Lead,
  Baritone, Bass (the usual TTBB score order). A weaker guess, flagged as such.

* ``LAYOUT``: the usual barbershop score, two staves with two voices each (the Tenor/Lead staff
  first, the Baritone/Bass staff second). On each staff the upper voice (the lower voice number:
  stems up) is the Tenor or Baritone and the other is the Lead or Bass. The voice, never the
  pitch, decides: the two cross often. Used only when no part name speaks, and only when each staff
  has exactly two real voices (a stray fragment of a few notes, as music recognition leaves
  behind, is left without a suggestion).

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


_STAVES = (
    (VoiceRole.TENOR, VoiceRole.LEAD, "Tenor/Lead"),
    (VoiceRole.BARITONE, VoiceRole.BASS, "Baritone/Bass"),
)
_STRAY_SHARE = 4  # a third voice with under 1/4 of the notes of the smaller real voice is a stray


class SuggestionBasis(Enum):
    NAME = "name"
    LAYOUT = "layout"
    ORDER = "order"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class StaffPosition:
    """Where a line sits in the two-staff barbershop layout."""

    role: VoiceRole | None  # None for a stray fragment: nobody sings it
    staff_label: str  # "Tenor/Lead" or "Baritone/Bass"
    upper: bool | None  # None for a stray fragment
    voice: str = ""

    @property
    def text(self) -> str:
        if self.upper is None:
            return f"{self.staff_label} staff, extra voice {self.voice}"
        return f"{self.staff_label} staff, {'upper' if self.upper else 'lower'} voice"


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


def _voice_of(part: Part) -> str:
    return part.source_line.voice if part.source_line is not None else ""


def _voice_key(part: Part) -> tuple[int, str]:
    voice = part.source_line.voice if part.source_line is not None else ""
    return (int(voice), voice) if voice.isdigit() else (1 << 30, voice)


def shared_staff_positions(parts: Sequence[Part]) -> dict[str, StaffPosition]:
    """Line id to position when ``parts`` are the two-staff, two-voice layout, else empty."""
    groups: dict[tuple[str, int], list[Part]] = {}
    for part in parts:
        if part.source_line is None:
            return {}
        if part.sounding_notes:
            link = part.source_line
            groups.setdefault((link.part_id, link.staff), []).append(part)
    if len(groups) != len(_STAVES):
        return {}
    found: dict[str, StaffPosition] = {}
    for (upper_role, lower_role, label), lines in zip(_STAVES, groups.values(), strict=True):
        by_size = sorted(lines, key=lambda p: len(p.sounding_notes), reverse=True)
        if len(by_size) < 2:
            return {}
        if len(by_size) > 2 and (
            len(by_size[2].sounding_notes) * _STRAY_SHARE >= len(by_size[1].sounding_notes)
        ):
            return {}  # a third real voice: which two sing is not for BLT to guess
        upper, lower = sorted(by_size[:2], key=_voice_key)
        found[upper.part_id] = StaffPosition(upper_role, label, True, _voice_of(upper))
        found[lower.part_id] = StaffPosition(lower_role, label, False, _voice_of(lower))
        for stray in by_size[2:]:
            found[stray.part_id] = StaffPosition(None, label, None, _voice_of(stray))
    return found


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
    layout = {} if any_name else shared_staff_positions(parts)
    if layout:
        return tuple(
            RoleSuggestion(
                part.part_id,
                position.role,
                SuggestionBasis.LAYOUT,
                f"the {position.text} (unconfirmed guess from the staff layout)",
            )
            if (position := layout.get(part.part_id)) is not None and position.role is not None
            else existing
            for part, existing in zip(parts, suggestions, strict=True)
        )
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
