"""Tempo encoding. Tick timing is exact; tempo is not: MIDI stores integer microseconds per quarter.

``exact = 60_000_000 / bpm`` (a rational); the encoded value is its nearest integer, ties to even,
decided on ``Fraction`` (no binary floating point). The error is recorded, never hidden.
"""

from dataclasses import dataclass
from fractions import Fraction

from barbershop_tracks.core.midi.errors import MidiExportError

MICROSECONDS_PER_MINUTE = 60_000_000
MIN_US_PER_QUARTER = 1
MAX_US_PER_QUARTER = 0xFFFFFF  # the set-tempo meta event payload is 3 bytes


@dataclass(frozen=True, slots=True)
class TempoEncoding:
    bpm: Fraction
    exact_us_per_quarter: Fraction
    encoded_us_per_quarter: int

    @property
    def error_us_per_quarter(self) -> Fraction:
        """``encoded - exact`` in microseconds per quarter note."""
        return self.encoded_us_per_quarter - self.exact_us_per_quarter

    @property
    def bpm_error(self) -> Fraction:
        """The tempo actually encoded minus the requested one, in quarter notes per minute."""
        return Fraction(MICROSECONDS_PER_MINUTE, self.encoded_us_per_quarter) - self.bpm

    @property
    def is_exact(self) -> bool:
        return self.error_us_per_quarter == 0


def encode_tempo(bpm: Fraction) -> TempoEncoding:
    if not isinstance(bpm, Fraction) or bpm <= 0:
        raise MidiExportError("MIDI_TEMPO_INVALID", f"tempo must be a positive number, got {bpm!r}")
    exact = Fraction(MICROSECONDS_PER_MINUTE) / bpm
    encoded = round(exact)  # Fraction.__round__: nearest integer, ties to even
    if not MIN_US_PER_QUARTER <= encoded <= MAX_US_PER_QUARTER:
        raise MidiExportError(
            "MIDI_TEMPO_UNREPRESENTABLE",
            f"{bpm} BPM needs {exact} microseconds per quarter note; MIDI can store "
            f"{MIN_US_PER_QUARTER}..{MAX_US_PER_QUARTER}",
        )
    return TempoEncoding(bpm=bpm, exact_us_per_quarter=exact, encoded_us_per_quarter=encoded)
