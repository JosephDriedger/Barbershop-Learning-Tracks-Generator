"""Turn four validated stems into the 13-track learning package, as one transaction.

1. Check the request; derive the package length from the score (``timeline.duration_frames``).
2. Load and place all four stems on the common timeline once (never re-rendered, never shifted).
3. In an isolated staging directory, mix every track in float64, quantise once, write the WAV.
   If MP3 is requested, encode each WAV through the injected encoder, which validates its output.
4. Re-read everything that was produced and verify it; write ``manifest.json``.
5. Publish the whole directory with one rename. Any failure, cancellation or invalid file anywhere
   discards staging and leaves ``destination`` exactly as it was.

``replace=True`` only ever replaces a directory that carries one of our manifests, so an unrelated
folder the user pointed at is never moved aside or deleted.
"""

import hashlib
import json
import shutil
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from fractions import Fraction
from pathlib import Path
from typing import Any, Protocol

from barbershop_tracks import __version__
from barbershop_tracks.core.melody import MelodySection
from barbershop_tracks.core.mixing.audio import SAMPLE_RATE, TailPolicy
from barbershop_tracks.core.mixing.errors import (
    MixCancelledError,
    MixConfigurationError,
    MixError,
    MixInputError,
    MixOutputError,
)
from barbershop_tracks.core.mixing.prelude import Prelude, PreludeOptions, build_prelude
from barbershop_tracks.core.mixing.specs import (
    DEFAULT_PROFILE,
    RAMP_SECONDS,
    GainProfile,
    MixSpec,
    following_melody,
    standard_mix_specs,
    validate_spec_set,
)
from barbershop_tracks.core.mixing.streaming import PlacedStem, place_stem, write_mix
from barbershop_tracks.core.mixing.timeline import duration_frames, exact_seconds
from barbershop_tracks.core.rendering.cancel import CancelToken
from barbershop_tracks.core.rendering.wav import WavFormatError, inspect_file
from barbershop_tracks.core.runtime import RuntimeLayout, StagingArea, StagingError
from barbershop_tracks.core.runtime.staging import cleanup_stale, publish_directory, remove_staging
from barbershop_tracks.core.synthesis import (
    VOICE_ORDER,
    MeterPoint,
    SourceIdentity,
    SynthesisPlan,
    TempoPoint,
)
from barbershop_tracks.models import KeySignature, VoiceRole

MANIFEST_NAME = "manifest.json"
MANIFEST_SCHEMA = "blt.learning-tracks/1"

QUANTIZATION = "round-half-to-even(x*32768), clip detection is an error, no dither"
DURATION_POLICY = "ceil(exact_seconds*sample_rate)"


class AudioFormat(Enum):
    WAV = "wav"
    MP3 = "mp3"


class Mp3Encoder(Protocol):
    """Encodes and validates one MP3; see ``mixing.mp3.FfmpegMp3Encoder``."""

    def settings(self) -> dict[str, Any]:
        """Manifest-safe settings (no paths)."""

    def encode(
        self, wav: Path, mp3: Path, *, expected_frames: int, cancel: CancelToken
    ) -> dict[str, Any]:
        """Write ``mp3`` from ``wav``; raise ``MixEncodingError`` on failure or invalid output."""


@dataclass(frozen=True, slots=True)
class PackageSource:
    """What the mixer needs to know about the score: identity, tempo map, performed length."""

    identity: SourceIdentity
    tempo: tuple[TempoPoint, ...]
    length: Fraction  # performed length in quarter notes
    # the pronunciations a person decided for this score (empty: the dictionary alone was used)
    pronunciations: tuple[Mapping[str, Any], ...] = ()
    meter: tuple[MeterPoint, ...] = ()  # for the count-in
    reference_midi: int | None = None  # the Lead's first note: the tune-up note sits near it
    melody: tuple[MelodySection, ...] = ()  # who has the melody when: the Full Quartet follows it

    @classmethod
    def from_plan(
        cls,
        plan: SynthesisPlan,
        *,
        pronunciations: Sequence[Mapping[str, Any]] = (),
        melody: Sequence[MelodySection] = (),
    ) -> "PackageSource":
        lead = next((v for v in plan.voices if v.role is VoiceRole.LEAD), None)
        reference = lead.notes[0].midi_pitch if lead is not None and lead.notes else None
        return cls(
            plan.source,
            plan.tempo,
            plan.output.performed_length,
            tuple(pronunciations),
            plan.meter,
            reference,
            tuple(melody),
        )

    @property
    def key(self) -> KeySignature | None:
        fifths = self.identity.key_fifths
        return None if fifths is None else KeySignature(fifths=fifths, mode=self.identity.key_mode)


@dataclass(frozen=True, slots=True)
class PackageSettings:
    layout: RuntimeLayout
    formats: frozenset[AudioFormat] = frozenset({AudioFormat.WAV})
    profile: GainProfile = DEFAULT_PROFILE
    tail: TailPolicy = field(default_factory=TailPolicy)
    mp3: Mp3Encoder | None = None
    prelude: PreludeOptions = field(default_factory=PreludeOptions)  # tune-up note, count-in
    follow_melody: bool = True  # the Full Quartet makes the voice with the melody louder


@dataclass(frozen=True, slots=True)
class PackagedFile:
    mix: str
    format: AudioFormat
    name: str
    path: Path  # inside the published destination
    bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class PackageResult:
    destination: Path
    files: tuple[PackagedFile, ...]
    manifest: Mapping[str, Any]
    frames: int
    job: str


ProgressHandler = Callable[[dict[str, Any]], None]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def is_our_package(directory: Path) -> bool:
    try:
        data = json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))
        return str(data.get("schema", "")).startswith("blt.learning-tracks/")
    except (OSError, ValueError, AttributeError):
        return False


def stems_from_render(result: Any) -> dict[VoiceRole, Path]:
    """The stem paths of an M8 ``RenderResult``."""
    return {role: report.path for role, report in result.stems.items()}


def _check_cancel(token: CancelToken) -> None:
    if token.cancelled:
        raise MixCancelledError("MIX_CANCELLED", "cancelled; staging was discarded")


def _verify_wav(path: Path, frames: int, name: str) -> None:
    try:
        info, _ = inspect_file(path)
    except WavFormatError as error:
        raise MixOutputError("MIX_OUTPUT_INVALID", f"{name}: {error.message}") from error
    if (info.sample_rate, info.bit_depth, info.channels, info.is_float) != (
        SAMPLE_RATE,
        16,
        1,
        False,
    ):
        raise MixOutputError("MIX_OUTPUT_FORMAT", f"{name} is not 44.1 kHz 16-bit mono PCM")
    if info.frames != frames:
        raise MixOutputError(
            "MIX_OUTPUT_FRAMES", f"{name} has {info.frames} frames, expected {frames}"
        )


def build_learning_tracks(
    source: PackageSource,
    stems: Mapping[VoiceRole, Path],
    destination: Path,
    settings: PackageSettings,
    *,
    cancel: CancelToken | None = None,
    on_progress: ProgressHandler | None = None,
    replace: bool = False,
    extras: Mapping[str, Path] | None = None,
) -> PackageResult:
    """Mix ``stems`` into the standard 13 tracks and publish them to ``destination``.

    ``extras`` maps relative names (``stems/Tenor.wav``) to files that are copied into the package
    as well and listed in the manifest; nothing but the 13 tracks, the manifest and these
    explicitly requested extras is ever published.
    """
    token = cancel or CancelToken()
    wanted = _check_extras(extras or {})
    if not settings.formats:
        raise MixConfigurationError("MIX_NO_FORMAT", "choose WAV, MP3 or both")
    if AudioFormat.MP3 in settings.formats and settings.mp3 is None:
        raise MixConfigurationError("MIX_MP3_NO_ENCODER", "MP3 output needs an encoder (FFmpeg)")
    missing = [r.value for r in VOICE_ORDER if r not in stems]
    if missing:
        raise MixInputError("MIX_STEM_MISSING", f"missing stem(s): {missing}")
    if replace is False and destination.exists():
        raise MixConfigurationError("PUBLISH_DESTINATION_EXISTS", f"{destination} already exists")
    if replace and destination.exists() and not is_our_package(destination):
        raise MixConfigurationError(
            "MIX_DESTINATION_FOREIGN",
            f"{destination} exists and is not a learning-track package; it will not be replaced",
        )
    frames = duration_frames(source.tempo, source.length, SAMPLE_RATE)
    specs = _with_melody(standard_mix_specs(settings.profile), source, settings, frames)
    validate_spec_set(specs)
    prelude = prelude_for(source, settings.prelude)
    _check_cancel(token)

    placed: dict[VoiceRole, PlacedStem] = {
        role: place_stem(role, stems[role], frames, settings.tail) for role in VOICE_ORDER
    }
    stem_hashes = {role: _sha256(stems[role]) for role in VOICE_ORDER}

    layout = settings.layout
    try:
        cleanup_stale(layout.staging)
        job = uuid.uuid4().hex[:12]
        area = StagingArea.create(layout.staging, job)
    except (StagingError, OSError) as error:
        raise MixConfigurationError(
            "STAGING_UNAVAILABLE", f"cannot create a staging directory: {error}"
        ) from error
    try:
        package = area.path / "package"
        work = area.path / "work"
        package.mkdir()
        work.mkdir()
        entries, files = _produce(
            specs, placed, frames, package, work, settings, token, on_progress, prelude
        )
        extra_entries = _copy_extras(package, wanted)
        manifest = _manifest(source, settings, specs, entries, placed, stem_hashes, frames, prelude)
        manifest["extras"] = extra_entries
        text = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
        (package / MANIFEST_NAME).write_text(text, encoding="utf-8", newline="\n")
        total = frames + (0 if prelude is None else prelude.frames)
        _verify_package(package, specs, settings.formats, total, set(wanted))
        _check_cancel(token)
        if on_progress is not None:
            on_progress({"event": "publish", "status": "started"})
        try:
            publish_directory(package, destination, replace=replace)
        except StagingError as error:
            raise MixConfigurationError(error.code, error.message) from error
        if on_progress is not None:
            on_progress({"event": "publish", "status": "finished"})
        published = tuple(
            PackagedFile(f.mix, f.format, f.name, destination / f.name, f.bytes, f.sha256)
            for f in files
        )
        return PackageResult(destination, published, manifest, total, job)
    finally:
        _discard(area.path)


def _with_melody(
    specs: tuple[MixSpec, ...], source: PackageSource, settings: PackageSettings, frames: int
) -> tuple[MixSpec, ...]:
    """The Full Quartet made to follow the melody, when it is wanted and the melody is known."""
    if not settings.follow_melody or not source.melody:
        return specs
    changes: list[tuple[int, VoiceRole]] = []
    for section in source.melody:
        frame = (
            0 if not changes else round(exact_seconds(source.tempo, section.start) * SAMPLE_RATE)
        )
        if changes and not 0 < frame < frames:
            continue  # at the very end, or on the frame of the one before
        if changes and frame <= changes[-1][0]:
            continue
        changes.append((frame, section.role))
    full = following_melody(specs[0], changes, settings.profile, round(RAMP_SECONDS * SAMPLE_RATE))
    return (full, *specs[1:])


def _produce(
    specs: tuple[MixSpec, ...],
    placed: Mapping[VoiceRole, PlacedStem],
    frames: int,
    package: Path,
    work: Path,
    settings: PackageSettings,
    token: CancelToken,
    on_progress: ProgressHandler | None,
    prelude: Prelude | None = None,
) -> tuple[list[dict[str, Any]], list[PackagedFile]]:
    total = frames + (0 if prelude is None else prelude.frames)
    entries: list[dict[str, Any]] = []
    files: list[PackagedFile] = []
    for spec in specs:
        _check_cancel(token)
        wav_name = f"{spec.filename_stem}.wav"
        keep_wav = AudioFormat.WAV in settings.formats
        wav_path = (package if keep_wav else work) / wav_name
        peak = write_mix(
            spec,
            placed,
            frames,
            wav_path,
            should_stop=lambda: token.cancelled,
            lead_in=None if prelude is None else prelude.samples,
        )
        _check_cancel(token)
        entry_files: list[dict[str, Any]] = []
        if keep_wav:
            digest = _sha256(wav_path)
            files.append(
                PackagedFile(
                    spec.identifier,
                    AudioFormat.WAV,
                    wav_name,
                    wav_path,
                    wav_path.stat().st_size,
                    digest,
                )
            )
            entry_files.append(
                {
                    "format": "wav",
                    "name": wav_name,
                    "bytes": wav_path.stat().st_size,
                    "sha256": digest,
                    "sample_rate": SAMPLE_RATE,
                    "bit_depth": 16,
                    "channels": 1,
                    "frames": total,
                }
            )
        if AudioFormat.MP3 in settings.formats:
            assert settings.mp3 is not None
            mp3_name = f"{spec.filename_stem}.mp3"
            mp3_path = package / mp3_name
            info = settings.mp3.encode(wav_path, mp3_path, expected_frames=total, cancel=token)
            if on_progress is not None:
                on_progress({"event": "mp3", "number": spec.number, "of": len(specs)})
            digest = _sha256(mp3_path)
            files.append(
                PackagedFile(
                    spec.identifier,
                    AudioFormat.MP3,
                    mp3_name,
                    mp3_path,
                    mp3_path.stat().st_size,
                    digest,
                )
            )
            entry_files.append(
                {
                    "format": "mp3",
                    "name": mp3_name,
                    "bytes": mp3_path.stat().st_size,
                    "sha256": digest,
                    "sample_rate": SAMPLE_RATE,
                    "channels": 1,
                    **info,
                }
            )
        entries.append(
            {
                "id": spec.identifier,
                "number": spec.number,
                "label": spec.label,
                "kind": spec.kind.value,
                "focus": spec.focus.value if spec.focus else None,
                "voices": [r.value for r in spec.voices],
                "gains": {r.value: spec.gain(r) for r in VOICE_ORDER},
                **_schedule_record(spec),
                "worst_case_gain_sum": spec.worst_case_sum,
                "peak": round(peak, 6),
                "files": entry_files,
            }
        )
        if on_progress is not None:
            on_progress(
                {"event": "mix", "number": spec.number, "of": len(specs), "id": spec.identifier}
            )
    return entries, files


def _schedule_record(spec: MixSpec) -> dict[str, Any]:
    """How the gains of a mix change over time (nothing for a mix with one balance throughout)."""
    if not spec.schedule:
        return {}
    return {
        "gains_are": "the most each voice reaches; they change as the gain_schedule says",
        "gain_schedule": [
            {
                "start_frame": step.frame,
                "gains": {r.value: g for r, g in zip(VOICE_ORDER, step.gains, strict=True)},
            }
            for step in spec.schedule
        ],
        "crossfade_frames": spec.ramp_frames,
    }


def _manifest(
    source: PackageSource,
    settings: PackageSettings,
    specs: tuple[MixSpec, ...],
    entries: list[dict[str, Any]],
    placed: Mapping[VoiceRole, PlacedStem],
    stem_hashes: Mapping[VoiceRole, str],
    frames: int,
    prelude: Prelude | None = None,
) -> dict[str, Any]:
    seconds = exact_seconds(source.tempo, source.length)
    profile = settings.profile
    return {
        "schema": MANIFEST_SCHEMA,
        "generator": {"name": "barbershop-tracks", "version": __version__},
        "source": {
            "display_name": source.identity.display_name,
            "sha256": source.identity.sha256,
            "title": source.identity.title,
            # None for MusicXML; otherwise the program that made the MusicXML, and whether its notes
            # were recognised from a picture (and so not checked by BLT)
            "conversion": None
            if source.identity.conversion is None
            else dict(source.identity.conversion),
        },
        "audio": {
            "sample_rate": SAMPLE_RATE,
            "bit_depth": 16,
            "channels": 1,
            "frames": frames + (0 if prelude is None else prelude.frames),
            "duration_exact_seconds": f"{seconds.numerator}/{seconds.denominator}",
            "duration_seconds": round(float(seconds), 6),
            # what comes before the music in every track (a tune-up note, a count-in), or None;
            # the duration above is the music's, which starts ``music_starts_at_frame`` frames in
            "prelude": None if prelude is None else prelude.info,
            "music_starts_at_frame": 0 if prelude is None else prelude.frames,
        },
        "settings": {
            "gain_profile": {
                "name": profile.name,
                "full_quartet": profile.full_quartet,
                "melody_focus": profile.melody_focus,
                "melody_others": profile.melody_others,
                "predominant_focus": profile.predominant_focus,
                "predominant_others": profile.predominant_others,
                "solo": profile.solo,
                "without_each": profile.without_each,
            },
            "formats": sorted(f.value for f in settings.formats),
            "duration_policy": DURATION_POLICY,
            "quantization": QUANTIZATION,
            "normalization": "none",
            "tail_policy": {
                "max_trim_seconds": settings.tail.max_trim_seconds,
                "max_trim_peak": settings.tail.max_trim_peak,
            },
            "mp3": settings.mp3.settings()
            if AudioFormat.MP3 in settings.formats and settings.mp3
            else None,
        },
        # what the engine was told to sing besides the score's own words: each pronunciation a
        # person decided, bound to this score, next to the score's lyric text (never in place of it)
        "pronunciation": {
            "dictionary": "CMUdict 0.7b; no pronunciation model; a word it lacks stops the run",
            "overrides": [dict(entry) for entry in source.pronunciations],
        },
        # who has the melody when (read from the lyrics, or marked by a person) and whether the Full
        # Quartet follows it; sections are in quarter notes of the performance
        "melody": {
            "followed": bool(source.melody) and settings.follow_melody,
            "sections": [section.as_record() for section in source.melody],
        },
        "stems": [
            {
                "voice": role.value,
                "sha256": stem_hashes[role],
                "frames": placed[role].frames,
                "padded_frames": placed[role].padded_frames,
                "trimmed_frames": placed[role].trimmed_frames,
            }
            for role in VOICE_ORDER
        ],
        "tracks": entries,
    }


def prelude_for(source: PackageSource, options: PreludeOptions) -> Prelude | None:
    """The tune-up note and count-in wanted, built before any stem is touched."""
    if not options.enabled:
        return None
    meter = source.meter[0] if source.meter else None
    if options.count_in and meter is None:
        raise MixConfigurationError(
            "MIX_COUNT_IN", "the score has no time signature, so there is nothing to count in"
        )
    return build_prelude(
        options,
        key=source.key,
        reference_midi=source.reference_midi,
        bpm=source.tempo[0].bpm,
        beats=meter.beats if meter else 4,
        beat_type=meter.beat_type if meter else 4,
    )


def _check_extras(extras: Mapping[str, Path]) -> dict[str, Path]:
    """Extras must be plain relative names under a subfolder, existing, and not collide."""
    checked: dict[str, Path] = {}
    for name, source in extras.items():
        parts = name.split("/")
        if len(parts) < 2 or any(
            not part or part in (".", "..") or ":" in part or "\\" in part for part in parts
        ):
            raise MixConfigurationError(
                "MIX_EXTRA_NAME", f"extra {name!r} must be a relative path inside a subfolder"
            )
        if not source.is_file():
            raise MixConfigurationError("MIX_EXTRA_MISSING", f"extra {name!r} does not exist")
        checked[name] = source
    lowered = [n.lower() for n in checked]
    if len(set(lowered)) != len(lowered):
        raise MixConfigurationError("MIX_NAME_COLLISION", "two extras share a name")
    return checked


def _copy_extras(package: Path, extras: Mapping[str, Path]) -> list[dict[str, Any]]:
    entries = []
    for name in sorted(extras):
        target = package / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(extras[name], target)
        entries.append({"name": name, "bytes": target.stat().st_size, "sha256": _sha256(target)})
    return entries


def _verify_package(
    package: Path,
    specs: tuple[MixSpec, ...],
    formats: frozenset[AudioFormat],
    frames: int,
    extras: set[str] = frozenset(),  # type: ignore[assignment]
) -> None:
    expected = {MANIFEST_NAME, *extras}
    for spec in specs:
        for fmt in formats:
            expected.add(f"{spec.filename_stem}.{fmt.value}")
    actual = {p.relative_to(package).as_posix() for p in package.rglob("*") if p.is_file()}
    if actual != expected:
        raise MixOutputError(
            "MIX_OUTPUT_SET",
            f"the package holds {sorted(actual ^ expected)} that differ from the expected set",
        )
    if AudioFormat.WAV in formats:
        for spec in specs:
            name = f"{spec.filename_stem}.wav"
            _verify_wav(package / name, frames, name)
    for name in expected:
        if (package / name).stat().st_size == 0:
            raise MixOutputError("MIX_OUTPUT_EMPTY", f"{name} is empty")


def _discard(path: Path) -> None:
    try:
        remove_staging(path)
    except OSError:
        shutil.rmtree(path, ignore_errors=True)


__all__ = [
    "MANIFEST_NAME",
    "MANIFEST_SCHEMA",
    "AudioFormat",
    "MixError",
    "Mp3Encoder",
    "PackageResult",
    "PackageSettings",
    "PackageSource",
    "PackagedFile",
    "build_learning_tracks",
    "is_our_package",
    "prelude_for",
    "stems_from_render",
]
