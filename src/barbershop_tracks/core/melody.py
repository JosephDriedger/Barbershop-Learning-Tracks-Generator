"""Who has the melody, moment by moment: found from the words, and overridable by marking bars.

In a barbershop arrangement the Lead usually has the melody, but not always: while the Lead holds an
"oo" or rests, another part may sing the words, and that part is then what the listener follows. BLT
has no way to hear a melody, so it reads what the score says:

* the **Lead** has the melody while it sings words, and also while nobody does (all four on "oo");
* when the Lead does not sing words (an "oo", a hum, a rest) and **exactly one other part does**,
  that part has the melody;
* when the Lead does not sing words and **several other parts do**, nothing says which is the
  melody: the Lead is kept and the section says so, so that a person can mark it.

A "word" is any lyric that is not a vocable: ``oo``, ``ooh``, ``mm``, ``doo``, ``bum`` and the like
(:func:`is_vocable`). A note that holds a syllable (a melisma, a tie) is as much a word as the note
that started it. None of this is musical analysis: it is the barbershop habit of singing the words
in the melody and "oo" behind it, read from the lyrics.

A person can override any stretch by marking it (:class:`MelodyMark`), down to the beat; a mark
always wins and is recorded as marked. Marks are by the bar numbers of the score and apply wherever
that bar is played (every pass of a repeat). A bar has as many beats as its time signature says: a
quarter note each in 4/4 or 3/4, an eighth note each in 3/8, 6/8 or 9/8.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise
from math import ceil

from barbershop_tracks.core.synthesis import (
    VOICE_ORDER,
    LyricState,
    MeasureMark,
    PlannedNote,
    SynthesisPlan,
)
from barbershop_tracks.models import VoiceRole

# Lyrics that are sounds, not words. Deliberately short: "la" and "oh" can be words ("fa la la",
# "Oh come"), so they are not here.
_VOCABLE = re.compile(r"^(?:o{2,}h?|a{2,}h?|h?m{2,}|hm|do{2,}|du?m|bu?m|bo?m|bah|wah)$")
_TEXT_STATES = (LyricState.SCORE_LYRIC, LyricState.USER_APPROVED, LyricState.LEAD_SYLLABLE)
_HOLD_STATES = (LyricState.SCORE_CONTINUATION, LyricState.LEAD_SUSTAIN)


class MelodyError(Exception):
    """A melody mark that cannot be used (a bar the score does not have, a range backwards)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def is_vocable(text: str) -> bool:
    """True for a sound that is not a word: ``Oo``, ``ooh``, ``mm``, ``doo``, ``bum``, ``wah``."""
    letters = re.sub(r"[^a-z]", "", text.lower())
    return bool(_VOCABLE.match(letters))


@dataclass(frozen=True, slots=True)
class MelodyMark:
    """A person's decision: ``role`` has the melody from ``first_bar`` to ``last_bar``.

    Without beats the marked stretch is the whole bars. ``first_beat`` (1 is the start of the bar)
    starts it on a beat of the first bar, and ``last_beat`` ends it with a beat of the last bar
    (that beat included); ``None`` for ``last_beat`` is the end of the bar.
    """

    role: VoiceRole
    first_bar: int
    last_bar: int
    first_beat: int = 1
    last_beat: int | None = None

    def __post_init__(self) -> None:
        if self.first_bar > self.last_bar:
            raise MelodyError(
                "MELODY_MARK_RANGE",
                f"bars {self.first_bar} to {self.last_bar}: the first bar comes after the last",
            )
        if self.first_beat < 1 or (self.last_beat is not None and self.last_beat < 1):
            raise MelodyError("MELODY_MARK_BEAT", "beats are counted from 1")
        if (
            self.first_bar == self.last_bar
            and self.last_beat is not None
            and self.first_beat > self.last_beat
        ):
            raise MelodyError(
                "MELODY_MARK_RANGE",
                f"beat {self.first_beat} to beat {self.last_beat}: the first beat comes after "
                "the last",
            )


@dataclass(frozen=True, slots=True)
class MelodySection:
    """A stretch of the performance in which ``role`` has the melody."""

    start: Fraction  # quarter notes
    end: Fraction
    role: VoiceRole
    marked: bool  # a person said so (otherwise it was read from the lyrics)
    first_bar: int | None  # the score's own bar numbers, None for a plan built by hand
    last_bar: int | None
    first_beat: Fraction = Fraction(1)  # the beat of first_bar it starts on (1 is the bar's start)
    last_beat: int | None = None  # the last beat of last_bar it covers; None: to the bar's end
    note: str = ""  # why, when it is not the usual Lead

    @property
    def bars(self) -> str:
        """Where it is, in the score's own terms: whole bars, or bars and beats."""
        if self.first_bar is None:
            return ""
        if self.first_beat == 1 and self.last_beat is None:
            if self.first_bar == self.last_bar:
                return f"bar {self.first_bar}"
            return f"bars {self.first_bar} to {self.last_bar}"
        begin = f"bar {self.first_bar} beat {_number(self.first_beat)}"
        if self.first_bar == self.last_bar:
            if self.last_beat is None:
                return f"{begin} to the end"
            if _number(self.first_beat) == str(self.last_beat):
                return begin
            return f"bar {self.first_bar} beats {_number(self.first_beat)} to {self.last_beat}"
        if self.last_beat is None:
            return f"{begin} to the end of bar {self.last_bar}"
        return f"{begin} to bar {self.last_bar} beat {self.last_beat}"

    def as_record(self) -> dict[str, object]:
        return {
            "start": str(self.start),
            "end": str(self.end),
            "role": self.role.value,
            "basis": "marked" if self.marked else "lyrics",
            "first_bar": self.first_bar,
            "last_bar": self.last_bar,
            "first_beat": str(self.first_beat),
            "last_beat": self.last_beat,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class _Words:
    start: Fraction
    end: Fraction
    words: bool


def _word_runs(notes: Sequence[PlannedNote]) -> list[_Words]:
    """Each note of a voice, with whether it sings a word (a held syllable keeps its kind)."""
    runs: list[_Words] = []
    previous: PlannedNote | None = None
    previous_words = False
    for note in notes:
        state = note.lyric.state
        if state in _TEXT_STATES and note.lyric.text is not None:
            words = not is_vocable(note.lyric.text)
        elif state in _HOLD_STATES and previous is not None and previous.end == note.start:
            words = previous_words  # holds the syllable before it
        else:
            words = False  # no decided lyric: it says nothing about the melody
        runs.append(_Words(note.start, note.end, words))
        previous, previous_words = note, words
    return runs


def _at(runs: Sequence[_Words], position: Fraction) -> bool | None:
    """Whether the note sounding at ``position`` sings a word; None while the voice rests."""
    for run in runs:
        if run.start <= position < run.end:
            return run.words
        if run.start > position:
            break
    return None


def _number(beat: Fraction) -> str:
    return f"{float(beat):.2f}".rstrip("0").rstrip(".")


def beat_length(plan: SynthesisPlan, position: Fraction) -> Fraction:
    """One beat, in quarter notes, of the time signature in force at ``position``."""
    point = plan.meter[0] if plan.meter else None
    for candidate in plan.meter:
        if candidate.position <= position:
            point = candidate
    if point is None:
        return Fraction(1)
    return Fraction(4, point.beat_type)


def _beats_in(plan: SynthesisPlan, measure: MeasureMark) -> int:
    return ceil(measure.length / beat_length(plan, measure.start))


def beats_in_bar(plan: SynthesisPlan, number: int) -> int:
    """The beats of bar ``number`` (a short pickup bar has fewer); 1 for a bar the plan lacks."""
    return max((_beats_in(plan, m) for m in plan.measures if m.number == number), default=1)


def _where(
    plan: SynthesisPlan, start: Fraction, end: Fraction
) -> tuple[int | None, int | None, Fraction, int | None]:
    """First bar, last bar, beat of the first bar it starts on, last beat of the last bar."""
    inside = [m for m in plan.measures if m.start < end and m.start + m.length > start]
    if not inside:
        return None, None, Fraction(1), None
    first, last = inside[0], inside[-1]
    begin = 1 + max(start - first.start, Fraction(0)) / beat_length(plan, first.start)
    last_beat = None
    if end < last.start + last.length:
        last_beat = ceil((end - last.start) / beat_length(plan, last.start))
    return first.number, last.number, begin, last_beat


def _span(plan: SynthesisPlan, mark: MelodyMark) -> list[tuple[Fraction, Fraction, VoiceRole]]:
    """The stretches of the performance a mark covers: every pass of each bar it names."""
    numbers = {m.number for m in plan.measures}
    for number in (mark.first_bar, mark.last_bar):
        if number not in numbers:
            raise MelodyError("MELODY_MARK_BAR", f"bar {number} is not in the score")
    spans: list[tuple[Fraction, Fraction, VoiceRole]] = []
    for measure in plan.measures:
        if not mark.first_bar <= measure.number <= mark.last_bar:
            continue
        length = beat_length(plan, measure.start)
        begin, finish = measure.start, measure.start + measure.length
        if measure.number == mark.first_bar:
            _check_beat(plan, measure, mark.first_beat)
            begin += (mark.first_beat - 1) * length
        if measure.number == mark.last_bar and mark.last_beat is not None:
            _check_beat(plan, measure, mark.last_beat)
            finish = min(finish, measure.start + mark.last_beat * length)
        spans.append((begin, finish, mark.role))
    return spans


def _check_beat(plan: SynthesisPlan, measure: MeasureMark, beat: int) -> None:
    beats = _beats_in(plan, measure)
    if beat > beats:
        raise MelodyError("MELODY_MARK_BEAT", f"bar {measure.number} has {beats} beats, not {beat}")


def detect_melody(plan: SynthesisPlan) -> tuple[MelodySection, ...]:
    """The melody holder over the whole performance, read from the lyrics, in time order."""
    runs = {voice.role: _word_runs(voice.notes) for voice in plan.voices}
    length = plan.output.performed_length
    cuts = {Fraction(0), length}
    for voice in plan.voices:
        for played in voice.notes:
            cuts.update((played.start, played.end))
    points = sorted(c for c in cuts if 0 <= c <= length)
    segments: list[tuple[Fraction, Fraction, VoiceRole, str]] = []
    for begin, finish in pairwise(points):
        state = {role: _at(runs[role], begin) for role in VOICE_ORDER if role in runs}
        others = [r for r in VOICE_ORDER if r is not VoiceRole.LEAD and state.get(r) is True]
        lead = state.get(VoiceRole.LEAD)
        why = ""
        if lead is True:
            holder = VoiceRole.LEAD
        elif len(others) == 1:
            holder = others[0]
            why = "sings the words while the Lead does not"
        else:
            holder = VoiceRole.LEAD  # nobody sings words: the usual; several: not for BLT to pick
            if len(others) > 1 and lead is False:
                # a Lead that rests for a moment while the others move is just a rest in the melody;
                # only a Lead singing an "oo" under several singers of words is a real question
                names = " and ".join(r.display_name for r in others)
                why = f"{names} all sing words while the Lead does not: the Lead is kept"
        if segments and segments[-1][2] is holder and segments[-1][3] == why:
            first, _, _, _ = segments[-1]
            segments[-1] = (first, finish, holder, why)
        else:
            segments.append((begin, finish, holder, why))
    return tuple(
        MelodySection(s, e, role, False, *_where(plan, s, e), note=why)
        for s, e, role, why in segments
    )


def apply_marks(
    plan: SynthesisPlan,
    sections: Sequence[MelodySection],
    marks: Sequence[MelodyMark],
) -> tuple[MelodySection, ...]:
    """``sections`` with the person's marks laid over them (a later mark wins over an earlier)."""
    if not marks:
        return tuple(sections)
    if not plan.measures:
        raise MelodyError(
            "MELODY_NO_BARS", "the score's bar numbers are not known, so bars cannot be marked"
        )
    spans = [span for mark in marks for span in _span(plan, mark)]
    cuts = {Fraction(0), plan.output.performed_length}
    for section in sections:
        cuts.update((section.start, section.end))
    for first, last, _ in spans:
        cuts.update((first, last))
    points = sorted(c for c in cuts if 0 <= c <= plan.output.performed_length)
    merged: list[tuple[Fraction, Fraction, VoiceRole, bool, str]] = []
    for begin, finish in pairwise(points):
        marked = [role for first, last, role in spans if first <= begin and finish <= last]
        if marked:
            role, is_marked, note = marked[-1], True, ""
        else:
            under = next((s for s in sections if s.start <= begin < s.end), None)
            if under is None:
                continue
            role, is_marked, note = under.role, False, under.note
        if merged and merged[-1][2] is role and merged[-1][3] is is_marked:
            first, _, _, _, kept = merged[-1]
            merged[-1] = (first, finish, role, is_marked, kept or note)
        else:
            merged.append((begin, finish, role, is_marked, note))
    return tuple(
        MelodySection(s, e, role, is_marked, *_where(plan, s, e), note=note)
        for s, e, role, is_marked, note in merged
    )


def melody_of(plan: SynthesisPlan, marks: Sequence[MelodyMark] = ()) -> tuple[MelodySection, ...]:
    """The melody holder over the whole performance: read from the lyrics, then the marks on top."""
    return apply_marks(plan, detect_melody(plan), marks)
