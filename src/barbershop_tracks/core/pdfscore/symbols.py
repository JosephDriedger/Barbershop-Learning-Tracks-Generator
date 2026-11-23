"""The SMuFL characters a score PDF is read by (Standard Music Font Layout code points).

A notation program that uses a SMuFL font (MuseScore's Leland and Bravura, Dorico's Bravura,
Finale's SMuFL fonts) draws every symbol as the character of its standard code point, so a symbol
is known by its character, whatever the font is called.
"""

from fractions import Fraction

# noteheads: the length of the note without flags or beams, in quarter notes
NOTEHEADS: dict[str, Fraction] = {
    chr(0xE0A0): Fraction(8),  # noteheadDoubleWhole
    chr(0xE0A1): Fraction(8),  # noteheadDoubleWholeSquare
    chr(0xE0A2): Fraction(4),  # noteheadWhole
    chr(0xE0A3): Fraction(2),  # noteheadHalf
    chr(0xE0A4): Fraction(1),  # noteheadBlack
    chr(0xE0A9): Fraction(1),  # noteheadXBlack
    chr(0xE0A8): Fraction(2),  # noteheadXHalf
    chr(0xE0A7): Fraction(4),  # noteheadXWhole
    chr(0xE0DB): Fraction(1),  # noteheadDiamondBlack
    chr(0xE0D9): Fraction(2),  # noteheadDiamondHalf
    chr(0xE0D8): Fraction(4),  # noteheadDiamondWhole
    # Bravura's and Petaluma's own (optional) noteheads, which MuseScore draws with those fonts
    # instead of the standard ones: noteheadWhole, noteheadHalf and noteheadBlack drawn larger
    chr(0xF4BC): Fraction(4),
    chr(0xF4BD): Fraction(2),
    chr(0xF4BE): Fraction(1),
}

RESTS: dict[str, Fraction] = {
    chr(0xE4E1): Fraction(16),  # restLonga
    chr(0xE4E2): Fraction(8),  # restDoubleWhole
    chr(0xE4E3): Fraction(4),  # restWhole (a whole-measure rest in any meter)
    chr(0xE4E4): Fraction(2),  # restHalf
    chr(0xE4E5): Fraction(1),  # restQuarter
    chr(0xE4E6): Fraction(1, 2),  # rest8th
    chr(0xE4E7): Fraction(1, 4),  # rest16th
    chr(0xE4E8): Fraction(1, 8),  # rest32nd
    chr(0xE4E9): Fraction(1, 16),  # rest64th
    chr(0xE4EA): Fraction(1, 32),  # rest128th
}
WHOLE_REST = chr(0xE4E3)
MULTI_REST = chr(0xE4EE)  # restHBar

# flags: how many times the length is halved; up flags hang from the top of a stem
FLAGS: dict[str, tuple[int, bool]] = {
    chr(0xE240): (1, True),
    chr(0xE241): (1, False),
    chr(0xE242): (2, True),
    chr(0xE243): (2, False),
    chr(0xE244): (3, True),
    chr(0xE245): (3, False),
    chr(0xE246): (4, True),
    chr(0xE247): (4, False),
    chr(0xE248): (5, True),
    chr(0xE249): (5, False),
}

AUGMENTATION_DOT = chr(0xE1E7)

ACCIDENTALS: dict[str, int] = {
    chr(0xE260): -1,  # flat
    chr(0xE261): 0,  # natural
    chr(0xE262): 1,  # sharp
    chr(0xE263): 2,  # double sharp
    chr(0xE264): -2,  # double flat
    chr(0xE26A): 99,  # parenthesis left (a courtesy accidental: ignored)
    chr(0xE26B): 99,
}

# clefs: (sign, the staff line it sits on counted from the bottom (1-5), octave change)
CLEFS: dict[str, tuple[str, int, int]] = {
    chr(0xE050): ("G", 2, 0),
    chr(0xE052): ("G", 2, -1),
    chr(0xE053): ("G", 2, 1),
    chr(0xE051): ("G", 2, -2),
    chr(0xE054): ("G", 2, 2),
    chr(0xE05C): ("C", 3, 0),
    chr(0xE05D): ("C", 3, -1),
    chr(0xE062): ("F", 4, 0),
    chr(0xE064): ("F", 4, -1),
    chr(0xE065): ("F", 4, 1),
    chr(0xE063): ("F", 4, -2),
    chr(0xE069): ("percussion", 3, 0),
}
# the bottom line's pitch for each clef sign at its usual line, as a diatonic index (C4 = 28)
_DIATONIC = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}
CLEF_REFERENCE = {"G": ("G", 4), "F": ("F", 3), "C": ("C", 4)}

TIME_DIGITS = {chr(0xE080 + d): d for d in range(10)}
TIME_COMMON = chr(0xE08A)
TIME_CUT = chr(0xE08B)
TUPLET_DIGITS = {chr(0xE880 + d): d for d in range(10)}

FERMATAS = {
    chr(0xE4C0): True,  # above
    chr(0xE4C1): False,  # below
    chr(0xE4C4): True,  # fermataShortAbove
    chr(0xE4C5): False,
    chr(0xE4C6): True,  # fermataLongAbove
    chr(0xE4C7): False,
    chr(0xE4C2): True,  # fermataVeryShortAbove
    chr(0xE4C3): False,
    chr(0xE4C8): True,  # fermataVeryLongAbove
    chr(0xE4C9): False,
}
BREATH_MARKS = {chr(0xE4CE), chr(0xE4CF), chr(0xE4D0), chr(0xE4D5)}
CAESURAS = {chr(0xE4D1), chr(0xE4D2), chr(0xE4D3), chr(0xE4D4)}

BRACE = chr(0xE000)
BRACKET_ENDS = {chr(0xE003), chr(0xE004)}

REPEAT_DOT = chr(0xE044)
REPEAT_DOTS = chr(0xE043)
SEGNO = chr(0xE047)
CODA = chr(0xE048)

# metronome marks (in a text font of the music font family)
METRONOME_NOTES: dict[str, Fraction] = {
    chr(0xECA2): Fraction(4),  # metNoteWhole
    chr(0xECA3): Fraction(2),  # metNoteHalfUp
    chr(0xECA4): Fraction(2),
    chr(0xECA5): Fraction(1),  # metNoteQuarterUp
    chr(0xECA6): Fraction(1),
    chr(0xECA7): Fraction(1, 2),  # metNote8thUp
    chr(0xECA8): Fraction(1, 2),
    chr(0xECA9): Fraction(1, 4),  # metNote16thUp
    chr(0xECAA): Fraction(1, 4),
}
METRONOME_DOT = chr(0xECB7)

STEPS = "CDEFGAB"


def diatonic(step: str, octave: int) -> int:
    return octave * 7 + _DIATONIC[step]


def is_music_symbol(text: str) -> bool:
    """A character of the SMuFL range (the private use area U+E000 to U+F8FF)."""
    return bool(text) and 0xE000 <= ord(text[0]) <= 0xF8FF
