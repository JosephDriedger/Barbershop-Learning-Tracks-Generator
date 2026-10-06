"""The original two-part / four-voice TTBB-layout fixtures, with MuseScore oracle comparison.

The fixtures are synthetic. They mirror the *structure* seen in real MuseScore barbershop
exports (two parts, shared staves, implied staff, divisions 12, a pickup, a tie across a
barline, a meter change, a forward gap, and tempo declared in one part, both, or neither).
"""

import json
from fractions import Fraction
from pathlib import Path

import pytest

from barbershop_tracks.core.musicxml import ParseResult, parse_musicxml
from barbershop_tracks.core.timeline import merge_tied_notes
from barbershop_tracks.models import Part

pytestmark = pytest.mark.usefixtures("no_network")

F = Fraction
TTBB = Path(__file__).resolve().parents[3] / "fixtures" / "musicxml" / "ttbb"
PPQ = 480
VARIANTS = ["inputs", "musescore_roundtrip"]
LINES = ["P1/s1/v1", "P1/s1/v2", "P2/s1/v1", "P2/s1/v2"]
NAMES = [
    "ttbb_layout",
    "ttbb_layout_shared_tempo",
    "ttbb_layout_tempo_change",
    "ttbb_layout_tempo_first_part_only",
]


def _parse(variant: str, name: str) -> ParseResult:
    return parse_musicxml(TTBB / variant / f"{name}.musicxml")


def _parts(result: ParseResult) -> list[Part]:
    assert result.song is not None
    return list(result.song.parts)


def _line(result: ParseResult, line_id: str) -> Part:
    return next(p for p in _parts(result) if p.part_id == line_id)


def _oracle(name: str) -> dict[str, object]:
    data: dict[str, object] = json.loads((TTBB / "oracle" / f"{name}.json").read_text())
    assert data["ppq"] == PPQ
    return data


def _oracle_onsets(name: str) -> list[tuple[int, int]]:
    tracks = _oracle(name)["tracks"]
    assert isinstance(tracks, list)
    return sorted((n["tick"], n["midi_note"]) for track in tracks for n in track)


def _performed(result: ParseResult) -> list[tuple[int, int]]:
    onsets: list[tuple[int, int]] = []
    for part in _parts(result):
        for performed in merge_tied_notes(part.events, part_id=part.part_id).notes:
            if performed.is_rest:
                continue
            ticks = performed.start * PPQ
            assert ticks.denominator == 1
            assert performed.pitch is not None
            onsets.append((int(ticks), performed.pitch.midi_note))
    return sorted(onsets)


# --- structure -------------------------------------------------------------------------


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("name", NAMES)
def test_parses_cleanly_into_four_source_lines_without_roles(variant: str, name: str) -> None:
    result = _parse(variant, name)
    assert not result.issues, [str(i) for i in result.issues]
    assert [p.part_id for p in _parts(result)] == LINES
    assert all(p.role is None for p in _parts(result))  # names like TENOR never become roles
    assert all(p.source_line is not None for p in _parts(result))


@pytest.mark.parametrize("variant", VARIANTS)
def test_part_names_collapse_for_display_and_keep_the_source_text(variant: str) -> None:
    result = _parse(variant, "ttbb_layout")
    first, third = _line(result, "P1/s1/v1"), _line(result, "P2/s1/v2")
    assert first.name == "TENOR LEAD"
    assert first.source_name == "TENOR\nLEAD"
    assert third.name == "BARI BASS"
    assert third.source_name == "BARI\nBASS"


@pytest.mark.parametrize("variant", VARIANTS)
def test_title_is_taken_from_the_work_title(variant: str) -> None:
    song = _parse(variant, "ttbb_layout").song
    assert song is not None
    assert song.title == "Synthetic TTBB Layout"


@pytest.mark.parametrize("variant", VARIANTS)
def test_clefs_are_informational_and_never_change_pitch(variant: str) -> None:
    result = _parse(variant, "ttbb_layout")
    assert result.song is not None
    clefs = {(c.part_id, c.sign, c.octave_change) for c in result.song.clef_changes}
    assert clefs == {("P1", "G", -1), ("P2", "F", 0)}
    assert all(n.transform.is_identity for p in _parts(result) for n in p.events)


@pytest.mark.parametrize("variant", VARIANTS)
def test_pickup_keeps_measure_zero_and_exact_positions(variant: str) -> None:
    result = _parse(variant, "ttbb_layout")
    first = _line(result, "P1/s1/v1").events[0]
    assert (first.measure, first.start, first.beat) == (0, F(0), F(1))
    assert _line(result, "P1/s1/v1").events[1].start == 1  # measure 1 begins after the pickup


@pytest.mark.parametrize("variant", VARIANTS)
def test_forward_gap_voice_two_enters_on_beat_two(variant: str) -> None:
    result = _parse(variant, "ttbb_layout")
    in_measure_three = [e for e in _line(result, "P1/s1/v2").events if e.measure == 3]
    assert [(e.beat, e.start) for e in in_measure_three] == [
        (F(2), F(1 + 4 + 3 + 1))
    ]  # pickup + m1 + m2, then beat 2
    assert not any(e.is_rest for e in in_measure_three)  # a gap, not a rest


@pytest.mark.parametrize("variant", VARIANTS)
def test_tie_across_the_barline_merges_in_the_performance_view(variant: str) -> None:
    result = _parse(variant, "ttbb_layout")
    line = _line(result, "P1/s1/v2")
    assert sum(e.tied_to_next for e in line.events) == 1
    merged = merge_tied_notes(line.events, part_id=line.part_id)
    assert not merged.issues
    group = next(p for p in merged.notes if p.is_tied_group)
    assert (group.measure, group.duration) == (1, F(1) + F(2))  # quarter + half
    assert len(line.events) == len(merged.notes) + 1  # the Song itself keeps both source notes


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("name", NAMES)
def test_meter_map_has_one_change_not_one_per_part(variant: str, name: str) -> None:
    song = _parse(variant, name).song
    assert song is not None
    assert [(s.position, s.beats, s.beat_type) for s in song.time_signatures] == [
        (F(0), 4, 4),
        (F(5), 3, 4),  # pickup (1) + one 4/4 measure
    ]


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("name", NAMES)
def test_every_note_agrees_with_the_musescore_midi_after_tie_merging(
    variant: str, name: str
) -> None:
    result = _parse(variant, name)
    assert _performed(result) == _oracle_onsets(name)


# --- tempo ------------------------------------------------------------------------------


def _our_tempos(result: ParseResult) -> list[tuple[int, Fraction]]:
    assert result.song is not None
    out: list[tuple[int, Fraction]] = []
    for t in result.song.tempo_map:
        ticks = t.position * PPQ
        assert ticks.denominator == 1
        out.append((int(ticks), t.bpm))
    return out


def _oracle_tempos(name: str) -> list[tuple[int, int]]:
    tempos = _oracle(name)["tempos"]
    assert isinstance(tempos, list)
    return [(t["tick"], t["microseconds_per_quarter"]) for t in tempos]


def _assert_same_tempos(ours: list[tuple[int, Fraction]], theirs: list[tuple[int, int]]) -> None:
    """MIDI stores whole microseconds per quarter; compare as exact rationals within 1 us."""
    assert [tick for tick, _ in ours] == [tick for tick, _ in theirs]
    for (_, bpm), (_, usec) in zip(ours, theirs, strict=True):
        assert abs(F(60_000_000) / bpm - usec) < 1


@pytest.mark.parametrize("variant", VARIANTS)
def test_no_tempo_fixture_leaves_the_tempo_unresolved(variant: str) -> None:
    result = _parse(variant, "ttbb_layout")
    assert result.song is not None
    assert result.song.tempo_map == ()  # never a default, whatever MuseScore's MIDI says
    # DOCUMENTED DIVERGENCE: MuseScore writes its default 120 bpm into the MIDI.
    assert _oracle_tempos("ttbb_layout") == [(0, 500000)]


@pytest.mark.parametrize("variant", VARIANTS)
def test_shared_tempo_in_both_parts_is_one_event(variant: str) -> None:
    result = _parse(variant, "ttbb_layout_shared_tempo")
    assert _our_tempos(result) == [(0, F(96))]
    _assert_same_tempos(_our_tempos(result), _oracle_tempos("ttbb_layout_shared_tempo"))


@pytest.mark.parametrize("variant", VARIANTS)
def test_later_tempo_change_declared_in_both_parts(variant: str) -> None:
    result = _parse(variant, "ttbb_layout_tempo_change")
    assert _our_tempos(result) == [(0, F(96)), (5 * PPQ, F(72))]
    _assert_same_tempos(_our_tempos(result), _oracle_tempos("ttbb_layout_tempo_change"))


@pytest.mark.parametrize("variant", VARIANTS)
def test_tempo_declared_in_the_first_part_only(variant: str) -> None:
    result = _parse(variant, "ttbb_layout_tempo_first_part_only")
    assert _our_tempos(result) == [(0, F(96)), (5 * PPQ, F(72))]
    _assert_same_tempos(_our_tempos(result), _oracle_tempos("ttbb_layout_tempo_first_part_only"))


def test_the_same_music_with_and_without_tempo_has_identical_notes() -> None:
    plain = _performed(_parse("inputs", "ttbb_layout"))
    assert plain == _performed(_parse("inputs", "ttbb_layout_shared_tempo"))
    assert plain == _performed(_parse("inputs", "ttbb_layout_tempo_change"))
