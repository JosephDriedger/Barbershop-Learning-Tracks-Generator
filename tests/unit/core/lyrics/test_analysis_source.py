"""Source preservation (a permanent architectural guarantee) and parser-driven analysis."""

import copy
from pathlib import Path

import pytest

from barbershop_tracks.core.lyrics import analyze_line, analyze_song_lyrics
from barbershop_tracks.core.musicxml import ParseResult, parse_musicxml
from barbershop_tracks.models import (
    AttackRole,
    Lyric,
    LyricSegment,
    Melisma,
    Note,
    PerformanceNote,
    Song,
    Syllabic,
)
from lyric_builders import LINE, L, n, performed, r
from xml_builders import (
    attributes,
    backup,
    extend,
    lyric_xml,
    measure,
    note,
    parse_text,
    rest,
    score,
    syl,
    text,
)

R = AttackRole
LYRIC_FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "musicxml" / "lyrics"
TTBB = Path(__file__).resolve().parents[3] / "fixtures" / "musicxml" / "ttbb"


# --- analysis never modifies its input (permanent regression) ---------------------------------


def _messy_line() -> list[PerformanceNote]:
    notes = [
        n(0, L("a", Syllabic.BEGIN, melisma=Melisma.UNTYPED, verse="1"), L("x", verse="2")),
        n(1),
        r(2),
        n(3, L(" la ", Syllabic.UNSPECIFIED), to=True),
        n(4, L("la"), frm=True),
        n(5, L("way", Syllabic.END, verse="1")),
        n(6, Lyric.humming()),
        n(7, Lyric.extension(Melisma.STOP)),
        n(8, L("the", elided=(LyricSegment(text="ir", joiner="‿"),))),
        n(9, L("+", Syllabic.SINGLE, verse=None), L("-", verse="1")),
    ]
    return performed(*notes)


def _fingerprint(line: list[PerformanceNote]) -> list[object]:
    out: list[object] = []
    for attack in line:
        for source in attack.source:
            out.append(
                (
                    source.start,
                    source.tied_to_next,
                    source.tied_from_previous,
                    tuple(
                        (
                            lyric.kind,
                            lyric.text,
                            lyric.verse,
                            lyric.syllabic,
                            lyric.melisma,
                            lyric.name,
                            lyric.time_only,
                            lyric.elided,
                        )
                        for lyric in source.lyrics
                    ),
                )
            )
    return out


def test_analysis_does_not_modify_any_source_value() -> None:
    line = _messy_line()
    before_copy = copy.deepcopy(line)
    before = _fingerprint(line)
    for verse in (None, "1", "2", "9"):
        analyze_line(line, part_id=LINE, verse=verse)
    assert _fingerprint(line) == before  # text, verse numbers, syllabic and melisma values
    assert line == before_copy  # Note, Lyric and PerformanceNote values are equal


def test_source_verse_numbers_are_never_rewritten() -> None:
    line = performed(n(0, L("la", verse=None)), n(1, L("ni", verse="1")))
    analyze_line(line, part_id=LINE)
    assert [lyric.verse for p in line for lyric in p.source[0].lyrics] == [None, "1"]


def test_source_text_is_never_stripped_or_joined() -> None:
    line = performed(n(0, L(" la ", Syllabic.BEGIN)), n(1, L("ba-", Syllabic.END)))
    result = analyze_line(line, part_id=LINE)
    assert result.words[0].text == " la ba-"  # reconstructed view; the source is unchanged
    assert [p.source[0].lyrics[0].text for p in line] == [" la ", "ba-"]


def test_result_attacks_reference_the_same_source_objects() -> None:
    line = performed(n(0, L("la")))
    result = analyze_line(line, part_id=LINE)
    assert result.attacks[0].performed is line[0]
    assert result.attacks[0].lyric is line[0].source[0].lyrics[0]


def test_analysis_results_are_immutable() -> None:
    result = analyze_line(performed(n(0, L("la"))), part_id=LINE)
    with pytest.raises(AttributeError):
        result.verse = "2"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        result.attacks[0].role = R.MISSING  # type: ignore[misc]
    assert isinstance(result.attacks, tuple)
    assert isinstance(result.words, tuple)


def test_results_carry_no_backend_fields() -> None:
    result = analyze_line(performed(n(0, L("la"))), part_id=LINE)
    names = {
        name
        for obj in (result, result.attacks[0], result.coverage)
        for name in obj.__dataclass_fields__
    }
    forbidden = {"tick", "ticks", "phoneme", "phonemes", "singer", "voicebank", "midi", "openutau"}
    assert names.isdisjoint(forbidden)
    assert not any("+" in name for name in names)


def test_song_analysis_leaves_the_song_unchanged() -> None:
    parsed = _parse_song_with_lyrics()
    assert parsed.song is not None
    before = copy.deepcopy(parsed.song)
    analyze_song_lyrics(parsed.song)
    assert parsed.song == before


# --- parser-driven analysis ----------------------------------------------------------------


def _parse(tmp_path: Path, body: str) -> ParseResult:
    return parse_text(tmp_path, score(measure(1, body, attrs=attributes())))


def _parse_song_with_lyrics() -> ParseResult:
    body = (
        note("C", 4, 2, lyrics=lyric_xml(syl("begin"), text("a")))
        + note("D", 4, 2, lyrics=lyric_xml(syl("end"), text("way"), extend()))
        + note("E", 4, 2)
        + note("F", 4, 2)
    )
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        return parse_text(Path(directory), score(measure(1, body, attrs=attributes())))


def test_a_parsed_line_is_analyzed_end_to_end(tmp_path: Path) -> None:
    result = _parse(
        tmp_path,
        note("C", 4, 2, lyrics=lyric_xml(syl("begin"), text("a")))
        + note("D", 4, 2, lyrics=lyric_xml(syl("end"), text("way"), extend()))
        + note("E", 4, 2)
        + note("F", 4, 2),
    )
    assert result.song is not None
    line = analyze_song_lyrics(result.song).lines[0]
    assert [a.role for a in line.attacks] == [
        R.SYLLABLE,
        R.SYLLABLE,
        R.MELISMA_CONTINUATION,
        R.MELISMA_CONTINUATION,
    ]
    assert [w.text for w in line.words] == ["away"]
    assert not line.issues


@pytest.mark.parametrize("count", [1, 2, 6, 23])
def test_untyped_extender_then_n_lyricless_notes_parsed_from_xml(
    tmp_path: Path, count: int
) -> None:
    # 23 lyric-less notes after an untyped extender is the longest run seen in a real score.
    total = count + 2
    notes = note("C", 4, 8, lyrics=lyric_xml(syl("single"), text("la"), extend()))
    notes += "".join(note("D", 4, 8) for _ in range(count))
    notes += note("E", 4, 8, lyrics=lyric_xml(syl("single"), text("ni")))
    measures = "".join(
        measure(i + 1, note_xml, attrs=attributes() if i == 0 else "")
        for i, note_xml in enumerate(_split(notes, total))
    )
    result = parse_text(tmp_path, score(measures))
    assert result.song is not None
    line = analyze_song_lyrics(result.song).lines[0]
    assert line.coverage.longest_melisma == count
    assert line.coverage.continuation_attacks == count
    assert line.coverage.missing_attacks == 0
    assert [a.role for a in line.attacks][-1] is R.SYLLABLE


def _split(joined: str, parts: int) -> list[str]:
    pieces = joined.split("</note>")[:-1]
    assert len(pieces) == parts
    return [f"{piece}</note>" for piece in pieces]


def test_a_completely_lyricless_voice_gives_one_issue(tmp_path: Path) -> None:
    body = "".join(note("C", 4, 8, voice="1") for _ in range(30))
    measures = "".join(
        measure(i + 1, piece, attrs=attributes() if i == 0 else "")
        for i, piece in enumerate(_split(body, 30))
    )
    result = parse_text(tmp_path, score(measures))
    assert result.song is not None
    line = analyze_song_lyrics(result.song).lines[0]
    assert [i.code for i in line.issues] == ["LYRIC_LINE_EMPTY"]


def test_two_voices_one_with_lyrics_one_without(tmp_path: Path) -> None:
    body = (
        note("C", 4, 8, voice="1", lyrics=lyric_xml(syl("single"), text("la")))
        + backup(8)
        + note("A", 3, 8, voice="2")
    )
    result = _parse(tmp_path, body)
    assert result.song is not None
    song = analyze_song_lyrics(result.song)
    voice1, voice2 = song.lines
    assert voice1.coverage.has_any_lyric
    assert [i.code for i in voice2.issues] == ["LYRIC_LINE_EMPTY"]
    assert song.choice.selected == "1"


def test_song_level_verse_choice_is_shared_by_every_line(tmp_path: Path) -> None:
    body = (
        note("C", 4, 8, voice="1", lyrics=lyric_xml(text("la"), number="2"))
        + backup(8)
        + note("A", 3, 8, voice="2", lyrics=lyric_xml(text("ni"), number="3"))
    )
    result = _parse(tmp_path, body)
    assert result.song is not None
    song = analyze_song_lyrics(result.song)
    assert song.choice.selected == "2"  # first in document order, no verse 1
    assert [line.verse for line in song.lines] == ["2", "2"]
    assert [i.code for i in song.issues] == ["LYRIC_MULTIPLE_VERSES"]  # once, at song level
    assert song.lines[1].coverage.syllable_attacks == 0  # voice 2 has no verse 2 lyrics


def test_requested_song_verse_and_missing_verse(tmp_path: Path) -> None:
    body = note("C", 4, 8, lyrics=lyric_xml(text("la"), number="1"))
    result = _parse(tmp_path, body)
    assert result.song is not None
    assert analyze_song_lyrics(result.song, verse="1").choice.found
    missing = analyze_song_lyrics(result.song, verse="4")
    assert [i.code for i in missing.issues] == ["LYRIC_VERSE_NOT_FOUND"]


def test_rest_in_a_parsed_line_keeps_an_untyped_melisma_boundary(tmp_path: Path) -> None:
    body = (
        note("C", 4, 2, lyrics=lyric_xml(syl("single"), text("la"), extend()))
        + rest(2)
        + note("D", 4, 2)
        + note("E", 4, 2, lyrics=lyric_xml(syl("single"), text("ni")))
    )
    result = _parse(tmp_path, body)
    assert result.song is not None
    line = analyze_song_lyrics(result.song).lines[0]
    assert [a.role for a in line.attacks] == [R.SYLLABLE, R.REST, R.MISSING, R.SYLLABLE]
    assert "LYRIC_MELISMA_INTERRUPTED" in [i.code for i in line.issues]


def test_parser_level_lyric_errors_do_not_stop_the_analysis(tmp_path: Path) -> None:
    body = note("C", 4, 8, lyrics=lyric_xml(text("la")) + lyric_xml(text("ni")))  # duplicate verse
    result = _parse(tmp_path, body)
    assert "LYRIC_DUPLICATE_VERSE" in [i.code for i in result.issues]
    assert result.song is not None
    line = analyze_song_lyrics(result.song).lines[0]
    assert line.attacks[0].role is R.CONFLICT
    assert isinstance(result.song, Song)
    assert isinstance(result.song.parts[0].events[0], Note)


# --- the research fixtures ----------------------------------------------------------------


@pytest.mark.parametrize("variant", ["inputs", "musescore_roundtrip"])
def test_the_ttbb_fixtures_are_lyricless_lines_with_one_summary_each(variant: str) -> None:
    parsed = parse_musicxml(TTBB / variant / "ttbb_layout.musicxml")
    assert parsed.song is not None
    song = analyze_song_lyrics(parsed.song)
    assert len(song.lines) == 4
    assert all([i.code for i in line.issues] == ["LYRIC_LINE_EMPTY"] for line in song.lines)
    assert song.choice.selected is None


def test_musescore_untyped_melisma_fixture_analysis() -> None:
    parsed = parse_musicxml(LYRIC_FIXTURES / "musescore_roundtrip" / "l01_extend_typed.musicxml")
    assert parsed.song is not None
    line = analyze_song_lyrics(parsed.song).lines[0]
    assert [a.role for a in line.attacks] == [
        R.SYLLABLE,
        R.MELISMA_CONTINUATION,
        R.MELISMA_CONTINUATION,
        R.SYLLABLE,
    ]
    assert line.attacks[1].melisma_basis is not None
    assert line.attacks[1].melisma_basis.value == "untyped"


def test_typed_input_fixture_analysis() -> None:
    parsed = parse_musicxml(LYRIC_FIXTURES / "inputs" / "l01_extend_typed.musicxml")
    assert parsed.song is not None
    line = analyze_song_lyrics(parsed.song).lines[0]
    assert [a.role for a in line.attacks] == [
        R.SYLLABLE,
        R.MELISMA_CONTINUATION,
        R.MELISMA_CONTINUATION,
        R.SYLLABLE,
    ]
    assert line.attacks[1].melisma_basis is not None
    assert line.attacks[1].melisma_basis.value == "typed"
    assert not line.issues


def test_slur_without_an_extender_is_not_melisma_evidence() -> None:
    for variant in ("inputs", "musescore_roundtrip"):
        parsed = parse_musicxml(LYRIC_FIXTURES / variant / "l03_slur_no_extend.musicxml")
        assert parsed.song is not None
        line = analyze_song_lyrics(parsed.song).lines[0]
        assert [a.role for a in line.attacks] == [R.SYLLABLE, R.MISSING, R.MISSING, R.SYLLABLE]


def test_word_split_by_a_rest_fixture() -> None:
    for variant in ("inputs", "musescore_roundtrip"):
        parsed = parse_musicxml(LYRIC_FIXTURES / variant / "l19_begin_then_rest_then_end.musicxml")
        assert parsed.song is not None
        line = analyze_song_lyrics(parsed.song).lines[0]
        assert [w.text for w in line.words] == ["bana"]
        assert line.words[0].interrupted_by_rest
        assert "LYRIC_WORD_UNCLOSED" not in [i.code for i in line.issues]


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("l20_end_without_begin", "LYRIC_WORD_UNOPENED"),
        ("l21_begin_never_ended", "LYRIC_WORD_UNCLOSED"),
    ],
)
def test_malformed_chain_fixtures(name: str, code: str) -> None:
    parsed = parse_musicxml(LYRIC_FIXTURES / "inputs" / f"{name}.musicxml")
    assert parsed.song is not None
    assert code in [i.code for i in analyze_song_lyrics(parsed.song).lines[0].issues]


def test_humming_and_laughing_fixtures() -> None:
    for name, role in (("l27_humming", R.HUMMING), ("l28_laughing", R.LAUGHING)):
        parsed = parse_musicxml(LYRIC_FIXTURES / "inputs" / f"{name}.musicxml")
        assert parsed.song is not None
        line = analyze_song_lyrics(parsed.song).lines[0]
        assert line.attacks[0].role is role


def test_elided_fixture() -> None:
    parsed = parse_musicxml(LYRIC_FIXTURES / "inputs" / "l23_elision_element.musicxml")
    assert parsed.song is not None
    line = analyze_song_lyrics(parsed.song).lines[0]
    assert line.attacks[0].syllable_count == 2
    assert "LYRIC_ELIDED" in [i.code for i in line.issues]


def test_two_verse_fixture_selects_verse_one_and_warns() -> None:
    parsed = parse_musicxml(LYRIC_FIXTURES / "inputs" / "l13_two_verses.musicxml")
    assert parsed.song is not None
    song = analyze_song_lyrics(parsed.song)
    assert song.choice.selected == "1"
    assert [i.code for i in song.issues] == ["LYRIC_MULTIPLE_VERSES"]
    assert [a.lyric.text for a in song.lines[0].attacks if a.lyric] == ["la", "na"]
