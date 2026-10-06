"""Choosing which logical verse of a line (or song) to analyze.

Grouping uses ``Lyric.logical_verse``: an absent ``number`` and an explicit ``"1"`` are the same
logical verse, while their source identities (``verse=None`` versus ``"1"``) stay distinct and
are never rewritten. Automatic choice: logical ``"1"`` if present, otherwise the first logical
verse in document order. A requested verse overrides the automatic choice.
"""

from collections.abc import Iterable, Sequence

from barbershop_tracks.models import DEFAULT_VERSE, Lyric, Note, PerformanceNote, VerseChoice


def line_lyrics(performed: Iterable[PerformanceNote]) -> list[Lyric]:
    """Every lyric of every source note, in document order."""
    return [lyric for p in performed for note in p.source for lyric in note.lyrics]


def logical_verses(performed: Iterable[PerformanceNote]) -> tuple[str, ...]:
    """The logical verses present, in order of first appearance."""
    seen: dict[str, None] = {}
    for lyric in line_lyrics(performed):
        seen.setdefault(lyric.logical_verse, None)
    return tuple(seen)


def merge_verses(per_line: Iterable[Sequence[str]]) -> tuple[str, ...]:
    """Combine several lines' verse lists, keeping first-appearance order."""
    seen: dict[str, None] = {}
    for verses in per_line:
        for verse in verses:
            seen.setdefault(verse, None)
    return tuple(seen)


def choose_verse(available: Sequence[str], requested: str | None = None) -> VerseChoice:
    """Pick the verse to analyze (see the module docstring)."""
    verses = tuple(available)
    if requested is not None:
        return VerseChoice(
            selected=requested,
            available=verses,
            requested=requested,
            found=requested in verses,
        )
    if DEFAULT_VERSE in verses:
        return VerseChoice(selected=DEFAULT_VERSE, available=verses)
    if verses:
        return VerseChoice(selected=verses[0], available=verses)
    return VerseChoice(selected=None, available=verses)


def lyrics_for(note: Note, verse: str | None) -> tuple[Lyric, ...]:
    """The lyrics of ``note`` that belong to the logical ``verse`` (none if ``verse`` is None)."""
    if verse is None:
        return ()
    return tuple(lyric for lyric in note.lyrics if lyric.logical_verse == verse)


def has_mixed_numbering(performed: Iterable[PerformanceNote], verse: str | None) -> bool:
    """True if the default verse occurs both numbered ``"1"`` and unnumbered in the line."""
    if verse != DEFAULT_VERSE:
        return False
    forms = {lyric.verse for lyric in line_lyrics(performed) if lyric.logical_verse == verse}
    return None in forms and DEFAULT_VERSE in forms
