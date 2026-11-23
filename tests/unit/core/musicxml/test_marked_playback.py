"""The tempo MuseScore plays, worked out from a score's fermatas and tempo lines."""

from fractions import Fraction
from pathlib import Path

from barbershop_tracks.core.musicxml import parse_musicxml
from barbershop_tracks.core.musicxml.convert import opened_score
from barbershop_tracks.core.musicxml.marked_playback import marked_tempo_changes
from barbershop_tracks.core.musicxml.opened import parse_opened
from barbershop_tracks.core.musicxml.source import load_musicxml_source


def _score(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "song.musicxml"
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>S</part-name>'
        '</score-part></part-list><part id="P1">' + body + "</part></score-partwise>",
        encoding="utf-8",
    )
    return path


def _note(step: str, fermata: bool = False) -> str:
    notations = "<notations><fermata/></notations>" if fermata else ""
    return (
        f"<note><pitch><step>{step}</step><octave>4</octave></pitch><duration>2</duration>"
        f"<voice>1</voice><type>quarter</type>{notations}<lyric><text>la</text></lyric></note>"
    )


TEMPO = (
    "<direction><direction-type><metronome><beat-unit>quarter</beat-unit>"
    '<per-minute>60</per-minute></metronome></direction-type><sound tempo="60"/></direction>'
)
ATTRIBUTES = (
    "<attributes><divisions>2</divisions><key><fifths>0</fifths></key>"
    "<time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line>"
    "</clef></attributes>"
)


def _changes(path: Path) -> list[tuple[Fraction, Fraction]]:
    changes = marked_tempo_changes(load_musicxml_source(path).root, parse_musicxml(path))
    assert changes is not None
    return [(c.position, c.bpm) for c in changes]


def test_a_fermata_halves_the_tempo_until_a_tick_before_the_next_note(tmp_path: Path) -> None:
    path = _score(
        tmp_path,
        f'<measure number="1">{ATTRIBUTES}{TEMPO}{_note("C")}{_note("D", fermata=True)}'
        f"{_note('E')}{_note('F')}</measure>",
    )
    assert _changes(path) == [
        (Fraction(0), Fraction(60)),
        (Fraction(1), Fraction(30)),
        (Fraction(2) - Fraction(1, 480), Fraction(60)),
    ]


def test_a_ritardando_slows_in_eight_steps_to_three_quarters(tmp_path: Path) -> None:
    rit = (
        "<direction><direction-type><words>rit.</words></direction-type>"
        '<direction-type><dashes type="start" number="1"/></direction-type></direction>'
    )
    stop = (
        '<direction><direction-type><dashes type="stop" number="1"/></direction-type></direction>'
    )
    path = _score(
        tmp_path,
        f'<measure number="1">{ATTRIBUTES}{TEMPO}{_note("C")}{rit}{_note("D")}{_note("E")}'
        f"{stop}{_note('F')}</measure>",
    )
    changes = _changes(path)
    assert changes[0] == (Fraction(0), Fraction(60))
    steps = changes[1:]
    # the line runs from beat 1 (after C) to beat 3 (before F): eight steps of a quarter of a beat
    assert [p for p, _ in steps] == [1 + Fraction(k, 4) for k in range(1, 9)]
    assert [b for _, b in steps] == [60 - Fraction(15, 8) * k for k in range(1, 9)]  # to 45


def test_a_score_without_fermatas_or_tempo_lines_keeps_its_own_marks(tmp_path: Path) -> None:
    path = _score(tmp_path, f'<measure number="1">{ATTRIBUTES}{TEMPO}{_note("C")}</measure>')
    assert marked_tempo_changes(load_musicxml_source(path).root, parse_musicxml(path)) is None


def test_a_musicxml_file_is_played_as_musescore_plays_its_marks(tmp_path: Path) -> None:
    path = _score(
        tmp_path,
        f'<measure number="1">{ATTRIBUTES}{TEMPO}{_note("C", fermata=True)}{_note("D")}'
        f"{_note('E')}{_note('F')}</measure>",
    )
    with opened_score(path) as opened:
        parsed, reading = parse_opened(opened, parse_musicxml)
    assert reading.tempo.applied
    assert "as MuseScore plays them" in reading.tempo.note
    assert parsed.performed is not None
    assert parsed.performed.tempo_events[0].bpm < 60  # the fermata is slower
