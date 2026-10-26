"""Giving the end of a fermata its normal length again: the slow stretch, with a full-tempo tail.

MuseScore plays a fermata as a slower tempo (half, by default) for the length of the note, and its
MIDI export puts the return to the tempo before in the last tick of the note. The singing engine
counts the closing of a syllable in ticks, not in seconds: its closing consonants and the quiet
release at the end of a note take about 60 ticks (``tails.CONSONANT_TICKS``). At half the tempo
those 60 ticks last twice as long, so a syllable held under a fermata sounds for three quarters of
its note and then stops: a gap of a quarter of a second before the next syllable, which is where
the song sounds chopped.

Here the stretch is reshaped so that the end of the note runs at the tempo before and the rest of
the note runs slower. Every note end stays at the same time in seconds (the time at the end of the
stretch is kept); only the tempo inside the tail changes, so the closing of the syllable takes the
time it takes everywhere else in the song. The tail is 300 ticks, a little under five eighths of a
quarter note, for two reasons measured against the same words at the normal tempo. The engine
puts the closing consonants of a word 60, 120 and 180 ticks before the end of its note (and the
opening ones of the next word the same before its start); with a tail of 60 ticks a word such as
"first" still had its "s" in the slow part, a third of a second too early. And a diphthong before
a stop ("night") on a long stretched note had a dip in the vowel about 200 to 230 ticks before the
end, which only a tail of 240 or more removes (300 matches the normal tempo exactly). A note too
short for that gets a tail of 60 to 240 ticks and always keeps 30 ticks of slow part. Nothing else
is touched: a ritardando, a section at another tempo, or a tempo that changes at a note start, is
left exactly as it is.
"""

from collections.abc import Sequence
from fractions import Fraction

from barbershop_tracks.models import TempoChange

CONSONANT = Fraction(
    1, 8
)  # quarter notes: 60 ticks at 480 per quarter, the engine's closing length
TAIL = 5 * CONSONANT  # 300 ticks: three consonants of one word, and the glide of a diphthong
_TICK = Fraction(1, 480)
_SLOW_PART = Fraction(1, 16)  # the least of a note that stays at the slow tempo: 30 ticks
# a stretch is slower than this fraction of the tempo it comes from and of the tempo it returns to
_SLOWER = Fraction(3, 4)
_LONGEST = 4  # quarter notes: a fermata note is no longer than a whole note
# MuseScore returns to the tempo before in the last tick of a fermata note, so the tick after the
# return is on the grid of the notes (a thirty-second or a triplet: 10 ticks); the steps of a
# ritardando, "a tempo" and a tempo mark are on that grid themselves
_GRID = 10
_BLIP = Fraction(1, 64)  # a return to the slow tempo this soon is the end of one fermata note
# the shaped slow tempo is a multiple of 2**-20 bpm: exact as a double (the project file states it
# with no quantisation error), and fine enough that rounding moves a note end by under a microsecond
_STEP = 1 << 20
# a MIDI file cannot hold a tempo under 3.58 bpm (the handoff export would refuse the score)
_MIN_BPM = 4


def _on_grid(position: Fraction) -> bool:
    return (position * 480).denominator == 1


def tail_for(length: Fraction) -> Fraction:
    """The tail of a fermata note ``length`` long (quarters): up to ``TAIL``, whole consonants.

    Zero when the note is too short to keep a slow part and a whole consonant.
    """
    room = max(length - _SLOW_PART, Fraction(0))
    return min(TAIL, CONSONANT * int(room / CONSONANT))


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


def _stretch_end(changes: Sequence[TempoChange], index: int) -> tuple[Fraction, Fraction] | None:
    """The end and the tail of the note whose slow stretch ends at ``changes[index]``, if any."""
    here, slow = changes[index], changes[index - 1]
    if slow.bpm >= here.bpm * _SLOWER:
        return None  # not clearly slower: a ritardando step or a tempo change, not a fermata
    start = slow.position
    if here.position - start > _LONGEST:
        return None  # a long stretch is a section at another tempo, not a held note
    if (here.position * 480 + 1) % _GRID != 0:
        return None  # MuseScore returns from a fermata one tick before the note end, never on it
    ending = here.position + _TICK
    following = changes[index + 1] if index + 1 < len(changes) else None
    if following is not None:
        if following.position - here.position < _BLIP and following.bpm == slow.bpm:
            ending = following.position  # another fermata note follows at once
        elif following.position <= ending:
            return None
    tail = tail_for(ending - start)
    if tail == 0 or not (_on_grid(ending) and _on_grid(ending - tail)):
        return None  # too short to have a tail of its own, or an end off the engine's grid
    return ending, tail


def _slow_part(
    changes: Sequence[TempoChange], index: int, ending: Fraction, tail: Fraction
) -> Fraction | None:
    """The tempo of the first part of the note when its last ``tail`` runs at the faster tempo."""
    slow, fast = changes[index - 1], changes[index]
    start = slow.position
    kept = _seconds(fast.position - start, slow.bpm) + _seconds(ending - fast.position, fast.bpm)
    remaining = kept - _seconds(tail, fast.bpm)
    if remaining <= 0:
        return None
    exact = (ending - tail - start) * 60 / remaining
    bpm = Fraction(round(exact * _STEP), _STEP)
    return bpm if bpm >= _MIN_BPM else None


def with_fermata_tails(changes: Sequence[TempoChange]) -> tuple[TempoChange, ...]:
    """``changes`` with the end of every fermata note at the faster tempo (see the module text)."""
    result = list(changes)
    for index in range(1, len(changes)):
        found = _stretch_end(changes, index)
        if found is None:
            continue
        ending, longest = found
        tail = longest
        while tail >= CONSONANT:  # a shorter tail when the first part would need a tempo too slow
            bpm = _slow_part(changes, index, ending, tail)
            if bpm is not None:
                start = changes[index - 1].position
                result[index - 1] = TempoChange(position=start, bpm=bpm)
                result[index] = TempoChange(position=ending - tail, bpm=changes[index].bpm)
                break
            tail -= CONSONANT
    return tuple(result)
