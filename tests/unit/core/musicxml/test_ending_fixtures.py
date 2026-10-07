"""The 38 synthetic ending fixtures against MuseScore's MIDI oracle (an oracle, not the spec).

Where we accept a structure, our performed onsets must equal MuseScore's. Where MuseScore
loses music, reinterprets a marker or lets one part win, we report a specific ERROR instead and
never emulate it: each such case is a permanent divergence test. Ties across endings (and the
skip-aware tie/lyric handling) are M3e2, so tie fixtures check the performed order only.
"""

import json
from pathlib import Path

import pytest

from barbershop_tracks.core.musicxml import ParseResult, parse_musicxml

pytestmark = pytest.mark.usefixtures("no_network")

DIRECTORY = Path(__file__).resolve().parents[3] / "fixtures" / "musicxml" / "endings"
PPQ = 480

# Accepted, and the performed onsets equal MuseScore's.
MATCHES_MUSESCORE = [
    "v01_standard",
    "v01b_second_ending_stop",
    "v02_first_ending_two_measures",
    "v03_second_ending_two_measures",
    "v04_times3_ending_1_2_then_3",
    "v05_three_endings",
    "v05b_three_endings_times3",
    "v10_first_ending_discontinue",
    "v14_ending_at_end_of_score",
    "v15_two_consecutive_voltas",
    "v18_ending_before_forward_no_forward",
    "v19_backward_inside_ending_before_its_stop",
    "v20_two_parts_agree",
    "x01_tempo_in_endings",
    "x02_meter_in_endings",
    "y01_pickup_with_endings",
]

# Rejected by us with this ERROR; MuseScore plays *something* (see the oracle JSON).
DIVERGES = {
    "v06_times3_only_endings_1_2": "REPEAT_TIMES_ENDINGS_CONFLICT",
    "v07_endings_without_repeat": "ENDING_WITHOUT_REPEAT",
    "v08_first_ending_stop_no_backward": "ENDING_WITHOUT_REPEAT",
    "v09a_missing_number": "ENDING_NUMBER_INVALID",
    "v09b_number_x": "ENDING_NUMBER_INVALID",
    "v09c_number_0": "ENDING_NUMBER_INVALID",
    "v09d_number_range": "ENDING_NUMBER_INVALID",
    "v09e_number_spaces": "ENDING_NUMBER_UNSPECIFIED",
    "v09f_number_leading_zero": "ENDING_NUMBER_INVALID",
    "v09g_number_3_only": "ENDING_PASS_MISSING",
    "v11_start_without_stop": "ENDING_UNCLOSED",
    "v12_stop_without_start": "ENDING_STOP_WITHOUT_START",
    "v13_only_second_ending": "ENDING_PASS_MISSING",
    "v16_start_at_right_of_previous": "ENDING_BARLINE_PLACEMENT",
    "v17_ending1_numbered_1_2_comma_times2": "ENDING_STRUCTURE_UNSUPPORTED",
    "v20b_two_parts_only_p1_endings": "ENDING_STOP_WITHOUT_START",
}

# Accepted; only the performed order is checked here (ties and short measures: M3e2 / policy).
# Letters are source measure indices: A = 0, B = 1, ...
ORDER_ONLY = {
    "w01_tie_into_ending1": "ABCABDE",
    "w02_tie_into_ending2_from_ending1_end": "ABCABDE",
    "w03_tie_out_of_ending2": "ABCABDE",
    "w04_tie_from_before_ending_to_ending2": "ABCABDE",
    "w05_tie_from_ending1_to_repeat_start": "ABCABDE",
    "y02_pickup_inside_repeat": "ABCABDE",
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
    assert len(on_disk) == 38
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


def test_musescore_drops_music_where_we_refuse() -> None:
    # v07/v08: MuseScore plays only A B C (three measures) and loses everything after.
    oracle = _oracle("v07_endings_without_repeat")[0]
    assert len(oracle) == 3
    ours = _parse("v07_endings_without_repeat").performed
    assert ours is not None
    assert len(ours.plan.played) == 5  # the written song stays whole; the ERROR blocks it


def test_the_volta_oracles_from_the_m3b_research_are_covered_elsewhere() -> None:
    # e9_volta and e12_volta_1_2_3 are compared in test_parser_oracle (both variants).
    assert (Path(__file__).resolve().parents[3] / "fixtures/musicxml/oracle/e9_volta.json").exists()
