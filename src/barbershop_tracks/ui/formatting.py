"""Words and numbers for people: note names, bar/beat positions, durations. No Qt here."""

from fractions import Fraction

from barbershop_tracks.core.synthesis.positions import beat_text
from barbershop_tracks.core.synthesis.positions import position_label as position_label

_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def note_name(midi: int) -> str:
    """``64`` -> ``E4`` (middle C is C4)."""
    return f"{_NAMES[midi % 12]}{midi // 12 - 1}"


def duration_label(quarters: Fraction) -> str:
    if quarters == 1:
        return "1 beat"
    return (
        f"{beat_text(quarters)} beats"
        if quarters.denominator <= 2
        else f"{float(quarters):.2f} beats"
    )


def clock(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 60}:{total % 60:02d}"


def sentence(text: str) -> str:
    """``the score has no tempo`` -> ``The score has no tempo`` (only a lower-case first letter)."""
    return text[:1].upper() + text[1:] if text[:1].islower() else text


# the short words a title keeps in lower case (not as its first or last word)
_MINOR = frozenset(
    {
        "a", "an", "the", "and", "but", "or", "nor", "for", "as", "at", "by", "in", "of", "on",
        "per", "to", "via", "from", "into", "onto", "with", "than",
    }
)  # fmt: skip

# what may stand around a word: quotes (straight and curly) and punctuation
_AROUND = "\"'(),.:;!?\u201c\u201d\u2018\u2019"


def _capitalised(word: str) -> str:
    # a word with a capital, a digit or a file name in it (BLT, MuseScore, ffmpeg.exe, 4/4) is
    # written as it is; only a plain lower-case word is capitalised, each part of a hyphenated one
    if not word[:1].islower() or any(c.isdigit() or c in "./\\_" for c in word):
        return word
    return "-".join(part[:1].upper() + part[1:] for part in word.split("-"))


def title_case(text: str) -> str:
    """``A pronunciation you gave cannot be used`` -> ``A Pronunciation You Gave Cannot Be Used``:
    for a heading made from a sentence."""
    words = text.split(" ")
    out = []
    for i, word in enumerate(words):
        bare = word.strip(_AROUND).lower()
        minor = bare in _MINOR and 0 < i < len(words) - 1 and word[:1].islower()
        out.append(word if minor else _capitalised(word))
    return " ".join(out)
