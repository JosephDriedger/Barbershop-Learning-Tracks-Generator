"""A word the dictionary lacks is built from entries it has (spelled out, or from pieces)."""

from collections.abc import Mapping

from barbershop_tracks.core.rendering.compose import (
    candidate_pieces,
    compose,
    compose_all,
    letters_of,
)

DICTIONARY: Mapping[str, str | None] = {
    "every": "eh1 v er0 iy0",
    "heaven": "hh eh1 v ah0 n",
    "over": "ow1 v er0",
    "loved": "l ah1 v d",
    "wondering": "w ah1 n d er0 ih0 ng",
    "ooh": "uw1",
    "bid": "b ih1 d",
    "dilly": "d ih1 l iy0",
    "dil": "d ih1 l",
    "ly": "l iy1",
    "cause": "k ao1 z",
    "nothing": "n ah1 th ih0 ng",
    "an": "ae1 n",
    "ab": "ae1 b",
}


def test_an_apostrophe_stands_for_a_left_out_letter() -> None:
    for word, spelled in (
        ("ev'ry", "every"),
        ("heav'n", "heaven"),
        ("o'er", "over"),
        ("lov'd", "loved"),
    ):
        made = compose(word, DICTIONARY)
        assert made is not None
        assert made.pieces == (spelled,)


def test_a_final_in_is_ing_said_short() -> None:
    made = compose("wond'rin", DICTIONARY)
    assert made is not None
    assert made.pieces == ("wondering",)
    assert made.symbols[-2:] == ("ih", "n")  # not "ng": the g is not sung
    assert "g not sung" in made.how


def test_an_outer_apostrophe_is_dropped() -> None:
    made = compose("'cause", DICTIONARY)
    assert made is not None
    assert made.pieces == ("cause",)
    nothing = compose("nothin'", DICTIONARY)
    assert nothing is not None
    assert nothing.symbols == ("n", "ah", "th", "ih", "n")


def test_a_vowel_interjection_is_the_dictionarys_h_form() -> None:
    made = compose("Oo", DICTIONARY)
    assert made is not None
    assert made.pieces == ("ooh",)
    assert made.symbols == ("uw",)


def test_stress_marks_are_not_part_of_the_symbols() -> None:
    made = compose("ev'ry", DICTIONARY)
    assert made is not None
    assert made.symbols == ("eh", "v", "er", "iy")


def test_a_word_is_put_together_from_pieces_with_the_fewest_pieces() -> None:
    made = compose("Biddilly", DICTIONARY)
    assert made is not None
    assert made.pieces == ("bid", "dilly")  # two pieces beat bid + dil + ly
    assert made.symbols == ("b", "ih", "d", "d", "ih", "l", "iy")
    assert "bid" in made.how
    assert "dilly" in made.how


def test_a_word_that_cannot_be_covered_completely_is_left_alone() -> None:
    assert compose("blorptastic", DICTIONARY) is None
    assert compose("biddlorp", DICTIONARY) is None  # "bid" covers only the start


def test_two_letter_dictionary_entries_do_not_stand_in_for_syllables() -> None:
    # "an" is a real short word, "ab" is not one BLT trusts as a piece
    assert compose("abab", DICTIONARY) is None
    assert compose("anan", DICTIONARY) is not None


def test_a_word_of_no_letters_gives_nothing() -> None:
    assert compose("'", DICTIONARY) is None


def test_the_candidates_to_ask_include_the_spellings_and_the_pieces() -> None:
    asked = candidate_pieces(["wond'rin", "Biddilly"])
    assert "wondering" in asked
    assert "wonderin" in asked
    assert "bid" in asked
    assert "dilly" in asked
    assert "wondrin" not in asked  # the whole word is what is already known to be missing


def test_compose_all_asks_the_dictionary_once_for_every_word() -> None:
    calls: list[list[str]] = []

    def lookup(pieces: list[str]) -> Mapping[str, str | None]:
        calls.append(pieces)
        return DICTIONARY

    found = compose_all(["ev'ry", "Oo", "blorptastic", "ev'ry"], lookup)
    assert len(calls) == 1
    assert set(found) == {"ev'ry", "Oo"}


def test_letters_of_keeps_only_the_letters() -> None:
    assert letters_of("Wond'rin!") == "wondrin"
