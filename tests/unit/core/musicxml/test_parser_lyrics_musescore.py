"""Our literal lyric parsing against MuseScore 4.7.4 behavior (research fixtures).

Each test names which side it documents:

* SOURCE: what our parser stores for the hand-written input (the standards-based reading);
* MUSESCORE: what MuseScore's re-export of the same input looks like and how we read it;
* DIVERGENCE: the two differ on purpose. We do not copy MuseScore's normalizations (it writes
  ``single`` for a missing syllabic, renumbers verses, moves grace and chord lyrics onto another
  note, writes an untyped ``<extend/>`` for every melisma, drops humming, name and time-only).
  Do not "fix" the source reading to match MuseScore.

All lyric text in these fixtures is original nonsense (la, ni, na, ma, ba) or a few symbols.
"""

from pathlib import Path

import pytest

from barbershop_tracks.core.musicxml import ParseResult, parse_musicxml
from barbershop_tracks.models import Lyric, LyricKind, Melisma, Note, Syllabic

pytestmark = pytest.mark.usefixtures("no_network")

LYRICS = Path(__file__).resolve().parents[3] / "fixtures" / "musicxml" / "lyrics"
GLYPH = chr(0xE551)  # MuseScore's elision glyph (SMuFL lyricsElisionNarrow)
NBSP = chr(0xA0)


def parse(variant: str, name: str) -> ParseResult:
    return parse_musicxml(LYRICS / variant / f"{name}.musicxml")


def src(name: str) -> ParseResult:
    return parse("inputs", name)


def ms(name: str) -> ParseResult:
    return parse("musescore_roundtrip", name)


def events(result: ParseResult, line: str = "P1/s1/v1") -> tuple[Note, ...]:
    assert result.song is not None
    return next(p for p in result.song.parts if p.part_id == line).events


def lyrics(result: ParseResult, index: int, line: str = "P1/s1/v1") -> tuple[Lyric, ...]:
    return events(result, line)[index].lyrics


def codes(result: ParseResult) -> set[str]:
    return {i.code for i in result.issues}


def first(result: ParseResult, index: int = 0) -> Lyric:
    (only,) = lyrics(result, index)
    return only


FIXTURE_NAMES = sorted(p.stem for p in (LYRICS / "inputs").glob("*.musicxml"))


# --- every fixture loads ----------------------------------------------------------------


def test_the_fixture_set_is_complete() -> None:
    assert len(FIXTURE_NAMES) == 38
    assert {p.stem for p in (LYRICS / "musescore_roundtrip").glob("*.musicxml")} == set(
        FIXTURE_NAMES
    )


@pytest.mark.parametrize("variant", ["inputs", "musescore_roundtrip"])
@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_every_fixture_parses_without_raising(variant: str, name: str) -> None:
    assert parse(variant, name).song is not None


# --- syllabic ---------------------------------------------------------------------------


def test_divergence_missing_syllabic_is_unspecified_but_musescore_writes_single() -> None:
    assert first(src("l22_text_without_syllabic")).syllabic is Syllabic.UNSPECIFIED  # SOURCE
    assert first(ms("l22_text_without_syllabic")).syllabic is Syllabic.SINGLE  # MUSESCORE


def test_syllabic_chain_values_are_preserved_in_both() -> None:
    for variant in (src, ms):
        result = variant("l18_word_three_syllables")
        assert [first(result, i).syllabic for i in range(3)] == [
            Syllabic.BEGIN,
            Syllabic.MIDDLE,
            Syllabic.END,
        ]


@pytest.mark.parametrize(
    "name", ["l19_begin_then_rest_then_end", "l20_end_without_begin", "l21_begin_never_ended"]
)
def test_broken_word_chains_are_stored_literally_not_judged_by_the_parser(name: str) -> None:
    for variant in (src, ms):
        assert not variant(name).issues  # judging them is the M3c2 analysis


def test_trailing_hyphen_in_the_text_is_kept() -> None:
    assert first(src("l31_text_with_trailing_hyphen")).text == "ba-"
    assert first(ms("l31_text_with_trailing_hyphen")).text == "ba-"


# --- extend -----------------------------------------------------------------------------


def test_divergence_typed_extend_input_is_kept_but_musescore_normalizes_to_untyped() -> None:
    source = src("l01_extend_typed")
    assert first(source, 0).melisma is Melisma.START  # SOURCE: typed start on the first note
    assert first(source, 1).melisma is Melisma.CONTINUE  # extension-only lyrics on the next notes
    assert first(source, 1).kind is LyricKind.EXTENSION
    assert first(source, 2).melisma is Melisma.STOP

    export = ms("l01_extend_typed")  # MUSESCORE: always an untyped extender, first note only
    assert first(export, 0).melisma is Melisma.UNTYPED
    assert lyrics(export, 1) == ()
    assert lyrics(export, 2) == ()


def test_musescore_always_writes_an_untyped_extender_and_leaves_following_notes_lyricless() -> None:
    for name in ("l01_extend_typed", "l02_extend_untyped_then_empty", "l08_tie_with_extend"):
        export = ms(name)
        extenders = [
            lyric.melisma
            for e in events(export)
            for lyric in e.lyrics
            if lyric.melisma is not Melisma.NONE
        ]
        assert extenders == [Melisma.UNTYPED]


def test_untyped_extender_input_is_read_as_untyped_not_start() -> None:
    assert first(src("l02_extend_untyped_then_empty")).melisma is Melisma.UNTYPED
    assert first(ms("l02_extend_untyped_then_empty")).melisma is Melisma.UNTYPED


def test_a_slur_without_an_extender_is_not_melisma_evidence() -> None:
    for variant in (src, ms):
        result = variant("l03_slur_no_extend")
        assert first(result, 0).melisma is Melisma.NONE
        assert lyrics(result, 1) == ()  # the slurred notes stay lyric-less
        assert lyrics(result, 2) == ()
        assert not result.issues  # slurs are not read at all in M3c


def test_extender_across_a_rest_and_at_the_end_of_the_line_are_stored_as_written() -> None:
    for name in ("l04_extend_across_rest", "l05_extend_ends_at_end_of_part"):
        for variant in (src, ms):
            result = variant(name)
            assert not result.issues
            assert any(
                lyric.melisma is Melisma.UNTYPED for e in events(result) for lyric in e.lyrics
            )


# --- verses, name, time-only ------------------------------------------------------------


def test_divergence_absent_number_is_none_but_musescore_writes_one() -> None:
    assert first(src("l15_no_number")).verse is None
    assert first(ms("l15_no_number")).verse == "1"


def test_divergence_a_lone_verse_two_is_not_renumbered_by_us() -> None:
    assert first(src("l14_verse_two_only")).verse == "2"
    assert first(ms("l14_verse_two_only")).verse == "1"  # MuseScore renumbered it


def test_two_verses_are_preserved_in_both() -> None:
    for variant in (src, ms):
        result = variant("l13_two_verses")
        assert [lyric.verse for lyric in lyrics(result, 0)] == ["1", "2"]
        assert [lyric.text for lyric in lyrics(result, 0)] == ["la", "ni"]
        assert not result.issues


def test_divergence_name_is_preserved_but_musescore_drops_it() -> None:
    source = src("l16_named_verse")
    assert (first(source, 0).name, first(source, 1).name) == ("verse", "chorus")
    assert not source.issues  # name is metadata, never unsupported
    assert first(ms("l16_named_verse"), 0).name is None


def test_divergence_time_only_is_preserved_and_unsupported_but_musescore_drops_it() -> None:
    source = src("l17_time_only")
    assert (first(source, 0).time_only, first(source, 1).time_only) == ("1", "2")
    assert codes(source) == {"LYRIC_TIME_ONLY_UNSUPPORTED"}
    export = ms("l17_time_only")
    assert first(export, 0).time_only is None
    assert not export.issues


# --- humming, laughing, formatting-only elements ---------------------------------------


@pytest.mark.parametrize(
    ("name", "kind"),
    [("l27_humming", LyricKind.HUMMING), ("l28_laughing", LyricKind.LAUGHING)],
)
def test_divergence_humming_and_laughing_are_preserved_but_musescore_drops_them(
    name: str, kind: LyricKind
) -> None:
    source = src(name)
    assert first(source, 0).kind is kind
    assert not source.issues  # legitimate vocal events, not errors
    assert lyrics(ms(name), 0) == ()


def test_end_line_and_end_paragraph_do_not_disturb_the_text() -> None:
    for variant in (src, ms):
        result = variant("l29_end_line")
        assert [first(result, i).text for i in (0, 1)] == ["la", "ni"]
        assert not result.issues


# --- placements that cannot hold a lyric --------------------------------------------------


def test_lyric_on_a_rest_is_an_error_in_both_because_musescore_keeps_it() -> None:
    for variant in (src, ms):
        result = variant("l09_lyric_on_rest")
        assert "LYRIC_ON_REST" in codes(result)
        assert lyrics(result, 1) == ()  # nothing is attached to the rest or to a neighbour
        assert [first(result, i).text for i in (0, 2)] == ["la", "na"]


def test_lyric_on_a_cue_note_is_an_error_in_both() -> None:
    for variant in (src, ms):
        assert "LYRIC_ON_CUE_NOTE" in codes(variant("l10_lyric_on_cue"))


def test_divergence_grace_lyric_is_an_error_where_musescore_moves_it_to_the_main_note() -> None:
    source = src("l11_lyric_on_grace")
    assert "LYRIC_ON_GRACE_NOTE" in codes(source)  # SOURCE: reported, not attached anywhere
    assert [lyric.text for lyric in lyrics(source, 0)] == ["la"]
    assert "LYRIC_DUPLICATE_VERSE" not in codes(source)

    export = ms("l11_lyric_on_grace")  # MUSESCORE moved "ni" onto the main note: two lyrics
    assert [lyric.text for lyric in lyrics(export, 0)] == ["ni", "la"]
    assert "LYRIC_DUPLICATE_VERSE" in codes(export)  # so MuseScore's own file is an ERROR for us


def test_divergence_chord_lyrics_stay_on_their_notes_but_musescore_moves_them() -> None:
    source = src("l12_lyric_on_chord_members")
    assert [first(source, 0).text, first(source, 1).text] == ["la", "ni"]
    assert not source.issues

    export = ms("l12_lyric_on_chord_members")
    assert [lyric.text for lyric in lyrics(export, 0)] == ["la", "ni"]  # both on the first member
    assert lyrics(export, 1) == ()
    assert "LYRIC_DUPLICATE_VERSE" in codes(export)


# --- ties ---------------------------------------------------------------------------------


def test_lyrics_on_tied_notes_stay_on_their_source_notes() -> None:
    for variant in (src, ms):
        first_only = variant("l06_tie_lyric_on_first_only")
        assert [bool(lyrics(first_only, i)) for i in range(2)] == [True, False]
        both = variant("l07_tie_lyric_on_both")
        assert [first(both, i).text for i in range(2)] == ["la", "ni"]  # MuseScore keeps both
        assert not both.issues.has_errors  # reporting the swallowed syllable is the analysis's job


# --- elision and multiple text -------------------------------------------------------------


def test_divergence_standard_elision_element_versus_musescores_single_text() -> None:
    source = first(src("l23_elision_element"))
    assert (source.text, source.elided[0].text, source.elided[0].joiner) == ("la", "ni", "‿")
    exported = first(ms("l23_elision_element"))
    assert (exported.text, exported.is_elided) == ("la‿ni", False)  # one literal text


def test_underscore_elision_element_and_musescores_single_text() -> None:
    assert first(src("l24_elision_underscore")).elided[0].joiner == "_"
    assert first(ms("l24_elision_underscore")).text == "la_ni"


@pytest.mark.parametrize(
    "name",
    [
        "l25_elision_smufl",
        "l35_elision_smufl_plain",
        "l36_elision_smufl_wide",
        "l38_elision_empty_no_smufl",
    ],
)
def test_musescores_glyph_pattern_is_recognized_deterministically(name: str) -> None:
    export = first(ms(name))
    assert export.text == "la"
    (segment,) = export.elided
    assert (segment.text, segment.joiner) == ("ni", GLYPH)
    assert not ms(name).issues


def test_smufl_elision_element_keeps_its_glyph_name_in_the_source() -> None:
    assert first(src("l35_elision_smufl_plain")).elided[0].joiner_smufl == "lyricsElision"
    assert first(src("l36_elision_smufl_wide")).elided[0].joiner_smufl == "lyricsElisionWide"
    assert first(src("l38_elision_empty_no_smufl")).elided[0].joiner_smufl is None


def test_no_break_space_elision() -> None:
    assert first(src("l37_elision_nbsp")).elided[0].joiner == NBSP
    assert first(ms("l37_elision_nbsp")).text == f"la{NBSP}ni"


def test_text_containing_a_space_is_one_literal_text() -> None:
    for variant in (src, ms):
        lyric = first(variant("l26_text_with_space"))
        assert (lyric.text, lyric.is_elided) == ("la ni", False)


# --- verbatim text ------------------------------------------------------------------------


def test_special_characters_and_edge_whitespace_survive_both() -> None:
    for variant in (src, ms):
        special = variant("l30_special_text")
        assert [first(special, i).text for i in range(4)] == ["+", "-", "[la]", "la~"]
        assert first(variant("l33_leading_trailing_space")).text == " la "


def test_divergence_empty_text_is_a_warning_for_us_and_dropped_by_musescore() -> None:
    assert codes(src("l34_empty_text")) == {"LYRIC_EMPTY"}
    assert lyrics(src("l34_empty_text"), 0) == ()
    assert lyrics(ms("l34_empty_text"), 0) == ()
    assert not ms("l34_empty_text").issues


def test_two_voices_keep_their_own_lyrics_in_both() -> None:
    for variant in (src, ms):
        result = variant("l32_two_voices_own_lyrics")
        assert (
            first(
                result,
                0,
            ).text
            == "la"
        )
        assert [lyric.text for lyric in lyrics(result, 0, "P1/s1/v2")] == ["ni"]
        assert [lyric.text for lyric in lyrics(result, 1, "P1/s1/v2")] == ["na"]
