"""A tune-up note and a metronome count-in placed before the music of every track.

Both are optional and are the same on all 13 tracks. The music itself is never touched: it only
starts later, ``Prelude.frames`` frames into each file, and the manifest says where.

* **Tune-up note**: the tonic of the score's first key signature, as a plain sine tone (a pitch
  pipe), in the octave nearest the Lead's first note so that it is comfortable to sing. A score
  without a key signature, or in a mode that has no tonic, has nothing to play and is refused
  (never guessed).
* **Count-in**: one bar of clicks at the score's first tempo and meter, the first click accented.
  The music starts exactly one beat after the last click, as if it were the next beat of the count.

After the tune-up note there is a second of silence so that it does not run into the count-in or
the music.
"""

import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

import numpy as np
import numpy.typing as npt

from barbershop_tracks.core.mixing.audio import SAMPLE_RATE, Int16
from barbershop_tracks.core.mixing.errors import MixConfigurationError
from barbershop_tracks.models import KeySignature

TUNE_SECONDS = 3.0
SILENCE_AFTER_TUNE_SECONDS = 1.0
TUNE_LEVEL = 0.3  # of full scale: a pitch pipe, not louder than the singing
TUNE_FADE_IN_SECONDS = 0.03
TUNE_FADE_OUT_SECONDS = 0.1
CLICK_SECONDS = 0.05
CLICK_ACCENT_HZ = 1600.0
CLICK_HZ = 1000.0
CLICK_ACCENT_LEVEL = 0.6
CLICK_LEVEL = 0.4
CLICK_DECAY_SECONDS = 0.008
DEFAULT_REFERENCE_MIDI = 60  # the octave of the tune-up note when no Lead note is known

_SHARP_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_FLAT_NAMES = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")


@dataclass(frozen=True, slots=True)
class PreludeOptions:
    tune_up: bool = False  # a note to tune to: the tonic of the first key signature
    count_in: bool = False  # a bar of metronome clicks

    @property
    def enabled(self) -> bool:
        return self.tune_up or self.count_in


@dataclass(frozen=True, slots=True)
class Prelude:
    samples: Int16  # 16-bit mono at ``SAMPLE_RATE``
    info: dict[str, Any]  # for the manifest

    @property
    def frames(self) -> int:
        return int(self.samples.shape[0])


def tonic_midi(key: KeySignature | None, reference_midi: int | None) -> int:
    """The MIDI note of the key's tonic, in the octave nearest ``reference_midi``."""
    pitch_class = None if key is None else key.tonic_pitch_class
    if key is None or pitch_class is None:
        raise MixConfigurationError(
            "MIX_TUNE_NO_KEY",
            "the score has no key signature with a tonic, so there is no tune-up note to play; "
            "turn the tune-up note off or add a key signature to the score",
        )
    reference = DEFAULT_REFERENCE_MIDI if reference_midi is None else reference_midi
    candidates = [
        pitch_class + 12 * octave
        for octave in range(0, 11)
        if 0 <= pitch_class + 12 * octave <= 127
    ]
    return min(candidates, key=lambda midi: (abs(midi - reference), midi))


def _name(midi: int, flats: bool) -> str:
    names = _FLAT_NAMES if flats else _SHARP_NAMES
    return f"{names[midi % 12]}{midi // 12 - 1}"


def _to_int16(signal: npt.NDArray[np.float64]) -> Int16:
    scaled = np.round(np.clip(signal, -1.0, 1.0) * 32767.0)
    return scaled.astype("<i2")


def _tune(midi: int) -> npt.NDArray[np.float64]:
    frames = round(TUNE_SECONDS * SAMPLE_RATE)
    time = np.arange(frames) / SAMPLE_RATE
    frequency = 440.0 * 2.0 ** ((midi - 69) / 12)
    envelope = np.minimum(1.0, time / TUNE_FADE_IN_SECONDS)
    envelope = np.minimum(
        envelope, np.clip((TUNE_SECONDS - time) / TUNE_FADE_OUT_SECONDS, 0.0, 1.0)
    )
    tone: npt.NDArray[np.float64] = np.sin(2.0 * np.pi * frequency * time)
    return TUNE_LEVEL * envelope * tone


def _click(accent: bool) -> npt.NDArray[np.float64]:
    frames = round(CLICK_SECONDS * SAMPLE_RATE)
    time = np.arange(frames) / SAMPLE_RATE
    frequency = CLICK_ACCENT_HZ if accent else CLICK_HZ
    level = CLICK_ACCENT_LEVEL if accent else CLICK_LEVEL
    attack = np.minimum(1.0, time / 0.001)
    tone: npt.NDArray[np.float64] = np.sin(2.0 * np.pi * frequency * time)
    return level * attack * np.exp(-time / CLICK_DECAY_SECONDS) * tone


def build_prelude(
    options: PreludeOptions,
    *,
    key: KeySignature | None,
    reference_midi: int | None,
    bpm: Fraction,
    beats: int,
    beat_type: int,
) -> Prelude | None:
    """The audio before the music, or ``None`` when neither part is wanted."""
    if not options.enabled:
        return None
    parts: list[npt.NDArray[np.float64]] = []
    info: dict[str, Any] = {"tune_up": None, "count_in": None}
    if options.tune_up:
        midi = tonic_midi(key, reference_midi)
        assert key is not None
        parts.append(_tune(midi))
        parts.append(np.zeros(round(SILENCE_AFTER_TUNE_SECONDS * SAMPLE_RATE)))
        info["tune_up"] = {
            "note": _name(midi, key.fifths < 0),
            "midi": midi,
            "frequency_hz": round(440.0 * 2.0 ** ((midi - 69) / 12), 3),
            "seconds": TUNE_SECONDS,
            "key": {"fifths": key.fifths, "mode": key.mode or "major"},
        }
    if options.count_in:
        if bpm <= 0 or beats <= 0 or beat_type <= 0:
            raise MixConfigurationError("MIX_COUNT_IN", "the tempo and meter must be positive")
        beat_seconds = Fraction(4, beat_type) * 60 / bpm  # one beat of the meter, exact
        frames = math.ceil(beat_seconds * beats * SAMPLE_RATE)
        bar = np.zeros(frames)
        for beat in range(beats):
            start = round(beat * beat_seconds * SAMPLE_RATE)
            click = _click(beat == 0)
            end = min(frames, start + click.shape[0])
            bar[start:end] += click[: end - start]
        parts.append(bar)
        info["count_in"] = {
            "beats": beats,
            "beat_unit": beat_type,
            "bpm": f"{bpm.numerator}/{bpm.denominator}" if bpm.denominator != 1 else str(bpm),
            "seconds": round(float(beat_seconds * beats), 6),
        }
    samples = _to_int16(np.concatenate(parts))
    info["frames"] = int(samples.shape[0])
    info["seconds"] = round(int(samples.shape[0]) / SAMPLE_RATE, 6)
    info["music_starts_at_frame"] = int(samples.shape[0])
    return Prelude(samples, info)


__all__ = ["Prelude", "PreludeOptions", "build_prelude", "tonic_midi"]
