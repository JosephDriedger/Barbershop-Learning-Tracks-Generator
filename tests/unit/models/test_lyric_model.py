"""The source lyric model: literal, with absence made explicit."""

import pytest

from barbershop_tracks.models import (
    DEFAULT_VERSE,
    Lyric,
    LyricKind,
    LyricSegment,
    Melisma,
    Syllabic,
)

# --- syllabic ---------------------------------------------------------------------------


def test_missing_syllabic_is_unspecified_never_single() -> None:
    assert Lyric(text="la").syllabic is Syllabic.UNSPECIFIED


def test_every_syllabic_value_including_unspecified_is_storable() -> None:
    for value in Syllabic:
        assert Lyric(text="la", syllabic=value).syllabic is value


def test_unspecified_is_distinct_from_single() -> None:
    assert len({Syllabic.UNSPECIFIED, Syllabic.SINGLE}) == 2
    assert Lyric(text="la") != Lyric(text="la", syllabic=Syllabic.SINGLE)


# --- verse / name / time-only -----------------------------------------------------------


def test_absent_number_is_none_not_one() -> None:
    assert Lyric(text="la").verse is None
    assert Lyric(text="la", verse="1").verse == "1"
    assert Lyric(text="la") != Lyric(text="la", verse="1")  # <lyric> vs <lyric number="1">


def test_logical_verse_groups_absent_with_the_default_without_changing_the_source() -> None:
    absent, one, two = Lyric(text="a"), Lyric(text="a", verse="1"), Lyric(text="a", verse="2")
    assert DEFAULT_VERSE == "1"
    assert absent.logical_verse == one.logical_verse == "1"
    assert two.logical_verse == "2"
    assert absent.verse is None  # the grouping key does not rewrite the source value


def test_empty_number_is_rejected() -> None:
    with pytest.raises(ValueError, match="verse"):
        Lyric(text="la", verse="")


def test_verse_two_alone_is_not_renumbered() -> None:
    assert Lyric(text="la", verse="2").verse == "2"


def test_name_and_time_only_are_kept_verbatim() -> None:
    lyric = Lyric(text="la", name="chorus", time_only="1, 3")
    assert (lyric.name, lyric.time_only) == ("chorus", "1, 3")
    assert Lyric(text="la").name is None
    assert Lyric(text="la").time_only is None


# --- text -------------------------------------------------------------------------------


def test_text_is_verbatim() -> None:
    for raw in (" la ", "la ni", "  ", "+", "-", "[la]", "la~", "ba-", "la‿ni", "la_ni"):
        assert Lyric(text=raw).text == raw


def test_a_text_lyric_needs_non_empty_text() -> None:
    with pytest.raises(ValueError, match="needs text"):
        Lyric(text="")


# --- extend forms -----------------------------------------------------------------------


def test_every_extend_form_is_distinguishable() -> None:
    forms = set(Melisma)
    assert forms == {Melisma.NONE, Melisma.UNTYPED, Melisma.START, Melisma.CONTINUE, Melisma.STOP}
    for form in forms:
        assert Lyric(text="la", melisma=form).melisma is form


def test_text_with_an_odd_extend_type_is_stored_as_written() -> None:
    # The model does not judge; the analysis does.
    assert Lyric(text="la", melisma=Melisma.STOP).melisma is Melisma.STOP
    assert Lyric(text="la", melisma=Melisma.CONTINUE).melisma is Melisma.CONTINUE


def test_extension_lyric_accepts_every_extend_form_but_not_none() -> None:
    for form in (Melisma.UNTYPED, Melisma.START, Melisma.CONTINUE, Melisma.STOP):
        lyric = Lyric.extension(form)
        assert lyric.kind is LyricKind.EXTENSION
        assert not lyric.has_text
    with pytest.raises(ValueError, match="needs an <extend>"):
        Lyric.extension(Melisma.NONE)


# --- humming / laughing -----------------------------------------------------------------


def test_humming_and_laughing_are_first_class_kinds() -> None:
    humming, laughing = Lyric.humming(), Lyric.laughing(verse="2", name="verse")
    assert humming.kind is LyricKind.HUMMING
    assert laughing.kind is LyricKind.LAUGHING
    assert (laughing.verse, laughing.name) == ("2", "verse")
    assert not humming.has_text
    assert humming.text == ""


def test_non_text_kinds_carry_no_text_segments_or_syllabic() -> None:
    for kind in (LyricKind.EXTENSION, LyricKind.HUMMING, LyricKind.LAUGHING):
        with pytest.raises(ValueError, match="no text"):
            Lyric(kind=kind, text="x", melisma=Melisma.STOP)
        with pytest.raises(ValueError, match="no text"):
            Lyric(kind=kind, syllabic=Syllabic.SINGLE, melisma=Melisma.STOP)
        with pytest.raises(ValueError, match="no text"):
            Lyric(kind=kind, elided=(LyricSegment(text="a"),), melisma=Melisma.STOP)


def test_humming_and_laughing_have_no_extend() -> None:
    with pytest.raises(ValueError, match="no <extend>"):
        Lyric(kind=LyricKind.HUMMING, melisma=Melisma.UNTYPED)
    with pytest.raises(ValueError, match="no <extend>"):
        Lyric(kind=LyricKind.LAUGHING, melisma=Melisma.START)


# --- elision segments -------------------------------------------------------------------


def test_segment_keeps_joiner_and_smufl_name_literally() -> None:
    segment = LyricSegment(text="ni", syllabic=Syllabic.END, joiner="‿")
    assert (segment.joiner, segment.joiner_smufl) == ("‿", None)
    bare = LyricSegment(text="ni", joiner_smufl="lyricsElision")
    assert (bare.joiner, bare.joiner_smufl, bare.syllabic) == (
        "",
        "lyricsElision",
        Syllabic.UNSPECIFIED,
    )


def test_elided_segments_are_a_tuple_and_extend_full_text() -> None:
    lyric = Lyric(
        text="la",
        elided=[LyricSegment(text="ni", joiner="‿")],  # type: ignore[arg-type]
    )
    assert isinstance(lyric.elided, tuple)
    assert lyric.is_elided
    assert lyric.full_text == "la‿ni"
    assert lyric.text == "la"


def test_segment_text_must_not_be_empty() -> None:
    with pytest.raises(ValueError, match="text"):
        LyricSegment(text="")


def test_lyrics_are_immutable() -> None:
    lyric = Lyric(text="la")
    with pytest.raises(AttributeError):
        lyric.text = "x"  # type: ignore[misc]
