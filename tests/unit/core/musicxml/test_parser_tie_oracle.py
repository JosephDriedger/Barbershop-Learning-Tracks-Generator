"""Tie merging compared with MuseScore's MIDI export.

Two kinds of result are kept distinct, and both are asserted so a future change cannot quietly
turn one into the other:

* AGREEMENT: after ``merge_tied_notes`` our performed attacks equal MuseScore's MIDI note-ons.
* DOCUMENTED DIVERGENCE: where MusicXML 4.0 and/or safety make us stricter than MuseScore, the
  test asserts our (standards-based) behavior and cites the oracle. These are intentional; do
  not "fix" them to copy MuseScore.
"""

import json
from pathlib import Path

import pytest

from barbershop_tracks.core.musicxml import ParseResult, parse_musicxml
from barbershop_tracks.core.timeline import merge_tied_notes

pytestmark = pytest.mark.usefixtures("no_network")

ROOT = Path(__file__).resolve().parents[3] / "fixtures" / "musicxml"
TIES = ROOT / "tempo_ties"
PPQ = 480
Onset = tuple[int, int]


def _oracle(directory: Path, name: str) -> list[Onset]:
    data = json.loads((directory / "oracle" / f"{name}.json").read_text())
    assert data["ppq"] == PPQ
    return sorted((n["tick"], n["midi_note"]) for track in data["tracks"] for n in track)


def _performed(result: ParseResult) -> list[Onset]:
    """Attacks of all lines after tie merging (rests dropped), at 480 PPQ."""
    assert result.song is not None
    onsets: list[Onset] = []
    for part in result.song.parts:
        for performed in merge_tied_notes(part.events, part_id=part.part_id).notes:
            if performed.is_rest:
                continue
            ticks = performed.start * PPQ
            assert ticks.denominator == 1
            assert performed.pitch is not None
            onsets.append((int(ticks), performed.pitch.midi_note))
    return sorted(onsets)


def _codes(result: ParseResult) -> set[str]:
    return {issue.code for issue in result.issues}


# --- agreement --------------------------------------------------------------------------


@pytest.mark.parametrize("variant", ["inputs", "musescore_roundtrip"])
def test_e6_is_an_exact_match_after_merging(variant: str) -> None:
    result = parse_musicxml(ROOT / variant / "e6_ties.musicxml")
    assert not result.issues.has_errors
    assert _performed(result) == _oracle(ROOT, "e6_ties")


@pytest.mark.parametrize("variant", ["inputs", "musescore_roundtrip"])
@pytest.mark.parametrize("name", ["u_tie_and_tied", "u_chain", "u_enharmonic"])
def test_valid_ties_match_musescore_after_merging(variant: str, name: str) -> None:
    result = parse_musicxml(TIES / variant / f"{name}.musicxml")
    assert not result.issues.has_errors, [str(i) for i in result.issues]
    assert _performed(result) == _oracle(TIES, name)


def test_chain_is_one_performed_attack() -> None:
    result = parse_musicxml(TIES / "inputs" / "u_chain.musicxml")
    assert result.song is not None
    notes = merge_tied_notes(result.song.parts[0].events, part_id="x").notes
    assert [len(p.source) for p in notes] == [3, 1]
    assert notes[0].duration == 3


def test_enharmonic_tie_in_musescore_is_matched_by_sounding_pitch() -> None:
    result = parse_musicxml(TIES / "inputs" / "u_enharmonic.musicxml")
    assert result.song is not None
    first = merge_tied_notes(result.song.parts[0].events, part_id="x").notes[0]
    assert [str(n.written_pitch) for n in first.source] == ["C#4", "Db4"]  # spellings kept
    assert str(first.pitch) == "C#4"
    assert (0, 61) in _oracle(TIES, "u_enharmonic")  # MuseScore also plays one attack at 61


def test_tie_without_tied_agrees_on_notes_and_only_warns() -> None:
    result = parse_musicxml(TIES / "inputs" / "u_tie_only.musicxml")
    assert _codes(result) == {"TIE_WITHOUT_TIED"}
    assert not result.issues.has_errors
    assert _performed(result) == _oracle(TIES, "u_tie_only")


# --- documented divergences (we follow MusicXML 4.0 / safety, not MuseScore) -----------


def test_divergence_tied_without_tie_is_an_error_where_musescore_merges() -> None:
    result = parse_musicxml(TIES / "inputs" / "u_tied_only.musicxml")
    assert "TIED_WITHOUT_TIE" in _codes(result)
    assert result.issues.has_errors
    oracle = _oracle(TIES, "u_tied_only")
    performed = _performed(result)
    assert oracle == [(0, 60), (960, 64), (1440, 65)]  # MuseScore treated <tied> as a tie
    assert (480, 60) in performed  # we did NOT: <tie> is the sound tie
    assert len(performed) == len(oracle) + 1


def test_musescore_reexport_of_that_file_is_consistent_so_it_loads_cleanly() -> None:
    # MuseScore normalizes the file on export (it writes both <tie> and <tied>), so its own
    # output never trips the TIED_WITHOUT_TIE error.
    result = parse_musicxml(TIES / "musescore_roundtrip" / "u_tied_only.musicxml")
    assert not result.issues.has_errors
    assert _performed(result) == _oracle(TIES, "u_tied_only")


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("u_pitch_mismatch", "TIE_PITCH_MISMATCH"),
        ("u_unmatched_start", "TIE_UNMATCHED_START"),
        ("u_unmatched_stop", "TIE_UNMATCHED_STOP"),
    ],
)
def test_divergence_invalid_ties_are_errors_where_musescore_just_plays_every_note(
    name: str, code: str
) -> None:
    result = parse_musicxml(TIES / "inputs" / f"{name}.musicxml")
    assert code in _codes(result)
    assert result.issues.has_errors
    # The notes still come out as separate attacks, exactly as MuseScore plays them.
    assert _performed(result) == _oracle(TIES, name)


def test_every_tie_fixture_is_covered_by_one_of_the_groups_above() -> None:
    covered = {
        "u_tie_and_tied", "u_chain", "u_enharmonic", "u_tie_only", "u_tied_only",
        "u_pitch_mismatch", "u_unmatched_start", "u_unmatched_stop",
    }  # fmt: skip
    present = {p.stem for p in (TIES / "inputs").glob("u_*.musicxml")}
    assert present == covered
