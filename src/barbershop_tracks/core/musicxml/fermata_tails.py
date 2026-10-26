"""Giving the end of a fermata its normal length again: the slow stretch, with a full-tempo tail.

MuseScore plays a fermata as a slower tempo (half, by default) for the length of the note, and its
MIDI export puts the return to the tempo before in the last tick of the note. The singing engine
counts the closing of a syllable in ticks, not in seconds: its closing consonants and the quiet
release at the end of a note take about 60 ticks (``tails.CONSONANT_TICKS``). At half the tempo
those 60 ticks last twice as long, so a syllable held under a fermata sounds for three quarters of
its note and then stops: a gap of a quarter of a second before the next syllable, which is where
the song sounds chopped.

Here the stretch is reshaped so that its last 60 ticks run at the tempo before and the rest runs
a little slower. Every note end stays at the same time in seconds (the time at the end of the
stretch is kept); only the tempo inside the last eighth of a quarter note changes, so the closing
of the syllable takes the time it takes everywhere else in the song. Nothing else is touched: a
ritardando, a section at another tempo, or a tempo that changes at a note start, is left exactly
as it is.
"""

from collections.abc import Sequence
from fractions import Fraction

from barbershop_tracks.models import TempoChange

TAIL = Fraction(1, 8)  # quarter notes: 60 ticks at 480 per quarter, the engine's closing length
_TICK = Fraction(1, 480)
# a stretch is slower than this fraction of the tempo it comes from and of the tempo it returns to
_SLOWER = Fraction(3, 4)
_LONGEST = 4  # quarter notes: a fermata note is no longer than a whole note
_BLIP = Fraction(1, 64)  # a return to the slow tempo this soon is the end of one fermata note
_STEP = 1024  # bpm is a multiple of 1/1024: exact as a double, as in midi_tempo.py


def _on_grid(position: Fraction) -> bool:
    return (position * 480).denominator == 1


def _seconds(quarters: Fraction, bpm: Fraction) -> Fraction:
    return quarters * 60 / bpm


def is_return(changes: Sequence[TempoChange], index: int) -> bool:
    """Whether ``changes[index]`` is the one-tick return to a tempo at the end of a fermata note."""
    if not 0 < index < len(changes) - 1:
        return False
    before, here, after = changes[index - 1], changes[index], changes[index + 1]
    return (
        before.bpm == after.bpm and here.bpm > before.bpm and after.position - here.position < _BLIP
    )


def tempo_changes_heard(changes: Sequence[TempoChange]) -> int:
    """How many changes of tempo there are after the first, not counting the one-tick returns."""
    kept = [c for i, c in enumerate(changes) if not is_return(changes, i)]
    merged = [c for i, c in enumerate(kept) if i == 0 or kept[i - 1].bpm != c.bpm]
    return max(len(merged) - 1, 0)


def _stretch_end(changes: Sequence[TempoChange], index: int) -> Fraction | None:
    """The end of the note whose slow stretch ends at ``changes[index]``, if it is a fermata's."""
    here, slow = changes[index], changes[index - 1]
    if slow.bpm >= here.bpm * _SLOWER:
        return None  # not clearly slower: a ritardando step or a tempo change, not a fermata
    start = slow.position
    if here.position - start > _LONGEST:
        return None  # a long stretch is a section at another tempo, not a held note
    if index >= 2 and slow.bpm >= changes[index - 2].bpm * _SLOWER:
        return None  # not entered by a clear drop: the last step of a ritardando
    ending = here.position + _TICK
    following = changes[index + 1] if index + 1 < len(changes) else None
    if following is not None:
        if following.position - here.position < _BLIP and following.bpm == slow.bpm:
            ending = following.position  # another fermata note follows at once
        elif following.position <= ending:
            return None
    if not (_on_grid(ending) and _on_grid(ending - TAIL)):
        return None
    if ending - TAIL < start + TAIL:
        return None  # a stretch too short to have a tail of its own
    return ending


def with_fermata_tails(changes: Sequence[TempoChange]) -> tuple[TempoChange, ...]:
    """``changes`` with the last eighth of a quarter of every fermata note at the faster tempo."""
    result = list(changes)
    for index in range(1, len(changes)):
        ending = _stretch_end(changes, index)
        if ending is None:
            continue
        slow, fast = changes[index - 1], changes[index]
        start = slow.position
        kept = _seconds(fast.position - start, slow.bpm) + _seconds(
            ending - fast.position, fast.bpm
        )
        remaining = kept - _seconds(TAIL, fast.bpm)
        if remaining <= 0:
            continue
        bpm = (ending - TAIL - start) * 60 / remaining
        bpm = Fraction(round(bpm * _STEP), _STEP)
        if bpm <= 0:
            continue
        result[index - 1] = TempoChange(position=start, bpm=bpm)
        result[index] = TempoChange(position=ending - TAIL, bpm=fast.bpm)
    return tuple(result)
