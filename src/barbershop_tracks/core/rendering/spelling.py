"""A rough guess at how an English word is said, from its spelling alone (ARPAbet).

This is the last resort for a word that neither the pronunciation dictionary nor its pieces can
explain: a few hand-written spelling rules (``ch`` is ``ch``, ``ee`` is ``iy``, a final silent
``e`` makes the vowel before it long...). It is not a model and it is often wrong; English
spelling is not regular. It exists so that a missing word is sung as *something* close and the
person is told, instead of the whole run stopping. Whatever it makes is recorded as a guess.
"""

import re

_VOWEL_LETTERS = "aeiouy"
_SHORT = {"a": "ae", "e": "eh", "i": "ih", "o": "aa", "u": "ah"}
_LONG = {"a": "ey", "e": "iy", "i": "ay", "o": "ow", "u": "uw"}
_SOFT = "eiy"

# longest spelling first; "^" marks the start of the word and "$" its end
_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("cei", ("s", "iy")),
    ("tch", ("ch",)),
    ("dge", ("jh",)),
    ("igh", ("ay",)),
    ("ough", ("ow",)),
    ("^kn", ("n",)),
    ("^wr", ("r",)),
    ("^ps", ("s",)),
    ("mb$", ("m",)),
    ("ch", ("ch",)),
    ("sh", ("sh",)),
    ("th", ("th",)),
    ("ph", ("f",)),
    ("wh", ("w",)),
    ("ng", ("ng",)),
    ("nk", ("ng", "k")),
    ("ck", ("k",)),
    ("qu", ("k", "w")),
    ("gh", ()),
    ("oo", ("uw",)),
    ("ee", ("iy",)),
    ("ea", ("iy",)),
    ("ai", ("ey",)),
    ("ay", ("ey",)),
    ("oa", ("ow",)),
    ("ow$", ("ow",)),
    ("ow", ("aw",)),
    ("ou", ("aw",)),
    ("oi", ("oy",)),
    ("oy", ("oy",)),
    ("au", ("ao",)),
    ("aw", ("ao",)),
    ("ie", ("iy",)),
    ("ei", ("ey",)),
    ("ue", ("uw",)),
    ("ew", ("uw",)),
    ("ar", ("aa", "r")),
    ("or", ("ao", "r")),
    ("er", ("er",)),
    ("ir", ("er",)),
    ("ur", ("er",)),
)
_PLAIN = {
    "b": "b",
    "d": "d",
    "f": "f",
    "h": "hh",
    "j": "jh",
    "k": "k",
    "l": "l",
    "m": "m",
    "n": "n",
    "p": "p",
    "r": "r",
    "s": "s",
    "t": "t",
    "v": "v",
    "w": "w",
    "z": "z",
}
_NOT_LETTERS = re.compile(r"[^a-z]")
# every symbol a guess can contain (ARPAbet, as the pronunciation dictionary writes it)
ARPABET_SYMBOLS = frozenset(
    {
        "aa",
        "ae",
        "ah",
        "ao",
        "aw",
        "ay",
        "eh",
        "er",
        "ey",
        "ih",
        "iy",
        "ow",
        "oy",
        "uh",
        "uw",
        "b",
        "ch",
        "d",
        "dh",
        "f",
        "g",
        "hh",
        "jh",
        "k",
        "l",
        "m",
        "n",
        "ng",
        "p",
        "r",
        "s",
        "sh",
        "t",
        "th",
        "v",
        "w",
        "y",
        "z",
        "zh",
    }
)


def _vowel(letter: str, magic: bool) -> str:
    return (_LONG if magic else _SHORT)[letter]


def guess_symbols(word: str) -> tuple[str, ...]:
    """The ARPAbet symbols a spelling-only guess gives for ``word`` (empty if it has no letters)."""
    text = _NOT_LETTERS.sub("", word.lower())
    if not text:
        return ()
    # a vowel, a consonant and a final e: the e is silent and the vowel is long ("make", "line")
    magic_at = -1
    found = re.search(r"([aeiou])([^aeiouy])e$", text)
    if found and len(text) > 2:
        magic_at = found.start(1)
        text = text[:-1]
    symbols: list[str] = []
    i = 0
    while i < len(text):
        start, end = i == 0, False
        matched = False
        for spelling, sounds in _GROUPS:
            key = spelling.strip("^$")
            if not text.startswith(key, i):
                continue
            if spelling.startswith("^") and not start:
                continue
            end = i + len(key) == len(text)
            if spelling.endswith("$") and not end:
                continue
            symbols.extend(sounds)
            i += len(key)
            matched = True
            break
        if matched:
            continue
        letter = text[i]
        following = text[i + 1] if i + 1 < len(text) else ""
        if following == letter and letter not in _VOWEL_LETTERS:
            i += 1  # a double consonant is one sound
            continue
        i += 1
        if letter in _PLAIN:
            symbols.append(_PLAIN[letter])
        elif letter == "c":
            symbols.append("s" if following and following in _SOFT else "k")
        elif letter == "g":
            symbols.append("jh" if following and following in _SOFT else "g")
        elif letter == "q":
            symbols.append("k")
        elif letter == "x":
            symbols.extend(("k", "s"))
        elif letter == "y":
            at_start = i - 1 == 0
            symbols.append("y" if at_start else ("iy" if i == len(text) else "ih"))
        elif letter in _SHORT:
            if letter == "e" and i == len(text) and len(text) > 2:
                continue  # a final e after a consonant cluster is silent
            symbols.append(_vowel(letter, i - 1 == magic_at))
    return tuple(symbols)


__all__ = ["ARPABET_SYMBOLS", "guess_symbols"]
