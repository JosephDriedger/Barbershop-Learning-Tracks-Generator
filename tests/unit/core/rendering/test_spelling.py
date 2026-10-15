"""A rough, spelling-only guess at an English word: last resort, always flagged by its caller."""

import pytest

from barbershop_tracks.core.rendering.compose import compose
from barbershop_tracks.core.rendering.spelling import ARPABET_SYMBOLS, guess_symbols


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ("ship", "sh ih p"),
        ("queen", "k w iy n"),
        ("make", "m ey k"),
        ("light", "l ay t"),
        ("ceive", "s iy v"),
        ("Kathleen", "k ae th l iy n"),
        ("cappuci", "k ae p ah s ih"),
        ("espreso", "eh s p r eh s aa"),
        ("box", "b aa k s"),
    ],
)
def test_common_spellings(word: str, expected: str) -> None:
    assert " ".join(guess_symbols(word)) == expected


def test_a_double_consonant_is_one_sound() -> None:
    assert guess_symbols("ball") == guess_symbols("bal")


def test_a_soft_c_and_g_before_e_i_y() -> None:
    assert guess_symbols("city")[0] == "s"
    assert guess_symbols("gem")[0] == "jh"
    assert guess_symbols("cat")[0] == "k"
    assert guess_symbols("go")[0] == "g"


def test_punctuation_and_case_do_not_matter() -> None:
    assert guess_symbols("Ship!") == guess_symbols("ship")


def test_a_word_with_no_letters_gives_nothing() -> None:
    assert guess_symbols("'") == ()
    assert guess_symbols("") == ()


def test_symbols_are_all_arpabet() -> None:
    for word in ["Biddilly", "thorough", "xylophone", "quiche", "wrong", "knight", "ocean"]:
        assert set(guess_symbols(word)) <= ARPABET_SYMBOLS, word


def test_the_guess_is_the_last_resort_and_says_so() -> None:
    dictionary = {"every": "eh v er iy"}
    spelled = compose("ev'ry", dictionary)
    assert spelled is not None
    assert not spelled.guessed  # a dictionary word: not a guess
    made = compose("blorptastic", dictionary)
    assert made is not None
    assert made.guessed
    assert "may be wrong" in made.how
    assert compose("blorptastic", dictionary, guess=False) is None


def test_a_piece_without_a_vowel_is_not_read_as_a_left_out_letter() -> None:
    # "n't" must not become "net": there is no vowel for the apostrophe to stand for
    made = compose("n't", {"net": "n eh t"})
    assert made is not None
    assert made.guessed
    assert made.symbols == ("n", "t")
