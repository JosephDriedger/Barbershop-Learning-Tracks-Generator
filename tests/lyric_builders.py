"""Helpers that build performed voice lines directly (no XML) for the lyric analysis tests."""

from fractions import Fraction

from barbershop_tracks.core.timeline import merge_tied_notes
from barbershop_tracks.models import (
    LineLyricAnalysis,
    Lyric,
    Melisma,
    Note,
    PerformanceNote,
    Pitch,
    Step,
    Syllabic,
)

C4 = Pitch(Step.C, 4)
LINE = "P1/s1/v1"


def L(  # noqa: N802 - short, test-only
    text: str = "la",
    syllabic: Syllabic = Syllabic.SINGLE,
    *,
    melisma: Melisma = Melisma.NONE,
    verse: str | None = None,
    elided: tuple = (),  # type: ignore[type-arg]
) -> Lyric:
    return Lyric(text=text, syllabic=syllabic, melisma=melisma, verse=verse, elided=elided)


def ext(melisma: Melisma, *, verse: str | None = None) -> Lyric:
    return Lyric.extension(melisma, verse=verse)


def n(
    start: int | Fraction,
    *lyrics: Lyric,
    pitch: Pitch | None = C4,
    dur: int | Fraction = 1,
    to: bool = False,
    frm: bool = False,
) -> Note:
    position = Fraction(start)
    return Note(
        start=position,
        duration=Fraction(dur),
        measure=int(position // 4) + 1,
        beat=Fraction(1) + position % 4,
        written_pitch=pitch,
        tied_to_next=to,
        tied_from_previous=frm,
        lyrics=lyrics,
    )


def r(start: int | Fraction, dur: int | Fraction = 1) -> Note:
    return n(start, pitch=None, dur=dur)


def performed(*notes: Note) -> list[PerformanceNote]:
    """The performed attacks of a line (ties merged). Tie diagnostics are not under test here."""
    return list(merge_tied_notes(notes, part_id=LINE).notes)


def codes(analysis: LineLyricAnalysis) -> list[str]:
    return [issue.code for issue in analysis.issues]
