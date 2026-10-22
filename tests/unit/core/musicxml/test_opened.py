"""A MuseScore project parsed with its own held-syllable lengths and playback tempo together."""

import zipfile
from fractions import Fraction
from pathlib import Path

from test_mscx_lyrics import chord
from test_mscx_lyrics import measure as mscx_measure
from test_mscx_lyrics import score as mscx_score

from barbershop_tracks.core.musicxml import parse_musicxml
from barbershop_tracks.core.musicxml.convert import Conversion, OpenedScore
from barbershop_tracks.core.musicxml.opened import parse_opened
from smf_builders import midi, tempo_event, track
from xml_builders import (
    attributes,
    extend,
    lyric_xml,
    measure,
    note,
    score,
    syl,
    tempo_direction,
    text,
)

HELD = lyric_xml(syl("single"), text("doo"), extend())


def opened(tmp_path: Path, *, with_project: bool = True, with_playback: bool = True) -> OpenedScore:
    xml = tmp_path / "exported.musicxml"
    body = (
        note("C", 4, 2, lyrics=HELD)
        + note("D", 4, 2)
        + note("E", 4, 2, lyrics=lyric_xml(syl("single"), text("so")))
        + note("F", 4, 2)
    )
    xml.write_text(score(measure(1, attributes() + tempo_direction("60") + body)), encoding="utf-8")
    project = tmp_path / "Hymn.mscz"
    with zipfile.ZipFile(project, "w") as archive:
        music = mscx_score(mscx_measure(chord("doo", ticks_f="1/2") + chord("so")))
        archive.writestr("Hymn.mscx", music if with_project else "<museScore/>")
    playback = tmp_path / "Hymn.mid"
    playback.write_bytes(
        midi(track(tempo_event(0, 60), tempo_event(480, 45), tempo_event(480, 60)))
    )
    note_about = Conversion("MuseScore", "ms", "export", "0" * 64, False, "exported")
    return OpenedScore(xml, project, "1" * 64, note_about, playback if with_playback else None)


def test_both_are_applied_and_the_tempo_survives_the_lines(tmp_path: Path) -> None:
    parsed, reading = parse_opened(opened(tmp_path), parse_musicxml)
    assert reading.lines.applied == 1
    assert reading.tempo.applied
    assert parsed.performed is not None
    # the lines re-derive the performance, and the playback tempo must still be what it plays
    assert [float(t.bpm) for t in parsed.performed.tempo_events] == [60.0, 45.0, 60.0]
    held = parsed.performed.merged[0][0].source[0].lyrics[0]
    assert held.extend_length == 2  # a half note's worth: 1/2 of a whole note, in quarter notes
    assert {kind for kind, _ in reading.notices()} == {"tempo", "lines"}


def test_each_is_recorded_for_the_package(tmp_path: Path) -> None:
    _, reading = parse_opened(opened(tmp_path), parse_musicxml)
    recorded = reading.into({"tool": "MuseScore"})
    assert recorded is not None
    assert recorded["tool"] == "MuseScore"
    assert recorded["playback_tempo"]["applied"] is True  # type: ignore[index]
    assert recorded["lyric_lines"]["applied"] == 1  # type: ignore[index]
    assert reading.into(None) is None  # a MusicXML score records no conversion at all


def test_a_project_that_does_not_match_leaves_the_lines_to_the_guess(tmp_path: Path) -> None:
    parsed, reading = parse_opened(opened(tmp_path, with_project=False), parse_musicxml)
    assert reading.lines.applied == 0
    assert reading.tempo.applied  # the tempo is a separate thing and is still followed
    assert parsed.performed is not None
    assert parsed.performed.merged[0][0].source[0].lyrics[0].extend_length is None


def test_without_a_playback_only_the_lines_are_read(tmp_path: Path) -> None:
    parsed, reading = parse_opened(opened(tmp_path, with_playback=False), parse_musicxml)
    assert reading.lines.applied == 1
    assert not reading.tempo.applied
    assert parsed.performed is not None
    assert [float(t.bpm) for t in parsed.performed.tempo_events] == [60.0]


def test_a_score_that_was_not_converted_is_read_as_it_is(tmp_path: Path) -> None:
    base = opened(tmp_path)
    plain = OpenedScore(base.parse_path, base.parse_path, "2" * 64, None, None)
    parsed, reading = parse_opened(plain, parse_musicxml)
    assert reading.notices() == []
    assert parsed.performed is not None
    assert Fraction(0) == parsed.performed.tempo_events[0].position
