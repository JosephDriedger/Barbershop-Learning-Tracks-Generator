"""Time-signature representability. A meter MIDI cannot hold exactly is omitted, never altered.

The auxiliary fields of the MIDI time-signature event are **not MusicXML facts**: they are the same
conventional values for every meter and are never derived from the source nor taken from a library
default.
"""

from dataclasses import dataclass

from barbershop_tracks.models import TimeSignature

METER_CLICK_CLOCKS = 24  # MIDI clocks per metronome click (conventional: a quarter note)
METER_32NDS_PER_QUARTER = 8  # notated 32nd notes per MIDI quarter note (conventional)
MAX_NUMERATOR = 255
MAX_DENOMINATOR_EXPONENT = 255


@dataclass(frozen=True, slots=True)
class MeterEncoding:
    numerator: int
    denominator_exponent: int


def encode_meter(signature: TimeSignature) -> MeterEncoding | str:
    """The MIDI encoding, or the reason this meter cannot be represented exactly."""
    if not 1 <= signature.beats <= MAX_NUMERATOR:
        return f"numerator {signature.beats} is outside 1..{MAX_NUMERATOR}"
    denominator = signature.beat_type
    if denominator <= 0 or denominator & (denominator - 1):
        return f"denominator {denominator} is not a power of two"
    exponent = denominator.bit_length() - 1
    if exponent > MAX_DENOMINATOR_EXPONENT:
        return f"denominator 2^{exponent} exceeds 2^{MAX_DENOMINATOR_EXPONENT}"
    return MeterEncoding(numerator=signature.beats, denominator_exponent=exponent)
