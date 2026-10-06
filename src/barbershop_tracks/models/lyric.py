"""Source lyric information, independent of any OpenUtau/MIDI representation.

The model stores what MusicXML says. It never contains OpenUtau conventions such as
``+`` or ``+~``; those are derived later by the exporter.
"""

from dataclasses import dataclass
from enum import Enum


class Syllabic(Enum):
    """Position of a syllable within a word (MusicXML ``syllabic``)."""

    SINGLE = "single"
    BEGIN = "begin"
    MIDDLE = "middle"
    END = "end"


class Melisma(Enum):
    """State of a melisma (extender line) on a note (MusicXML ``extend`` type)."""

    NONE = "none"
    START = "start"
    CONTINUE = "continue"
    STOP = "stop"


@dataclass(frozen=True, slots=True, kw_only=True)
class LyricSegment:
    """One additional syllable sung on the same note after an elision."""

    text: str
    syllabic: Syllabic = Syllabic.SINGLE
    joiner: str = " "  # the elision glyph joining this segment to the previous one

    def __post_init__(self) -> None:
        if not self.text:
            raise ValueError("lyric segment text must not be empty")


@dataclass(frozen=True, slots=True, kw_only=True)
class Lyric:
    """A lyric attached to one note for one verse.

    ``text`` and ``syllabic`` are stored exactly as in the source. A lyric with empty
    ``text`` is a pure melisma continuation (an extender with no syllable) and must have
    ``syllabic=None`` and ``melisma`` CONTINUE or STOP; build it with ``Lyric.extension``.
    ``elided`` holds further syllables joined to this one on the same note.
    """

    text: str
    syllabic: Syllabic | None = Syllabic.SINGLE
    verse: str = "1"
    melisma: Melisma = Melisma.NONE
    elided: tuple[LyricSegment, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "elided", tuple(self.elided))
        if not self.verse:
            raise ValueError("verse must not be empty")
        if self.text:
            if self.syllabic is None:
                raise ValueError("a lyric with text needs a syllabic value")
        else:
            if self.syllabic is not None:
                raise ValueError("an extension-only lyric must not have a syllabic value")
            if self.melisma not in (Melisma.CONTINUE, Melisma.STOP):
                raise ValueError("an empty lyric must be a melisma continuation or stop")
            if self.elided:
                raise ValueError("an extension-only lyric cannot have elided segments")

    @classmethod
    def extension(cls, melisma: Melisma, *, verse: str = "1") -> "Lyric":
        """A melisma continuation/stop with no syllable text."""
        return cls(text="", syllabic=None, verse=verse, melisma=melisma)

    @property
    def has_text(self) -> bool:
        return bool(self.text)

    @property
    def is_elided(self) -> bool:
        return bool(self.elided)

    @property
    def full_text(self) -> str:
        """The syllable text including any elided segments, joined with their glyphs."""
        return self.text + "".join(seg.joiner + seg.text for seg in self.elided)
