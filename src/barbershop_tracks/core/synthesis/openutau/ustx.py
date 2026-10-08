"""Write a ready ``SynthesisPlan`` as an OpenUtau 0.1.565 project (USTX 0.7).

Rules, all enforced here rather than hoped for:

* the plan must be ready (no unresolved lyric decision), and the target must be the tested one;
* every position and duration must land on whole project ticks (resolution 480), or the write fails:
  nothing is rounded. An OpenUtau 0.1.565 project does not preserve finer positions (observed in
  A06 with a PPQ-960 file), and notes shorter than ``MIN_NOTE_TICKS`` are refused because a shorter
  one was observed to be lengthened;
* lyrics are written exactly as the plan states them; a continuation is written with the one
  documented extender token and only after a note that has a lyric; ``+~``, ``-``, bracketed
  phonetic hints and non-ASCII text are refused because their handling is not established;
* tempo is stored as a double. An exact value a double cannot hold is written as the nearest double,
  reported, and refused when the accumulated timing deviation over the performed score exceeds
  ``MAX_TEMPO_DRIFT_SECONDS`` (``USTX_TEMPO_DRIFT``);
* the meter is mandatory evidence: no meter at position zero, a beat unit that is not a power of
  two, or a change that is not on a bar line of the preceding meter is an error
  (``USTX_METER_MISSING`` / ``USTX_METER_UNSUPPORTED``). Nothing is assumed to be 4/4 and nothing is
  silently dropped;
* singer, phonemizer and renderer are written exactly as the plan's references state them. Whether
  the singer is installed and the phonemizer resolves is checked by the render host (OpenUtau itself
  would silently substitute), not here.

Output is deterministic: fixed key order, LF line endings, no timestamps, no paths.
"""

import math
import re
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from typing import Any

from barbershop_tracks.core.synthesis.errors import PlanNotReadyError
from barbershop_tracks.core.synthesis.openutau.expressions_0_7 import STATIC_BLOCK
from barbershop_tracks.core.synthesis.openutau.target import (
    TARGET_0_1_565,
    TARGETS,
    OpenUtauTarget,
    UstxError,
)
from barbershop_tracks.core.synthesis.openutau.yaml_emit import Flow, Quoted, emit
from barbershop_tracks.core.synthesis.plan import (
    VOICE_ORDER,
    LyricState,
    SynthesisPlan,
    VoiceEngineRef,
)

# Shorter notes were lengthened on import in A06 (a 7.5-tick duration became 10); the real rule was
# not isolated, so shorter notes are refused rather than risked.
MIN_NOTE_TICKS = 10
_SINGER = re.compile(r'^[^\\/:*?"<>|\x00-\x1f]+$')
_PHONEMIZER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+$")
_RESERVED_LYRICS = frozenset({"+", "+~", "-"})
_BEAT_UNITS = frozenset({1, 2, 4, 8, 16, 32})

# Total allowed difference between the plan's exact timeline and the timeline the stored doubles
# give, summed over every tempo segment of the performed score. A double has a relative error of
# about 1e-16, so any ordinary score is far inside this; it exists so that an absurd value or a
# future representation change fails loudly instead of drifting. One microsecond is far below
# anything audible (one sample at 44.1 kHz is about 23 microseconds).
MAX_TEMPO_DRIFT_SECONDS = Fraction(1, 1_000_000)


class ContinuationToken(Enum):
    """How a score melisma continuation is written. Only the documented extender is supported.

    ``+`` is documented as the extender lyric in OpenUtau's Phonemizer API README. ``+~`` and ``-``
    are deliberately absent: Part B showed they import differently from ``+`` (``-`` becomes ``+``)
    and nothing establishes ``+~`` at synthesis time.
    """

    PLUS = "+"


@dataclass(frozen=True, slots=True)
class UstxWarning:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class TempoRecord:
    position: Fraction
    tick: int
    bpm_exact: Fraction
    bpm_written: float
    error_bpm: Fraction  # written minus exact; zero when a double holds the value exactly


@dataclass(frozen=True, slots=True)
class UstxDocument:
    text: str
    target: OpenUtauTarget
    warnings: tuple[UstxWarning, ...]
    tempo_records: tuple[TempoRecord, ...]
    note_count: int
    tempo_drift_seconds: Fraction = Fraction(0)  # accumulated |stored - exact| over the score

    def encode(self) -> bytes:
        return self.text.encode("utf-8")


def validate_lyric_text(text: str) -> None:
    """Refuse lyric text whose handling by OpenUtau is not established."""
    if text in _RESERVED_LYRICS or text.startswith("+"):
        raise UstxError(
            "USTX_LYRIC_RESERVED", f"{text!r} would be read as an extender, not as text"
        )
    if text != text.strip() or not text:
        raise UstxError(
            "USTX_LYRIC_TEXT", f"lyric {text!r} has leading or trailing space or is empty"
        )
    if any(not 0x20 <= ord(c) <= 0x7E for c in text):
        raise UstxError("USTX_LYRIC_TEXT", f"lyric {text!r} has non-ASCII or control characters")
    if "[" in text or "]" in text:
        raise UstxError(
            "USTX_LYRIC_TEXT", f"lyric {text!r} contains a bracket (phonetic hint syntax)"
        )


def _ticks(value: Fraction, resolution: int, what: str) -> int:
    ticks = value * resolution
    if ticks.denominator != 1:
        raise UstxError(
            "USTX_TIMING_NOT_ON_GRID",
            f"{what} at quarter-note position {value} is not a whole number of ticks at resolution "
            f"{resolution} ({ticks} ticks); nothing is rounded",
        )
    return int(ticks)


def _check_ref(role_name: str, ref: VoiceEngineRef, target: OpenUtauTarget) -> None:
    if not _SINGER.match(ref.singer):
        raise UstxError("USTX_SINGER_REF", f"{role_name}: singer {ref.singer!r} is not a plain id")
    if not _PHONEMIZER.match(ref.phonemizer):
        raise UstxError(
            "USTX_PHONEMIZER_REF",
            f"{role_name}: {ref.phonemizer!r} is not a fully qualified class name",
        )
    if ref.renderer not in target.renderers:
        raise UstxError(
            "USTX_RENDERER_UNKNOWN",
            f"{role_name}: renderer {ref.renderer!r} is not one of {sorted(target.renderers)}",
        )


def _tempo(
    plan: SynthesisPlan, resolution: int, tolerance: Fraction
) -> tuple[list[dict[str, Any]], list[TempoRecord], list[UstxWarning], Fraction]:
    entries: list[dict[str, Any]] = []
    records: list[TempoRecord] = []
    warnings: list[UstxWarning] = []
    end = max(plan.output.performed_length, *(voice.end for voice in plan.voices))
    drift = Fraction(0)
    for index, point in enumerate(plan.tempo):
        tick = _ticks(point.position, resolution, "tempo event")
        written = float(point.bpm)
        if not math.isfinite(written) or written <= 0:
            raise UstxError("USTX_TEMPO_UNREPRESENTABLE", f"{point.bpm} BPM cannot be stored")
        error = Fraction(written) - point.bpm
        records.append(TempoRecord(point.position, tick, point.bpm, written, error))
        stop = plan.tempo[index + 1].position if index + 1 < len(plan.tempo) else end
        quarters = max(stop - point.position, Fraction(0))
        # seconds of the segment: quarters * 60 / bpm, exact versus as stored
        drift += abs(quarters * 60 / Fraction(written) - quarters * 60 / point.bpm)
        if error != 0:
            warnings.append(
                UstxWarning(
                    "USTX_TEMPO_QUANTIZED",
                    f"{point.bpm} BPM at {point.position} is stored as the double {written!r} "
                    f"(error {float(error):.3e} BPM)",
                )
            )
        entries.append({"position": tick, "bpm": written})
    if drift > tolerance:
        raise UstxError(
            "USTX_TEMPO_DRIFT",
            f"stored tempos drift {float(drift):.3e} s from the exact timeline over the performed "
            f"score; the limit is {float(tolerance):.3e} s",
        )
    return entries, records, warnings, drift


def _meter(plan: SynthesisPlan) -> list[dict[str, Any]]:
    """Time signatures by bar index. Anything that cannot be placed exactly is an error."""
    if not plan.meter or plan.meter[0].position != 0:
        raise UstxError(
            "USTX_METER_MISSING",
            "the plan has no meter at position zero; a 4/4 default would be an assumption "
            "without evidence",
        )
    entries: list[dict[str, Any]] = []
    bar = Fraction(0)
    segment_start = Fraction(0)
    length = plan.meter[0].measure_length
    for index, point in enumerate(plan.meter):
        if point.beat_type not in _BEAT_UNITS:
            raise UstxError(
                "USTX_METER_UNSUPPORTED",
                f"{point.beats}/{point.beat_type} at {point.position}: the beat unit is not a "
                "power of two",
            )
        if index > 0:
            bars = (point.position - segment_start) / length
            if bars.denominator != 1 or bars <= 0:
                raise UstxError(
                    "USTX_METER_UNSUPPORTED",
                    f"{point.beats}/{point.beat_type} at {point.position} is not on a bar line "
                    "of the preceding meter (pickup or irregular measure)",
                )
            bar += bars
            segment_start = point.position
            length = point.measure_length
        entries.append(
            {"bar_position": int(bar), "beat_per_bar": point.beats, "beat_unit": point.beat_type}
        )
    return entries


def _track(role_name: str, ref: VoiceEngineRef) -> dict[str, Any]:
    return {
        "singer": ref.singer,
        "phonemizer": ref.phonemizer,
        "renderer_settings": {"renderer": ref.renderer},
        "track_name": role_name,
        "track_color": "Blue",
        "mute": False,
        "solo": False,
        "volume": 0,
        "pan": 0,
        "track_expressions": [],
        "voice_color_names": [""],
    }


def _note(position: int, duration: int, tone: int, lyric: str) -> dict[str, Any]:
    return {
        "position": position,
        "duration": duration,
        "tone": tone,
        "lyric": Quoted(lyric),
        "pitch": {
            "data": [
                Flow([("x", -40), ("y", 0), ("shape", "io")]),
                Flow([("x", 40), ("y", 0), ("shape", "io")]),
            ],
            "snap_first": True,
        },
        "vibrato": Flow(
            [
                ("length", 0),
                ("period", 175),
                ("depth", 25),
                ("in", 10),
                ("out", 10),
                ("shift", 0),
                ("drift", 0),
                ("vol_link", 0),
            ]
        ),
        "phoneme_expressions": [],
        "phoneme_overrides": [],
    }


def write_ustx(
    plan: SynthesisPlan,
    *,
    target: OpenUtauTarget = TARGET_0_1_565,
    continuation: ContinuationToken = ContinuationToken.PLUS,
    tempo_tolerance_seconds: Fraction = MAX_TEMPO_DRIFT_SECONDS,
) -> UstxDocument:
    """The plan as USTX text for ``target``; raises ``PlanNotReadyError`` or ``UstxError``."""
    if TARGETS.get(target.openutau_version) != target:
        raise UstxError(
            "USTX_TARGET_UNSUPPORTED", f"{target.openutau_version} is not a tested target"
        )
    if not plan.is_ready:
        items = plan.review_items
        raise PlanNotReadyError(
            len(items),
            "; ".join(f"{i.role.display_name}#{i.note_index} {i.reason.value}" for i in items[:5]),
        )
    resolution = target.resolution
    tempo_entries, tempo_records, warnings, tempo_drift = _tempo(
        plan, resolution, tempo_tolerance_seconds
    )
    meter_entries = _meter(plan)

    tracks: list[dict[str, Any]] = []
    parts: list[dict[str, Any]] = []
    note_count = 0
    for track_no, voice in enumerate(plan.voices):
        name = voice.role.display_name
        ref = plan.engine_ref(voice.role)
        _check_ref(name, ref, target)
        tracks.append(_track(name, ref))
        notes: list[dict[str, Any]] = []
        previous_has_lyric = False
        previous_end: int | None = None
        for note in voice.notes:
            where = f"{name} note {note.index}"
            start = _ticks(note.start, resolution, where + " start")
            duration = _ticks(note.duration, resolution, where + " duration")
            if duration < MIN_NOTE_TICKS:
                raise UstxError(
                    "USTX_NOTE_TOO_SHORT",
                    f"{where} lasts {duration} ticks; OpenUtau 0.1.565 lengthens notes under "
                    f"{MIN_NOTE_TICKS}, so it is refused",
                )
            lyric = note.lyric
            if lyric.state is LyricState.SCORE_CONTINUATION:
                if not previous_has_lyric:
                    raise UstxError("USTX_CONTINUATION_ORPHAN", f"{where} continues nothing")
                if previous_end != start:
                    # OpenUtau treats "+" as an extender only when the previous note ends exactly
                    # where it starts (UPart.Validate); after a gap it is a silent note
                    raise UstxError(
                        "USTX_CONTINUATION_GAP",
                        f"{where} starts at tick {start} but the previous note ends at "
                        f"{previous_end}; a continuation must touch the note it continues",
                    )
                text = continuation.value
            elif lyric.text is not None:
                validate_lyric_text(lyric.text)
                text = lyric.text
                previous_has_lyric = True
            else:  # unreachable for a ready plan; kept so that nothing silently gets a default
                raise UstxError("USTX_LYRIC_MISSING", f"{where} has no lyric decision")
            notes.append(_note(start, duration, note.midi_pitch, text))
            previous_end = start + duration
        note_count += len(notes)
        parts.append(
            {
                "duration": _ticks(voice.end, resolution, f"{name} end"),
                "name": name,
                "comment": "",
                "track_no": track_no,
                "position": 0,
                "notes": notes,
                "curves": [],
            }
        )

    first = plan.tempo[0]
    first_meter = meter_entries[0]
    head: dict[str, Any] = {
        "name": plan.source.title or plan.source.display_name,
        "comment": "",
        "output_dir": "Vocal",
        "cache_dir": "UCache",
        "ustx_version": target.ustx_version,
        "resolution": resolution,
        "bpm": float(first.bpm),
        "beat_per_bar": first_meter["beat_per_bar"],
        "beat_unit": first_meter["beat_unit"],
    }
    tail: dict[str, Any] = {
        "time_signatures": meter_entries,
        "tempos": tempo_entries,
        "tracks": tracks,
        "voice_parts": parts,
        "wave_parts": [],
    }
    # the static block carries the release's own expressions; it sits between head and tail exactly
    # where OpenUtau 0.1.565 writes it
    text = emit(head) + STATIC_BLOCK + emit(tail)
    assert [v.role for v in plan.voices] == list(VOICE_ORDER)
    return UstxDocument(
        text=text,
        target=target,
        warnings=tuple(warnings),
        tempo_records=tuple(tempo_records),
        note_count=note_count,
        tempo_drift_seconds=tempo_drift,
    )
