"""A word the dictionary lacks, put together from what it does have.

The pronunciation dictionary (CMUdict, asked through the render host) lacks words such as
``Biddilly``, ``wond'rin`` or ``Oo``. Rather than stopping, BLT looks for a way to write the word
with entries the dictionary *has*, in this order, and joins their sounds:

1. **The word spelled out.** An apostrophe in a sung word stands for a letter left out (``ev'ry`` is
   ``every``, ``heav'n`` is ``heaven``, ``o'er`` is ``over``), a final ``in`` is ``ing`` said short
   (``wond'rin`` is ``wondering`` with the final ``g`` not sung), and ``Oo`` is the dictionary's
   ``ooh``. The first such spelling the dictionary has is used.
2. **Pieces.** Otherwise the word is cut into a few dictionary words: ``bid`` + ``dilly`` sings as
   the two sounds one after the other. A piece is at least three letters (or one of a few short
   everyday words), so that stray two-letter entries do not stand in for syllables; the fewest
   pieces win.

A word that cannot be covered completely is left alone: BLT then stops for that word, as it always
did, and a person decides. Nothing is made up, and the result is only ever a phonetic hint for
that one note, recorded in the package next to the score's own text, with how it was built, so it
is never taken for a decision a person made.

This is only possible for the engine whose hints are ARPAbet (the dictionary's own sounds).
"""

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

SHORT_WORDS = frozenset(
    {
        "a",
        "am",
        "an",
        "as",
        "at",
        "be",
        "by",
        "do",
        "go",
        "he",
        "i",
        "if",
        "in",
        "is",
        "it",
        "me",
        "my",
        "no",
        "of",
        "oh",
        "on",
        "or",
        "so",
        "to",
        "up",
        "us",
        "we",
    }
)
MIN_PIECE = 3
MAX_PIECES = 4
_NOT_LETTERS = re.compile(r"[^a-z]")
_NOT_WORD = re.compile(r"[^a-z']")
_LEFT_OUT = "eaoiuv"  # what an apostrophe may stand for, most likely first


@dataclass(frozen=True, slots=True)
class Composition:
    """A word as dictionary entries and the sounds they make (ARPAbet, no stress marks)."""

    word: str
    pieces: tuple[str, ...]
    symbols: tuple[str, ...]
    how: str  # in words, for the person reading the record


@dataclass(frozen=True, slots=True)
class _Spelling:
    text: str  # a dictionary word that may be what was meant
    short_g: bool  # the final g is not sung ("in" for "ing")
    how: str


def letters_of(word: str) -> str:
    """The word as bare lower-case letters (an apostrophe is not a sound of its own)."""
    return _NOT_LETTERS.sub("", word.lower())


def _spellings(word: str) -> list[_Spelling]:
    """The words the dictionary might have for this spelling, most likely first."""
    raw = _NOT_WORD.sub("", word.lower())
    base = raw.strip("'")
    if not base:
        return []
    forms: list[tuple[str, str]] = []
    if "'" in base:
        if base.count("'") == 1:
            forms = [
                (base.replace("'", ch), f"the apostrophe read as a left-out {ch!r}")
                for ch in _LEFT_OUT
            ]
    elif raw != base:
        forms = [(base, "without its outer apostrophe")]
    elif base[-1] in "aeiou":
        forms = [(base + "h", "with a final h")]
    found: list[_Spelling] = []
    for text, how in forms:
        found.append(_Spelling(text, False, how))
        if text.endswith("in") and len(text) >= 4:
            found.append(_Spelling(text + "g", True, how + ", the final g not sung"))
    return found


def _usable(piece: str) -> bool:
    return len(piece) >= MIN_PIECE or piece in SHORT_WORDS


def candidate_pieces(words: Iterable[str]) -> list[str]:
    """Everything that might be in the dictionary and help with these words (to ask in one go)."""
    found: set[str] = set()
    for word in words:
        letters = letters_of(word)
        found.update(s.text for s in _spellings(word))
        for start in range(len(letters)):
            for stop in range(start + 1, len(letters) + 1):
                piece = letters[start:stop]
                if _usable(piece) and piece != letters:
                    found.add(piece)
    return sorted(found)


def _plain(symbols: str) -> tuple[str, ...]:
    """ARPAbet symbols with the stress digit dropped (``ah0`` is ``ah``)."""
    return tuple(re.sub(r"\d+$", "", s) for s in symbols.split())


def _spelled_out(word: str, dictionary: Mapping[str, str | None]) -> Composition | None:
    for spelling in _spellings(word):
        sounds = dictionary.get(spelling.text)
        if not sounds:
            continue
        symbols = _plain(sounds)
        if spelling.short_g and symbols[-1] == "ng":
            symbols = (*symbols[:-1], "n")
        how = f"spelled out as {spelling.text!r}: {spelling.how}"
        return Composition(word, (spelling.text,), symbols, how)
    return None


def _from_pieces(word: str, dictionary: Mapping[str, str | None]) -> Composition | None:
    letters = letters_of(word)
    if not letters:
        return None
    best: dict[int, tuple[int, tuple[str, ...]]] = {len(letters): (0, ())}
    for start in range(len(letters) - 1, -1, -1):
        options: list[tuple[int, tuple[str, ...]]] = []
        for stop in range(len(letters), start, -1):
            piece = letters[start:stop]
            if not _usable(piece) or piece == letters or not dictionary.get(piece):
                continue
            rest = best.get(stop)
            if rest is not None and rest[0] + 1 <= MAX_PIECES:
                options.append((rest[0] + 1, (piece, *rest[1])))
        if options:
            # fewest pieces first; then the longer first piece (`options` run longest first)
            best[start] = min(options, key=lambda o: o[0])
    chosen = best.get(0)
    if chosen is None or not chosen[1]:
        return None
    symbols: tuple[str, ...] = ()
    for piece in chosen[1]:
        sounds = dictionary.get(piece)
        assert sounds is not None
        symbols += _plain(sounds)
    how = "put together from the dictionary's " + " + ".join(repr(p) for p in chosen[1])
    return Composition(word, chosen[1], symbols, how)


def compose(word: str, dictionary: Mapping[str, str | None]) -> Composition | None:
    """``word`` from dictionary entries, or None when it cannot be covered completely.

    ``dictionary`` maps a piece to the dictionary's sounds for it (None or absent: no entry).
    """
    return _spelled_out(word, dictionary) or _from_pieces(word, dictionary)


def compose_all(
    words: Iterable[str], lookup: Callable[[list[str]], Mapping[str, str | None]]
) -> dict[str, Composition]:
    """Compose every word that can be; ``lookup`` asks the dictionary about pieces at once."""
    wanted = sorted(set(words))
    dictionary = lookup(candidate_pieces(wanted))
    composed: dict[str, Composition] = {}
    for word in wanted:
        result = compose(word, dictionary)
        if result is not None:
            composed[word] = result
    return composed


__all__ = ["Composition", "candidate_pieces", "compose", "compose_all", "letters_of"]
