"""Stems in, mixed PCM16 out: float64 arithmetic, one quantisation, no silent clipping.

* Input: 44.1 kHz, 16-bit PCM, mono WAV (what M8 validated). Anything else is a ``MixInputError``.
* Decoding is ``sample / 32768`` (exact in float64).
* Every stem is placed on a common timeline of ``target_frames`` frames starting at frame 0: it is
  padded with exact zeros at the end, never shifted. A stem longer than the target is an error
  unless the excess is within the :class:`TailPolicy` (short and nearly silent), in which case it
  is trimmed and the trim is reported.
* Mixing is a weighted sum in float64, always in voice order (tenor, lead, baritone, bass), so the
  result is deterministic.
* Quantisation happens once: ``rint(x * 32768)`` (round half to even), no dither. A value that
  lands outside -32768..32767 is clipping and raises ``MixClippingError``; nothing is clamped.
"""

import struct
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from barbershop_tracks.core.mixing.errors import (
    MixClippingError,
    MixConfigurationError,
    MixDurationError,
    MixInputError,
)
from barbershop_tracks.core.mixing.specs import MixSpec
from barbershop_tracks.core.rendering.wav import WavFormatError, read_raw
from barbershop_tracks.core.synthesis import VOICE_ORDER
from barbershop_tracks.models import VoiceRole

SAMPLE_RATE = 44100
SCALE = 32768.0

Float = NDArray[np.float64]
Int16 = NDArray[np.int16]


@dataclass(frozen=True, slots=True)
class TailPolicy:
    """How much of a stem's end beyond the target may be dropped, and only if it is nearly silent."""

    max_trim_seconds: float = 0.05
    max_trim_peak: float = 1e-3  # share of full scale; -60 dBFS

    def __post_init__(self) -> None:
        if self.max_trim_seconds < 0 or not 0 <= self.max_trim_peak <= 1:
            raise MixConfigurationError("MIX_TAIL_POLICY", "the tail policy is out of range")


@dataclass(frozen=True, slots=True)
class StemAudio:
    role: VoiceRole
    samples: Int16  # int16, mono
    sample_rate: int = SAMPLE_RATE

    @property
    def frames(self) -> int:
        return int(self.samples.shape[0])


@dataclass(frozen=True, slots=True)
class FittedStem:
    role: VoiceRole
    samples: Float  # exactly target_frames long, in -1..1
    padded_frames: int
    trimmed_frames: int


def load_stem(role: VoiceRole, path: Path) -> StemAudio:
    try:
        info, body = read_raw(path)
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
    samples = np.frombuffer(body, dtype="<i2").astype(np.int16)
    return StemAudio(role, samples)


def fit_stem(stem: StemAudio, target_frames: int, tail: TailPolicy) -> FittedStem:
    """Place the stem on the common timeline: pad the end, or trim a short, nearly silent excess."""
    decoded = stem.samples.astype(np.float64) / SCALE
    excess = stem.frames - target_frames
    if excess > 0:
        dropped = decoded[target_frames:]
        peak = float(np.max(np.abs(dropped)))
        limit = int(tail.max_trim_seconds * stem.sample_rate)
        if excess > limit or peak > tail.max_trim_peak:
            raise MixDurationError(
                "MIX_STEM_TOO_LONG",
                f"{stem.role.display_name} sounds {excess} frames "
                f"({excess / stem.sample_rate:.4f} s) past the performed duration of "
                f"{target_frames} frames; the excess peaks at {peak:.4f} of full scale",
                {"excess_frames": excess, "excess_peak": peak},
            )
        return FittedStem(stem.role, np.ascontiguousarray(decoded[:target_frames]), 0, excess)
    out = np.zeros(target_frames, dtype=np.float64)
    out[: stem.frames] = decoded
    return FittedStem(stem.role, out, -excess, 0)


def mix_float(spec: MixSpec, stems: Mapping[VoiceRole, FittedStem]) -> Float:
    """The weighted sum, in voice order, in float64."""
    frames = {fitted.samples.shape[0] for fitted in stems.values()}
    if len(frames) != 1:
        raise MixInputError("MIX_FRAME_MISMATCH", f"stems differ in length: {sorted(frames)}")
    out = np.zeros(frames.pop(), dtype=np.float64)
    for role, gain in zip(VOICE_ORDER, spec.gains, strict=True):
        if gain == 0.0:
            continue
        if role not in stems:
            raise MixInputError(
                "MIX_STEM_MISSING", f"{spec.identifier} needs the {role.value} stem"
            )
        out += gain * stems[role].samples
    return out


def quantize(mixed: Float, mix_id: str) -> tuple[Int16, float]:
    """Round once to PCM16; returns the samples and the float peak. Clipping is an error."""
    scaled = np.rint(mixed * SCALE)
    peak = float(np.max(np.abs(mixed))) if mixed.size else 0.0
    over = np.flatnonzero((scaled > 32767.0) | (scaled < -32768.0))
    if over.size:
        raise MixClippingError(
            "MIX_CLIPPING",
            f"{mix_id} would clip: {over.size} sample(s) exceed full scale (peak {peak:.4f}, "
            f"first at frame {int(over[0])}); lower the gains instead of letting it clip",
            {"mix": mix_id, "peak": peak, "clipped_samples": int(over.size), "first": int(over[0])},
        )
    return scaled.astype("<i2"), peak


def wav_bytes(samples: Int16, sample_rate: int = SAMPLE_RATE) -> bytes:
    """A canonical 44-byte-header mono PCM16 WAV: identical input gives identical bytes."""
    data = samples.astype("<i2", copy=False).tobytes()
    header = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt "
    header += struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16)
    return header + b"data" + struct.pack("<I", len(data)) + data
