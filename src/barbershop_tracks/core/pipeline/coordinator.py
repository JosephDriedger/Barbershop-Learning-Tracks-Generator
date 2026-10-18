"""MusicXML in, the 13-track learning package out: one coordinated, cancellable, transactional run.

The coordinator only connects existing modules and translates their failures into one error type:

    parse (M2/M3) -> readiness (M4) -> SynthesisPlan (M7b) -> USTX check -> voicebank check ->
    render + validate four stems (M8) -> mix 13 tracks, optional MP3 (M9) -> publish

Nothing is repaired: a missing tempo or meter, an undecided lyric, an unknown singer or a missing
FFmpeg stops the run with an explanatory :class:`PipelineError`. All temporary files (stems,
render staging, MP3 intermediates) live under a job-scoped staging directory that is removed on
every exit path; the published package holds only the 13 tracks in the chosen formats, the
manifest and any explicitly requested extras. A failure never touches an existing package.
"""

import dataclasses
import shutil
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from barbershop_tracks.core.errors import ScoreConversionError, ScoreLoadError
from barbershop_tracks.core.handoff import HandoffError, sanitize_name
from barbershop_tracks.core.mixing import (
    AudioFormat,
    FfmpegMp3Encoder,
    MixCancelledError,
    MixConfigurationError,
    MixError,
    Mp3Encoder,
    PackageResult,
    PackageSettings,
    PackageSource,
    build_learning_tracks,
    is_our_package,
    stems_from_render,
)
from barbershop_tracks.core.musicxml import ParseResult, opened_score, parse_musicxml
from barbershop_tracks.core.pipeline.config import (
    ENGLISH_PHONEMIZERS,
    ResolvedConfig,
    default_voices_dir,
    discover_singers,
    ensure_default_voices_dir,
    removed_phonemizer,
    voicebanks_without_character_file,
)
from barbershop_tracks.core.pipeline.errors import ErrorCategory, PipelineError
from barbershop_tracks.core.pipeline.events import EventHandler, Stage, ignore
from barbershop_tracks.core.pipeline.preparation import blocking_details, prepare
from barbershop_tracks.core.pipeline.pronunciation_files import provenance_entries
from barbershop_tracks.core.readiness import RoleAssignments
from barbershop_tracks.core.rendering import (
    CancelToken,
    OpenUtauRenderBackend,
    RenderCancelledError,
    RenderConfigurationError,
    RenderError,
    RenderResult,
    RenderSettings,
    RenderTimeoutError,
    SynthesisError,
)
from barbershop_tracks.core.rendering.engine_detect import detect as detect_engine
from barbershop_tracks.core.rendering.engine_detect import neural_kind
from barbershop_tracks.core.rendering.errors import (
    OutputValidationError,
    ProjectValidationError,
    PronunciationError,
)
from barbershop_tracks.core.runtime import StagingArea, StagingError
from barbershop_tracks.core.runtime.staging import cleanup_stale, remove_staging
from barbershop_tracks.core.runtime.vcruntime import DOWNLOAD_PAGE, runtime_status
from barbershop_tracks.core.synthesis import (
    VOICE_ORDER,
    LyricApproval,
    SourceIdentity,
    SynthesisPlan,
    SynthesisPlanError,
    VoiceEngineRef,
)
from barbershop_tracks.core.synthesis.openutau import (
    NO_OVERRIDES,
    OverrideError,
    PronunciationOverride,
    ResolvedOverrides,
    UstxError,
    resolve_overrides,
    write_ustx,
)
from barbershop_tracks.models import VoiceRole

PACKAGE_SUFFIX = "_learning_tracks"


class Renderer(Protocol):
    def render(
        self,
        plan: SynthesisPlan,
        destination: Path,
        *,
        cancel: CancelToken | None = ...,
        on_event: Callable[[dict[str, Any]], None] | None = ...,
        replace: bool = ...,
        overrides: ResolvedOverrides = ...,
    ) -> RenderResult: ...

    def check_pronunciations(
        self,
        plan: SynthesisPlan,
        overrides: ResolvedOverrides = ...,
        *,
        cancel: CancelToken | None = ...,
        on_event: Callable[[dict[str, Any]], None] | None = ...,
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class Services:
    """The collaborators, replaceable in tests. The defaults are the real implementations."""

    parse: Callable[[Path], ParseResult] = parse_musicxml
    make_renderer: Callable[[RenderSettings], Renderer] = OpenUtauRenderBackend
    make_encoder: Callable[[Path, int], Mp3Encoder] = lambda ffmpeg, quality: FfmpegMp3Encoder(
        [ffmpeg], quality=quality
    )
    package: Callable[..., PackageResult] = build_learning_tracks


@dataclass(frozen=True, slots=True)
class EngineChoice:
    """Singer, phonemizer and renderer per voice; ``per_voice`` overrides ``singer``."""

    singer: str | None
    phonemizer: str
    renderer: str
    per_voice: Mapping[VoiceRole, str] = field(default_factory=dict)
    # nobody chose the pronunciation engine: use the one the voices' own sound names point to
    automatic: bool = False

    def refs(self) -> dict[VoiceRole, VoiceEngineRef]:
        removed = removed_phonemizer(self.phonemizer)
        if removed:
            raise PipelineError(
                ErrorCategory.CONFIGURATION,
                "PHONEMIZER_REMOVED",
                f"the pronunciation engine {self.phonemizer} ({removed}) is not part of this "
                "version "
                "of BLT (it needs a dictionary whose origin could not be verified); use the "
                "default, "
                f"or one of: {', '.join(ENGLISH_PHONEMIZERS)}",
            )
        refs = {}
        for role in VOICE_ORDER:
            singer = self.per_voice.get(role, self.singer)
            if not singer:
                raise PipelineError(
                    ErrorCategory.CONFIGURATION,
                    "SINGER_NOT_CHOSEN",
                    f"no singer was chosen for {role.display_name}; pass --singer ID "
                    "(the voicebank is never picked for you)",
                )
            refs[role] = VoiceEngineRef(
                singer=singer, phonemizer=self.phonemizer, renderer=self.renderer
            )
        return refs


@dataclass(frozen=True, slots=True)
class GenerateRequest:
    score: Path
    output: Path  # the folder that will contain the package folder
    assignments: RoleAssignments
    engine: EngineChoice
    formats: frozenset[AudioFormat] = frozenset({AudioFormat.WAV})
    name: str | None = None
    verse: str | None = None
    approvals: tuple[LyricApproval, ...] = ()
    pronunciations: tuple[PronunciationOverride, ...] = ()  # decided per voice, note and engine
    replace: bool = False
    keep_stems: bool = False
    keep_project: bool = False
    timeout_seconds: float = 900.0
    mp3_quality: int = 2
    follow_lead: bool | None = None  # None: the default (parts sing the Lead's words)
    # a PDF or image of music is read by recognising its notes (which makes mistakes): only when the
    # person has accepted that
    accept_recognition: bool = False
    # a word the dictionary lacks is built from dictionary entries; False: it stops for a person
    compose_unknown_words: bool = True
    # ... and one that cannot is guessed from its spelling (False: it stops for a person)
    guess_by_spelling: bool = True


@dataclass(frozen=True, slots=True)
class GenerateResult:
    destination: Path
    package: PackageResult
    render: RenderResult
    plan: SynthesisPlan
    seconds: float
    warnings: tuple[str, ...]
    pronunciations: tuple[
        dict[str, Any], ...
    ] = ()  # the overrides used, as the package records them


def package_dirname(name: str) -> str:
    return name + PACKAGE_SUFFIX


def translate(error: BaseException) -> PipelineError:
    """Map an underlying failure to a PipelineError (already-translated errors pass through)."""
    if isinstance(error, PipelineError):
        return error
    cat = ErrorCategory
    if isinstance(error, RenderCancelledError | MixCancelledError):
        return PipelineError(cat.CANCELLED, "CANCELLED", error.message)
    if isinstance(error, RenderTimeoutError):
        return PipelineError(cat.TIMEOUT, error.code, error.message, error.details)
    if isinstance(error, OverrideError):
        # a pronunciation a person gave does not fit this score, voice or engine (stale, mismatched,
        # for another phonemizer): the person decides it again; nothing was rendered
        return PipelineError(cat.CONFIGURATION, error.code, error.message)
    if isinstance(error, PronunciationError):
        # the score has a word BLT cannot pronounce: the singer decides (a respelling in the
        # score); BLT never guesses a pronunciation and never drops the syllable
        return PipelineError(cat.SOURCE, error.code, error.message, error.details)
    if isinstance(error, ProjectValidationError):
        return PipelineError(cat.SOURCE, error.code, error.message, error.details)
    if isinstance(error, RenderConfigurationError):
        return PipelineError(cat.CONFIGURATION, error.code, error.message, error.details)
    if isinstance(error, SynthesisError):
        return PipelineError(cat.SYNTHESIS, error.code, error.message, error.details)
    if isinstance(error, OutputValidationError | RenderError):
        return PipelineError(cat.AUDIO, error.code, error.message, error.details)
    if isinstance(error, MixConfigurationError):
        return PipelineError(cat.CONFIGURATION, error.code, error.message, error.details)
    if isinstance(error, MixError):
        timeout = error.code.endswith("TIMEOUT")
        return PipelineError(
            cat.TIMEOUT if timeout else cat.AUDIO, error.code, error.message, error.details
        )
    if isinstance(error, SynthesisPlanError | UstxError):
        return PipelineError(cat.SOURCE, error.code, error.message)
    if isinstance(error, StagingError):
        return PipelineError(cat.CONFIGURATION, error.code, error.message)
    if isinstance(error, ScoreConversionError):
        if error.code == "CONVERSION_CANCELLED":
            return PipelineError(cat.CANCELLED, "CANCELLED", error.message)
        return PipelineError(cat.SOURCE, error.code, error.message, {"tool": error.tool})
    if isinstance(error, ScoreLoadError):
        return PipelineError(cat.SOURCE, "SCORE_LOAD_FAILED", str(error))
    if isinstance(error, OSError):
        return PipelineError(cat.CONFIGURATION, "FILESYSTEM", str(error))
    raise error


class _Run:
    """One generation; keeps the stage bookkeeping out of the main flow."""

    def __init__(self, emit: EventHandler, cancel: CancelToken) -> None:
        self.emit = emit
        self.cancel = cancel

    def stage(self, stage: Stage, status: str, **extra: Any) -> None:
        self.emit({"event": "stage", "stage": stage.value, "status": status, **extra})

    def check(self) -> None:
        if self.cancel.cancelled:
            raise PipelineError(ErrorCategory.CANCELLED, "CANCELLED", "cancelled")


def generate(
    request: GenerateRequest,
    config: ResolvedConfig,
    *,
    services: Services | None = None,
    cancel: CancelToken | None = None,
    on_event: EventHandler = ignore,
) -> GenerateResult:
    """Run the whole pipeline; raises :class:`PipelineError` (nothing else) on any failure."""
    try:
        return _generate(request, config, services or Services(), cancel or CancelToken(), on_event)
    except PipelineError:
        raise
    except BaseException as error:
        if isinstance(error, KeyboardInterrupt):
            raise
        raise translate(error) from error


def _load_plan(
    request: GenerateRequest,
    services: Services,
    run: _Run,
    refs: Mapping[VoiceRole, VoiceEngineRef],
    cache: Path | None = None,
) -> tuple[SynthesisPlan, str]:
    """Read and analyse the score and build the ready plan; returns it with the score's SHA-256.

    A MuseScore project or a PDF is converted first (``core/musicxml/convert.py``); the SHA-256 is
    that of the file the person chose, so approvals and pronunciations stay bound to it.
    """
    # --- source ---
    run.stage(Stage.SOURCE_LOADING, "started")
    try:
        with opened_score(
            request.score,
            accept_recognition=request.accept_recognition,
            cache=cache,
            cancel=run.cancel,
        ) as opened:
            parsed = services.parse(opened.parse_path)
            sha = opened.sha256
            conversion = None if opened.conversion is None else opened.conversion.as_record()
    except OSError as error:
        raise PipelineError(
            ErrorCategory.SOURCE, "SCORE_UNREADABLE", f"cannot read {request.score}: {error}"
        ) from error
    run.stage(Stage.SOURCE_LOADING, "finished")
    run.check()

    run.stage(Stage.SCORE_ANALYSIS, "started")
    if parsed.performed is None or parsed.song is None:
        raise PipelineError(
            ErrorCategory.SOURCE,
            "NO_PERFORMANCE",
            "no performed score could be built from the file",
        )
    run.stage(Stage.SCORE_ANALYSIS, "finished", title=parsed.song.title)

    run.stage(Stage.READINESS_VALIDATION, "started")
    identity = SourceIdentity(
        display_name=request.score.name,
        sha256=sha,
        title=parsed.song.title or None,
        conversion=conversion,
    )
    prepared = prepare(
        parsed,
        request.assignments,
        identity=identity,
        engine_refs=refs,
        verse=request.verse,
        approvals=request.approvals,
        follow_lead=request.follow_lead,
    )
    if prepared.report is not None and not prepared.report.ready:
        raise PipelineError(
            ErrorCategory.SOURCE,
            "SOURCE_NOT_READY",
            f"{len(prepared.report.blocking)} problem(s) in the score or the voice mapping block "
            "generation",
            {"findings": blocking_details(prepared.report)},
        )
    assert prepared.plan is not None
    plan = prepared.plan
    if prepared.review is not None:
        raise PipelineError(
            ErrorCategory.REVIEW,
            "LYRICS_NEED_REVIEW",
            f"{len(plan.review_items)} note(s) have no decided lyric; nothing is guessed (a part "
            "sings the Lead's words only where the Lead is singing at that moment)",
            {"review": prepared.review},
        )
    run.stage(Stage.READINESS_VALIDATION, "finished")
    run.check()

    return plan, sha


def _require_environment(
    config: ResolvedConfig, run: _Run, refs: Mapping[VoiceRole, VoiceEngineRef]
) -> None:
    """The runtime, the voicebanks and the render host the run needs; raises PipelineError."""
    # --- the Microsoft runtime the native parts need (BLT does not ship it) ---
    runtime = runtime_status()
    if not runtime.ok:
        raise PipelineError(
            ErrorCategory.CONFIGURATION,
            "VC_RUNTIME_MISSING",
            f"the Microsoft Visual C++ runtime is {runtime.text}; install Microsoft's "
            f"'Visual C++ Redistributable' (x64) from {DOWNLOAD_PAGE} and try again",
        )

    # --- voicebank ---
    run.stage(Stage.VOICEBANK_DISCOVERY, "started")
    singers_dir = config.singers_dir
    ensure_default_voices_dir(singers_dir)
    if singers_dir is None or not singers_dir.is_dir():
        raise PipelineError(
            ErrorCategory.CONFIGURATION,
            "SINGERS_DIR_MISSING",
            f"the voices folder {singers_dir or '(none)'} does not exist; pass --singers-dir or "
            f"set BLT_SINGERS_DIR, or put your voicebanks in {default_voices_dir()} "
            "(OpenUtau itself is not needed)",
        )
    available = discover_singers(singers_dir)
    wanted = sorted({ref.singer for ref in refs.values()})
    absent = [w for w in wanted if w not in available]
    if absent:
        raise PipelineError(
            ErrorCategory.CONFIGURATION,
            "SINGER_NOT_FOUND",
            f"singer(s) {absent} not found in the singers folder; installed: "
            f"{sorted(available)[:20] or 'none'}" + _singer_hints(singers_dir, absent, available),
            {"installed": sorted(available)},
        )
    for name in wanted:
        kind = neural_kind(singers_dir / name)
        if kind is not None:
            raise PipelineError(
                ErrorCategory.CONFIGURATION,
                "SINGER_KIND_UNSUPPORTED",
                f"'{name}' is a {kind} voicebank; BLT renders UTAU-style voicebanks (recordings "
                "named in an oto.ini) only, so every note would be silent. Choose another voice",
            )
    run.stage(Stage.VOICEBANK_DISCOVERY, "finished", installed=len(available))
    run.check()
    if config.host_binaries is None:
        raise PipelineError(
            ErrorCategory.CONFIGURATION,
            "HOST_NOT_FOUND",
            "the render host was not found; pass --host-dir or set BLT_HOST_DIR",
        )


def _singer_hints(singers_dir: Path, absent: list[str], available: set[str]) -> str:
    """What to tell the person about a voicebank that is there but not under the name used."""
    unseen = voicebanks_without_character_file(singers_dir)
    said: list[str] = []
    for name in absent:
        if name in unseen:
            said.append(
                f"'{name}' has no character.txt, so the singing engine does not list it as a "
                "voicebank; add a text file named character.txt to that folder with one line, "
                f"name={name.rsplit(chr(92), 1)[-1]}"
            )
            continue
        nested = sorted(a for a in available if a.lower().endswith(chr(92) + name.lower()))
        if nested:
            said.append(f"'{name}' is inside a folder; its name is '{nested[0]}'")
    return "".join(f". {line}" for line in said)


def _matching_engine(
    request: GenerateRequest, config: ResolvedConfig
) -> tuple[GenerateRequest, str | None]:
    """The request with the engine the voices were made for, when nobody chose one.

    Read from the names of the voices' sounds (``core/rendering/engine_detect.py``); used only when
    every voice points to the same engine. Returns the notice to show the person, or None.
    """
    choice = request.engine
    if not choice.automatic or config.singers_dir is None:
        return request, None
    singers = {choice.per_voice.get(role, choice.singer) for role in VOICE_ORDER}
    found = {s: detect_engine(config.singers_dir / s) for s in singers if s}
    detections = {d.phonemizer: d for d in found.values() if d is not None}
    if not found or None in found.values() or len(detections) != 1:
        return request, None
    detected = next(iter(detections.values()))
    if detected.phonemizer == choice.phonemizer:
        return request, None
    notice = (
        f"the voice's sounds are made for {detected.phonemizer.rsplit('.', 1)[-1]} "
        f"({detected.why}), so that pronunciation engine is used; "
        "choose another one in Advanced to change it"
    )
    engine = dataclasses.replace(choice, phonemizer=detected.phonemizer)
    return dataclasses.replace(request, engine=engine), notice


def check_pronunciations(
    request: GenerateRequest,
    config: ResolvedConfig,
    *,
    services: Services | None = None,
    cancel: CancelToken | None = None,
    on_event: EventHandler = ignore,
) -> dict[str, Any]:
    """Phonemize the score with the real engine and stop: nothing is rendered or published.

    Everything up to the engine is exactly what ``generate`` does (the score, the voice mapping,
    the lyric decisions, the pronunciations given), so this says, before a long render, whether the
    words and the pronunciations will be accepted. Raises :class:`PipelineError`: a word the
    dictionary lacks is ``PRONUNCIATION_UNKNOWN``, a pronunciation the engine refuses is
    ``PRONUNCIATION_INVALID`` (each placed in the score), a pronunciation that no longer fits the
    score is ``OVERRIDE_*``. Returns the engine's report (``pronunciations``: the sounds it made
    of each pronunciation given).
    """
    try:
        return _check(request, config, services or Services(), cancel or CancelToken(), on_event)
    except PipelineError:
        raise
    except BaseException as error:
        if isinstance(error, KeyboardInterrupt):
            raise
        raise translate(error) from error


def _check(
    request: GenerateRequest,
    config: ResolvedConfig,
    services: Services,
    cancel: CancelToken,
    emit: EventHandler,
) -> dict[str, Any]:
    run = _Run(emit, cancel)
    request, notice = _matching_engine(request, config)
    if notice is not None:
        emit({"event": "warning", "code": "ENGINE_AUTO", "message": notice})
    refs = request.engine.refs()
    plan, sha = _load_plan(request, services, run, refs, config.layout.cache / "converted")
    resolved = resolve_overrides(plan, request.pronunciations, source_sha256=sha)
    write_ustx(plan, overrides=resolved)  # refuses anything OpenUtau could not hold faithfully
    _require_environment(config, run, refs)
    settings = RenderSettings(
        layout=config.layout,
        singers_dir=config.singers_dir or Path(),
        host_binaries=config.host_binaries,
        extra_env=config.host_environment(),
        timeout_seconds=request.timeout_seconds,
        compose_unknown_words=request.compose_unknown_words,
        guess_by_spelling=request.guess_by_spelling,
    )
    renderer = services.make_renderer(settings)
    result = renderer.check_pronunciations(plan, resolved, cancel=cancel, on_event=emit)
    return dict(result)


def _generate(
    request: GenerateRequest,
    config: ResolvedConfig,
    services: Services,
    cancel: CancelToken,
    emit: EventHandler,
) -> GenerateResult:
    run = _Run(emit, cancel)
    started = time.monotonic()
    warnings: list[str] = []
    request, notice = _matching_engine(request, config)
    if notice is not None:
        warnings.append(f"ENGINE_AUTO: {notice}")
        run.emit({"event": "warning", "code": "ENGINE_AUTO", "message": notice})
    refs = request.engine.refs()  # an unchosen singer is reported before any work

    # --- the output location, checked up front (publication re-checks it atomically) ---
    try:
        base = sanitize_name(request.name if request.name is not None else request.score.stem)
    except HandoffError as error:
        raise PipelineError(ErrorCategory.CONFIGURATION, error.code, error.message) from error
    destination = request.output / package_dirname(base)
    if destination.exists():
        if not request.replace:
            raise PipelineError(
                ErrorCategory.CONFIGURATION,
                "OUTPUT_EXISTS",
                f"{destination.name} already exists in the output folder; use --replace to "
                "replace a previous package",
            )
        if not is_our_package(destination):
            raise PipelineError(
                ErrorCategory.CONFIGURATION,
                "OUTPUT_FOREIGN",
                f"{destination.name} exists but is not a learning-track package; it will not be "
                "replaced",
            )
    if AudioFormat.MP3 in request.formats and config.ffmpeg is None:
        raise PipelineError(
            ErrorCategory.CONFIGURATION,
            "FFMPEG_NOT_CONFIGURED",
            "MP3 output needs FFmpeg: pass --ffmpeg PATH, set BLT_FFMPEG, or put ffmpeg on PATH",
        )

    plan, sha = _load_plan(request, services, run, refs, config.layout.cache / "converted")

    run.stage(Stage.USTX_PREPARATION, "started")
    # every pronunciation a person gave must belong to this score, voice, note, word and engine
    resolved = resolve_overrides(plan, request.pronunciations, source_sha256=sha)
    document_ustx = write_ustx(plan, overrides=resolved)  # refuses what OpenUtau could not hold
    for warning in document_ustx.warnings:
        warnings.append(f"{warning.code}: {warning.message}")
        run.emit({"event": "warning", "code": warning.code, "message": warning.message})
    run.stage(Stage.USTX_PREPARATION, "finished", notes=document_ustx.note_count)

    _require_environment(config, run, refs)

    # --- everything below runs inside a job-scoped working directory ---
    layout = config.layout
    try:
        cleanup_stale(layout.staging)
        area = StagingArea.create(layout.staging, "job-" + uuid.uuid4().hex[:10])
    except (StagingError, OSError) as error:
        raise PipelineError(
            ErrorCategory.CONFIGURATION,
            "STAGING_UNAVAILABLE",
            f"cannot create a working directory: {error}",
        ) from error
    try:
        return _render_and_mix(
            request,
            config,
            services,
            run,
            plan,
            document_ustx.text,
            destination,
            area,
            warnings,
            started,
            resolved,
        )
    finally:
        try:
            remove_staging(area.path)
        except OSError:
            shutil.rmtree(area.path, ignore_errors=True)


def _render_and_mix(
    request: GenerateRequest,
    config: ResolvedConfig,
    services: Services,
    run: _Run,
    plan: SynthesisPlan,
    ustx_text: str,
    destination: Path,
    area: StagingArea,
    warnings: list[str],
    started: float,
    resolved: ResolvedOverrides = NO_OVERRIDES,
) -> GenerateResult:
    settings = RenderSettings(
        layout=config.layout,
        singers_dir=config.singers_dir or Path(),
        host_binaries=config.host_binaries,
        extra_env=config.host_environment(),
        timeout_seconds=request.timeout_seconds,
        compose_unknown_words=request.compose_unknown_words,
        guess_by_spelling=request.guess_by_spelling,
    )
    renderer = services.make_renderer(settings)
    stems_destination = area.path / "stems"

    def on_render_event(event: dict[str, Any]) -> None:
        if event.get("event") == "blt_stage":
            stage = Stage(event["stage"])
            run.stage(stage, str(event["status"]))
        else:
            run.emit(
                {
                    "event": "host",
                    **{k: v for k, v in event.items() if k != "event"},
                    "kind": event.get("event"),
                }
            )

    run.stage(Stage.STEM_RENDERING, "started")
    rendered = renderer.render(
        plan, stems_destination, cancel=run.cancel, on_event=on_render_event, overrides=resolved
    )
    pronunciations = provenance_entries(plan, resolved, rendered.host_result)
    built: dict[tuple[str, str, str, str], list[str]] = {}
    for entry in pronunciations:
        if entry["source"] in ("composed", "guessed"):
            key = (entry["source"], entry["word"], entry["where"], entry["composed_how"])
            built.setdefault(key, []).append(str(entry["voice"]).capitalize())
    for (source, word, where, how), voices in built.items():
        code = "PRONUNCIATION_GUESSED" if source == "guessed" else "PRONUNCIATION_COMPOSED"
        message = (
            f"{word!r} ({where}; {', '.join(voices)}) is not in the pronunciation dictionary; "
            f"it was {how} (listen to it; the score is unchanged)"
        )
        warnings.append(f"{code}: {message}")
        run.emit({"event": "warning", "code": code, "message": message})
    run.stage(Stage.STEM_RENDERING, "finished")
    run.check()

    mp3: Mp3Encoder | None = None
    if AudioFormat.MP3 in request.formats:
        assert config.ffmpeg is not None
        mp3 = services.make_encoder(config.ffmpeg, request.mp3_quality)
    extras: dict[str, Path] = {}
    if request.keep_stems:
        for report in rendered.stems.values():
            extras[f"stems/{report.path.name}"] = report.path
    if request.keep_project:
        project = area.path / "project.ustx"
        project.write_text(rendered.project_text or ustx_text, encoding="utf-8", newline="\n")
        extras["project/project.ustx"] = project

    def on_package_event(event: dict[str, Any]) -> None:
        kind = event.get("event")
        if kind == "mix":
            run.emit(
                {
                    "event": "progress",
                    "stage": Stage.MIXING.value,
                    "completed": event["number"],
                    "total": event["of"],
                    "mix": event["id"],
                }
            )
        elif kind == "mp3":
            run.emit(
                {
                    "event": "progress",
                    "stage": Stage.MP3_ENCODING.value,
                    "completed": event["number"],
                    "total": event["of"],
                }
            )
        elif kind == "publish":
            run.stage(Stage.PACKAGE_PUBLICATION, str(event["status"]))

    run.stage(Stage.MIXING, "started")
    if mp3 is not None:
        run.stage(Stage.MP3_ENCODING, "started")
    package = services.package(
        PackageSource.from_plan(plan, pronunciations=pronunciations),
        stems_from_render(rendered),
        destination,
        PackageSettings(
            layout=config.layout,
            formats=request.formats,
            profile=config.gain_profile,
            mp3=mp3,
        ),
        cancel=run.cancel,
        on_progress=on_package_event,
        replace=request.replace,
        extras=extras,
    )
    if mp3 is not None:
        run.stage(Stage.MP3_ENCODING, "finished")
    run.stage(Stage.MIXING, "finished")
    return GenerateResult(
        destination=destination,
        package=package,
        render=rendered,
        plan=plan,
        seconds=time.monotonic() - started,
        warnings=tuple(warnings),
        pronunciations=tuple(pronunciations),
    )


__all__ = [
    "EngineChoice",
    "GenerateRequest",
    "GenerateResult",
    "Renderer",
    "Services",
    "check_pronunciations",
    "generate",
    "package_dirname",
    "translate",
]
