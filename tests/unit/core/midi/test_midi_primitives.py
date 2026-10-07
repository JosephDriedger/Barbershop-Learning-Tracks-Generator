"""Ticks, PPQ, tempo and meter encoding: exact where possible, explicit where not."""

from fractions import Fraction

import pytest

from barbershop_tracks.core.midi import (
    DEFAULT_PPQ,
    MAX_PPQ,
    METER_32NDS_PER_QUARTER,
    METER_CLICK_CLOCKS,
    MeterEncoding,
    MidiExportError,
    encode_meter,
    encode_tempo,
    to_ticks,
    validate_ppq,
)
from barbershop_tracks.models import TimeSignature


def code_of(call, *args, **kwargs) -> str:  # type: ignore[no-untyped-def]
    with pytest.raises(MidiExportError) as info:
        call(*args, **kwargs)
    return info.value.code


# --- PPQ ---


def test_the_default_ppq_is_480() -> None:
    assert DEFAULT_PPQ == 480


@pytest.mark.parametrize("ppq", [1, 96, 480, 960, MAX_PPQ])
def test_valid_ppq(ppq: int) -> None:
    assert validate_ppq(ppq) == ppq


@pytest.mark.parametrize("ppq", [0, -1, MAX_PPQ + 1, 0x8000, 65535, 480.0, "480", None, True])
def test_invalid_ppq_is_rejected(ppq: object) -> None:
    assert code_of(validate_ppq, ppq) == "MIDI_PPQ_INVALID"


# --- exact ticks ---


@pytest.mark.parametrize(
    ("position", "ticks"),
    [
        (Fraction(0), 0),
        (Fraction(1), 480),
        (Fraction(1, 2), 240),
        (Fraction(1, 3), 160),  # a triplet eighth
        (Fraction(1, 5), 96),  # a quintuplet
        (Fraction(1, 6), 80),
        (Fraction(1, 16), 30),
        (Fraction(7, 3), 1120),
    ],
)
def test_representable_positions_convert_exactly(position: Fraction, ticks: int) -> None:
    assert to_ticks(position, 480, what="x") == ticks


@pytest.mark.parametrize("position", [Fraction(1, 7), Fraction(1, 9), Fraction(1, 64)])
def test_a_non_integral_tick_is_an_error_never_rounded(position: Fraction) -> None:
    assert code_of(to_ticks, position, 480, what="a note start") == "MIDI_TICK_NOT_INTEGRAL"


def test_a_septuplet_becomes_representable_only_by_choosing_the_ppq() -> None:
    assert code_of(to_ticks, Fraction(1, 7), 480, what="x") == "MIDI_TICK_NOT_INTEGRAL"
    assert to_ticks(Fraction(1, 7), 840, what="x") == 120


def test_the_error_names_what_and_where() -> None:
    with pytest.raises(MidiExportError, match=r"a tempo event at quarter-note position 1/7"):
        to_ticks(Fraction(1, 7), 480, what="a tempo event")


def test_a_negative_position_is_rejected() -> None:
    assert code_of(to_ticks, Fraction(-1), 480, what="x") == "MIDI_TICK_NEGATIVE"


# --- tempo ---


def test_an_integral_microsecond_value_is_exact() -> None:
    encoding = encode_tempo(Fraction(100))
    assert encoding.encoded_us_per_quarter == 600000
    assert encoding.is_exact
    assert encoding.error_us_per_quarter == 0
    assert encoding.bpm_error == 0


def test_a_non_integral_value_is_rounded_and_the_error_is_exact() -> None:
    encoding = encode_tempo(Fraction(90))  # 666666.666... us
    assert encoding.exact_us_per_quarter == Fraction(2000000, 3)
    assert encoding.encoded_us_per_quarter == 666667
    assert encoding.error_us_per_quarter == Fraction(1, 3)
    assert not encoding.is_exact
    assert encoding.bpm_error == Fraction(60_000_000, 666667) - 90
    assert encoding.bpm_error < 0  # a slightly longer quarter is a slightly slower tempo


def test_exact_halves_round_to_even_never_up_or_down_by_habit() -> None:
    down = encode_tempo(Fraction(120_000_000, 2_000_001))  # exactly 1000000.5 us
    up = encode_tempo(Fraction(120_000_000, 2_000_003))  # exactly 1000001.5 us
    assert down.exact_us_per_quarter == Fraction(2000001, 2)
    assert down.encoded_us_per_quarter == 1_000_000  # even
    assert up.encoded_us_per_quarter == 1_000_002  # even


def test_the_decision_uses_no_binary_floating_point() -> None:
    # 60e6 / (60e6 / 666667 + tiny) would be fragile in floats; Fractions are exact
    bpm = Fraction(60_000_000, 666667)
    assert encode_tempo(bpm).encoded_us_per_quarter == 666667
    assert encode_tempo(bpm).is_exact


def test_the_range_of_the_set_tempo_payload_is_checked_by_us() -> None:
    assert encode_tempo(Fraction(60_000_000)).encoded_us_per_quarter == 1
    assert encode_tempo(Fraction(60_000_000, 0xFFFFFF)).encoded_us_per_quarter == 0xFFFFFF
    assert code_of(encode_tempo, Fraction(3)) == "MIDI_TEMPO_UNREPRESENTABLE"  # 20,000,000 us
    assert code_of(encode_tempo, Fraction(120_000_000)) == "MIDI_TEMPO_UNREPRESENTABLE"  # 0.5 -> 0


@pytest.mark.parametrize("bpm", [Fraction(0), Fraction(-5)])
def test_a_non_positive_tempo_is_rejected_defensively(bpm: Fraction) -> None:
    assert code_of(encode_tempo, bpm) == "MIDI_TEMPO_INVALID"


# --- meter ---


@pytest.mark.parametrize(
    ("beats", "beat_type", "exponent"), [(4, 4, 2), (3, 4, 2), (6, 8, 3), (3, 2, 1), (5, 16, 4)]
)
def test_representable_meters(beats: int, beat_type: int, exponent: int) -> None:
    encoding = encode_meter(TimeSignature(position=Fraction(0), beats=beats, beat_type=beat_type))
    assert encoding == MeterEncoding(numerator=beats, denominator_exponent=exponent)


def test_an_unrepresentable_numerator_is_omitted_with_a_reason() -> None:
    result = encode_meter(TimeSignature(position=Fraction(0), beats=256, beat_type=4))
    assert isinstance(result, str)
    assert "256" in result


def test_the_auxiliary_fields_are_documented_constants_not_source_facts() -> None:
    assert METER_CLICK_CLOCKS == 24
    assert METER_32NDS_PER_QUARTER == 8
