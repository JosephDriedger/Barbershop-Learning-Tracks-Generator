"""Music fonts older than SMuFL: Finale's Maestro and the fonts laid out like it.

Before SMuFL, a music font put its symbols on ordinary character codes: Maestro's quarter-note
head is the character 0xCF, its sharp is "#", its bass clef "?". Finale's Maestro, Petrucci,
Engraver Font Set, Jazz and Broadway Copyist all use this layout. A PDF printed from such a score
(often through "Microsoft: Print To PDF", which renames every font to "CIDFont+F1" and so on) draws
the symbols as those codes, usually moved into the symbol-font range U+F020 to U+F0FF.

Here each such character becomes the SMuFL character of the same symbol, so the rest of the reader
knows it. Like SMuFL fonts, these fonts are one em to four staff spaces and draw a notehead with
its origin on the line or space of its pitch.
"""

import re
from dataclasses import replace

from barbershop_tracks.core.pdfscore.pdf import Glyph, Page

# a font name that says nothing of the face, as "Microsoft: Print To PDF" writes them
_RENAMED_FONT = re.compile(r"(?:[A-Z]{6}\+)?(?:CIDFont\+)?F\d+")


def is_renamed_font(name: str) -> bool:
    """Whether the font's name was replaced by a bare number ("CIDFont+F5"), so that it no longer
    says whether the face is italic or bold."""
    return _RENAMED_FONT.fullmatch(name) is not None


# the font's character code (0x20 to 0xFF) -> the SMuFL character of the same symbol
MAESTRO: dict[int, str] = {
    # noteheads
    0xCF: chr(0xE0A4),  # quarter (and shorter) notehead
    0xFA: chr(0xE0A3),  # half notehead
    0x77: chr(0xE0A2),  # whole note
    0x57: chr(0xE0A0),  # double whole note
    # rests
    0xB7: chr(0xE4E3),  # whole rest
    0xEE: chr(0xE4E4),  # half rest
    0xCE: chr(0xE4E5),  # quarter rest
    0xE4: chr(0xE4E6),  # eighth rest
    0xC5: chr(0xE4E7),  # sixteenth rest
    0xA8: chr(0xE4E8),  # 32nd rest
    # flags: lower case hangs from an up stem, upper case from a down stem
    0x6A: chr(0xE240),  # eighth, stem up
    0x4A: chr(0xE241),  # eighth, stem down
    0x72: chr(0xE242),  # sixteenth, stem up
    0x52: chr(0xE243),  # sixteenth, stem down
    # augmentation dot
    0x2E: chr(0xE1E7),
    # accidentals
    0x62: chr(0xE260),  # flat
    0x6E: chr(0xE261),  # natural
    0x23: chr(0xE262),  # sharp
    0xDC: chr(0xE263),  # double sharp
    0xBA: chr(0xE264),  # double flat
    # clefs
    0x26: chr(0xE050),  # treble
    0x56: chr(0xE052),  # treble, an octave lower (tenor)
    0x3F: chr(0xE062),  # bass
    0x42: chr(0xE05C),  # alto
    # time signatures
    **{0x30 + d: chr(0xE080 + d) for d in range(10)},
    0x63: chr(0xE08A),  # common time
    0x43: chr(0xE08B),  # cut time
    # marks
    0x55: chr(0xE4C0),  # fermata above
    0x75: chr(0xE4C1),  # fermata below
    0x2C: chr(0xE4CE),  # breath mark
    0x25: chr(0xE047),  # segno
    0xDE: chr(0xE048),  # coda
}

# the characters whose presence makes a font a music font of this layout: the noteheads
_NOTEHEAD_CODES = {0xCF, 0xFA, 0x77}
_FONT_NAMES = ("maestro", "petrucci", "engraver", "jazz", "broadway", "sonata", "opus")


def _code(text: str, named: bool) -> int | None:
    """The font's character code of ``text``: from the symbol-font range, or (in a font known by
    name) the character itself as a Mac Roman or Windows character."""
    if len(text) != 1:
        return None
    value = ord(text)
    if 0xF020 <= value <= 0xF0FF:
        return value - 0xF000
    if not named:
        return None
    if value < 0x80:
        return value
    for encoding in ("mac_roman", "cp1252"):
        try:
            return text.encode(encoding)[0]
        except UnicodeEncodeError:
            continue
    return None


def _legacy_fonts(pages: list[Page]) -> dict[str, bool]:
    """The fonts drawn in the Maestro layout, each with whether it is known by name."""
    found: dict[str, bool] = {}
    by_font: dict[str, list[str]] = {}
    for page in pages:
        for g in page.glyphs:
            by_font.setdefault(g.font, []).append(g.text)
    for font, texts in by_font.items():
        named = any(name in font.lower() for name in _FONT_NAMES)
        codes = [_code(t, named) for t in texts]
        symbol = sum(1 for c in codes if c is not None)
        # nearly every character of the font is in the symbol range, and some are noteheads
        if symbol >= 0.9 * len(texts) and any(c in _NOTEHEAD_CODES for c in codes):
            found[font] = named
    return found


def translate_legacy_music_fonts(pages: list[Page]) -> None:
    """Replace, in place, every character of a Maestro-layout font by its SMuFL character (the
    characters without a SMuFL counterpart here are left out: they are not read)."""
    fonts = _legacy_fonts(pages)
    if not fonts:
        return
    for page in pages:
        glyphs: list[Glyph] = []
        for g in page.glyphs:
            if g.font not in fonts:
                glyphs.append(g)
                continue
            code = _code(g.text, fonts[g.font])
            smufl = MAESTRO.get(code) if code is not None else None
            if smufl is not None:
                glyphs.append(replace(g, text=smufl))
        page.glyphs = glyphs


__all__ = ["MAESTRO", "is_renamed_font", "translate_legacy_music_fonts"]
