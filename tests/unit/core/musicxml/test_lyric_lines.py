"""Held syllables get the length MuseScore drew, matched by what each voice sings."""

from fractions import Fraction
from pathlib import Path

from barbershop_tracks.core.musicxml import ParseResult
from barbershop_tracks.core.musicxml.lyric_lines import NOT_READ, apply_lyric_lines
from barbershop_tracks.core.musicxml.mscx_lyrics import ProjectLyric
from barbershop_tracks.models import Lyric, Melisma
from xml_builders import attributes, extend, lyric_xml, measure, note, parse_text, score, syl, text

HELD = lyric_xml(syl("single"), text("doo"), extend())
PLAIN = lyric_xml(syl("single"), text("so"))


def one_voice(tmp_path: Path) -> ParseResult:
    """ "doo" held (an untyped line, as MuseScore writes it) over two notes, then "so"."""
    body = (
        note("C", 4, 2, lyrics=HELD)
        + note("D", 4, 2)
        + note("E", 4, 2, lyrics=PLAIN)
        + note("F", 4, 2)
    )
    return parse_text(tmp_path, score(measure(1, attributes() + body)))


def lyrics_of(result: ParseResult) -> list[Lyric]:
    assert result.song is not None
    return [lyric for part in result.song.parts for n in part.events for lyric in n.lyrics]


def project(*lyrics: tuple[str, int | None]) -> dict[int, list[list[ProjectLyric]]]:
    voice = [ProjectLyric(t, None if ln is None else Fraction(ln)) for t, ln in lyrics]
    return {1: [voice]}


def test_a_held_syllable_gets_the_length_of_its_line(tmp_path: Path) -> None:
    result, done = apply_lyric_lines(one_voice(tmp_path), project(("doo", 2), ("so", None)))
    held, plain = lyrics_of(result)
    assert held.extend_length == 2
    assert plain.extend_length is None
    assert (done.applied, done.wanted) == (1, 1)
    assert "1 of 1" in done.note


def test_the_performance_sees_the_lengths_too(tmp_path: Path) -> None:
    result, _ = apply_lyric_lines(one_voice(tmp_path), project(("doo", 2), ("so", None)))
    assert result.performed is not None
    first = result.performed.merged[0][0]
    assert first.source[0].lyrics[0].extend_length == 2


def test_nothing_else_about_the_score_changes(tmp_path: Path) -> None:
    before = one_voice(tmp_path)
    result, _ = apply_lyric_lines(before, project(("doo", 2), ("so", None)))
    assert before.song is not None
    assert result.song is not None
    assert [(n.start, n.duration, n.written_pitch) for n in result.song.parts[0].events] == [
        (n.start, n.duration, n.written_pitch) for n in before.song.parts[0].events
    ]
    assert result.issues is before.issues
    assert all(
        lyric.melisma is Melisma.UNTYPED for lyric in lyrics_of(result) if lyric.text == "doo"
    )


def test_a_voice_that_sings_other_words_is_not_matched_and_the_guess_stays(tmp_path: Path) -> None:
    before = one_voice(tmp_path)
    result, done = apply_lyric_lines(before, project(("loo", 2), ("so", None)))
    assert result is before
    assert (done.applied, done.wanted) == (0, 1)
    assert done.note == ""


def test_a_different_number_of_lyrics_is_not_matched(tmp_path: Path) -> None:
    before = one_voice(tmp_path)
    result, _ = apply_lyric_lines(before, project(("doo", 2)))
    assert result is before


def test_a_syllable_without_a_line_in_the_project_keeps_the_guess(tmp_path: Path) -> None:
    before = one_voice(tmp_path)
    result, done = apply_lyric_lines(before, project(("doo", None), ("so", None)))
    assert result is before
    assert done.applied == 0


def test_nothing_is_read_without_a_project(tmp_path: Path) -> None:
    before = one_voice(tmp_path)
    assert apply_lyric_lines(before, {}) == (before, NOT_READ)


def test_two_parts_use_their_own_staves(tmp_path: Path) -> None:
    one = measure(1, attributes() + note("C", 4, 4, lyrics=HELD) + note("D", 4, 4, lyrics=PLAIN))
    two = measure(1, attributes() + note("C", 3, 4, lyrics=HELD) + note("D", 3, 4, lyrics=PLAIN))
    parsed = parse_text(tmp_path, score(one, two))
    upper = [ProjectLyric("doo", Fraction(1)), ProjectLyric("so", None)]
    lower = [ProjectLyric("doo", Fraction(3)), ProjectLyric("so", None)]
    result, done = apply_lyric_lines(parsed, {1: [upper], 2: [lower]})
    held = [lyric.extend_length for lyric in lyrics_of(result) if lyric.text == "doo"]
    assert held == [1, 3]
    assert (done.applied, done.wanted) == (2, 2)


def test_two_voices_that_sing_the_same_words_are_matched_in_order(tmp_path: Path) -> None:
    both = (
        note("C", 4, 4, voice="1", lyrics=HELD)
        + note("D", 4, 4, voice="1", lyrics=PLAIN)
        + "<backup><duration>8</duration></backup>"
        + note("C", 3, 4, voice="2", lyrics=HELD)
        + note("D", 3, 4, voice="2", lyrics=PLAIN)
    )
    parsed = parse_text(tmp_path, score(measure(1, attributes() + both)))
    voices = [
        [ProjectLyric("doo", Fraction(1)), ProjectLyric("so", None)],
        [ProjectLyric("doo", Fraction(4)), ProjectLyric("so", None)],
    ]
    result, _ = apply_lyric_lines(parsed, {1: voices})
    assert [lyric.extend_length for lyric in lyrics_of(result) if lyric.text == "doo"] == [1, 4]
