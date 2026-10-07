"""Checks on what sounds: monophony, pitch fitness, tempo and the performed timeline."""

from collections.abc import Callable, Sequence
from fractions import Fraction

from barbershop_tracks.core.readiness.context import Facts, LineFacts, make_finding
from barbershop_tracks.core.readiness.findings import ReadinessFinding
from barbershop_tracks.models import PerformanceNote, Severity


def _aggregate(
    facts: Facts,
    line: LineFacts,
    attacks: Sequence[PerformanceNote],
    severity: Severity,
    code: str,
    message: str,
) -> list[ReadinessFinding]:
    """One finding per line and kind, located at the first offending attack."""
    if not attacks:
        return []
    return [
        make_finding(
            facts.capability,
            severity,
            code,
            f"{len(attacks)} attack(s) {message}",
            facts=facts,
            role=facts.role_of(line.line_id),
            line_id=line.line_id,
            note=attacks[0].source[0],
        )
    ]


def check_monophony(facts: Facts) -> list[ReadinessFinding]:
    """Assigned lines must sing one note at a time (exact ``Fraction`` timing).

    Rests, gaps, adjacent attacks and tie-merged sustains are fine. A chord is never reduced to a
    top or bottom note: it is reported.
    """
    if not facts.capability.monophony_required:
        return []
    out: list[ReadinessFinding] = []
    for line in facts.assigned_lines:
        simultaneous: list[PerformanceNote] = []
        overlapping: list[PerformanceNote] = []
        previous_start = None
        furthest_end = None
        for attack in line.attacks:
            if previous_start is not None and attack.start == previous_start:
                simultaneous.append(attack)
            elif furthest_end is not None and attack.start < furthest_end:
                overlapping.append(attack)
            previous_start = attack.start
            furthest_end = attack.end if furthest_end is None else max(furthest_end, attack.end)
        out += _aggregate(
            facts, line, simultaneous, Severity.ERROR, "LINE_SIMULTANEOUS_NOTES",
            "start together with another attack in the same line (a chord or two voices)",
        )  # fmt: skip
        out += _aggregate(
            facts, line, overlapping, Severity.ERROR, "LINE_OVERLAPPING_NOTES",
            "start before the previous attack in the same line has ended",
        )  # fmt: skip
    return out


def check_pitch(facts: Facts) -> list[ReadinessFinding]:
    """Pitch fitness for the capability. The sounding pitch is authoritative; nothing is rounded."""
    cap = facts.capability
    out: list[ReadinessFinding] = []
    for line in facts.assigned_lines:
        role = facts.role_of(line.line_id)
        non_integral: list[PerformanceNote] = []
        out_of_range: list[PerformanceNote] = []
        unusual: list[PerformanceNote] = []
        typical = cap.range_for(role) if role is not None else None
        for attack in line.attacks:
            pitch = attack.pitch
            if pitch is None:  # pragma: no cover - rests are excluded
                continue
            height = pitch.absolute_semitones
            if cap.integral_midi_pitch_required and height.denominator != 1:
                non_integral.append(attack)
            if cap.midi_range is not None and not cap.midi_range[0] <= height <= cap.midi_range[1]:
                out_of_range.append(attack)
            elif (
                typical is not None
                and height.denominator == 1
                and not typical[0] <= height <= typical[1]
            ):
                unusual.append(attack)
        out += _aggregate(
            facts, line, non_integral, Severity.ERROR, "PITCH_NOT_INTEGRAL",
            "have a sounding pitch that is not a whole semitone; it is not rounded",
        )  # fmt: skip
        if cap.midi_range is not None:
            low, high = cap.midi_range
            out += _aggregate(
                facts, line, out_of_range, Severity.ERROR, "PITCH_OUT_OF_MIDI_RANGE",
                f"have a sounding pitch outside the supported range {low}-{high}",
            )  # fmt: skip
        if typical is not None:
            out += _aggregate(
                facts, line, unusual, Severity.WARNING, "VOICE_RANGE_UNUSUAL",
                f"lie outside the usual range {typical[0]}-{typical[1]} for this voice (check the "
                "clef and octave; pitches are never changed)",
            )  # fmt: skip
    return out


def check_tempo(facts: Facts, *, metronome_hint: bool = False) -> list[ReadinessFinding]:
    """A capability that renders in real time needs a tempo at position 0; 120 is never assumed."""
    if not facts.capability.tempo_required:
        return []
    hint = (
        " A metronome mark was found but it sets no tempo (notation only)."
        if metronome_hint
        else ""
    )
    performed = facts.performed
    if not performed.tempo_events:
        return [
            make_finding(
                facts.capability,
                Severity.ERROR,
                "TEMPO_MISSING",
                "the score has no tempo, and none is assumed." + hint,
            )
        ]
    if performed.effective_tempo_at(Fraction(0)) is None:
        first = performed.tempo_events[0].position
        return [
            make_finding(
                facts.capability,
                Severity.ERROR,
                "TEMPO_INITIAL_MISSING",
                f"the first tempo only begins at quarter note {first}; nothing sets the tempo at "
                "the start, and none is assumed." + hint,
            )
        ]
    return []


def check_timeline(facts: Facts) -> list[ReadinessFinding]:
    """Final performed-model invariants: positive length, every attack inside it."""
    out: list[ReadinessFinding] = []
    extent = facts.extent
    if extent <= 0:
        out.append(
            make_finding(
                facts.capability, Severity.ERROR, "SONG_EMPTY", "the performed song has no length"
            )
        )
        return out
    for line in facts.lines:
        outside = [a for a in line.attacks if a.start < 0 or a.end > extent]
        out += _aggregate(
            facts, line, outside, Severity.ERROR, "EVENT_OUTSIDE_TIMELINE",
            f"lie outside the performed song (0 to {extent} quarter notes)",
        )  # fmt: skip
    return out


Check = Callable[[Facts], list[ReadinessFinding]]
