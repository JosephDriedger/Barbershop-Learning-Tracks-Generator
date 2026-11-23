"""Glyph names used in a font's encoding, to the text they stand for.

A PDF whose font has no ``ToUnicode`` map still names each glyph (``/Differences``). Ordinary
letters use Adobe's names; ``uniXXXX`` and ``uXXXXX`` name a code point directly, which is how SMuFL
music fonts are usually encoded.
"""

_NAMED = {
    "space": " ",
    "hyphen": "-",
    "minus": "-",
    "endash": chr(0x2013),
    "emdash": chr(0x2014),
    "underscore": "_",
    "period": ".",
    "comma": ",",
    "colon": ":",
    "semicolon": ";",
    "exclam": "!",
    "question": "?",
    "quotesingle": "'",
    "quoteright": chr(0x2019),
    "quoteleft": chr(0x2018),
    "quotedbl": '"',
    "quotedblleft": chr(0x201C),
    "quotedblright": chr(0x201D),
    "parenleft": "(",
    "parenright": ")",
    "bracketleft": "[",
    "bracketright": "]",
    "equal": "=",
    "plus": "+",
    "slash": "/",
    "ampersand": "&",
    "asterisk": "*",
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "fi": "fi",
    "fl": "fl",
    "ff": "ff",
    "ffi": "ffi",
    "ffl": "ffl",
}


def glyph_name_to_text(name: str) -> str:
    if len(name) == 1 and name.isalpha():
        return name
    if name in _NAMED:
        return _NAMED[name]
    base = name.split(".", 1)[0]
    if base in _NAMED:
        return _NAMED[base]
    if len(base) == 1 and base.isalpha():
        return base
    if base.startswith("uni") and len(base) >= 7:
        try:
            return "".join(chr(int(base[i : i + 4], 16)) for i in range(3, len(base), 4))
        except ValueError:
            return ""
    if base.startswith("u") and 5 <= len(base) <= 7:
        try:
            return chr(int(base[1:], 16))
        except ValueError:
            return ""
    return ""
