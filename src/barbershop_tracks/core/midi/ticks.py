"""Exact quarter-note ``Fraction`` to MIDI tick conversion. The only place that multiplies."""

from fractions import Fraction

from barbershop_tracks.core.midi.errors import MidiExportError

DEFAULT_PPQ = 480
# The SMF division field is 16 bits; a set top bit selects SMPTE time code, so a metrical
# (ticks-per-quarter) division has 15 bits. SMPTE division is not supported.
MIN_PPQ = 1
MAX_PPQ = 0x7FFF


def validate_ppq(ppq: object) -> int:
    if isinstance(ppq, bool) or not isinstance(ppq, int) or not MIN_PPQ <= ppq <= MAX_PPQ:
        raise MidiExportError(
            "MIDI_PPQ_INVALID",
            f"ppq must be an int in {MIN_PPQ}..{MAX_PPQ} (ticks per quarter note), got {ppq!r}",
        )
    return ppq


def to_ticks(position: Fraction, ppq: int, *, what: str) -> int:
    """``position * ppq`` as an exact integer, or ``MIDI_TICK_NOT_INTEGRAL``. Never rounds."""
    ticks = position * ppq
    if ticks.denominator != 1:
        raise MidiExportError(
            "MIDI_TICK_NOT_INTEGRAL",
            f"{what} at quarter-note position {position} is not a whole number of ticks at "
            f"ppq {ppq} ({ticks} ticks); nothing is rounded",
        )
    if ticks < 0:
        raise MidiExportError("MIDI_TICK_NEGATIVE", f"{what} at position {position} is negative")
    return int(ticks)
