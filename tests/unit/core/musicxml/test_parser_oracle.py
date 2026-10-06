"""Compare the parser with MuseScore's own MIDI export (an *oracle*, not the specification).

The MusicXML specification defines the format; these tests only show that, on the research
fixtures, our exact timeline and sounding pitches agree with what MuseScore 4.7.4 plays.
Plain repeats are compared in performed order; endings are rejected until M3e.
"""

import json
from pathlib import Path

import pytest

from barbershop_tracks.core.musicxml import ParseResult, parse_musicxml
from barbershop_tracks.models import Part

pytestmark = pytest.mark.usefixtures("no_network")

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "musicxml"
PPQ = 480
Onset = tuple[int, int]  # (tick at 480 PPQ, MIDI note)

# Fixtures without repeats or jumps that M3b1 must reproduce exactly.
PLAIN = [
    "e10_lyrics",
    "e1_control_treble",
    "e1_tenor_clef8vb_pitch_oct4",
    "e1_tenor_clef8vb_pitch_oct5",
    "e2_transpose_bb",
    "e2b_clef8vb_plus_transpose",
    "e2c_transpose_oct_only",
    "e4_forward_gap",
    "e5_pickup",
    "e7_triplet",
]
PLAIN_REPEATS = ["e8_simple_repeat", "e8b_repeat_times3"]
ENDINGS = ["e9_volta", "e12_volta_1_2_3"]
VARIANTS = ["inputs", "musescore_roundtrip"]


def _oracle(name: str) -> list[list[Onset]]:
    data = json.loads((FIXTURES / "oracle" / f"{name}.json").read_text())
    assert data["ppq"] == PPQ
    return [sorted((n["tick"], n["midi_note"]) for n in track) for track in data["tracks"]]


def _onsets(parts: list[Part]) -> list[Onset]:
    result: list[Onset] = []
    for part in parts:
        for event in part.sounding_notes:
            ticks = event.start * PPQ
            assert ticks.denominator == 1, f"{event.start} is not exact at {PPQ} PPQ"
            assert event.midi_note is not None
            result.append((int(ticks), event.midi_note))
    return sorted(result)


def _parse(variant: str, name: str) -> ParseResult:
    return parse_musicxml(FIXTURES / variant / f"{name}.musicxml")


def _parts(result: ParseResult) -> list[Part]:
    assert result.song is not None
    return list(result.song.parts)


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("name", PLAIN)
def test_single_staff_fixtures_match_the_musescore_midi(variant: str, name: str) -> None:
    result = _parse(variant, name)
    assert not result.issues.has_errors, [str(i) for i in result.issues]
    expected = [onset for track in _oracle(name) for onset in track]
    assert _onsets(_parts(result)) == sorted(expected)


@pytest.mark.parametrize("variant", VARIANTS)
def test_tied_notes_appear_as_separate_source_notes(variant: str) -> None:
    # MuseScore's MIDI merges the tie into one note-on at tick 1440. The parser keeps both
    # source notes (merging is a later, derived step), so the only difference is the
    # tie-continuation note at the start of measure 2.
    result = _parse(variant, "e6_ties")
    assert not result.issues.has_errors
    expected = sorted([onset for track in _oracle("e6_ties") for onset in track] + [(1920, 67)])
    assert _onsets(_parts(result)) == expected


@pytest.mark.parametrize("variant", VARIANTS)
def test_shared_staves_match_the_musescore_tracks_staff_by_staff(variant: str) -> None:
    result = _parse(variant, "e3_shared_staves")
    assert not result.issues.has_errors
    tracks = _oracle("e3_shared_staves")  # MuseScore writes one MIDI track per staff
    parts = _parts(result)
    staff1 = [p for p in parts if p.source_line is not None and p.source_line.staff == 1]
    staff2 = [p for p in parts if p.source_line is not None and p.source_line.staff == 2]
    assert len(staff1) == len(staff2) == 2
    assert _onsets(staff1) == tracks[0]
    assert _onsets(staff2) == tracks[1]


def test_musescore_renumbers_voices_across_staves() -> None:
    # Hand-written input uses voices 1,2 / 3,4; MuseScore's re-export uses 1,2 / 5,6.
    original = [p.part_id for p in _parts(_parse("inputs", "e3_shared_staves"))]
    exported = [p.part_id for p in _parts(_parse("musescore_roundtrip", "e3_shared_staves"))]
    assert original == ["P1/s1/v1", "P1/s1/v2", "P1/s2/v3", "P1/s2/v4"]
    assert exported == ["P1/s1/v1", "P1/s1/v2", "P1/s2/v5", "P1/s2/v6"]


@pytest.mark.parametrize("variant", VARIANTS)
def test_four_separate_parts_match_the_musescore_tracks(variant: str) -> None:
    result = _parse(variant, "e3b_four_parts")
    assert not result.issues.has_errors
    tracks = _oracle("e3b_four_parts")
    parts = _parts(result)
    assert [p.part_id for p in parts] == ["P1/s1/v1", "P2/s1/v1", "P3/s1/v1", "P4/s1/v1"]
    for part, track in zip(parts, tracks, strict=True):
        assert _onsets([part]) == track


@pytest.mark.parametrize("variant", VARIANTS)
def test_forward_gap_voice_two_starts_on_beat_three(variant: str) -> None:
    parts = _parts(_parse(variant, "e4_forward_gap"))
    voice2 = next(p for p in parts if p.part_id.endswith("/v2"))
    assert [e.start for e in voice2.events] == [2, 3]
    assert [e.beat for e in voice2.events] == [3, 4]


@pytest.mark.parametrize("variant", VARIANTS)
def test_pickup_fixture_keeps_measure_zero(variant: str) -> None:
    events = _parts(_parse(variant, "e5_pickup"))[0].events
    assert events[0].measure == 0
    assert events[0].start == 0
    assert events[0].beat == 1
    assert events[1].measure == 1


@pytest.mark.parametrize("variant", VARIANTS)
def test_triplet_fixture_is_exact_at_480_ppq(variant: str) -> None:
    events = _parts(_parse(variant, "e7_triplet"))[0].events
    assert [int(e.start * PPQ) for e in events[:3]] == [0, 160, 320]


def test_transposed_fixtures_keep_the_written_pitch() -> None:
    result = _parse("inputs", "e2_transpose_bb")
    event = _parts(result)[0].events[0]
    assert str(event.written_pitch) == "C5"
    assert str(event.sounding_pitch) == "Bb4"


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("name", PLAIN_REPEATS)
def test_plain_repeat_fixtures_perform_like_the_musescore_midi(variant: str, name: str) -> None:
    result = _parse(variant, name)
    assert not result.issues.has_errors, [str(i) for i in result.issues]
    assert result.performed is not None
    notes = [e for line in result.performed.lines for e in line.part.sounding_notes]
    onsets = sorted((int(e.start * PPQ), e.midi_note) for e in notes if e.midi_note is not None)
    assert onsets == sorted(onset for track in _oracle(name) for onset in track)


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("name", ENDINGS)
def test_ending_fixtures_are_rejected_until_m3e(variant: str, name: str) -> None:
    result = _parse(variant, name)
    assert "ENDING_NOT_SUPPORTED_YET" in [i.code for i in result.issues]
    assert result.issues.has_errors


def test_dacapo_fixture_is_rejected() -> None:
    result = _parse("inputs", "e11_dacapo")
    assert "UNSUPPORTED_JUMP" in [i.code for i in result.issues]


def test_compressed_fixture_parses_like_the_plain_one() -> None:
    plain = parse_musicxml(
        FIXTURES / "musescore_roundtrip" / "e1_tenor_clef8vb_pitch_oct4.musicxml"
    )
    packed = parse_musicxml(FIXTURES / "musescore_roundtrip" / "e1_tenor_clef8vb_pitch_oct4.mxl")
    assert _onsets(_parts(plain)) == _onsets(_parts(packed))
    assert [str(p.part_id) for p in _parts(plain)] == [str(p.part_id) for p in _parts(packed)]
