"""Generation capabilities: what a generator needs from a performed score.

A ``Capability`` is a small immutable set of requirements. Validators read these fields; they
never branch on a capability name, so adding a capability (a new backend, a subset of voices) never
means editing a validator. Presets are plain values built from the same fields.
"""

from dataclasses import dataclass
from enum import Enum

from barbershop_tracks.models import VoiceRole


class LyricPolicy(Enum):
    """How much of the lyrics a capability needs."""

    NONE = "none"
    AT_LEAST_ONE_COMPLETE_LINE = "at_least_one_complete_line"
    ALL_ASSIGNED_LINES_COMPLETE = "all_assigned_lines_complete"


class Feature(Enum):
    """Capability features that warning policies can depend on."""

    MONOPHONY = "monophony"
    INTEGRAL_PITCH = "integral_pitch"
    TEMPO = "tempo"
    LYRICS_USED = "lyrics_used"


# Generous *sounding* ranges (MIDI note numbers, C4 = 60) used only for the advisory
# ``VOICE_RANGE_UNUSUAL`` finding. They are a heuristic for catching clef and octave mistakes,
# never a rule: arrangements legitimately exceed them and voices cross. Change them here.
DEFAULT_TYPICAL_RANGES: tuple[tuple[VoiceRole, int, int], ...] = (
    (VoiceRole.TENOR, 48, 79),  # C3 - G5
    (VoiceRole.LEAD, 43, 74),  # G2 - D5
    (VoiceRole.BARITONE, 38, 69),  # D2 - A4
    (VoiceRole.BASS, 31, 62),  # G1 - D4
)


@dataclass(frozen=True, slots=True, kw_only=True)
class Capability:
    """The requirements of one generation capability."""

    name: str
    required_roles: frozenset[VoiceRole] = frozenset()
    all_musical_lines_accounted_for: bool = False
    assigned_lines_must_sound: bool = False
    monophony_required: bool = False
    integral_midi_pitch_required: bool = False
    midi_range: tuple[int, int] | None = None
    tempo_required: bool = False
    lyric_policy: LyricPolicy = LyricPolicy.NONE
    lyric_source_role: VoiceRole | None = None
    typical_ranges: tuple[tuple[VoiceRole, int, int], ...] | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("a capability needs a name")
        object.__setattr__(self, "required_roles", frozenset(self.required_roles))
        if not all(isinstance(role, VoiceRole) for role in self.required_roles):
            raise TypeError("required_roles must contain only VoiceRole values")
        if self.midi_range is not None and self.midi_range[0] > self.midi_range[1]:
            raise ValueError("midi_range must be (low, high) with low <= high")
        if self.lyric_source_role is not None and self.lyric_policy is LyricPolicy.NONE:
            raise ValueError("a lyric source role needs a lyric policy that uses lyrics")
        if self.typical_ranges is not None:
            for _, low, high in self.typical_ranges:
                if low > high:
                    raise ValueError("a typical range must have low <= high")

    @property
    def features(self) -> frozenset[Feature]:
        """The features this capability has; warning policies key on these."""
        found = set()
        if self.monophony_required:
            found.add(Feature.MONOPHONY)
        if self.integral_midi_pitch_required:
            found.add(Feature.INTEGRAL_PITCH)
        if self.tempo_required:
            found.add(Feature.TEMPO)
        if self.lyric_policy is not LyricPolicy.NONE:
            found.add(Feature.LYRICS_USED)
        return frozenset(found)

    def range_for(self, role: VoiceRole) -> tuple[int, int] | None:
        """The advisory typical range for ``role``, if the capability uses the heuristic."""
        if self.typical_ranges is None:
            return None
        for known, low, high in self.typical_ranges:
            if known is role:
                return low, high
        return None

    def with_lyric_source(self, role: VoiceRole) -> "Capability":
        """A copy that names ``role`` as the authoritative lyric source."""
        from dataclasses import replace

        return replace(self, lyric_source_role=role)


QUARTET_VOCAL = Capability(
    name="quartet-vocal",
    required_roles=frozenset(VoiceRole),
    all_musical_lines_accounted_for=True,
    assigned_lines_must_sound=True,
    monophony_required=True,
    integral_midi_pitch_required=True,
    midi_range=(0, 127),
    tempo_required=True,
    lyric_policy=LyricPolicy.AT_LEAST_ONE_COMPLETE_LINE,
    typical_ranges=DEFAULT_TYPICAL_RANGES,
)

TEST_TONE = Capability(
    name="test-tone",
    monophony_required=True,
    tempo_required=True,
)

CAPABILITIES: dict[str, Capability] = {c.name: c for c in (QUARTET_VOCAL, TEST_TONE)}
