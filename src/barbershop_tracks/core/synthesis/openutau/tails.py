"""Letting a short last note of a held word sound its own pitch, not only the closing consonant.

Arpasing puts a word's closing consonant(s) at the very end of the whole group of notes the word is
sung over: each gets ``ConsonantLength`` (60 ticks, a fifth of a quarter note at 480 per quarter)
before the end of the group. Over a single note that is natural. Over a word held on several notes
whose last note is short, such as the dotted eighth and sixteenth of "babe", the consonant takes
half of the sixteenth and the consonant sample's own lead-in more, so almost none of the new pitch
is heard: the word sounds as if it were sung on one note. (Measured on a rendered "babe": the
sixteenth was a brief dip in pitch followed by 0.12 s of closed lips.)

OpenUtau lets a project move a phoneme by a number of ticks (``phoneme_overrides`` with an
``offset``, applied to the phoneme of that index in its note). Moving the closing consonants a
little later leaves the vowel the room to sound on the last note, and the consonant is still
crisp at the end. It is done only where the word is held over several notes, its last note is
short, the next note follows without a gap, and only for the English phonemizer that places
phonemes this way (Arpasing). Everything else is left exactly as the engine places it.
"""

from collections.abc import Sequence

# the engine's own values (OpenUtau.Plugin.Builtin.PhonemeBasedPhonemizer.ConsonantLength), in ticks
# at 480 per quarter note; USTX files written by BLT always use that resolution
CONSONANT_TICKS = 60
PER_QUARTER = 480
# how much later the closing consonants are put: the last one then has 10 ticks left before the
# end of the group. That is as late as the engine allows (a phoneme left with no duration is
# dropped), and about as late as the voicebank's closing "b" can go: its quiet lip closure comes
# before the point it is placed at, so moving it later only gives the vowel up to that much more
SHIFT_TICKS = 50
# a short held note changes pitch over this many milliseconds each side of its start instead of
# the 40 the engine uses for every note, so that a step of a semitone on a sixteenth is a step
# and not a slide that has barely arrived when the note is over
QUICK_GLIDE_MS = 15
DEFAULT_GLIDE_MS = 40
# a held note up to this long (a sixteenth) gets the quick glide
QUICK_GLIDE_NOTE_TICKS = 120
# a last note up to this long (a sixteenth is 120 ticks, an eighth 240) is short enough to need it
SHORT_LAST_NOTE_TICKS = 3 * CONSONANT_TICKS

# ARPAbet vowels, as the engine's English dictionary spells them (lower case, no stress digits)
_VOWEL_LIST = "aa ae ah ao aw ax ay eh er ey ih iy ow oy uh uw"
ARPABET_VOWELS = frozenset(_VOWEL_LIST.split())


def trailing_consonants(symbols: Sequence[str]) -> tuple[int, ...]:
    """Indices of the consonants after the last vowel (none if the word ends on a vowel)."""
    last_vowel = -1
    for index, symbol in enumerate(symbols):
        if symbol.lower() in ARPABET_VOWELS:
            last_vowel = index
    if last_vowel < 0:  # no vowel: the engine spreads such a word differently; leave it
        return ()
    return tuple(range(last_vowel + 1, len(symbols)))


def needs_shift(last_note_ticks: int, notes_in_group: int, followed_without_gap: bool) -> bool:
    """Whether a word held over ``notes_in_group`` notes needs its closing consonants moved."""
    return notes_in_group >= 2 and followed_without_gap and last_note_ticks <= SHORT_LAST_NOTE_TICKS


def overrides_for(symbols: Sequence[str], resolution: int) -> list[dict[str, int]]:
    """The ``phoneme_overrides`` that move the word's closing consonants later (maybe empty)."""
    shift = round(SHIFT_TICKS * resolution / PER_QUARTER)
    return [{"index": index, "offset": shift} for index in trailing_consonants(symbols)]


def glide_ms(holds_a_syllable: bool, duration_ticks: int, resolution: int) -> int:
    """The pitch transition of a note, in milliseconds each side of its start."""
    short = duration_ticks * PER_QUARTER <= QUICK_GLIDE_NOTE_TICKS * resolution
    return QUICK_GLIDE_MS if holds_a_syllable and short else DEFAULT_GLIDE_MS
