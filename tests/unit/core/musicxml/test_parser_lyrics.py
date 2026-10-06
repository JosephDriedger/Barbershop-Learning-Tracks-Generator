"""Literal ``<lyric>`` parsing (M3c1). Nothing is inferred; the source is kept as written."""

from pathlib import Path

import pytest

from barbershop_tracks.core.musicxml import ParseResult
from barbershop_tracks.models import Lyric, LyricKind, Melisma, Note, Severity, Syllabic
from xml_builders import (
    attributes,
    backup,
    extend,
    lyric_xml,
    measure,
    note,
    parse_text,
    quarters,
    rest,
    score,
    syl,
    text,
    tie_xml,
    tied_xml,
)

pytestmark = pytest.mark.usefixtures("no_network")

GLYPH = chr(0xE551)  # MuseScore's elision glyph (SMuFL lyricsElisionNarrow)


def _parse(tmp_path: Path, body: str) -> ParseResult:
    return parse_text(tmp_path, score(measure(1, body, attrs=attributes())))


def _lyrics_of(result: ParseResult, index: int = 0, line: str = "P1/s1/v1") -> tuple[Lyric, ...]:
    assert result.song is not None
    part = next(p for p in result.song.parts if p.part_id == line)
    return part.events[index].lyrics


def _one(tmp_path: Path, *content: str, **attrs: str | None) -> tuple[ParseResult, Lyric]:
    body = note("C", 4, 8, lyrics=lyric_xml(*content, **attrs))
    result = _parse(tmp_path, body)
    (lyric,) = _lyrics_of(result)
    return result, lyric


def _codes(result: ParseResult) -> list[str]:
    return [i.code for i in result.issues]


# --- text, syllabic, verse -------------------------------------------------------------


def test_simple_lyric(tmp_path: Path) -> None:
    result, lyric = _one(tmp_path, syl("single"), text("la"))
    assert (lyric.kind, lyric.text, lyric.syllabic) == (LyricKind.TEXT, "la", Syllabic.SINGLE)
    assert lyric.verse == "1"
    assert lyric.melisma is Melisma.NONE
    assert not result.issues


@pytest.mark.parametrize("value", ["single", "begin", "middle", "end"])
def test_each_syllabic_value(tmp_path: Path, value: str) -> None:
    _, lyric = _one(tmp_path, syl(value), text("la"))
    assert lyric.syllabic is Syllabic(value)


def test_missing_syllabic_is_preserved_as_unspecified(tmp_path: Path) -> None:
    result, lyric = _one(tmp_path, text("la"))
    assert lyric.syllabic is Syllabic.UNSPECIFIED  # never silently single
    assert not result.issues


def test_invalid_syllabic_value_is_an_unsupported_structure(tmp_path: Path) -> None:
    result = _parse(tmp_path, note("C", 4, 8, lyrics=lyric_xml(syl("whole"), text("la"))))
    assert "LYRIC_TEXT_STRUCTURE_UNSUPPORTED" in _codes(result)
    assert _lyrics_of(result) == ()  # nothing is guessed


def test_absent_number_is_none(tmp_path: Path) -> None:
    _, lyric = _one(tmp_path, text("la"), number=None)
    assert lyric.verse is None


def test_number_one_is_distinct_from_absent(tmp_path: Path) -> None:
    _, absent = _one(tmp_path, text("la"), number=None)
    _, one = _one(tmp_path, text("la"), number="1")
    assert absent.verse is None
    assert one.verse == "1"
    assert absent != one


def test_verse_two_alone_is_not_renumbered(tmp_path: Path) -> None:
    _, lyric = _one(tmp_path, text("la"), number="2")
    assert lyric.verse == "2"


def test_non_numeric_verse_tokens_are_kept(tmp_path: Path) -> None:
    _, lyric = _one(tmp_path, text("la"), number="v2a")
    assert lyric.verse == "v2a"


def test_empty_number_is_an_error_and_becomes_absent(tmp_path: Path) -> None:
    result, lyric = _one(tmp_path, text("la"), number="")
    assert "LYRIC_NUMBER_INVALID" in _codes(result)
    assert lyric.verse is None


def test_text_is_never_stripped(tmp_path: Path) -> None:
    for raw in (" la ", "la ni", "+", "-", "[la]", "la~", "ba-"):
        _, lyric = _one(tmp_path, syl("single"), text(raw))
        assert lyric.text == raw


def test_whitespace_only_text_is_kept_verbatim(tmp_path: Path) -> None:
    _, lyric = _one(tmp_path, syl("single"), text("  "))
    assert lyric.text == "  "


def test_text_with_xml_entities_is_decoded_once(tmp_path: Path) -> None:
    _, lyric = _one(tmp_path, text("a&amp;b"))
    assert lyric.text == "a&b"


def test_openutau_markers_are_ordinary_text_in_the_source(tmp_path: Path) -> None:
    for marker in ("+", "+~", "-"):
        _, lyric = _one(tmp_path, text(marker))
        assert lyric.text == marker  # no conversion, no reinterpretation


def test_two_voices_keep_their_own_lyrics(tmp_path: Path) -> None:
    body = (
        note("C", 4, 8, voice="1", lyrics=lyric_xml(syl("single"), text("la")))
        + backup(8)
        + note("A", 3, 8, voice="2", lyrics=lyric_xml(syl("single"), text("ni")))
    )
    result = _parse(tmp_path, body)
    assert _lyrics_of(result, line="P1/s1/v1")[0].text == "la"
    assert _lyrics_of(result, line="P1/s1/v2")[0].text == "ni"


def test_lyricless_notes_stay_lyricless_nothing_is_inferred(tmp_path: Path) -> None:
    body = (
        note("C", 4, 2, lyrics=lyric_xml(syl("single"), text("la"), extend()))
        + quarters(("D", 4), ("E", 4))
        + note("F", 4, 2)
    )
    result = _parse(tmp_path, body)
    assert [bool(_lyrics_of(result, i)) for i in range(4)] == [True, False, False, False]
    assert not result.issues


# --- <extend> forms ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("form", "expected"),
    [
        (extend(), Melisma.UNTYPED),
        (extend("start"), Melisma.START),
        (extend("continue"), Melisma.CONTINUE),
        (extend("stop"), Melisma.STOP),
    ],
)
def test_extend_forms_on_a_text_lyric(tmp_path: Path, form: str, expected: Melisma) -> None:
    result, lyric = _one(tmp_path, syl("single"), text("la"), form)
    assert lyric.melisma is expected
    assert not result.issues


def test_no_extend_is_none(tmp_path: Path) -> None:
    assert _one(tmp_path, text("la"))[1].melisma is Melisma.NONE


def test_untyped_extend_is_not_translated_to_start(tmp_path: Path) -> None:
    lyric = _one(tmp_path, text("la"), extend())[1]
    assert lyric.melisma is Melisma.UNTYPED
    assert lyric.melisma.value == "untyped"  # not "start"


@pytest.mark.parametrize(
    ("form", "expected"),
    [
        (extend(), Melisma.UNTYPED),
        (extend("start"), Melisma.START),
        (extend("continue"), Melisma.CONTINUE),
        (extend("stop"), Melisma.STOP),
    ],
)
def test_extension_only_lyrics(tmp_path: Path, form: str, expected: Melisma) -> None:
    result, lyric = _one(tmp_path, form)
    assert lyric.kind is LyricKind.EXTENSION
    assert lyric.melisma is expected
    assert lyric.syllabic is Syllabic.UNSPECIFIED
    assert not result.issues


@pytest.mark.parametrize("kind", ["foo", "", "Start"])
def test_invalid_extend_type_is_an_error(tmp_path: Path, kind: str) -> None:
    result = _parse(tmp_path, note("C", 4, 8, lyrics=lyric_xml(text("la"), extend(kind))))
    issue = next(i for i in result.issues if i.code == "LYRIC_EXTEND_TYPE_INVALID")
    assert issue.severity is Severity.ERROR
    assert _lyrics_of(result) == ()


def test_two_extends_are_unsupported(tmp_path: Path) -> None:
    result = _parse(tmp_path, note("C", 4, 8, lyrics=lyric_xml(text("la"), extend(), extend())))
    assert "LYRIC_TEXT_STRUCTURE_UNSUPPORTED" in _codes(result)


# --- name and time-only -----------------------------------------------------------------


def test_name_is_preserved_and_is_not_a_problem(tmp_path: Path) -> None:
    result, lyric = _one(tmp_path, text("la"), name="chorus")
    assert lyric.name == "chorus"
    assert not result.issues


def test_time_only_is_preserved_and_unsupported(tmp_path: Path) -> None:
    result, lyric = _one(tmp_path, text("la"), time_only="1, 2")
    assert lyric.time_only == "1, 2"  # kept for when repeats exist
    issue = next(i for i in result.issues if i.code == "LYRIC_TIME_ONLY_UNSUPPORTED")
    assert issue.severity is Severity.ERROR
    assert (issue.part_id, issue.measure) == ("P1/s1/v1", 1)
    assert "1, 2" in issue.message


# --- humming / laughing -----------------------------------------------------------------


def test_humming_is_preserved_literally(tmp_path: Path) -> None:
    result, lyric = _one(tmp_path, "<humming/>")
    assert lyric.kind is LyricKind.HUMMING
    assert not result.issues  # a legitimate vocal event, not an error


def test_laughing_is_preserved_literally(tmp_path: Path) -> None:
    result, lyric = _one(tmp_path, "<laughing/>", number="2")
    assert (lyric.kind, lyric.verse) == (LyricKind.LAUGHING, "2")
    assert not result.issues


def test_humming_with_text_is_an_unsupported_structure(tmp_path: Path) -> None:
    result = _parse(tmp_path, note("C", 4, 8, lyrics=lyric_xml("<humming/>", text("la"))))
    assert "LYRIC_TEXT_STRUCTURE_UNSUPPORTED" in _codes(result)


def test_humming_and_laughing_together_are_unsupported(tmp_path: Path) -> None:
    result = _parse(tmp_path, note("C", 4, 8, lyrics=lyric_xml("<humming/>", "<laughing/>")))
    assert "LYRIC_TEXT_STRUCTURE_UNSUPPORTED" in _codes(result)


# --- formatting-only elements and empty lyrics ------------------------------------------


def test_end_line_and_end_paragraph_are_ignored(tmp_path: Path) -> None:
    result, lyric = _one(tmp_path, text("la"), "<end-line/>", "<end-paragraph/>")
    assert lyric.text == "la"
    assert not result.issues


@pytest.mark.parametrize("content", [(), (syl("single"),), (text(""),), (syl("single"), text(""))])
def test_lyric_with_no_usable_content_is_skipped_with_a_warning(
    tmp_path: Path, content: tuple[str, ...]
) -> None:
    result = _parse(tmp_path, note("C", 4, 8, lyrics=lyric_xml(*content)))
    issue = next(i for i in result.issues if i.code == "LYRIC_EMPTY")
    assert issue.severity is Severity.WARNING
    assert _lyrics_of(result) == ()
    assert not result.issues.has_errors


# --- <elision> and multiple <text> -------------------------------------------------------


def test_standard_elision_becomes_a_segment(tmp_path: Path) -> None:
    _, lyric = _one(
        tmp_path,
        syl("single"),
        text("la"),
        "<elision>‿</elision>",
        syl("end"),
        text("ni"),
    )
    assert (lyric.text, lyric.syllabic) == ("la", Syllabic.SINGLE)
    (segment,) = lyric.elided
    assert (segment.text, segment.syllabic, segment.joiner) == ("ni", Syllabic.END, "‿")
    assert segment.joiner_smufl is None


def test_elision_without_a_second_syllabic(tmp_path: Path) -> None:
    _, lyric = _one(tmp_path, syl("begin"), text("la"), "<elision>_</elision>", text("ni"))
    assert lyric.elided[0].syllabic is Syllabic.UNSPECIFIED
    assert lyric.elided[0].joiner == "_"


def test_smufl_elision_keeps_the_glyph_name(tmp_path: Path) -> None:
    _, lyric = _one(tmp_path, text("la"), '<elision smufl="lyricsElision"/>', text("ni"))
    assert lyric.elided[0].joiner == ""
    assert lyric.elided[0].joiner_smufl == "lyricsElision"


def test_two_elisions_make_three_syllables(tmp_path: Path) -> None:
    _, lyric = _one(
        tmp_path, text("la"), "<elision>_</elision>", text("ni"), "<elision>_</elision>", text("na")
    )
    assert [s.text for s in lyric.elided] == ["ni", "na"]
    assert lyric.full_text == "la_ni_na"


@pytest.mark.parametrize(
    "content",
    [
        (text("la"), "<elision>_</elision>"),  # trailing elision
        ("<elision>_</elision>", text("la")),  # leading elision
        (text("la"), "<elision>_</elision>", "<elision>_</elision>", text("ni")),
        (text("la"), text("ni"), "<elision>_</elision>", text("na")),  # texts without an elision
        (text("la"), "<elision>_</elision>", syl("end"), syl("end"), text("ni")),
        (text("la"), "<elision>_</elision>", text("")),
    ],
)
def test_malformed_elision_structures_are_unsupported(
    tmp_path: Path, content: tuple[str, ...]
) -> None:
    result = _parse(tmp_path, note("C", 4, 8, lyrics=lyric_xml(*content)))
    assert "LYRIC_TEXT_STRUCTURE_UNSUPPORTED" in _codes(result)
    assert _lyrics_of(result) == ()


def test_second_syllabic_without_elision_is_unsupported(tmp_path: Path) -> None:
    result = _parse(
        tmp_path, note("C", 4, 8, lyrics=lyric_xml(syl("begin"), syl("end"), text("la")))
    )
    assert "LYRIC_TEXT_STRUCTURE_UNSUPPORTED" in _codes(result)


def test_musescore_glyph_pattern_is_recognized(tmp_path: Path) -> None:
    _, lyric = _one(tmp_path, syl("end"), text("la"), text(GLYPH), text("ni"))
    assert (lyric.text, lyric.syllabic) == ("la", Syllabic.END)
    (segment,) = lyric.elided
    assert (segment.text, segment.joiner, segment.syllabic) == ("ni", GLYPH, Syllabic.UNSPECIFIED)


def test_musescore_glyph_pattern_with_three_syllables(tmp_path: Path) -> None:
    _, lyric = _one(tmp_path, text("la"), text(GLYPH), text("ni"), text(GLYPH), text("na"))
    assert [s.text for s in lyric.elided] == ["ni", "na"]


@pytest.mark.parametrize(
    "other",
    [chr(0xE550), chr(0xE552), chr(0xE000), chr(0xF8FF), chr(0x203F), "_", " "],
)
def test_other_characters_are_not_treated_as_elision_joiners(tmp_path: Path, other: str) -> None:
    result = _parse(
        tmp_path, note("C", 4, 8, lyrics=lyric_xml(text("la"), text(other), text("ni")))
    )
    assert "LYRIC_TEXT_STRUCTURE_UNSUPPORTED" in _codes(result)
    assert _lyrics_of(result) == ()  # never concatenated on a guess


@pytest.mark.parametrize(
    "content",
    [
        (text("la"), text("ni")),  # two texts, no joiner
        (text("la"), text(GLYPH)),  # even count
        (text(GLYPH), text("la"), text("ni")),  # glyph first
        (text("la"), text(GLYPH), text(GLYPH), text("ni")),  # doubled glyph
        (text("la"), text(GLYPH), text("")),  # empty syllable
        (syl("begin"), syl("end"), text("la"), text(GLYPH), text("ni")),  # two syllabics
    ],
)
def test_other_multi_text_shapes_are_unsupported(tmp_path: Path, content: tuple[str, ...]) -> None:
    result = _parse(tmp_path, note("C", 4, 8, lyrics=lyric_xml(*content)))
    assert "LYRIC_TEXT_STRUCTURE_UNSUPPORTED" in _codes(result)
    assert _lyrics_of(result) == ()


def test_single_text_with_an_undertie_is_one_literal_text(tmp_path: Path) -> None:
    _, lyric = _one(tmp_path, text("la‿ni"))
    assert lyric.text == "la‿ni"
    assert not lyric.is_elided


# --- duplicate logical verse --------------------------------------------------------------


def test_two_lyrics_with_the_same_number_are_an_error_and_both_are_kept(tmp_path: Path) -> None:
    body = note("C", 4, 8, lyrics=lyric_xml(text("la")) + lyric_xml(text("ni")))
    result = _parse(tmp_path, body)
    issue = next(i for i in result.issues if i.code == "LYRIC_DUPLICATE_VERSE")
    assert issue.severity is Severity.ERROR
    assert issue.part_id == "P1/s1/v1"
    assert issue.measure == 1
    assert issue.beat == 1
    assert "'la'" in issue.message
    assert "'ni'" in issue.message
    assert [lyric.text for lyric in _lyrics_of(result)] == ["la", "ni"]  # none chosen


def test_absent_number_and_number_one_are_the_same_logical_verse(tmp_path: Path) -> None:
    body = note(
        "C", 4, 8, lyrics=lyric_xml(text("la"), number=None) + lyric_xml(text("ni"), number="1")
    )
    result = _parse(tmp_path, body)
    assert "LYRIC_DUPLICATE_VERSE" in _codes(result)
    assert [lyric.verse for lyric in _lyrics_of(result)] == [None, "1"]  # source kept as written


def test_different_verses_are_not_duplicates(tmp_path: Path) -> None:
    body = note(
        "C", 4, 8, lyrics=lyric_xml(text("la"), number="1") + lyric_xml(text("ni"), number="2")
    )
    result = _parse(tmp_path, body)
    assert not result.issues
    assert [lyric.verse for lyric in _lyrics_of(result)] == ["1", "2"]


def test_one_duplicate_report_per_duplicated_verse(tmp_path: Path) -> None:
    body = note(
        "C",
        4,
        8,
        lyrics=lyric_xml(text("a"), number="1")
        + lyric_xml(text("b"), number="1")
        + lyric_xml(text("c"), number="2")
        + lyric_xml(text("d"), number="2"),
    )
    assert _codes(_parse(tmp_path, body)).count("LYRIC_DUPLICATE_VERSE") == 2


def test_duplicates_across_different_notes_are_not_reported(tmp_path: Path) -> None:
    body = note("C", 4, 4, lyrics=lyric_xml(text("la"))) + note(
        "D", 4, 4, lyrics=lyric_xml(text("ni"))
    )
    assert not _parse(tmp_path, body).issues


# --- placements that cannot hold a lyric ------------------------------------------------


def test_lyric_on_a_rest_is_an_error_and_is_not_attached_anywhere(tmp_path: Path) -> None:
    body = rest(2, lyrics=lyric_xml(syl("single"), text("la"))) + note("C", 4, 6)
    result = _parse(tmp_path, body)
    issue = next(i for i in result.issues if i.code == "LYRIC_ON_REST")
    assert issue.severity is Severity.ERROR
    assert issue.part_id == "P1/s1/v1"
    assert issue.measure == 1
    assert issue.beat == 1
    assert "'la'" in issue.message  # the literal text survives in the diagnostic
    assert _lyrics_of(result, 0) == ()
    assert _lyrics_of(result, 1) == ()  # not moved to the following note


def test_lyric_on_a_cue_note_is_an_error_and_not_moved(tmp_path: Path) -> None:
    body = note("C", 4, 2, extra="<cue/>", lyrics=lyric_xml(text("la"))) + note(
        "D", 4, 6, lyrics=lyric_xml(text("ni"))
    )
    result = _parse(tmp_path, body)
    issue = next(i for i in result.issues if i.code == "LYRIC_ON_CUE_NOTE")
    assert issue.severity is Severity.ERROR
    assert "'la'" in issue.message
    assert [lyric.text for lyric in _lyrics_of(result, 0)] == ["ni"]  # the next note keeps its own


def test_lyric_on_a_grace_note_is_an_error_and_not_moved_to_the_next_note(tmp_path: Path) -> None:
    grace = (
        "<note><grace/><pitch><step>B</step><octave>3</octave></pitch><voice>1</voice>"
        + lyric_xml(text("ni"))
        + "</note>"
    )
    body = grace + note("C", 4, 8, lyrics=lyric_xml(text("la")))
    result = _parse(tmp_path, body)
    issue = next(i for i in result.issues if i.code == "LYRIC_ON_GRACE_NOTE")
    assert "'ni'" in issue.message
    assert [lyric.text for lyric in _lyrics_of(result, 0)] == ["la"]  # exactly one, not two
    assert "LYRIC_DUPLICATE_VERSE" not in _codes(result)  # we do not reproduce MuseScore's move


def test_lyric_on_an_unpitched_note_is_an_error(tmp_path: Path) -> None:
    unpitched = (
        "<note><unpitched><display-step>E</display-step><display-octave>4</display-octave>"
        "</unpitched><duration>2</duration><voice>1</voice>" + lyric_xml(text("la")) + "</note>"
    )
    result = _parse(tmp_path, unpitched + quarters(("C", 4), ("D", 4), ("E", 4)))
    issue = next(i for i in result.issues if i.code == "LYRIC_ON_UNPITCHED_NOTE")
    assert "'la'" in issue.message


def test_a_rest_without_a_lyric_is_unaffected(tmp_path: Path) -> None:
    assert not _parse(tmp_path, rest(8)).issues


def test_chord_member_lyrics_stay_on_their_own_note(tmp_path: Path) -> None:
    body = (
        note("C", 4, 4, lyrics=lyric_xml(text("la")))
        + note("E", 4, 4, extra="<chord/>", lyrics=lyric_xml(text("ni")))
        + quarters(("D", 4), ("E", 4))
    )
    result = _parse(tmp_path, body)
    assert [lyric.text for lyric in _lyrics_of(result, 0)] == ["la"]
    assert [lyric.text for lyric in _lyrics_of(result, 1)] == [
        "ni"
    ]  # not moved to the first member
    assert "LYRIC_DUPLICATE_VERSE" not in _codes(result)


# --- ties -----------------------------------------------------------------------------


def _tied_pair(first: str, second: str) -> str:
    return (
        note("C", 4, 2, tie=tie_xml("start"), notations=tied_xml("start"), lyrics=first)
        + note("C", 4, 2, tie=tie_xml("stop"), notations=tied_xml("stop"), lyrics=second)
        + quarters(("E", 4), ("F", 4))
    )


def test_lyric_on_the_first_tied_note_stays_there(tmp_path: Path) -> None:
    result = _parse(tmp_path, _tied_pair(lyric_xml(text("la")), ""))
    assert [lyric.text for lyric in _lyrics_of(result, 0)] == ["la"]
    assert _lyrics_of(result, 1) == ()
    assert not result.issues


def test_lyric_on_a_tie_continuation_is_preserved_on_that_note(tmp_path: Path) -> None:
    result = _parse(tmp_path, _tied_pair(lyric_xml(text("la")), lyric_xml(text("ni"))))
    assert [lyric.text for lyric in _lyrics_of(result, 0)] == ["la"]
    assert [lyric.text for lyric in _lyrics_of(result, 1)] == ["ni"]  # not moved, not dropped
    assert not result.issues  # reporting it is the lyric analysis' job (M3c2)


def test_extend_on_a_tied_first_note_is_kept(tmp_path: Path) -> None:
    result = _parse(tmp_path, _tied_pair(lyric_xml(text("la"), extend()), ""))
    assert _lyrics_of(result, 0)[0].melisma is Melisma.UNTYPED


def test_returned_notes_are_plain_notes(tmp_path: Path) -> None:
    result = _parse(tmp_path, note("C", 4, 8, lyrics=lyric_xml(text("la"))))
    assert result.song is not None
    assert isinstance(result.song.parts[0].events[0], Note)
