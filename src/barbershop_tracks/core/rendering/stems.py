"""Check the host's output against the plan before anything is published, then name the stems.

A successful process exit proves nothing about the audio: OpenUtau renders an unsupported alias as
an empty or silent WAV without any error. These checks look at the files themselves. They establish
that each stem exists, decodes, has the supported format and a plausible length, starts where the
plan says its first note does and is audible. They do **not** and cannot establish that the singing
is correct: a non-silent stem says nothing about pronunciation, pitch accuracy or lyric accuracy.
"""

import shutil
from dataclasses import dataclass, field, replace
from fractions import Fraction
from pathlib import Path

from barbershop_tracks.core.rendering.errors import OutputValidationError
from barbershop_tracks.core.rendering.wav import WavAudio, WavFormatError, read_wav
from barbershop_tracks.core.synthesis import SynthesisPlan, VoicePlan
from barbershop_tracks.models import VoiceRole

STEM_BASE = "stem"


@dataclass(frozen=True, slots=True)
class StemPolicy:
    """What a stem must look like. Defaults describe what OpenUtau.Core 0.1.565 writes."""

    sample_rates: tuple[int, ...] = (44100,)
    bit_depths: tuple[int, ...] = (16,)
    channels: tuple[int, ...] = (1,)
    # a stem whose loudest sample is below this (full scale = 1.0) is silent; -80 dBFS
    silence_peak: float = 1e-4
    # seconds the stem may be shorter / longer than the end of the voice's last note
    duration_shorter: float = 0.05
    duration_longer: float = 0.5
    # seconds the first audible sample may precede / follow the voice's first note start
    onset_earlier: float = 0.25
    onset_later: float = 0.5
    # the first audible sample is the first one above this share of the stem's peak
    onset_threshold: float = 0.02
    # every note's middle half must carry at least this RMS; -60 dBFS
    note_rms_floor: float = 1e-3
    # notes shorter than this (seconds) are too short to judge
    note_min_seconds: float = 0.06


@dataclass(frozen=True, slots=True)
class StemReport:
    role: VoiceRole
    path: Path
    frames: int
    sample_rate: int
    channels: int
    bit_depth: int
    duration_seconds: float
    peak: float
    first_audible_seconds: float | None
    notes_checked: int = 0
    warnings: tuple[str, ...] = field(default_factory=tuple)


def host_file_name(role: VoiceRole) -> str:
    return f"{STEM_BASE}_{role.display_name}.wav"


def stem_file_name(role: VoiceRole) -> str:
    return f"{role.display_name}.wav"


def seconds_at(plan: SynthesisPlan, position: Fraction) -> float:
    """Wall-clock seconds of a quarter-note position under the plan's tempo map."""
    total = Fraction(0)
    for index, point in enumerate(plan.tempo):
        stop = plan.tempo[index + 1].position if index + 1 < len(plan.tempo) else None
        if position <= point.position:
            break
        end = position if stop is None or position < stop else stop
        total += (end - point.position) * 60 / point.bpm
    return float(total)


def voices_that_sing(plan: SynthesisPlan) -> list[VoicePlan]:
    return [voice for voice in plan.voices if voice.notes]


def _fail(code: str, message: str, **details: object) -> OutputValidationError:
    return OutputValidationError(code, message, details)


def _check_files(plan: SynthesisPlan, host_out: Path) -> dict[VoiceRole, Path]:
    expected = {
        voice.role: host_out / host_file_name(voice.role) for voice in voices_that_sing(plan)
    }
    try:
        actual = {entry.name for entry in host_out.iterdir()}
    except OSError as error:
        raise _fail("STEM_OUTPUT_UNREADABLE", f"cannot list the host output: {error}") from error
    wanted = {path.name for path in expected.values()}
    missing, unexpected = sorted(wanted - actual), sorted(actual - wanted)
    if missing or unexpected:
        raise _fail(
            "STEM_FILES_MISMATCH",
            f"expected exactly {sorted(wanted)}; missing {missing}, unexpected {unexpected}",
            missing=missing,
            unexpected=unexpected,
        )
    for path in expected.values():
        if not path.is_file():
            raise _fail("STEM_NOT_A_FILE", f"{path.name} is not a regular file")
    return expected


def _decode(role: VoiceRole, path: Path, policy: StemPolicy) -> WavAudio:
    name = role.display_name
    try:
        audio = read_wav(path)
    except WavFormatError as error:
        raise _fail(
            "STEM_NOT_DECODABLE", f"{name}: {error.message}", wav_code=error.code
        ) from error
    info = audio.info
    if info.frames == 0:
        raise _fail("STEM_EMPTY", f"{name}: the WAV has no audio frames")
    if (
        info.sample_rate not in policy.sample_rates
        or info.bit_depth not in policy.bit_depths
        or info.channels not in policy.channels
        or info.is_float
    ):
        raise _fail(
            "STEM_FORMAT_UNSUPPORTED",
            f"{name}: {info.sample_rate} Hz, {info.bit_depth}-bit"
            f"{' float' if info.is_float else ''}, {info.channels} channel(s) is not one of the "
            f"supported formats",
        )
    return audio


def _check_audio(
    plan: SynthesisPlan, voice: VoicePlan, path: Path, audio: WavAudio, policy: StemPolicy
) -> StemReport:
    name = voice.role.display_name
    info, samples = audio.info, audio.samples
    rate = info.sample_rate
    peak = max(max(samples), -min(samples))
    if peak < policy.silence_peak:
        raise _fail("STEM_SILENT", f"{name}: the stem is silent although the voice has notes")

    first_start = seconds_at(plan, voice.notes[0].start)
    last_end = seconds_at(plan, voice.end)
    seconds = info.seconds
    if seconds < last_end - policy.duration_shorter or seconds > last_end + policy.duration_longer:
        raise _fail(
            "STEM_DURATION",
            f"{name}: {seconds:.3f} s long, but the last note ends at {last_end:.3f} s",
            seconds=seconds,
            expected_end=last_end,
        )

    threshold = peak * policy.onset_threshold
    onset_frame = next((i for i, x in enumerate(samples) if abs(x) >= threshold), None)
    assert onset_frame is not None  # the peak itself qualifies
    onset = onset_frame / rate
    if not first_start - policy.onset_earlier <= onset <= first_start + policy.onset_later:
        raise _fail(
            "STEM_ORIGIN",
            f"{name}: the first sound is at {onset:.3f} s but the first note starts at "
            f"{first_start:.3f} s; the stem does not keep the score's timeline",
            onset=onset,
            first_note=first_start,
        )

    silent_notes: list[int] = []
    checked = 0
    for note in voice.notes:
        begin, end = seconds_at(plan, note.start), seconds_at(plan, note.start + note.duration)
        if end - begin < policy.note_min_seconds:
            continue
        quarter = (end - begin) / 4
        a, b = int((begin + quarter) * rate), int((end - quarter) * rate)
        window = samples[a:b]
        if not window:
            continue
        checked += 1
        rms = (sum(x * x for x in window) / len(window)) ** 0.5
        if rms < policy.note_rms_floor:
            silent_notes.append(note.index)
    if silent_notes:
        raise _fail(
            "STEM_NOTE_SILENT",
            f"{name}: note(s) {silent_notes} render as silence (an unsupported alias renders "
            "silently); the voicebank cannot sing those lyrics",
            notes=silent_notes,
        )
    return StemReport(
        role=voice.role,
        path=path,
        frames=info.frames,
        sample_rate=rate,
        channels=info.channels,
        bit_depth=info.bit_depth,
        duration_seconds=seconds,
        peak=peak,
        first_audible_seconds=onset,
        notes_checked=checked,
    )


def validate_and_collect(
    plan: SynthesisPlan, host_out: Path, stems_dir: Path, policy: StemPolicy
) -> dict[VoiceRole, StemReport]:
    """Validate every stem, then move them to ``stems_dir/<Role>.wav``; raises on any problem."""
    files = _check_files(plan, host_out)
    reports: dict[VoiceRole, StemReport] = {}
    for voice in voices_that_sing(plan):
        path = files[voice.role]
        audio = _decode(voice.role, path, policy)
        reports[voice.role] = _check_audio(plan, voice, path, audio, policy)
    stems_dir.mkdir()
    final: dict[VoiceRole, StemReport] = {}
    for role, report in reports.items():
        target = stems_dir / stem_file_name(role)
        shutil.move(report.path, target)
        final[role] = replace(report, path=target)
    return final
