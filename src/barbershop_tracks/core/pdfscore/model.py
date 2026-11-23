"""What is read from a score PDF: the notes, rests, words and marks, before MusicXML is written."""

from dataclasses import dataclass, field
from fractions import Fraction

from barbershop_tracks.core.pdfscore.layout import Staff, System
from barbershop_tracks.core.pdfscore.pdf import Glyph


@dataclass(slots=True)
class Head:
    glyph: Glyph
    staff: Staff
    base: Fraction  # the length the notehead itself shows (whole, half, black)
    small: bool  # a grace or cue note
    accidental: int | None = None  # drawn in front of it
    dots: int = 0
    step: str = "C"
    alter: int = 0
    octave: int = 4
    tie_start: bool = False
    tie_stop: bool = False
    tied_to: "Head | None" = field(default=None, repr=False, compare=False)
    tied_from: "Head | None" = field(default=None, repr=False, compare=False)

    @property
    def x(self) -> float:
        return self.glyph.x

    @property
    def y(self) -> float:
        return self.glyph.y

    @property
    def w(self) -> float:
        return self.glyph.width

    @property
    def diatonic(self) -> int:
        return self.octave * 7 + "CDEFGAB".index(self.step)

    @property
    def midi(self) -> int:
        return (
            12 * (self.octave + 1) + [0, 2, 4, 5, 7, 9, 11]["CDEFGAB".index(self.step)] + self.alter
        )


@dataclass(slots=True)
class LyricOut:
    text: str
    syllabic: str  # single, begin, middle, end
    number: int
    above: bool
    extend_to: float | None = None  # the x the underscore line after it reaches
    offset: float = 0.0  # how far its row is from the staff (above or below), in points
    # set at its note's left instead of centred on it: a syllable held over the next note, its
    # line too short to draw
    left_aligned: bool = False
    line: Fraction | None = None  # how many quarter notes the line runs from the note


@dataclass(frozen=True, slots=True)
class LineGoesOn:
    """An underscore line that comes over from the system before: it starts the row of words at
    ``offset`` from the staff and reaches ``to``."""

    system: System
    staff_index: int
    above: bool
    offset: float
    to: float


@dataclass(slots=True)
class Event:
    """A chord or a rest in one voice of one staff."""

    system: System
    staff: Staff
    x: float  # where its column is (the left of a notehead on the usual side of the stem)
    heads: list[Head] = field(default_factory=list)
    rest: Fraction | None = None  # the rest's own length, None for a chord
    rest_glyph: Glyph | None = None
    stem: int = 0  # 1 up, -1 down, 0 none
    stem_x: float = 0.0
    tip: float = 0.0
    halvings: int = 0
    dots: int = 0
    tuplet: Fraction = Fraction(1)  # actual over written (2/3 in a triplet)
    tuplet_shown: tuple[int, int] | None = None  # (actual notes, normal notes)
    tuplet_group: int = 0  # the notes under one tuplet number share it (0: none)
    measure_rest: bool = False
    voice_hint: int = 0  # 1 or 2 when the drawing says which voice; 0 when it does not
    voice: int = 1
    measure: int = 0  # index in the score
    onset: Fraction = Fraction(0)  # from the start of its measure
    duration: Fraction = Fraction(0)
    lyrics: list[LyricOut] = field(default_factory=list)
    fermata: bool = False
    beams: list[int] = field(default_factory=list)  # ids of the beam shapes at its stem
    slur_starts: int = 0  # slurs that start at it
    slur_stops: int = 0  # slurs that end at it

    @property
    def y_mid(self) -> float:
        """The middle height of its noteheads (or its rest)."""
        if self.heads:
            return sum(h.y for h in self.heads) / len(self.heads)
        return self.rest_glyph.y if self.rest_glyph is not None else self.staff.middle

    @property
    def is_rest(self) -> bool:
        return self.rest is not None

    def written(self) -> Fraction:
        base = self.rest if self.rest is not None else self.heads[0].base
        length: Fraction = base / 2**self.halvings
        add = length
        for _ in range(self.dots):
            add /= 2
            length += add
        return Fraction(length * self.tuplet)


@dataclass(slots=True)
class Direction:
    measure: int
    onset: Fraction
    staff_index: int
    words: str = ""
    above: bool = True
    tempo: Fraction | None = None  # quarter notes per minute
    beat_unit: Fraction | None = None  # in quarter notes (dotted quarter: 3/2)
    per_minute: str = ""
    bold: bool = False
    # a tempo line (rit., accel.): where its dashed line ends, as (measure, onset)
    line_to: tuple[int, Fraction] | None = None
    dashes: str = ""  # "start" or "stop" of such a line


@dataclass(slots=True)
class MeasureInfo:
    index: int
    system: System
    x0: float
    x1: float
    number: int = 0
    length: Fraction = Fraction(4)  # as performed
    nominal: Fraction = Fraction(4)
    time: tuple[int, int] | None = None  # declared here
    time_symbol: str = ""  # common or cut
    keys: dict[int, int] = field(default_factory=dict)  # staff index: fifths declared here
    clefs: dict[int, list[tuple[float, tuple[str, int, int]]]] = field(default_factory=dict)
    repeat_start: bool = False
    repeat_end: bool = False
    ending_start: str = ""  # the numbers of an ending that starts here ("1", "1, 2")
    ending_stop: tuple[str, str] | None = None  # (numbers, "stop" or "discontinue") ending here
    barline_end: str = "regular"


@dataclass(slots=True)
class PartInfo:
    id: str
    name: str
    staves: list[int]  # staff indexes in each system


@dataclass(slots=True)
class ReadScore:
    title: str
    subtitle: str
    composer: str
    arranger: str
    parts: list[PartInfo]
    measures: list[MeasureInfo]
    events: list[Event]
    directions: list[Direction]
    staff_count: int
    notes: list[str] = field(default_factory=list)  # what could not be read, for the person
    # per staff index: (measure, x, clef) and (measure, fifths), in order
    clef_at: dict[int, list[tuple[int, float, tuple[str, int, int]]]] = field(default_factory=dict)
    key_at: dict[int, list[tuple[int, int]]] = field(default_factory=dict)
