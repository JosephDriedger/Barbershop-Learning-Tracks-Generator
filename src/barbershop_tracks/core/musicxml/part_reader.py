"""Walk one ``<part>`` and place its notes on an exact quarter-note timeline.

Four notions are kept apart on purpose:

* the **XML cursor**: where ``<note>``, ``<backup>`` and ``<forward>`` currently are inside
  the measure being read (``_cursor``);
* the **occupied extent**: the furthest position reached by any event in the measure
  (``_extent``);
* the **expected meter duration**: the length implied by the time signature (``_nominal``);
* the **logical voice lines**: notes grouped by (staff, voice), which may have gaps.

A measure's length on the timeline is derived from those, never from summing one voice.
Everything is ``Fraction`` quarter notes. Problems in the music become issues, not
exceptions, and nothing is guessed: an element that cannot be placed safely is reported
and left out.
"""

import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction

from barbershop_tracks.core.musicxml.duration_type import notated_quarters
from barbershop_tracks.core.musicxml.issues import IssueCollector
from barbershop_tracks.core.musicxml.repeats import (
    REPEAT_NOT_SUPPORTED_YET,
    UNSUPPORTED_JUMP,
    barline_has_repeat_structure,
    jump_attributes_of,
)
from barbershop_tracks.core.musicxml.tie_notation import TieInfo, read_tie_info
from barbershop_tracks.core.musicxml.values import child_text, parse_decimal, parse_int
from barbershop_tracks.models import (
    IDENTITY_TRANSFORM,
    ClefChange,
    Note,
    Pitch,
    PitchTransform,
    SourceLine,
    Step,
    TimeSignature,
)

_ONE = Fraction(1)
_ZERO = Fraction(0)
LineKey = tuple[int, str]  # (staff, voice)


@dataclass(slots=True)
class PartTimeline:
    """What was read from one ``<part>``."""

    part_id: str
    lines: dict[LineKey, list[Note]]  # in order of first appearance
    clefs: list[ClefChange]
    measure_numbers: list[int]
    measure_lengths: list[Fraction]  # quarter notes, per measure, in score order


class _PitchError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def read_part(part: ET.Element, part_id: str, issues: IssueCollector) -> PartTimeline:
    """Read ``part`` (a ``<part>`` element) into voice lines, clefs and measure lengths."""
    reader = _PartReader(part, part_id, issues)
    reader.read()
    return PartTimeline(
        part_id=part_id,
        lines=reader.lines,
        clefs=reader.clefs,
        measure_numbers=reader.measure_numbers,
        measure_lengths=reader.measure_lengths,
    )


class _PartReader:
    def __init__(self, part: ET.Element, part_id: str, issues: IssueCollector) -> None:
        self._part = part
        self._part_id = part_id
        self._issues = issues
        self.lines: dict[LineKey, list[Note]] = {}
        self.clefs: list[ClefChange] = []
        self.measure_numbers: list[int] = []
        self.measure_lengths: list[Fraction] = []
        # state that persists across measures
        self._divisions: Fraction | None = None
        self._nominal: Fraction | None = None
        self._default_transform: PitchTransform | None = IDENTITY_TRANSFORM
        self._staff_transforms: dict[int, PitchTransform | None] = {}
        self._reported_divisions = False
        self._reported_time = False
        # state of the measure being read
        self._number = 0
        self._measure_start = _ZERO
        self._cursor = _ZERO
        self._extent = _ZERO
        self._last_local: Fraction | None = None
        self._handlers: dict[str, Callable[[ET.Element], None]] = {
            "attributes": self._attributes,
            "note": self._note,
            "backup": self._backup,
            "forward": self._forward,
            "barline": self._barline,
            "direction": self._direction,
            "sound": self._direction,
        }

    # --- measure loop -----------------------------------------------------------------

    def read(self) -> None:
        start = _ZERO
        for ordinal, measure in enumerate(self._part.findall("measure"), start=1):
            self._begin_measure(measure, ordinal, start)
            for child in measure:
                handler = self._handlers.get(child.tag)
                if handler is not None:
                    handler(child)
            length = self._measure_length(measure)
            self.measure_numbers.append(self._number)
            self.measure_lengths.append(length)
            start += length

    def _begin_measure(self, measure: ET.Element, ordinal: int, start: Fraction) -> None:
        raw = measure.get("number")
        number = parse_int(raw) if raw is not None and raw.isascii() else None
        if number is None or number < 0:
            number = ordinal
            self._issues.warning(
                "MEASURE_NUMBER_NONNUMERIC",
                f"measure number {raw!r} is not a non-negative integer; "
                f"using its position ({ordinal}) instead",
                part_id=self._part_id,
                measure=ordinal,
            )
        self._number = number
        self._measure_start = start
        self._cursor = _ZERO
        self._extent = _ZERO
        self._last_local = None

    def _measure_length(self, measure: ET.Element) -> Fraction:
        """Length of the measure on the timeline, in quarter notes."""
        occupied = self._extent
        nominal = self._nominal
        if nominal is None:
            if not self._reported_time:
                self._reported_time = True
                self._error(
                    "TIME_SIGNATURE_MISSING",
                    "no usable time signature before this measure, so its length is unknown",
                )
            return occupied
        implicit = measure.get("implicit") == "yes"
        if occupied > nominal:
            self._error(
                "MEASURE_DURATION_MISMATCH",
                f"events extend to {occupied} quarter notes but the time signature allows "
                f"{nominal}",
            )
            return occupied
        if implicit:
            return occupied  # a pickup or other deliberately short measure
        if occupied < nominal:
            self._issues.warning(
                "MEASURE_INCOMPLETE",
                f"measure is only filled to {occupied} of {nominal} quarter notes; "
                "the timeline assumes the full measure length",
                part_id=self._part_id,
                measure=self._number,
            )
        return nominal

    # --- helpers ----------------------------------------------------------------------

    def _error(
        self,
        code: str,
        message: str,
        *,
        line: SourceLine | None = None,
        local: Fraction | None = None,
    ) -> None:
        self._issues.error(
            code,
            message,
            part_id=str(line) if line is not None else self._part_id,
            measure=self._number,
            beat=None if local is None else _ONE + local,
        )

    def _warn(
        self,
        code: str,
        message: str,
        *,
        line: SourceLine | None = None,
        local: Fraction | None = None,
    ) -> None:
        self._issues.warning(
            code,
            message,
            part_id=str(line) if line is not None else self._part_id,
            measure=self._number,
            beat=None if local is None else _ONE + local,
        )

    def _best_line(self, element: ET.Element) -> SourceLine | None:
        """The source line of a note if its staff and voice are readable, else ``None``."""
        voice = child_text(element, "voice")
        raw_staff = child_text(element, "staff")
        staff = 1 if raw_staff is None else parse_int(raw_staff)
        if voice is None or staff is None or staff < 1:
            return None
        return SourceLine(part_id=self._part_id, staff=staff, voice=voice)

    def _quarters(
        self, element: ET.Element, missing_code: str, invalid_code: str, what: str
    ) -> Fraction | None:
        """``<duration>`` of ``element`` converted to quarter notes, or ``None`` (reported)."""
        raw = child_text(element, "duration")
        if raw is None:
            self._error(missing_code, f"{what} has no <duration>", local=self._cursor)
            return None
        value = parse_decimal(raw)
        if value is None or value <= 0:
            self._error(invalid_code, f"{what} has an invalid <duration>", local=self._cursor)
            return None
        if self._divisions is None:
            if not self._reported_divisions:
                self._reported_divisions = True
                self._error("DIVISIONS_MISSING", "<divisions> was not given before this point")
            return None
        return value / self._divisions

    # --- <attributes> -----------------------------------------------------------------

    def _attributes(self, element: ET.Element) -> None:
        raw_divisions = child_text(element, "divisions")
        if raw_divisions is not None:
            divisions = parse_decimal(raw_divisions)
            if divisions is None or divisions <= 0:
                self._error("DIVISIONS_INVALID", "<divisions> must be a positive number")
            else:
                self._divisions = divisions
        time = element.find("time")
        if time is not None:
            self._time(time)
        for clef in element.findall("clef"):
            self._clef(clef)
        for transpose in element.findall("transpose"):
            self._transpose(transpose)

    def _time(self, time: ET.Element) -> None:
        if self._cursor != _ZERO:
            # A meter change after the measure has begun would need the measure to be split
            # or reinterpreted. That is not supported, and the new meter is NOT applied (the
            # one in effect at the start of the measure keeps governing its length).
            self._error(
                "TIME_SIGNATURE_CHANGE_MID_MEASURE",
                "a time signature appears after the start of a measure, which is not "
                "supported; the measure keeps the meter it started with",
                local=self._cursor,
            )
            return
        beats, beat_types = time.findall("beats"), time.findall("beat-type")
        beats_n = parse_int(beats[0].text) if len(beats) == 1 else None
        type_n = parse_int(beat_types[0].text) if len(beat_types) == 1 else None
        length: Fraction | None = None
        if beats_n is not None and type_n is not None:
            try:
                length = TimeSignature(
                    position=_ZERO, beats=beats_n, beat_type=type_n
                ).measure_length
            except ValueError:
                length = None
        if length is None:
            self._nominal = None
            self._reported_time = True
            self._error(
                "TIME_SIGNATURE_UNSUPPORTED",
                "only simple time signatures such as 4/4 or 6/8 are supported "
                "(not senza misura, additive or composite meters)",
            )
        else:
            self._nominal = length
            self._reported_time = False

    def _clef(self, clef: ET.Element) -> None:
        number = parse_int(clef.get("number")) if clef.get("number") is not None else 1
        sign = child_text(clef, "sign")
        raw_line, raw_octave = child_text(clef, "line"), child_text(clef, "clef-octave-change")
        line = parse_int(raw_line)
        octave = parse_int(raw_octave) if raw_octave is not None else 0
        try:
            if number is None or sign is None or octave is None:
                raise ValueError("incomplete clef")
            if raw_line is not None and line is None:
                raise ValueError("invalid clef line")
            self.clefs.append(
                ClefChange(
                    part_id=self._part_id,
                    staff=number,
                    sign=sign,
                    line=line,
                    octave_change=octave,
                    measure=self._number,
                    position=self._measure_start + self._cursor,
                )
            )
        except ValueError:
            self._issues.warning(
                "CLEF_INVALID",
                "a <clef> could not be read and was skipped (clefs are informational only)",
                part_id=self._part_id,
                measure=self._number,
            )

    def _transpose(self, transpose: ET.Element) -> None:
        """Apply ``<transpose>`` to the staff it names, or to all staves if it names none."""
        raw_number = transpose.get("number")
        staff = parse_int(raw_number) if raw_number is not None else None
        value = self._transform_of(transpose)
        if raw_number is None:
            self._default_transform = value
            self._staff_transforms.clear()
        elif staff is None or staff < 1:
            self._error("TRANSPOSE_INVALID", "<transpose> has an invalid staff number")
        else:
            self._staff_transforms[staff] = value

    def _transform_of(self, transpose: ET.Element) -> PitchTransform | None:
        """The ``PitchTransform`` for a ``<transpose>``, or ``None`` (reported) if unusable."""
        if transpose.find("double") is not None:
            # MusicXML 4.0: <double> says the music is doubled one octave from what is
            # written, i.e. a second sounding note. A PitchTransform maps one written pitch
            # to one sounding pitch and cannot express that, so it is rejected, not ignored.
            self._error(
                "TRANSPOSE_DOUBLE_UNSUPPORTED",
                "<transpose> contains <double> (octave doubling), which is not supported",
            )
            return None
        chromatic = parse_decimal(child_text(transpose, "chromatic"))
        raw_diatonic = child_text(transpose, "diatonic")
        raw_octave = child_text(transpose, "octave-change")
        diatonic = parse_int(raw_diatonic) if raw_diatonic is not None else None
        octave = parse_int(raw_octave) if raw_octave is not None else 0
        if chromatic is None or chromatic.denominator != 1 or octave is None:
            self._error("TRANSPOSE_INVALID", "<transpose> needs whole-number chromatic steps")
            return None
        if raw_diatonic is not None and diatonic is None:
            self._error("TRANSPOSE_INVALID", "<transpose> has an invalid <diatonic>")
            return None
        if diatonic is None and chromatic != 0:
            self._error(
                "TRANSPOSE_NOT_SPELLABLE",
                "<transpose> has no <diatonic>, so the sounding spelling cannot be derived",
            )
            return None
        try:
            return PitchTransform(
                diatonic=diatonic or 0, chromatic=int(chromatic), octave_change=octave
            )
        except ValueError as exc:
            self._error("TRANSPOSE_INVALID", f"<transpose> is contradictory: {exc}")
            return None

    # --- notes ------------------------------------------------------------------------

    def _note(self, element: ET.Element) -> None:
        chord = element.find("chord") is not None
        if element.find("grace") is not None:
            # A grace note has no <duration> and does not advance the cursor.
            self._error(
                "UNSUPPORTED_GRACE_NOTE",
                "grace notes are not supported",
                line=self._best_line(element),
                local=self._cursor,
            )
            return
        duration = self._quarters(
            element, "NOTE_DURATION_MISSING", "NOTE_DURATION_INVALID", "a note"
        )
        if duration is None:
            return
        if chord:
            if self._last_local is None:
                self._error(
                    "CHORD_WITHOUT_PRECEDING_NOTE",
                    "a <chord/> note has no note before it in this measure",
                    local=self._cursor,
                )
                return
            local = self._last_local
        else:
            local = self._cursor
            self._cursor = local + duration
            self._last_local = local
        self._extent = max(self._extent, local + duration)
        self._check_duration_type(element, duration, local)
        self._emit(element, local, duration)

    def _check_duration_type(
        self, element: ET.Element, duration: Fraction, local: Fraction
    ) -> None:
        """Warn if ``<type>`` disagrees with ``<duration>``. Never changes the timing."""
        notated = notated_quarters(element)
        if notated is not None and notated != duration:
            self._warn(
                "DURATION_TYPE_MISMATCH",
                f"<duration> is {duration} quarter notes but <type>, dots and tuplet ratio "
                f"say {notated}; the <duration> is used",
                line=self._best_line(element),
                local=local,
            )

    def _emit(self, element: ET.Element, local: Fraction, duration: Fraction) -> None:
        """Turn a placed ``<note>`` into a ``Note`` on its voice line, or report why not."""
        if element.find("cue") is not None:
            # A cue note is silent but, like any other <note> without <chord/>, it has
            # already moved the cursor. It is not a singer event.
            self._warn(
                "CUE_NOTE_SKIPPED",
                "a cue note was skipped (it does not sound)",
                line=self._best_line(element),
                local=local,
            )
            return
        if element.find("unpitched") is not None:
            self._error(
                "UNSUPPORTED_UNPITCHED_NOTE",
                "unpitched notes are not supported",
                line=self._best_line(element),
                local=local,
            )
            return
        voice = child_text(element, "voice")
        raw_staff = child_text(element, "staff")
        staff = 1 if raw_staff is None else parse_int(raw_staff)
        if voice is None:
            self._error("VOICE_MISSING", "a note has no <voice>", local=local)
            return
        if staff is None or staff < 1:
            self._error("STAFF_INVALID", "a note has an invalid <staff>", local=local)
            return
        line = SourceLine(part_id=self._part_id, staff=staff, voice=voice)
        note = self._build_note(element, line, local, duration)
        if note is not None:
            self.lines.setdefault((staff, voice), []).append(note)

    def _build_note(
        self, element: ET.Element, line: SourceLine, local: Fraction, duration: Fraction
    ) -> Note | None:
        start, beat = self._measure_start + local, _ONE + local
        if element.find("rest") is not None:
            return Note.rest(start=start, duration=duration, measure=self._number, beat=beat)
        try:
            pitch = _read_pitch(element)
        except _PitchError as problem:
            self._error(problem.code, str(problem), line=line, local=local)
            return None
        transform = self._staff_transforms.get(line.staff, self._default_transform)
        if transform is None:
            return None  # the unusable <transpose> was already reported
        try:
            transform.apply(pitch)
        except ValueError as exc:
            self._error(
                "TRANSPOSE_NOT_SPELLABLE",
                f"cannot spell the sounding pitch: {exc}",
                line=line,
                local=local,
            )
            return None
        ties = read_tie_info(element)
        self._tie_diagnostics(ties, pitch, line, local)
        return Note(
            start=start,
            duration=duration,
            measure=self._number,
            beat=beat,
            written_pitch=pitch,
            transform=transform,
            tied_to_next=ties.starts,
            tied_from_previous=ties.stops,
        )

    def _tie_diagnostics(
        self, ties: TieInfo, pitch: Pitch, line: SourceLine, local: Fraction
    ) -> None:
        """Compare the sound tie (``<tie>``) with the notated tie (``<tied>``).

        ``<tie>`` alone decides whether the note is tied. Disagreement is reported and never
        silently resolved, because tied or not changes what is sung. A future UI may offer an
        explicit repair; the parser never makes one.
        """
        for bad in ties.invalid_tie_types:
            self._error(
                "TIE_TYPE_INVALID",
                f"<tie> on {pitch} has type {bad!r}; only 'start' and 'stop' are valid",
                line=line,
                local=local,
            )
        sound, notated = sorted(ties.tie_types), sorted(ties.tied_types)
        if sound == notated:
            return
        if sound and not notated:
            self._warn(
                "TIE_WITHOUT_TIED",
                f"{pitch} has a sound <tie> ({', '.join(sound)}) but no notated <tied>; "
                "the sound tie is used",
                line=line,
                local=local,
            )
        elif notated and not sound:
            self._error(
                "TIED_WITHOUT_TIE",
                f"{pitch} has a notated <tied> ({', '.join(notated)}) but no sound <tie>, so it "
                "is NOT treated as tied; the notation and the playback tie disagree",
                line=line,
                local=local,
            )
        else:
            self._error(
                "TIE_TIED_MISMATCH",
                f"{pitch} has <tie> ({', '.join(sound)}) and <tied> ({', '.join(notated)}) "
                "that disagree",
                line=line,
                local=local,
            )

    # --- <backup> / <forward> ---------------------------------------------------------

    def _backup(self, element: ET.Element) -> None:
        distance = self._quarters(
            element, "MOVE_DURATION_INVALID", "MOVE_DURATION_INVALID", "<backup>"
        )
        if distance is None:
            return
        if distance > self._cursor:
            self._error(
                "BACKUP_BEFORE_MEASURE_START",
                f"<backup> moves {distance} quarter notes back but only {self._cursor} "
                "have been read in this measure",
                local=self._cursor,
            )
            # Error recovery only, NOT an interpretation of valid MusicXML: the score is
            # already blocked by the ERROR above. Resetting to the measure start keeps later
            # positions in this measure plausible so further real problems can still be
            # reported instead of a cascade of nonsense positions.
            self._cursor = _ZERO
        else:
            self._cursor -= distance
        self._last_local = None

    def _forward(self, element: ET.Element) -> None:
        distance = self._quarters(
            element, "MOVE_DURATION_INVALID", "MOVE_DURATION_INVALID", "<forward>"
        )
        if distance is None:
            return
        self._cursor += distance
        self._extent = max(self._extent, self._cursor)
        self._last_local = None

    # --- structures that are detected but not interpreted yet -------------------------

    def _barline(self, element: ET.Element) -> None:
        if barline_has_repeat_structure(element):
            self._error(
                REPEAT_NOT_SUPPORTED_YET,
                "repeat and ending structures are not supported yet; "
                "this score would otherwise be read as a single pass",
            )

    def _direction(self, element: ET.Element) -> None:
        for name in jump_attributes_of(element):
            self._error(UNSUPPORTED_JUMP, f"jump marker '{name}' is not supported")


def _read_pitch(note: ET.Element) -> Pitch:
    """The ``<pitch>`` of ``note`` exactly as written. Raises ``_PitchError``."""
    pitch = note.find("pitch")
    if pitch is None:
        raise _PitchError("NOTE_WITHOUT_PITCH", "a note has no <pitch> and is not a rest")
    try:
        step = Step(child_text(pitch, "step") or "")
    except ValueError:
        raise _PitchError("PITCH_INVALID", "a <pitch> has an invalid <step>") from None
    octave = parse_int(child_text(pitch, "octave"))
    raw_alter = child_text(pitch, "alter")
    alter = _ZERO if raw_alter is None else parse_decimal(raw_alter)
    if octave is None or alter is None:
        raise _PitchError("PITCH_INVALID", "a <pitch> has an invalid <octave> or <alter>")
    try:
        return Pitch(step, octave, alter)
    except ValueError as exc:
        raise _PitchError("PITCH_OUT_OF_RANGE", f"pitch is out of range: {exc}") from None
