"""Analysis-only text hazards. The text is reported, never rewritten.

Each kind is aggregated to one issue per line (a count and the first location), so a long
line cannot flood the report. They describe what a later synthesis step might misread.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from barbershop_tracks.models import Lyric


@dataclass(frozen=True, slots=True)
class Hazard:
    code: str
    count: int
    first_attack_index: int
    description: str


def _has_edge_space(text: str) -> bool:
    return text != text.strip()


def _has_inner_space(text: str) -> bool:
    return any(ch.isspace() for ch in text.strip())


def _has_trailing_hyphen(text: str) -> bool:
    stripped = text.rstrip()
    return stripped.endswith("-") and stripped.strip() != "-"


def _has_reserved(text: str) -> bool:
    stripped = text.strip()
    return stripped == "-" or stripped.startswith("+") or any(c in text for c in "[]~")


_CHECKS: tuple[tuple[str, str, Callable[[str], bool]], ...] = (
    ("LYRIC_TEXT_WHITESPACE", "has leading or trailing whitespace", _has_edge_space),
    ("LYRIC_TEXT_INNER_SPACE", "contains a space inside one note's text", _has_inner_space),
    ("LYRIC_TEXT_TRAILING_HYPHEN", "ends in a hyphen written in the text", _has_trailing_hyphen),
    (
        "LYRIC_TEXT_RESERVED_CHARACTERS",
        "is, starts or contains characters a synthesis front end may interpret (-, +, [ ] or ~)",
        _has_reserved,
    ),
)


def scan_hazards(syllables: Sequence[tuple[int, Lyric]]) -> list[Hazard]:
    """Scan ``(attack index, lyric)`` pairs for text hazards, one aggregate per kind."""
    found: list[Hazard] = []
    for code, description, check in _CHECKS:
        hits = [index for index, lyric in syllables if any(check(text) for text in _texts(lyric))]
        if hits:
            found.append(Hazard(code, len(hits), hits[0], description))
    elided = [index for index, lyric in syllables if lyric.is_elided]
    if elided:
        found.append(
            Hazard("LYRIC_ELIDED", len(elided), elided[0], "puts two syllables on one note")
        )
    return found


def _texts(lyric: Lyric) -> list[str]:
    return [lyric.text, *(segment.text for segment in lyric.elided)]
