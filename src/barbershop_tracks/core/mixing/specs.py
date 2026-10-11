"""The 13 learning tracks as immutable mix specifications with explicit per-role gains.

Every number that decides how loud a voice is lives in :class:`GainProfile`; nothing else in the
mixer contains a gain. A :class:`MixSpec` carries its four gains explicitly, so a future GUI can
offer presets (other profiles) or arbitrary balances without touching the mixer.

Defaults (see ``docs/m9-mixing.md`` for the rationale): the gains of every default mix add up to
at most 1.0, and the stems are at most full scale, so a default mix cannot clip whatever the stems
contain. No loudness normalisation is applied.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from barbershop_tracks.core.mixing.errors import MixConfigurationError
from barbershop_tracks.core.synthesis import VOICE_ORDER
from barbershop_tracks.models import VoiceRole

MAX_GAIN = 4.0


class MixKind(Enum):
    FULL = "full"
    PREDOMINANT = "predominant"
    SOLO = "solo"
    WITHOUT = "without"


def _gain(value: float, what: str) -> float:
    if not isinstance(value, float | int) or isinstance(value, bool) or not math.isfinite(value):
        raise MixConfigurationError("MIX_GAIN_INVALID", f"{what} must be a finite number")
    if not 0 <= value <= MAX_GAIN:
        raise MixConfigurationError("MIX_GAIN_RANGE", f"{what} = {value} is outside 0..{MAX_GAIN}")
    return float(value)


@dataclass(frozen=True, slots=True)
class GainProfile:
    """Linear gains (1.0 = the stem unchanged) for the four kinds of mix."""

    name: str = "default"
    full_quartet: float = 0.25  # each of the four voices
    predominant_focus: float = 0.5  # the prominent voice
    predominant_others: float = 0.15  # each of the other three
    solo: float = 0.5  # the single voice
    without_each: float = 0.33  # each of the three remaining voices

    def __post_init__(self) -> None:
        if not self.name:
            raise MixConfigurationError("MIX_PROFILE_NAME", "a gain profile needs a name")
        for field_name in (
            "full_quartet",
            "predominant_focus",
            "predominant_others",
            "solo",
            "without_each",
        ):
            _gain(getattr(self, field_name), field_name)
        for field_name in ("full_quartet", "predominant_focus", "solo", "without_each"):
            if getattr(self, field_name) <= 0:
                raise MixConfigurationError("MIX_GAIN_SILENT", f"{field_name} must be above zero")
        if not 0 < self.predominant_others < self.predominant_focus:
            raise MixConfigurationError(
                "MIX_PREDOMINANT_ORDER",
                "predominant_others must be above zero and below predominant_focus",
            )


DEFAULT_PROFILE = GainProfile()

# Named presets a command line or a GUI can offer. All keep every mix's gain sum at or below 1.0
# for full-scale stems, except where noted in docs/m9-mixing.md.
PRESETS: dict[str, GainProfile] = {
    "default": DEFAULT_PROFILE,
    "strong-focus": GainProfile(
        name="strong-focus", predominant_focus=0.6, predominant_others=0.1, solo=0.6
    ),
    "gentle-focus": GainProfile(
        name="gentle-focus", predominant_focus=0.4, predominant_others=0.18, solo=0.5
    ),
}

_PROFILE_FIELDS = (
    "full_quartet",
    "predominant_focus",
    "predominant_others",
    "solo",
    "without_each",
)


def profile_from_dict(raw: object) -> GainProfile:
    """A profile from a JSON object: ``name`` plus any of the five gains (others stay default)."""
    if not isinstance(raw, dict):
        raise MixConfigurationError("MIX_PROFILE_FILE", "a gain profile must be a JSON object")
    unknown = sorted(set(raw) - {"name", *_PROFILE_FIELDS})
    if unknown:
        raise MixConfigurationError("MIX_PROFILE_FILE", f"unknown gain profile field(s) {unknown}")
    values = {k: raw[k] for k in _PROFILE_FIELDS if k in raw}
    name = raw.get("name", "custom")
    if not isinstance(name, str):
        raise MixConfigurationError("MIX_PROFILE_NAME", "the profile name must be text")
    return GainProfile(name=name, **values)


@dataclass(frozen=True, slots=True)
class MixSpec:
    number: int
    identifier: str
    label: str
    kind: MixKind
    focus: VoiceRole | None
    gains: tuple[float, float, float, float]  # in VOICE_ORDER: tenor, lead, baritone, bass

    def __post_init__(self) -> None:
        if self.number < 1:
            raise MixConfigurationError("MIX_NUMBER", f"mix number {self.number} must be positive")
        if not self.identifier or not self.label:
            raise MixConfigurationError("MIX_NAME", "a mix needs an identifier and a label")
        if len(self.gains) != len(VOICE_ORDER):
            raise MixConfigurationError("MIX_GAIN_COUNT", "a mix needs one gain per voice")
        for role, gain in zip(VOICE_ORDER, self.gains, strict=True):
            _gain(gain, f"{self.identifier} gain for {role.value}")
        if not any(g > 0 for g in self.gains):
            raise MixConfigurationError("MIX_EMPTY", f"{self.identifier} has no audible voice")

    @property
    def filename_stem(self) -> str:
        return f"{self.number:02d}_{self.label.replace(' ', '_')}"

    def gain(self, role: VoiceRole) -> float:
        return self.gains[VOICE_ORDER.index(role)]

    @property
    def voices(self) -> tuple[VoiceRole, ...]:
        return tuple(r for r, g in zip(VOICE_ORDER, self.gains, strict=True) if g > 0)

    @property
    def worst_case_sum(self) -> float:
        """The largest possible output peak for stems that are at most full scale."""
        return sum(self.gains)


def standard_mix_specs(profile: GainProfile = DEFAULT_PROFILE) -> tuple[MixSpec, ...]:
    """The 13 tracks, always in this order: full, 4 predominant, 4 solo, 4 without."""
    specs: list[MixSpec] = [
        MixSpec(1, "full_quartet", "Full Quartet", MixKind.FULL, None, (profile.full_quartet,) * 4)
    ]
    number = 2
    for kind in (MixKind.PREDOMINANT, MixKind.SOLO, MixKind.WITHOUT):
        for role in VOICE_ORDER:
            name = role.display_name
            if kind is MixKind.PREDOMINANT:
                gains = tuple(
                    profile.predominant_focus if r is role else profile.predominant_others
                    for r in VOICE_ORDER
                )
                label, identifier = f"{name} Predominant", f"{role.value}_predominant"
            elif kind is MixKind.SOLO:
                gains = tuple(profile.solo if r is role else 0.0 for r in VOICE_ORDER)
                label, identifier = f"{name} Solo", f"{role.value}_solo"
            else:
                gains = tuple(0.0 if r is role else profile.without_each for r in VOICE_ORDER)
                label, identifier = f"Without {name}", f"without_{role.value}"
            specs.append(
                MixSpec(number, identifier, label, kind, role, _four(gains))  # explicit gains
            )
            number += 1
    validate_spec_set(specs)
    return tuple(specs)


def _four(gains: Sequence[float]) -> tuple[float, float, float, float]:
    a, b, c, d = gains
    return (a, b, c, d)


def validate_spec_set(specs: Sequence[MixSpec]) -> None:
    """Numbers, identifiers and filenames must each be unique (filenames compared ignoring case)."""
    if not specs:
        raise MixConfigurationError("MIX_SET_EMPTY", "no mixes were specified")
    for what, values in (
        ("number", [s.number for s in specs]),
        ("identifier", [s.identifier for s in specs]),
        ("filename", [s.filename_stem.lower() for s in specs]),
    ):
        if len(set(values)) != len(values):
            raise MixConfigurationError(
                "MIX_NAME_COLLISION", f"two mixes share the same {what}: {sorted(values)}"
            )
