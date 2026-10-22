"""Which source line sings which voice: the user's explicit choices, and nothing guessed.

A line is *chosen* for exactly one of Tenor, Lead, Baritone, Bass, or *ignored* on purpose, or
still *undecided*. Two lines can never take the same voice. Suggestions (from the part names) are
only ever proposals: applying them marks the rows "suggested" and generation stays blocked until
the user confirms them or changes the rows. Pure Python; the widgets just reflect this state.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum

from barbershop_tracks.core.readiness import RoleAssignments
from barbershop_tracks.core.readiness.lines import LineInfo
from barbershop_tracks.core.synthesis import VOICE_ORDER
from barbershop_tracks.models import VoiceRole


class Ignore(Enum):
    IGNORE = "ignore"


Choice = VoiceRole | Ignore | None


@dataclass
class AssignmentState:
    lines: tuple[LineInfo, ...]
    choices: dict[str, Choice] = field(default_factory=dict)
    suggested: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        for info in self.lines:
            self.choices.setdefault(info.line_id, None)

    # --- editing ---------------------------------------------------------------------------

    def holder(self, role: VoiceRole) -> str | None:
        return next((line for line, choice in self.choices.items() if choice is role), None)

    def can_choose(self, line_id: str, choice: Choice) -> bool:
        if line_id not in self.choices:
            return False
        if isinstance(choice, VoiceRole):
            holder = self.holder(choice)
            return holder is None or holder == line_id
        return True

    def set_choice(self, line_id: str, choice: Choice) -> bool:
        """Set a line's choice; returns False (and changes nothing) if the voice is taken."""
        if not self.can_choose(line_id, choice):
            return False
        self.choices[line_id] = choice
        self.suggested.discard(line_id)  # touching a row confirms it
        return True

    def suggest(self) -> int:
        """Apply the name-based suggestions to rows that are still undecided; returns how many."""
        applied = 0
        for info in self.lines:
            role = info.suggestion.role
            if role is None or self.choices.get(info.line_id) is not None:
                continue
            if self.holder(role) is None:
                self.choices[info.line_id] = role
                self.suggested.add(info.line_id)
                applied += 1
        return applied

    def confirm_suggestions(self) -> None:
        self.suggested.clear()

    def clear(self) -> None:
        for line in self.choices:
            self.choices[line] = None
        self.suggested.clear()

    # --- reading ---------------------------------------------------------------------------

    def role_of(self, line_id: str) -> VoiceRole | None:
        choice = self.choices.get(line_id)
        return choice if isinstance(choice, VoiceRole) else None

    def missing_roles(self) -> list[VoiceRole]:
        return [r for r in VOICE_ORDER if self.holder(r) is None]

    def undecided(self) -> list[LineInfo]:
        return [i for i in self.lines if self.choices.get(i.line_id) is None]

    def problems(self) -> list[str]:
        """Plain-language reasons the mapping is not complete yet (empty when it is)."""
        out = []
        if self.suggested:
            out.append("Please confirm the suggested voices (or choose them yourself).")
        missing = self.missing_roles()
        if missing:
            names = ", ".join(r.display_name for r in missing)
            out.append(f"Choose a part for: {names}.")
        musical = [i for i in self.undecided() if i.sounding_attacks > 0]
        if not missing and musical:
            names = ", ".join(i.display_name for i in musical)
            out.append(f"Say what to do with: {names} (choose a voice, or ignore it).")
        return out

    @property
    def complete(self) -> bool:
        return not self.problems()

    def to_role_assignments(self) -> RoleAssignments:
        entries = tuple(
            (role, line) for role in VOICE_ORDER if (line := self.holder(role)) is not None
        )
        ignored = tuple(line for line, choice in self.choices.items() if choice is Ignore.IGNORE)
        return RoleAssignments(entries=entries, ignored=ignored)

    def snapshot(self) -> dict[str, Choice]:
        return dict(self.choices)

    def restore(self, saved: dict[str, Choice], valid: Iterable[str]) -> None:
        """Re-apply earlier choices for lines that still exist (same score, edited again)."""
        known = set(valid)
        for line, choice in saved.items():
            if line in known and self.can_choose(line, choice):
                self.choices[line] = choice
