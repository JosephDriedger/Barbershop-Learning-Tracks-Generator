"""The 50 synthetic repeat fixtures against MuseScore's MIDI oracle (an oracle, not the spec).

Where we accept a structure, our performed onsets must equal MuseScore's. Where MuseScore
silently does something the specification does not support (nesting, last-part-wins, the
containing-measure reading of a barline, ambiguous returns) we report a specific ERROR instead;
each such case is a permanent divergence test. Ties across repeats are M3d2.
"""

import json
from pathlib import Path

import pytest

from barbershop_tracks.core.musicxml import ParseResult, parse_musicxml

pytestmark = pytest.mark.usefixtures("no_network")

DIRECTORY = Path(__file__).resolve().parents[3] / "fixtures" / "musicxml" / "repeats"
PPQ = 480

# Accepted, and the performed onsets equal MuseScore's.
MATCHES_MUSESCORE = [
    "r01_simple",
    "r01_times_1",
    "r01_times_2",
    "r01_times_3",
    "r01_times_4",
    "r01_times_9",
    "r02_backward_no_forward",
    "r02b_back_at_first_measure",
    "r02d_forward_no_backward",
    "r04_consecutive_one_measure",
    "r04b_consecutive_two_measure",
    "r06_two_parts_agree",
    "r08_tempo_inside",
    "r08b_tempo_before_repeat",
    "r09_meter_inside",
    "q06_back_no_location",  # a backward repeat's default location is right
    "s01_tempo_carry",
    "s02_tempo_start_marked",
    "s03_tempo_after_repeat_only",
    "s04_meter_carry",
    "s05_repeat_at_end",
    "s08_consecutive_times",
]

# Rejected by us with this ERROR; MuseScore plays *something* (see the oracle JSON).
DIVERGES = {
    "r01_times_0": "REPEAT_TIMES_INVALID",
    "r01_times_x": "REPEAT_TIMES_INVALID",
    "r02c_second_back_no_forward": "REPEAT_START_AMBIGUOUS",
    "s06_fwd_then_back_nofwd": "REPEAT_START_AMBIGUOUS",
    "r03_nested": "REPEAT_NESTED_UNSUPPORTED",
    "r03b_nested_times": "REPEAT_NESTED_UNSUPPORTED",
    "s07_two_forwards": "REPEAT_NESTED_UNSUPPORTED",
    "r06b_only_p1_marks": "REPEAT_STRUCTURE_CONFLICT",
    "r06c_different_ranges": "REPEAT_STRUCTURE_CONFLICT",
    "r06d_different_times": "REPEAT_STRUCTURE_CONFLICT",
    "s09_parts_forward_only_in_p2": "REPEAT_STRUCTURE_CONFLICT",
    "s10_parts_back_only_p1_shorter": "REPEAT_STRUCTURE_CONFLICT",
    "r12_after_jump": "REPEAT_AFTER_JUMP_UNSUPPORTED",
    "r13_forward_at_right": "REPEAT_BARLINE_PLACEMENT",
    "q01_fwd_right_of_m1": "REPEAT_BARLINE_PLACEMENT",
    "q02_back_left_of_m3": "REPEAT_BARLINE_PLACEMENT",
    "q03_back_left_of_m1": "REPEAT_BARLINE_PLACEMENT",
    "q04_fwd_right_of_last": "REPEAT_BARLINE_PLACEMENT",
    "q05_fwd_left_back_left_next": "REPEAT_BARLINE_PLACEMENT",
    "q07_fwd_no_location": "REPEAT_BARLINE_PLACEMENT",
    "q08_mid_measure_back": "REPEAT_MID_MEASURE",
}

# Accepted; only the performed order is checked here (ties, pickup completion: M3d2).
# Letters are source measure indices: A = 0, B = 1, ...
ORDER_ONLY = {
    "r05_pickup_fwd_in_pickup": "ABCABCD",
    "r05b_pickup_fwd_after_pickup": "ABCBCD",
    "r05c_pickup_back_no_forward": "ABCABCD",
    "r07_tie_out_of_repeat": "ABABCD",
    "r07b_tie_across_jump": "ABABC",
    "r07c_tie_into_repeat_start": "ABCBCD",
    "r07d_tie_inside_repeat": "ABABC",
}


def _parse(name: str) -> ParseResult:
    return parse_musicxml(DIRECTORY / f"{name}.musicxml")


def _oracle(name: str) -> list[list[tuple[int, int]]]:
    data = json.loads((DIRECTORY / f"{name}.oracle.json").read_text(encoding="utf-8"))
    assert data["ppq"] == PPQ
    return [sorted((n["tick"], n["midi_note"]) for n in track) for track in data["tracks"]]


def test_every_fixture_is_classified() -> None:
    on_disk = {p.stem for p in DIRECTORY.glob("*.musicxml")}
    classified = set(MATCHES_MUSESCORE) | set(DIVERGES) | set(ORDER_ONLY)
    assert len(on_disk) == 50
    assert on_disk == classified


@pytest.mark.parametrize("name", MATCHES_MUSESCORE)
def test_performed_onsets_equal_the_musescore_midi(name: str) -> None:
    result = _parse(name)
    assert not result.issues.has_errors, [str(i) for i in result.issues]
    assert result.performed is not None
    lines = result.performed.lines
    tracks = _oracle(name)
    assert len(lines) == len(tracks)
    for line, track in zip(lines, tracks, strict=True):
        onsets = []
        for event in line.part.sounding_notes:
            ticks = event.start * PPQ
            assert ticks.denominator == 1
            assert event.midi_note is not None
            onsets.append((int(ticks), event.midi_note))
        assert sorted(onsets) == track


@pytest.mark.parametrize(("name", "code"), sorted(DIVERGES.items()))
def test_unsupported_structures_are_specific_errors_not_musescore_behaviour(
    name: str, code: str
) -> None:
    result = _parse(name)
    assert code in [i.code for i in result.issues]
    assert result.issues.has_errors
    assert result.performed is not None
    assert result.performed.plan.is_identity  # we never adopt MuseScore's reinterpretation


@pytest.mark.parametrize(("name", "expected"), sorted(ORDER_ONLY.items()))
def test_accepted_structures_play_in_the_expected_order(name: str, expected: str) -> None:
    result = _parse(name)
    assert result.performed is not None
    letters = "ABCDEFG"
    assert "".join(letters[p.source_index] for p in result.performed.plan.played) == expected
