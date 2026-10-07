"""Part A recipes: tiny synthetic scores that are exported with the *production* M5 code.

Each recipe builds an in-memory performed score; ``generate.py`` runs the real
``prepare_handoff``/``write_package`` on it, so the artifact is exactly what BLT Music Generator
produces. Notes are ``(start, duration, midi_pitch | None)`` in exact quarter-note ``Fraction``s.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from barbershop_tracks.core.musicxml import ParseResult
from barbershop_tracks.core.readiness import RoleAssignments
from barbershop_tracks.core.timeline import perform_song
from barbershop_tracks.models import (
    MeasureSpan,
    Note,
    Part,
    Pitch,
    RepeatKind,
    RepeatMark,
    Song,
    Step,
    TempoChange,
    TimeSignature,
    VoiceRole,
)
from barbershop_tracks.models.pitch_transform import PitchTransform

Spec = tuple[Fraction | int, Fraction | int, int | None]  # (start, duration, midi pitch or rest)
VOICES = (VoiceRole.TENOR, VoiceRole.LEAD, VoiceRole.BARITONE, VoiceRole.BASS)
LINE_IDS = {role: f"P{i}/s1/v1" for i, role in enumerate(VOICES, start=1)}

# semitone above C -> (step, alter), sharps only
_SPELLING = {
    0: (Step.C, 0),
    1: (Step.C, 1),
    2: (Step.D, 0),
    3: (Step.D, 1),
    4: (Step.E, 0),
    5: (Step.F, 0),
    6: (Step.F, 1),
    7: (Step.G, 0),
    8: (Step.G, 1),
    9: (Step.A, 0),
    10: (Step.A, 1),
    11: (Step.B, 0),
}


def pitch_of(midi: int) -> Pitch:
    step, alter = _SPELLING[midi % 12]
    return Pitch(step, midi // 12 - 1, alter=Fraction(alter))


@dataclass(frozen=True, slots=True)
class Recipe:
    artifact_id: str
    description: str
    parsed: ParseResult
    assignments: RoleAssignments
    ppq: int = 480


def _notes(
    spans: Sequence[MeasureSpan], specs: Sequence[Spec], transform: PitchTransform | None
) -> tuple[Note, ...]:
    notes = []
    for raw_start, raw_duration, midi in specs:
        start, duration = Fraction(raw_start), Fraction(raw_duration)
        span = next(s for s in spans if s.start <= start < s.end)
        notes.append(
            Note(
                start=start,
                duration=duration,
                measure=span.number,
                beat=Fraction(1) + (start - span.start),
                written_pitch=None if midi is None else pitch_of(midi),
                transform=transform
                if (transform is not None and midi is not None)
                else PitchTransform(),
            )
        )
    return tuple(notes)


def build(
    artifact_id: str,
    description: str,
    voices: Mapping[VoiceRole, Sequence[Spec]],
    *,
    measure_lengths: Sequence[int | Fraction],
    tempos: Sequence[tuple[int | Fraction, int | Fraction]] = ((0, 100),),
    signatures: Sequence[tuple[int | Fraction, int, int]] = (),
    backward_repeat_at: int | None = None,
    implicit_first: bool = False,
    transforms: Mapping[VoiceRole, PitchTransform] | None = None,
    ppq: int = 480,
) -> Recipe:
    spans: list[MeasureSpan] = []
    cursor = Fraction(0)
    for index, length in enumerate(measure_lengths):
        spans.append(
            MeasureSpan(
                index=index,
                number=index if implicit_first else index + 1,
                start=cursor,
                length=Fraction(length),
                implicit=implicit_first and index == 0,
            )
        )
        cursor += Fraction(length)
    parts = tuple(
        Part(
            part_id=LINE_IDS[role],
            name=role.display_name,
            events=_notes(spans, voices[role], (transforms or {}).get(role)),
        )
        for role in VOICES
    )
    marks: tuple[RepeatMark, ...] = ()
    if backward_repeat_at is not None:
        marks = (RepeatMark(kind=RepeatKind.BACKWARD, measure_index=backward_repeat_at),)
    song = Song(
        title=artifact_id,
        parts=parts,
        measures=tuple(spans),
        tempo_map=tuple(TempoChange(position=Fraction(p), bpm=Fraction(b)) for p, b in tempos),
        time_signatures=tuple(
            TimeSignature(position=Fraction(p), beats=n, beat_type=d) for p, n, d in signatures
        ),
        repeat_marks=marks,
    )
    performed = perform_song(song)
    parsed = ParseResult(song=song, issues=performed.issues, performed=performed)
    assignments = RoleAssignments(entries=tuple((role, LINE_IDS[role]) for role in VOICES))
    return Recipe(artifact_id, description, parsed, assignments, ppq)


_BASES = {VoiceRole.TENOR: 64, VoiceRole.LEAD: 60, VoiceRole.BARITONE: 55, VoiceRole.BASS: 48}
_SHAPE = (0, 2, 4, 2, 0, 2, 4, 2)


def _quarters(role: VoiceRole, count: int) -> list[Spec]:
    return [(i, 1, _BASES[role] + _SHAPE[i % len(_SHAPE)]) for i in range(count)]


def baseline() -> Recipe:
    """Quarter notes, two 4/4 bars at 100 BPM; the voices have 8, 7, 6 and 5 notes so a mix-up of
    tracks shows in the note counts."""
    counts = dict(zip(VOICES, (8, 7, 6, 5), strict=True))
    return build(
        "baseline",
        "Two bars of quarter notes, 100 BPM, 4/4; note counts Tenor 8, Lead 7, Baritone 6, Bass 5",
        {role: _quarters(role, counts[role]) for role in VOICES},
        measure_lengths=[4, 4],
        signatures=[(0, 4, 4)],
    )


def pitches() -> Recipe:
    """Chromatic run, octave boundaries, extremes, and a transposed line (sounding != written)."""
    return build(
        "pitches",
        "Tenor chromatic C4-B4; Lead octave boundaries; Baritone written C4.. sounding an octave "
        "lower (octave_change -1); Bass low extremes",
        {
            VoiceRole.TENOR: [(i, 1, 60 + i) for i in range(12)],
            VoiceRole.LEAD: [(i, 1, p) for i, p in enumerate((59, 60, 71, 72, 47, 48, 83, 84))],
            VoiceRole.BARITONE: [(i, 1, p) for i, p in enumerate((60, 62, 64, 65))],
            VoiceRole.BASS: [(i, 1, p) for i, p in enumerate((36, 40, 43, 47))],
        },
        measure_lengths=[4, 4, 4],
        signatures=[(0, 4, 4)],
        transforms={VoiceRole.BARITONE: PitchTransform(octave_change=-1)},
    )


def grid() -> Recipe:
    """Exactly representable rhythms at PPQ 480, including odd tick positions."""
    third, fifth = Fraction(1, 3), Fraction(1, 5)
    lead: list[Spec] = [(0, 1, 60), (1, Fraction(1, 2), 62), (Fraction(3, 2), Fraction(1, 2), 64)]
    lead += [(2 + i * third, third, 65 + i) for i in range(3)]  # triplet eighths
    lead += [(3 + i * fifth, fifth, 67 + i) for i in range(5)]  # quintuplet
    # bar 2: 7/12 and 5/12 (280 and 200 ticks), 1/16 (30), 3/32 (45) at an odd tick position
    lead += [(4, Fraction(7, 12), 60), (Fraction(4) + Fraction(7, 12), Fraction(5, 12), 62)]
    lead += [(5, Fraction(1, 16), 64), (Fraction(5) + Fraction(1, 16), Fraction(3, 32), 65)]
    lead += [(6, 1, 67)]
    simple: dict[VoiceRole, list[Spec]] = {
        role: [(0, 1, _BASES[role]), (4, 1, _BASES[role] + 2)] for role in VOICES
    }
    simple[VoiceRole.LEAD] = lead
    return build(
        "grid",
        "Lead: quarter, eighths, triplet eighths, quintuplet, 280/200/30/45-tick values at PPQ 480",
        simple,
        measure_lengths=[4, 4],
        signatures=[(0, 4, 4)],
    )


def grid_ppq960() -> Recipe:
    """The PPQ discriminator: the same musical idea exported at PPQ 960 (a variant of ``grid``).

    A quarter note is tick 960 here, so a copy of the ticks and a rescale onto a 480-per-quarter
    timebase give different numbers, while the musical position (tick / PPQ) is what must agree.
    1/64 of a quarter is tick 15 at PPQ 960 and would be 7.5 at 480: an exact BLT position that a
    480-based importer can only round.
    """
    third = Fraction(1, 3)
    lead: list[Spec] = [(0, 1, 60), (1, Fraction(1, 2), 62), (Fraction(3, 2), Fraction(1, 2), 64)]
    lead += [(2 + i * third, third, 65 + i) for i in range(3)]  # triplet eighths: 320 ticks
    fine = Fraction(3)
    lead += [(fine, Fraction(1, 64), 60)]  # 15 ticks at PPQ 960 (7.5 at 480)
    lead += [(fine + Fraction(1, 64), Fraction(3, 64), 62)]  # starts at 975, 45 ticks long
    lead += [(fine + Fraction(1, 16), Fraction(1, 32), 64)]  # starts at 1020, 30 ticks long
    lead += [(4, Fraction(7, 12), 65)]  # 560 ticks at PPQ 960
    simple: dict[VoiceRole, list[Spec]] = {
        role: [(0, 1, _BASES[role]), (4, 1, _BASES[role] + 2)] for role in VOICES
    }
    simple[VoiceRole.LEAD] = lead
    return build(
        "grid_ppq960",
        "A06 discriminator: exported at PPQ 960; Lead has a quarter, eighths, triplet eighths "
        "(320 ticks), a 1/64 (tick 15) and 3/64 (45) probe, and a 7/12 note (560 ticks)",
        simple,
        measure_lengths=[4, 4],
        signatures=[(0, 4, 4)],
        ppq=960,
    )


def tempo() -> Recipe:
    return build(
        "tempo",
        "100 BPM at 0, 120 BPM at bar 3 (exact 500000 us), 90 BPM at bar 4 (666666.67 us, rounded "
        "to 666667 by M5)",
        {role: _quarters(role, 16) for role in VOICES},
        measure_lengths=[4, 4, 4, 4],
        tempos=[(0, 100), (8, 120), (12, 90)],
        signatures=[(0, 4, 4)],
    )


def meter() -> Recipe:
    return build(
        "meter",
        "4/4 at 0, 3/4 at quarter 4, 6/8 at quarter 7 (a meter change twice)",
        {role: _quarters(role, 10) for role in VOICES},
        measure_lengths=[4, 3, 3],
        signatures=[(0, 4, 4), (4, 3, 4), (7, 6, 8)],
    )


def pickup() -> Recipe:
    return build(
        "pickup",
        "A one-quarter pickup (implicit first measure) then two 4/4 bars",
        {role: [(i, 1, _BASES[role] + _SHAPE[i % 8]) for i in range(9)] for role in VOICES},
        measure_lengths=[1, 4, 4],
        signatures=[(0, 4, 4)],
        implicit_first=True,
    )


def repeats() -> Recipe:
    """Bars 1-2 are repeated (M3 expands them), then bar 3; each bar has its own pitch."""

    def line(base: int) -> list[Spec]:
        return [(i, 1, base + (i // 4) * 2) for i in range(12)]

    return build(
        "repeats",
        "Bars 1-2 repeated then bar 3, performed length 20; each written bar has its own pitch",
        {role: line(_BASES[role]) for role in VOICES},
        measure_lengths=[4, 4, 4],
        signatures=[(0, 4, 4)],
        backward_repeat_at=1,
    )


def adjacent() -> Recipe:
    """Back-to-back notes: note-off and note-on at the same tick, same pitch and changed pitch."""
    pattern = (0, 0, 2, 2, 0, 0, 0, 3)
    return build(
        "adjacent",
        "Back-to-back quarter notes, repeated pitches and changed pitches (no gaps, not tied)",
        {role: [(i, 1, _BASES[role] + pattern[i]) for i in range(8)] for role in VOICES},
        measure_lengths=[4, 4],
        signatures=[(0, 4, 4)],
    )


RECIPES: dict[str, Callable[[], Recipe]] = {
    "baseline": baseline,
    "pitches": pitches,
    "grid": grid,
    "grid_ppq960": grid_ppq960,
    "tempo": tempo,
    "meter": meter,
    "pickup": pickup,
    "repeats": repeats,
    "adjacent": adjacent,
}
