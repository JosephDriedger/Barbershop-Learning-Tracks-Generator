"""Chunked mixing: memory bounded by the block size, not by the length of the song.

A stem is never held whole. Each mix is produced block by block (``BLOCK_FRAMES`` frames): the
needed stems are read from disk for that block, decoded to float64, summed in voice order with the
same arithmetic as :func:`audio.mix_float`, rounded once by :func:`audio.quantize_block`, and
appended to the output file. Because every operation is element-wise and independent of the block
size, the output is **bit-for-bit identical** to the whole-array implementation in ``audio.py``
(which stays as the reference; a test compares the two on varied inputs). Differences in behaviour:
none in the bytes; clipping is still detected over the whole mix (the error reports the global
peak, count and first frame); cancellation is now checked every block, not only between tracks.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from barbershop_tracks.core.mixing.audio import (
    SAMPLE_RATE,
    SCALE,
    Float,
    Int16,
    TailPolicy,
    clipping_error,
    gain_block,
    quantize_block,
    wav_header,
)
from barbershop_tracks.core.mixing.errors import MixDurationError, MixInputError
from barbershop_tracks.core.mixing.specs import MixSpec
from barbershop_tracks.core.rendering.wav import WavFormatError, inspect_file
from barbershop_tracks.core.synthesis import VOICE_ORDER
from barbershop_tracks.models import VoiceRole

BLOCK_FRAMES = 1 << 18  # 262144 frames: about 6 s of audio, 2 MB of float64 per stem block


@dataclass(frozen=True, slots=True)
class PlacedStem:
    """A stem on the common timeline: where its samples are, and how it was fitted."""

    role: VoiceRole
    path: Path
    offset: int  # byte offset of the samples
    frames: int  # frames in the file
    target_frames: int
    padded_frames: int
    trimmed_frames: int

    def block(self, start: int, stop: int) -> Float:
        """Float64 samples ``start:stop`` of the timeline: zeros before/after the file's audio."""
        out = np.zeros(stop - start, dtype=np.float64)
        end = min(stop, self.frames, self.target_frames)
        if end > start:
            with self.path.open("rb") as handle:
                handle.seek(self.offset + 2 * start)
                raw = handle.read(2 * (end - start))
            out[: end - start] = np.frombuffer(raw, dtype="<i2").astype(np.float64) / SCALE
        return out


def _peak(path: Path, offset: int, first: int, last: int) -> float:
    """Largest |sample| (fraction of full scale) in ``first:last``, read in blocks."""
    peak = 0
    with path.open("rb") as handle:
        for start in range(first, last, BLOCK_FRAMES):
            stop = min(last, start + BLOCK_FRAMES)
            handle.seek(offset + 2 * start)
            block = np.frombuffer(handle.read(2 * (stop - start)), dtype="<i2").astype(np.int32)
            peak = max(peak, int(np.max(np.abs(block))))
    return peak / SCALE


def place_stem(role: VoiceRole, path: Path, target_frames: int, tail: TailPolicy) -> PlacedStem:
    """Check the stem's format from its header, then fit it to the timeline."""
    try:
        info, offset = inspect_file(path)
    except WavFormatError as error:
        raise MixInputError(
            "MIX_STEM_UNREADABLE", f"{role.display_name}: {error.message}", {"wav_code": error.code}
        ) from error
    if (info.sample_rate, info.bit_depth, info.channels, info.is_float) != (
        SAMPLE_RATE,
        16,
        1,
        False,
    ):
        raise MixInputError(
            "MIX_STEM_FORMAT",
            f"{role.display_name}: {info.sample_rate} Hz, {info.bit_depth}-bit, "
            f"{info.channels} channel(s){' float' if info.is_float else ''}; the mixer takes "
            f"{SAMPLE_RATE} Hz 16-bit PCM mono",
        )
    if info.frames == 0:
        raise MixInputError("MIX_STEM_EMPTY", f"{role.display_name}: the stem has no audio")
    excess = info.frames - target_frames
    if excess > 0:
        peak = _peak(path, offset, target_frames, info.frames)
        limit = int(tail.max_trim_seconds * SAMPLE_RATE)
        if excess > limit or peak > tail.max_trim_peak:
            raise MixDurationError(
                "MIX_STEM_TOO_LONG",
                f"{role.display_name} sounds {excess} frames "
                f"({excess / SAMPLE_RATE:.4f} s) past the performed duration of "
                f"{target_frames} frames; the excess peaks at {peak:.4f} of full scale",
                {"excess_frames": excess, "excess_peak": peak},
            )
        return PlacedStem(role, path, offset, info.frames, target_frames, 0, excess)
    return PlacedStem(role, path, offset, info.frames, target_frames, -excess, 0)


def write_mix(
    spec: MixSpec,
    stems: Mapping[VoiceRole, PlacedStem],
    frames: int,
    destination: Path,
    *,
    should_stop: Callable[[], bool] = lambda: False,
    block_frames: int = BLOCK_FRAMES,
    lead_in: Int16 | None = None,
) -> float:
    """Write the mix as a canonical WAV, block by block; returns the float peak.

    ``lead_in`` (a tune-up note, a count-in: ``prelude.py``) is written first, as it is, so the
    file is ``len(lead_in) + frames`` frames long and the mix starts after it.

    Raises ``MixClippingError`` (after the whole mix has been checked) if any sample would exceed
    full scale; the partial file is the caller's to discard.
    """
    needed = [
        (index, role)
        for index, (role, gain) in enumerate(zip(VOICE_ORDER, spec.gains, strict=True))
        if gain != 0.0
    ]
    for _, role in needed:
        if role not in stems:
            raise MixInputError(
                "MIX_STEM_MISSING", f"{spec.identifier} needs the {role.value} stem"
            )
    peak = 0.0
    clipped = 0
    first_clipped: int | None = None
    with destination.open("wb") as out:
        lead = 0 if lead_in is None else int(lead_in.shape[0])
        out.write(wav_header(lead + frames))
        if lead_in is not None:
            out.write(lead_in.astype("<i2", copy=False).tobytes())
        for start in range(0, frames, block_frames):
            if should_stop():
                return peak
            stop = min(frames, start + block_frames)
            mixed = np.zeros(stop - start, dtype=np.float64)
            for index, role in needed:
                mixed += gain_block(spec, index, start, stop) * stems[role].block(start, stop)
            quantized = quantize_block(mixed)
            peak = max(peak, quantized.peak)
            if quantized.samples is None:
                clipped += quantized.clipped
                if first_clipped is None and quantized.first_clipped is not None:
                    first_clipped = start + quantized.first_clipped
                continue
            out.write(quantized.samples.tobytes())
    if clipped:
        assert first_clipped is not None
        raise clipping_error(spec.identifier, peak, clipped, first_clipped)
    return peak
