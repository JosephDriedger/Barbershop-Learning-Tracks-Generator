"""Barbershop voice roles."""

from enum import Enum


class VoiceRole(Enum):
    """The four barbershop voice parts.

    Roles are always assigned explicitly by the caller; nothing in the model infers a
    role from a part name.
    """

    TENOR = "tenor"
    LEAD = "lead"
    BARITONE = "baritone"
    BASS = "bass"

    @property
    def display_name(self) -> str:
        return self.value.capitalize()
