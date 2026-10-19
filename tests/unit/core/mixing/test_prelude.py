"""The tune-up note and the metronome count-in before the music of every track."""

import math
from fractions import Fraction

import numpy as np
import pytest

from barbershop_tracks.core.mixing import MixConfigurationError, PreludeOptions, tonic_midi
from barbershop_tracks.core.mixing.audio import SAMPLE_RATE
from barbershop_tracks.core.mixing.prelude import (
    CLICK_SECONDS,
    SILENCE_AFTER_TUNE_SECONDS,
    TUNE_SECONDS,
    build_prelude,
)
from barbershop_tracks.models import KeySignature

D_MAJOR = KeySignature(fifths=2, mode="major")
A_MINOR = KeySignature(fifths=0, mode="minor")


@pytest.mark.parametrize(
    ("fifths", "mode", "pitch_class", "name"),
    [
        (0, None, 0, "C"),
        (0, "major", 0, "C"),
        (1, "major", 7, "G"),
        (2, "major", 2, "D"),
        (-1, "major", 5, "F"),
        (-3, "major", 3, "Eb"),
        (0, "minor", 9, "A"),
        (-1, "minor", 2, "D"),
        (0, "dorian", 2, "D"),
        (0, "mixolydian", 7, "G"),
        (6, "major", 6, "F#"),
        (-6, "major", 6, "Gb"),
    ],
)
def test_the_tonic_follows_the_key_signature_and_mode(
    fifths: int, mode: str | None, pitch_class: int, name: str
) -> None:
    key = KeySignature(fifths=fifths, mode=mode)
    assert key.tonic_pitch_class == pitch_class
    assert key.tonic_name == name


def test_a_mode_without_a_tonic_has_none() -> None:
    assert KeySignature(fifths=0, mode="none").tonic_pitch_class is None


def test_the_tune_up_note_is_in_the_octave_nearest_the_leads_first_note() -> None:
    assert tonic_midi(D_MAJOR, 62) == 62  # D4
    assert tonic_midi(D_MAJOR, 57) == 62  # A3 is nearer D4 than D3
    assert tonic_midi(D_MAJOR, 52) == 50  # E3 is nearer D3
    assert tonic_midi(D_MAJOR, None) == 62  # no Lead note: around middle C


@pytest.mark.parametrize("key", [None, KeySignature(fifths=0, mode="none")])
def test_a_score_without_a_tonic_cannot_have_a_tune_up_note(key: KeySignature | None) -> None:
    with pytest.raises(MixConfigurationError, match="tune-up"):
        tonic_midi(key, 60)


def make(options: PreludeOptions, key: KeySignature | None = D_MAJOR, **extra: object):  # type: ignore[no-untyped-def]
    values: dict[str, object] = {
        "key": key,
        "reference_midi": 62,
        "bpm": Fraction(120),
        "beats": 4,
        "beat_type": 4,
    }
    values.update(extra)
    return build_prelude(options, **values)  # type: ignore[arg-type]


def test_nothing_is_added_unless_asked_for() -> None:
    assert make(PreludeOptions()) is None


def test_the_tune_up_note_is_a_sine_at_the_tonic_followed_by_silence() -> None:
    prelude = make(PreludeOptions(tune_up=True))
    assert prelude is not None
    tune = round(TUNE_SECONDS * SAMPLE_RATE)
    silence = round(SILENCE_AFTER_TUNE_SECONDS * SAMPLE_RATE)
    assert prelude.frames == tune + silence
    assert prelude.info["tune_up"]["note"] == "D4"
    assert prelude.info["tune_up"]["frequency_hz"] == pytest.approx(293.665, abs=0.001)
    assert prelude.info["count_in"] is None
    assert not prelude.samples[tune:].any()  # silent after the note
    middle = prelude.samples[SAMPLE_RATE : 2 * SAMPLE_RATE].astype(np.float64)
    spectrum = np.abs(np.fft.rfft(middle))
    assert np.argmax(spectrum) * SAMPLE_RATE / len(middle) == pytest.approx(293.665, abs=1.0)
    assert prelude.samples[0] == 0  # fades in, so there is no click at the start
    assert abs(prelude.samples[tune - 1]) < 200  # and out


def test_the_count_in_is_one_bar_of_clicks_with_an_accented_first_click() -> None:
    prelude = make(PreludeOptions(count_in=True))
    assert prelude is not None
    beat = SAMPLE_RATE // 2  # 120 BPM: half a second
    # one bar of 4/4: the music starts one beat after the last click
    assert prelude.frames == 4 * beat
    assert prelude.info["tune_up"] is None
    assert prelude.info["count_in"]["beats"] == 4
    click = round(CLICK_SECONDS * SAMPLE_RATE)
    peaks = [int(np.abs(prelude.samples[i * beat : i * beat + click]).max()) for i in range(4)]
    assert peaks[0] > peaks[1]  # the first click is accented
    assert min(peaks) > 5000  # and every click is audible
    for i in range(4):  # silence between the clicks: it is clicks, not a continuous sound
        assert not prelude.samples[i * beat + click : (i + 1) * beat].any()


def test_the_count_in_follows_the_meter_and_the_tempo() -> None:
    prelude = make(PreludeOptions(count_in=True), bpm=Fraction(90), beats=3, beat_type=4)
    assert prelude is not None
    assert prelude.frames == math.ceil(Fraction(60, 90) * 3 * SAMPLE_RATE)  # three beats at 90
    prelude = make(PreludeOptions(count_in=True), bpm=Fraction(60), beats=6, beat_type=8)
    assert prelude is not None
    assert prelude.info["count_in"]["beats"] == 6  # six clicks, one per eighth note
    assert prelude.frames == 3 * SAMPLE_RATE  # an eighth is half a quarter: 6 x 0.5 s


def test_both_come_one_after_the_other() -> None:
    prelude = make(PreludeOptions(tune_up=True, count_in=True), key=A_MINOR)
    assert prelude is not None
    tune = round(TUNE_SECONDS * SAMPLE_RATE) + round(SILENCE_AFTER_TUNE_SECONDS * SAMPLE_RATE)
    assert prelude.frames == tune + 4 * (SAMPLE_RATE // 2)
    assert prelude.info["tune_up"]["note"].startswith("A")
    assert prelude.info["music_starts_at_frame"] == prelude.frames
    assert prelude.samples[tune : tune + 2000].any()  # the first click follows the silence


def test_the_count_in_needs_no_key_signature() -> None:
    assert make(PreludeOptions(count_in=True), key=None) is not None
