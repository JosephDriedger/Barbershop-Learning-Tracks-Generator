"""Mix description data structures. No audio processing happens here."""

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from fractions import Fraction
from types import MappingProxyType

from barbershop_tracks.models.timing import to_fraction
from barbershop_tracks.models.voice import VoiceRole


class TrackKind(Enum):
    """The kinds of learning track produced for a song."""

    FULL = "full"
    PREDOMINANT = "predominant"
    SOLO = "solo"
    MINUS = "minus"


def _require_finite(value: float, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")


def _require_pan(value: float, name: str) -> None:
    _require_finite(value, name)
    if not -1.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between -1 (left) and 1 (right)")


@dataclass(frozen=True, slots=True, kw_only=True)
class MixProfile:
    """Gains (dB) for predominant mixes, plus optional per-voice panning.

    Defaults: target part 0 dB, the other three parts -12 dB, everything centered.
    ``panning`` maps a role to a position in [-1, 1]; roles not listed are centered.
    """

    target_gain_db: float = 0.0
    background_gain_db: float = -12.0
    panning: Mapping[VoiceRole, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_finite(self.target_gain_db, "target_gain_db")
        _require_finite(self.background_gain_db, "background_gain_db")
        for role, pan in self.panning.items():
            if not isinstance(role, VoiceRole):
                raise TypeError("panning keys must be VoiceRole values")
            _require_pan(pan, f"panning[{role.name}]")
        object.__setattr__(self, "panning", MappingProxyType(dict(self.panning)))


@dataclass(frozen=True, slots=True, kw_only=True)
class StemMix:
    """One stem's contribution to a track: which voice, at what gain, and where."""

    role: VoiceRole
    gain_db: float = 0.0
    pan: float | None = None  # None = centered

    def __post_init__(self) -> None:
        if not isinstance(self.role, VoiceRole):
            raise TypeError("role must be a VoiceRole")
        _require_finite(self.gain_db, "gain_db")
        if self.pan is not None:
            _require_pan(self.pan, "pan")


@dataclass(frozen=True, slots=True, kw_only=True)
class TrackPlan:
    """A description of one output file: which stems, at what gains.

    ``speed`` is a tempo multiplier (1 = original). It exists so practice-speed variants
    can be planned later without changing the mixer's inputs.

    Invariants by kind: FULL has no target; PREDOMINANT and SOLO have a target that is
    among the inputs (SOLO has only that input); MINUS has a target that is *not* among
    the inputs. Roles are unique within ``inputs``.
    """

    kind: TrackKind
    inputs: tuple[StemMix, ...]
    target: VoiceRole | None = None
    speed: Fraction = Fraction(1)

    def __post_init__(self) -> None:
        inputs = tuple(self.inputs)
        speed = to_fraction(self.speed, name="speed")
        roles = [stem.role for stem in inputs]
        if speed <= 0:
            raise ValueError("speed must be positive")
        if not inputs:
            raise ValueError("a track plan needs at least one input")
        if len(set(roles)) != len(roles):
            raise ValueError("input roles must be unique")
        if self.kind is TrackKind.FULL:
            if self.target is not None:
                raise ValueError("a FULL track has no target")
        elif self.target is None:
            raise ValueError(f"a {self.kind.name} track needs a target")
        elif self.kind is TrackKind.MINUS:
            if self.target in roles:
                raise ValueError("a MINUS track must not include its target")
        elif self.target not in roles:
            raise ValueError(f"a {self.kind.name} track must include its target")
        elif self.kind is TrackKind.SOLO and len(inputs) != 1:
            raise ValueError("a SOLO track has exactly one input")
        object.__setattr__(self, "inputs", inputs)
        object.__setattr__(self, "speed", speed)

    @property
    def roles(self) -> tuple[VoiceRole, ...]:
        return tuple(stem.role for stem in self.inputs)
