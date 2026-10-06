"""Source lyric information, independent of any OpenUtau/MIDI representation.

The model stores **what the score says**, including what it does not say. Nothing here
interprets: a missing ``<syllabic>`` stays ``UNSPECIFIED``, a missing ``number`` stays ``None``,
an untyped ``<extend/>`` stays ``UNTYPED``, and odd combinations are stored, not rejected.
Interpreting them (melisma runs, word chains, the verse to sing) belongs to the lyric analysis,
and OpenUtau conventions such as ``+`` and ``+~`` never appear in the model.
"""

from dataclasses import dataclass
from enum import Enum


class Syllabic(Enum):
    """The ``<syllabic>`` value as written; ``UNSPECIFIED`` means the element was absent."""

    SINGLE = "single"
    BEGIN = "begin"
    MIDDLE = "middle"
    END = "end"
    UNSPECIFIED = "unspecified"


class Melisma(Enum):
    """The source form of ``<extend>``.

    ``NONE`` is no ``<extend>`` at all; ``UNTYPED`` is ``<extend/>`` with no ``type``
    (MuseScore always writes this form); the others are the three typed forms. Whether an
    untyped extender "is" a start is an interpretation left to the analysis.
    """

    NONE = "none"
    UNTYPED = "untyped"
    START = "start"
    CONTINUE = "continue"
    STOP = "stop"


class LyricKind(Enum):
    """What the lyric element contains."""

    TEXT = "text"  # a syllable of text, possibly with an extender
    EXTENSION = "extension"  # an extender with no text
    HUMMING = "humming"  # <humming/>, "a humming voice"
    LAUGHING = "laughing"  # <laughing/>, "a laughing voice"


DEFAULT_VERSE = "1"
"""The logical verse that an absent ``number`` is grouped with (analysis only; see
``Lyric.logical_verse``). It is never stored as the source ``verse``."""


@dataclass(frozen=True, slots=True, kw_only=True)
class LyricSegment:
    """A further syllable sung on the same note, after an elision.

    ``joiner`` is the elision symbol exactly as written (``""`` if the element was empty);
    ``joiner_smufl`` is the ``smufl`` glyph name of an empty ``<elision smufl="...">``.
    """

    text: str
    syllabic: Syllabic = Syllabic.UNSPECIFIED
    joiner: str = ""
    joiner_smufl: str | None = None

    def __post_init__(self) -> None:
        if not self.text:
            raise ValueError("lyric segment text must not be empty")


@dataclass(frozen=True, slots=True, kw_only=True)
class Lyric:
    """One ``<lyric>`` element attached to one note, kept literally.

    ``verse`` is the ``number`` attribute (``None`` if absent; never silently ``"1"``), ``name``
    the ``name`` attribute, and ``time_only`` the ``time-only`` attribute, all verbatim.
    ``text`` is verbatim too: no stripping, no case change. ``elided`` holds the syllables that
    follow an elision on the same note.

    Invariants: a ``TEXT`` lyric has non-empty text; every other kind has no text, no elided
    segments and ``UNSPECIFIED`` syllabic; an ``EXTENSION`` has some ``<extend>`` form;
    ``HUMMING`` and ``LAUGHING`` have none. Odd source combinations (for example text together
    with ``type="stop"``) are stored as written.
    """

    kind: LyricKind = LyricKind.TEXT
    text: str = ""
    syllabic: Syllabic = Syllabic.UNSPECIFIED
    verse: str | None = None
    name: str | None = None
    time_only: str | None = None
    melisma: Melisma = Melisma.NONE
    elided: tuple[LyricSegment, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "elided", tuple(self.elided))
        if self.verse is not None and not self.verse:
            raise ValueError("verse must not be empty (use None for an absent number)")
        if self.kind is LyricKind.TEXT:
            if not self.text:
                raise ValueError("a text lyric needs text")
            return
        if self.text or self.elided or self.syllabic is not Syllabic.UNSPECIFIED:
            raise ValueError(f"a {self.kind.value} lyric has no text, segments or syllabic")
        if self.kind is LyricKind.EXTENSION and self.melisma is Melisma.NONE:
            raise ValueError("an extension lyric needs an <extend> form")
        if (
            self.kind in (LyricKind.HUMMING, LyricKind.LAUGHING)
            and self.melisma is not Melisma.NONE
        ):
            raise ValueError(f"a {self.kind.value} lyric has no <extend>")

    @classmethod
    def extension(
        cls,
        melisma: Melisma,
        *,
        verse: str | None = None,
        name: str | None = None,
        time_only: str | None = None,
    ) -> "Lyric":
        """An extender with no syllable (``<lyric><extend .../></lyric>``)."""
        return cls(
            kind=LyricKind.EXTENSION,
            melisma=melisma,
            verse=verse,
            name=name,
            time_only=time_only,
        )

    @classmethod
    def humming(
        cls, *, verse: str | None = None, name: str | None = None, time_only: str | None = None
    ) -> "Lyric":
        return cls(kind=LyricKind.HUMMING, verse=verse, name=name, time_only=time_only)

    @classmethod
    def laughing(
        cls, *, verse: str | None = None, name: str | None = None, time_only: str | None = None
    ) -> "Lyric":
        return cls(kind=LyricKind.LAUGHING, verse=verse, name=name, time_only=time_only)

    @property
    def has_text(self) -> bool:
        return self.kind is LyricKind.TEXT

    @property
    def is_elided(self) -> bool:
        return bool(self.elided)

    @property
    def full_text(self) -> str:
        """The text including any elided segments, each preceded by its joiner."""
        return self.text + "".join(segment.joiner + segment.text for segment in self.elided)

    @property
    def logical_verse(self) -> str:
        """The verse this lyric is grouped with: ``verse``, or ``DEFAULT_VERSE`` if absent.

        **This is an analysis/grouping convenience and is NOT source identity.** It must
        never be used to reconstruct, compare for equality, or serialize the original
        MusicXML: ``verse=None`` and ``verse="1"`` are different source facts (``<lyric>``
        versus ``<lyric number="1">``) even though both have ``logical_verse == "1"``. It
        exists so duplicate detection and verse selection can treat them as the same stream.
        """
        return DEFAULT_VERSE if self.verse is None else self.verse
