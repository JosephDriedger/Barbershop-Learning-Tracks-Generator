"""The deterministic MIDI representation: immutable, in memory, no file names or paths."""

import hashlib
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction

from barbershop_tracks.models import VoiceRole

# Fixed voice order and channels. Channel 9 is General MIDI percussion ("channel 10"): it must
# never appear in this mapping, so a future policy change cannot accidentally enter it.
VOICE_ORDER: tuple[VoiceRole, ...] = (
    VoiceRole.TENOR,
    VoiceRole.LEAD,
    VoiceRole.BARITONE,
    VoiceRole.BASS,
)
PERCUSSION_CHANNEL = 9
VOICE_CHANNELS: dict[VoiceRole, int] = {role: index for index, role in enumerate(VOICE_ORDER)}
if PERCUSSION_CHANNEL in VOICE_CHANNELS.values() or not all(
    0 <= channel <= 15 for channel in VOICE_CHANNELS.values()
):
    raise RuntimeError("voice channels must be 0..15 and must not include the percussion channel")

CONDUCTOR_NAME = "Conductor"
NOTE_ON_VELOCITY = 80  # one constant for every attack; no dynamics are read from the score
NOTE_OFF_VELOCITY = 64  # a real note-off event, never note-on with velocity 0


class EventKind(Enum):
    """The value is the event's priority at an equal tick (lower first)."""

    TRACK_NAME = 0
    TIME_SIGNATURE = 1
    TEMPO = 2
    NOTE_OFF = 3  # always before NOTE_ON: no transient overlap of back-to-back notes
    NOTE_ON = 4
    END_OF_TRACK = 9


@dataclass(frozen=True, slots=True)
class MidiEvent:
    """One event at an absolute tick.

    ``data``: note events ``(pitch, velocity)``; tempo ``(us_per_quarter,)``; time signature
    ``(numerator, denominator_exponent, clocks_per_click, notated_32nds_per_quarter)``.
    """

    tick: int
    kind: EventKind
    channel: int | None = None
    data: tuple[int, ...] = ()
    text: str = ""

    @property
    def sort_key(self) -> tuple[int, int, int]:
        is_note = self.kind in (EventKind.NOTE_ON, EventKind.NOTE_OFF)
        return (self.tick, self.kind.value, self.data[0] if is_note else 0)


@dataclass(frozen=True, slots=True)
class MidiTrack:
    name: str
    channel: int | None  # None for the conductor
    events: tuple[MidiEvent, ...]


@dataclass(frozen=True, slots=True)
class RoleSummary:
    role: VoiceRole
    track_name: str
    channel: int
    line_id: str
    part_name: str
    attacks: int
    lowest_midi: int
    highest_midi: int


@dataclass(frozen=True, slots=True)
class TempoRecord:
    """One exported tempo event with its exact value, its encoding and the encoding error."""

    position: Fraction
    tick: int
    bpm: Fraction
    exact_us_per_quarter: Fraction
    encoded_us_per_quarter: int
    error_us_per_quarter: Fraction  # encoded - exact
    bpm_error: Fraction  # encoded tempo - requested tempo, quarter notes per minute


@dataclass(frozen=True, slots=True)
class MeterRecord:
    """An explicit performed meter event, written or omitted (with the reason)."""

    position: Fraction
    tick: int
    beats: int
    beat_type: int
    written: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class MidiWarning:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class MidiPlan:
    """Everything the file contains, as absolute-tick events in their final order."""

    ppq: int
    end_position: Fraction  # the exact performed song length in quarter notes
    end_tick: int
    tracks: tuple[MidiTrack, ...]  # conductor first, then the voices in ``VOICE_ORDER``
    roles: tuple[RoleSummary, ...]
    tempo: tuple[TempoRecord, ...]
    meter: tuple[MeterRecord, ...]
    warnings: tuple[MidiWarning, ...]


@dataclass(frozen=True, slots=True)
class MidiExport:
    """The immutable result of a pure export: plan, encoded bytes, warnings."""

    plan: MidiPlan
    data: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    @property
    def warnings(self) -> tuple[MidiWarning, ...]:
        return self.plan.warnings
