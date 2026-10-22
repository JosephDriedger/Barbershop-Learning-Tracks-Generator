"""Following the tempo MuseScore plays (ritardando, fermata, "a tempo") when it can be trusted."""

from fractions import Fraction
from pathlib import Path

import pytest

from barbershop_tracks.core.musicxml import ParseResult, parse_musicxml
from barbershop_tracks.core.musicxml.convert import OpenedScore
from barbershop_tracks.core.musicxml.playback import (
    NOT_USED,
    apply_playback_tempo,
    parse_with_playback_tempo,
)
from barbershop_tracks.models import TempoChange
from smf_builders import midi, tempo_event, track
from xml_builders import attributes, measure, parse_text, quarters, score, tempo_direction

pytestmark = pytest.mark.usefixtures("no_network")

FOUR = quarters(("C", 4), ("D", 4), ("E", 4), ("F", 4))


def change(position: Fraction | int, bpm: Fraction | float) -> TempoChange:
    return TempoChange(position=Fraction(position), bpm=Fraction(bpm))


def parsed(tmp_path: Path, *, with_tempo: bool = True) -> ParseResult:
    head = tempo_direction("63") if with_tempo else ""
    return parse_text(tmp_path, score(measure(1, attributes() + head + FOUR)))


RITARDANDO = [change(0, 63), change(Fraction(3, 2), 59), change(Fraction(5, 2), 47), change(3, 63)]


def test_the_playback_tempo_becomes_the_tempo_of_the_performance(tmp_path: Path) -> None:
    result, done = apply_playback_tempo(parsed(tmp_path), RITARDANDO)
    assert result.performed is not None
    assert result.performed.tempo_events == tuple(RITARDANDO)
    assert done.applied
    assert done.changes == 3
    assert "3 tempo changes" in done.note
    assert done.as_record()["applied"] is True


def test_the_score_itself_and_its_own_tempo_marks_are_left_as_they_were(tmp_path: Path) -> None:
    before = parsed(tmp_path)
    result, _ = apply_playback_tempo(before, RITARDANDO)
    assert result.song is before.song
    assert result.issues is before.issues


def test_a_score_with_no_tempo_of_its_own_is_not_given_one(tmp_path: Path) -> None:
    before = parsed(tmp_path, with_tempo=False)
    result, done = apply_playback_tempo(before, RITARDANDO)
    assert result is before
    assert done is NOT_USED  # TEMPO_MISSING stays, to be resolved by the person


def test_playback_that_disagrees_with_a_tempo_mark_is_not_used_and_says_so(tmp_path: Path) -> None:
    before = parsed(tmp_path)
    result, done = apply_playback_tempo(before, [change(0, 100), change(3, 63)])
    assert result is before
    assert not done.applied
    assert "does not agree" in done.note
    assert "ritardando" in done.note  # what is lost by not following it


def test_a_difference_below_a_hundredth_of_a_beat_is_the_same_tempo(tmp_path: Path) -> None:
    result, done = apply_playback_tempo(
        parsed(tmp_path), [change(0, Fraction(62999, 1000)), *RITARDANDO[1:]]
    )
    assert done.applied
    assert result.performed is not None


def test_playback_that_adds_nothing_is_not_mentioned(tmp_path: Path) -> None:
    before = parsed(tmp_path)
    result, done = apply_playback_tempo(before, [change(0, 63)])
    assert result is before
    assert done is NOT_USED


def test_playback_must_start_at_the_beginning(tmp_path: Path) -> None:
    before = parsed(tmp_path)
    result, done = apply_playback_tempo(before, [change(1, 63), change(2, 60)])
    assert result is before
    assert done is NOT_USED


def test_no_playback_changes_nothing(tmp_path: Path) -> None:
    before = parsed(tmp_path)
    assert apply_playback_tempo(before, []) == (before, NOT_USED)


def opened_with(path: Path, playback: Path | None) -> OpenedScore:
    return OpenedScore(path, path, "0" * 64, None, playback)


def test_a_midi_file_beside_the_score_is_read_and_followed(tmp_path: Path) -> None:
    xml = tmp_path / "score.musicxml"
    xml.write_text(score(measure(1, attributes() + tempo_direction("63") + FOUR)), encoding="utf-8")
    playback = tmp_path / "score.mid"
    steps = [tempo_event(0, 63), tempo_event(720, 59), tempo_event(480, 47)]
    playback.write_bytes(midi(track(*steps)))
    result, done = parse_with_playback_tempo(opened_with(xml, playback), parse_musicxml)
    assert done.applied
    assert result.performed is not None
    assert [float(t.bpm) for t in result.performed.tempo_events] == [63.0, 59.0, 47.0]


@pytest.mark.parametrize("playback", ["missing", "garbage", "none"])
def test_a_playback_that_is_not_there_or_not_midi_leaves_the_score_alone(
    tmp_path: Path, playback: str
) -> None:
    xml = tmp_path / "score.musicxml"
    xml.write_text(score(measure(1, attributes() + tempo_direction("63") + FOUR)), encoding="utf-8")
    path: Path | None
    if playback == "none":
        path = None
    elif playback == "missing":
        path = tmp_path / "nothing.mid"
    else:
        path = tmp_path / "bad.mid"
        path.write_bytes(b"this is not a midi file")
    result, done = parse_with_playback_tempo(opened_with(xml, path), parse_musicxml)
    assert done is NOT_USED
    assert result.performed is not None
    assert [float(t.bpm) for t in result.performed.tempo_events] == [63.0]
