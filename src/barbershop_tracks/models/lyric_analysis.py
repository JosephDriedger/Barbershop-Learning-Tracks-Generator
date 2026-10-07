"""Immutable results of the performed-lyric analysis.

These describe what is sung per performed attack for one chosen verse. They reference the
source objects (``PerformanceNote``, ``Lyric``) rather than copying them, and contain nothing
backend-specific: no OpenUtau ``+`` or ``+~``, no phonemes, MIDI ticks, singer or FFmpeg
concept. The source ``Song`` is never modified by producing them.
"""

from dataclasses import dataclass, field
from enum import Enum
from fractions import Fraction

from barbershop_tracks.models.lyric import Lyric, Syllabic
from barbershop_tracks.models.performance import PerformanceNote
from barbershop_tracks.models.performed import LocatedIssue
from barbershop_tracks.models.validation import ValidationResult


class AttackRole(Enum):
    """What a performed attack is, for the analyzed verse."""

    SYLLABLE = "syllable"  # carries a new syllable of text
    MELISMA_CONTINUATION = "melisma_continuation"  # sung on an earlier syllable (extender)
    MISSING = "missing"  # sung, but no resolved lyric
    HUMMING = "humming"  # an explicit <humming/> vocal event
    LAUGHING = "laughing"  # an explicit <laughing/> vocal event
    REST = "rest"  # not sung
    CONFLICT = "conflict"  # cannot be classified without choosing between source lyrics


class MelismaBasis(Enum):
    """Why an attack is a melisma continuation."""

    TYPED = "typed"  # explicit <extend type="start|continue|stop"> state
    UNTYPED = "untyped"  # inferred from an untyped <extend/> (MuseScore style)


@dataclass(frozen=True, slots=True, kw_only=True)
class AttackLyric:
    """The analysis of one performed attack (``index`` is its position in the input)."""

    index: int
    performed: PerformanceNote
    role: AttackRole
    lyric: Lyric | None = None  # the source lyric that supplies the role, if any
    word_indices: tuple[int, ...] = ()  # one per syllable (more than one if elided)
    melisma_origin: int | None = None  # index of the attack that opened the extension
    melisma_position: int | None = None  # 1-based position within that melisma
    melisma_basis: MelismaBasis | None = None

    @property
    def syllable_count(self) -> int:
        if self.role is not AttackRole.SYLLABLE or self.lyric is None:
            return 0
        return 1 + len(self.lyric.elided)


@dataclass(frozen=True, slots=True, kw_only=True)
class WordSyllable:
    attack_index: int
    segment: int  # 0 for the lyric's own text, 1.. for elided segments
    text: str  # verbatim
    syllabic: Syllabic


@dataclass(frozen=True, slots=True, kw_only=True)
class LyricWord:
    """A reconstructed word: syllables joined literally, with the source untouched."""

    index: int
    syllables: tuple[WordSyllable, ...]
    interrupted_by_rest: bool = False
    closed: bool = True  # False if the source never ended the word

    @property
    def text(self) -> str:
        return "".join(syllable.text for syllable in self.syllables)


@dataclass(frozen=True, slots=True, kw_only=True)
class MissingRun:
    """Consecutive sung attacks without a resolved lyric (rests between them do not split it)."""

    first_index: int
    last_index: int
    count: int
    first_measure: int
    first_beat: Fraction
    last_measure: int
    last_beat: Fraction


@dataclass(frozen=True, slots=True, kw_only=True)
class LyricCoverage:
    sung_attacks: int = 0
    syllable_attacks: int = 0
    continuation_attacks: int = 0
    missing_attacks: int = 0
    humming_attacks: int = 0
    laughing_attacks: int = 0
    conflict_attacks: int = 0
    missing_runs: tuple[MissingRun, ...] = ()
    # The number of additional PERFORMED ATTACKS classified MELISMA_CONTINUATION in the longest
    # melisma (a syllable attack followed by 23 continuation attacks gives 23). It never counts
    # source notes, <extend> elements, tie-continuation notes, rests or start/continue/stop
    # markers. There is no maximum.
    longest_melisma: int = 0

    @property
    def has_any_lyric(self) -> bool:
        return bool(self.syllable_attacks or self.humming_attacks or self.laughing_attacks)


@dataclass(frozen=True, slots=True, kw_only=True)
class LineLyricAnalysis:
    """Everything the analysis found for one voice line and one logical verse."""

    part_id: str
    verse: str | None  # the analyzed logical verse (None if the line has no lyrics at all)
    verses: tuple[str, ...]  # every logical verse in the line, in document order
    attacks: tuple[AttackLyric, ...]
    words: tuple[LyricWord, ...]
    coverage: LyricCoverage
    issues: ValidationResult = field(default_factory=ValidationResult)
    # the same issues, in the same order, with a performance location where one exists
    located: tuple[LocatedIssue, ...] = ()

    def roles(self) -> tuple[AttackRole, ...]:
        return tuple(attack.role for attack in self.attacks)


@dataclass(frozen=True, slots=True, kw_only=True)
class VerseChoice:
    """The outcome of choosing the logical verse to analyze."""

    selected: str | None
    available: tuple[str, ...]
    requested: str | None = None
    found: bool = True  # False if a requested verse does not exist

    @property
    def fell_back(self) -> bool:
        """True if a verse other than ``"1"`` was chosen automatically among several."""
        return (
            self.requested is None
            and self.selected is not None
            and self.selected != "1"
            and len(self.available) > 1
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class SongLyricAnalysis:
    """Per-line analyses for one song-wide verse, plus the song-level verse diagnostics."""

    choice: VerseChoice
    lines: tuple[LineLyricAnalysis, ...]
    issues: ValidationResult = field(default_factory=ValidationResult)

    def all_issues(self) -> ValidationResult:
        return self.issues.merged(*(line.issues for line in self.lines))
