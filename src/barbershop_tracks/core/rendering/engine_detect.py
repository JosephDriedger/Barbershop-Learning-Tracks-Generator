"""Which pronunciation engine a voicebank was made for, read from the names of its sounds.

A voicebank is a folder of recordings with an ``oto.ini`` that names each sound (its alias). The
names show how the bank is meant to be driven: ``@ p`` and ``S@`` are X-SAMPA, ``k ae`` is ARPAbet,
``ka`` is a plain syllable. The default engine uses the lyric as the sound, so an English word given
to an X-SAMPA bank finds no sound and comes out silent. When the person has not chosen an engine,
BLT looks at the voices it is going to use and, when the evidence is clear, uses the matching engine
and says so. A choice made by the person is never overridden, and anything unclear stays as it was.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

ARPASING = "OpenUtau.Plugin.Builtin.ArpasingPhonemizer"
ENGLISH_XSAMPA = "OpenUtau.Plugin.Builtin.EnXSampaPhonemizer"

_XSAMPA_MARKS = ("@", "{")
_ARPABET = frozenset(
    {
        "aa",
        "ae",
        "ah",
        "ao",
        "aw",
        "ay",
        "eh",
        "er",
        "ey",
        "ih",
        "iy",
        "ow",
        "oy",
        "uh",
        "uw",
        "sh",
        "zh",
        "hh",
        "jh",
        "ng",
        "dh",
        "th",
        "ch",
    }
)
_MIN_SOUNDS = 20
_SHARE = 0.10
_MAX_FILES = 12


@dataclass(frozen=True, slots=True)
class Detection:
    phonemizer: str
    why: str  # in words, for the person reading the notice


def _encoding(folder: Path) -> str:
    """The encoding the bank says its text files use (UTAU banks are Shift-JIS unless told)."""
    try:
        text = (folder / "character.yaml").read_text(encoding="utf-8-sig")
    except OSError:
        return "shift_jis"
    found = re.search(r"text_file_encoding:\s*([\w-]+)", text)
    return found.group(1) if found else "shift_jis"


def aliases_of(folder: Path) -> list[str]:
    """The names of the sounds in every ``oto.ini`` of the bank (a bounded number of files)."""
    encoding = _encoding(folder)
    found: list[str] = []
    for count, path in enumerate(sorted(folder.rglob("oto.ini"))):
        if count >= _MAX_FILES:
            break
        try:
            text = path.read_text(encoding=encoding, errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            head, _, rest = line.partition("=")
            if rest:
                alias = rest.split(",", 1)[0].strip()
                found.append(alias or head.rsplit(".", 1)[0])
    return found


def classify(aliases: Iterable[str]) -> Detection | None:
    """The engine the sound names point to, or None when they do not say clearly."""
    names = [a for a in aliases if a]
    if len(names) < _MIN_SOUNDS:
        return None
    x_sampa = sum(1 for a in names if any(mark in a for mark in _XSAMPA_MARKS))
    if x_sampa / len(names) >= _SHARE:
        return Detection(
            ENGLISH_XSAMPA,
            f"{x_sampa} of its {len(names)} sounds are named in X-SAMPA (such as '@ p' or 'S@')",
        )
    arpabet = sum(1 for a in names if _ARPABET.intersection(a.lower().split()))
    if arpabet / len(names) >= 2 * _SHARE:
        return Detection(
            ARPASING,
            f"{arpabet} of its {len(names)} sounds are named in ARPAbet (such as 'k ae')",
        )
    return None


def detect(folder: Path) -> Detection | None:
    """The engine a voicebank folder was made for, if its sound names say so."""
    try:
        if not folder.is_dir():
            return None
        return classify(aliases_of(folder))
    except OSError:
        return None


__all__ = ["ARPASING", "ENGLISH_XSAMPA", "Detection", "aliases_of", "classify", "detect"]
