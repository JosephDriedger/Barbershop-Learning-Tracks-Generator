"""The application's behaviour, without widgets.

``AppController`` owns the state of one working session (the loaded score, the user's explicit
voice assignments and singer choices, lyric approvals, output options), runs the slow parts on
background threads, and calls the M10 pipeline for everything musical: ``generate`` does the work,
``prepare`` previews the same readiness and lyric review while the user is still choosing. It
emits Qt signals; the main window only displays them. Everything the user must decide stays
undecided until they decide it: no tempo, meter, lyric, voice assignment or singer is invented.
"""

import hashlib
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from barbershop_tracks.core.handoff import HandoffError, sanitize_name
from barbershop_tracks.core.mixing import (
    PRESETS,
    AudioFormat,
    GainProfile,
    MixConfigurationError,
)
from barbershop_tracks.core.musicxml import ParseResult, parse_musicxml
from barbershop_tracks.core.pipeline import (
    DEFAULT_PHONEMIZER,
    DEFAULT_RENDERER,
    EngineChoice,
    ErrorCategory,
    GenerateRequest,
    GenerateResult,
    PipelineError,
    Preparation,
    ResolvedConfig,
    config_path,
    discover_singers,
    generate,
    load_config_file,
    package_dirname,
    prepare,
    resolve_config,
)
from barbershop_tracks.core.pipeline.coordinator import translate
from barbershop_tracks.core.readiness.lines import LineInfo, describe_lines
from barbershop_tracks.core.rendering import CancelToken
from barbershop_tracks.core.synthesis import (
    VOICE_ORDER,
    LyricApproval,
    SourceIdentity,
    SynthesisPlan,
    VoiceEngineRef,
)
from barbershop_tracks.models import VoiceRole
from barbershop_tracks.ui.assignments import AssignmentState, Choice
from barbershop_tracks.ui.background import Dispatcher
from barbershop_tracks.ui.lyric_review import LyricReviewState
from barbershop_tracks.ui.preferences import Preferences

GenerateFn = Callable[..., GenerateResult]
ParseFn = Callable[[Path], ParseResult]


@dataclass(frozen=True, slots=True)
class LoadedScore:
    path: Path
    sha256: str
    title: str
    parsed: ParseResult
    lines: tuple[LineInfo, ...]
    problems: tuple[str, ...]  # readable parse problems (errors only)


@dataclass(frozen=True, slots=True)
class Message:
    severity: str  # "error", "warning" or "info"
    text: str


@dataclass(frozen=True, slots=True)
class ValidationView:
    """What the preview found, in terms the window can show."""

    messages: tuple[Message, ...]
    source_ready: bool
    baseline: SynthesisPlan | None  # the plan with no approvals: the rows of the lyric review
    effective: SynthesisPlan | None  # the plan with the current approvals
    unresolved: int  # notes still without a decided lyric
    technical: str = ""

    @property
    def generatable(self) -> bool:
        return self.effective is not None and self.effective.is_ready


@dataclass(frozen=True, slots=True)
class OutputOptions:
    name: str = ""
    audio_format: str = "wav"
    gain_preset: str = "default"
    custom_focus: float = 0.5
    custom_others: float = 0.15
    mp3_quality: int = 2
    keep_stems: bool = False
    keep_project: bool = False
    replace: bool = False


class AppController(QObject):
    score_loaded = Signal(object)  # LoadedScore
    score_failed = Signal(object)  # Explanation-ready PipelineError
    state_changed = Signal()  # anything the window displays may have changed
    validation_changed = Signal(object)  # ValidationView
    voices_changed = Signal(object)  # list[str]
    generation_started = Signal()
    generation_event = Signal(object)  # dict
    generation_finished = Signal(object)  # GenerateResult
    generation_failed = Signal(object)  # PipelineError

    def __init__(
        self,
        prefs: Preferences,
        *,
        dispatcher: Dispatcher | None = None,
        generate_fn: GenerateFn = generate,
        parse_fn: ParseFn = parse_musicxml,
        environ: Mapping[str, str] | None = None,
        config_file: Path | None = None,
        debounce_ms: int = 150,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.prefs = prefs
        self.dispatcher = dispatcher or Dispatcher(self)
        self._generate = generate_fn
        self._parse = parse_fn
        self._environ = dict(os.environ if environ is None else environ)
        self._config_file = config_file
        self.score: LoadedScore | None = None
        self.assignments: AssignmentState | None = None
        self.singers: dict[VoiceRole, str] = {r: prefs.singer(r) for r in VOICE_ORDER}
        self.installed: list[str] | None = None  # None until the voices folder was scanned
        self.review: LyricReviewState | None = None
        self.approvals: tuple[LyricApproval, ...] = ()
        self.validation: ValidationView | None = None
        self.validating = False
        self.loading = False
        self.running = False
        self.token: CancelToken | None = None
        self.started_at = 0.0
        self.last_result: GenerateResult | None = None
        self._validation_serial = 0
        self._remembered: dict[str, dict[str, Choice]] = {}
        self.options = OutputOptions(
            audio_format=prefs.audio_format,
            gain_preset=prefs.gain_preset,
            custom_focus=prefs.custom_focus,
            custom_others=prefs.custom_others,
            mp3_quality=prefs.mp3_quality,
            keep_stems=prefs.keep_stems,
            keep_project=prefs.keep_project,
        )
        self.output_dir = prefs.output_dir
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(debounce_ms)
        self._debounce.timeout.connect(self.validate_now)

    # --- configuration ---------------------------------------------------------------------

    def config(self) -> ResolvedConfig:
        """The pipeline's configuration: preferences on top of environment and config file."""
        prefs = self.prefs
        file_values = load_config_file(self._config_file or config_path(self._environ))
        resolved = resolve_config(
            file_values,
            overrides={
                "singers_dir": prefs.singers_dir,
                "ffmpeg": prefs.ffmpeg_path,
                "host_dir": prefs.host_dir,
                "dotnet_root": prefs.dotnet_root,
                "phonemizer": prefs.phonemizer,
                "renderer": prefs.renderer,
            },
            environ=self._environ,
        )
        try:
            profile = self.gain_profile()
        except MixConfigurationError:
            profile = resolved.gain_profile  # reported by gain_problem(); generation is blocked
        return replace(resolved, gain_profile=profile)

    def gain_profile(self) -> GainProfile:
        options = self.options
        if options.gain_preset == "custom":
            return GainProfile(
                name="custom",
                predominant_focus=options.custom_focus,
                predominant_others=options.custom_others,
            )
        return PRESETS[options.gain_preset]

    def gain_problem(self) -> str | None:
        try:
            self.gain_profile()
        except MixConfigurationError as error:
            return error.message
        return None

    def singers_folder(self) -> Path | None:
        try:
            return self.config().singers_dir
        except PipelineError:
            return None

    # --- score -----------------------------------------------------------------------------

    def load_score(self, path: Path) -> None:
        self.loading = True
        self.state_changed.emit()

        def work(_emit: Callable[[dict[str, Any]], None]) -> LoadedScore:
            try:
                data = path.read_bytes()
            except OSError as error:
                raise PipelineError(
                    ErrorCategory.SOURCE, "SCORE_UNREADABLE", f"cannot read {path.name}: {error}"
                ) from error
            try:
                parsed = self._parse(path)
            except BaseException as error:
                raise translate(error) from error
            if parsed.song is None:
                raise PipelineError(
                    ErrorCategory.SOURCE, "SCORE_LOAD_FAILED", "no music was found in this file"
                )
            problems = tuple(issue.message for issue in parsed.issues.errors)
            return LoadedScore(
                path=path,
                sha256=hashlib.sha256(data).hexdigest(),
                title=parsed.song.title or path.stem,
                parsed=parsed,
                lines=describe_lines(parsed),
                problems=problems,
            )

        self.dispatcher.submit(work, self._score_ready, self._score_failed)

    def _score_ready(self, score: LoadedScore) -> None:
        self.loading = False
        previous = self.score
        if previous is not None and self.assignments is not None:
            self._remembered[previous.sha256] = self.assignments.snapshot()
        self.score = score
        self.assignments = AssignmentState(score.lines)
        saved = self._remembered.get(score.sha256)
        if saved:  # the same score opened again in this session keeps the user's choices
            self.assignments.restore(saved, [info.line_id for info in score.lines])
        self.review = None
        self.approvals = ()
        self.validation = None
        self.last_result = None
        self.options = replace(self.options, name="", replace=False)
        self.prefs.last_score_dir = str(score.path.parent)
        self.score_loaded.emit(score)
        self.state_changed.emit()
        self.schedule_validation()

    def _score_failed(self, error: BaseException) -> None:
        self.loading = False
        self.score_failed.emit(translate(error))
        self.state_changed.emit()

    # --- assignments -----------------------------------------------------------------------

    def set_choice(self, line_id: str, choice: Choice) -> bool:
        if self.assignments is None or not self.assignments.set_choice(line_id, choice):
            return False
        self._assignments_changed()
        return True

    def suggest(self) -> int:
        if self.assignments is None:
            return 0
        count = self.assignments.suggest()
        self._assignments_changed()
        return count

    def confirm_suggestions(self) -> None:
        if self.assignments is not None:
            self.assignments.confirm_suggestions()
            self._assignments_changed()

    def _assignments_changed(self) -> None:
        # approvals belong to a particular mapping of lines to voices: start the review afresh
        self.review = None
        self.approvals = ()
        self.state_changed.emit()
        self.schedule_validation()

    # --- singers ---------------------------------------------------------------------------

    def set_singer(self, role: VoiceRole, singer: str) -> None:
        self.singers[role] = singer
        self.prefs.set_singer(role, singer)
        self.state_changed.emit()

    def use_same_singer(self, singer: str) -> None:
        for role in VOICE_ORDER:
            self.set_singer(role, singer)

    def refresh_voices(self) -> None:
        folder = self.singers_folder()

        def work(_emit: Callable[[dict[str, Any]], None]) -> list[str]:
            if folder is None or not folder.is_dir():
                return []
            return sorted(discover_singers(folder), key=str.lower)

        self.dispatcher.submit(work, self._voices_ready, lambda error: self._voices_ready([]))

    def _voices_ready(self, names: list[str]) -> None:
        self.installed = names
        self.voices_changed.emit(names)
        self.state_changed.emit()

    def singer_problem(self, role: VoiceRole) -> str | None:
        singer = self.singers.get(role, "")
        if not singer:
            return f"Choose a singing voice for {role.display_name}."
        if self.installed is not None and singer not in self.installed:
            return f"The voice “{singer}” for {role.display_name} is not installed."
        return None

    # --- output ----------------------------------------------------------------------------

    def set_options(self, **changes: Any) -> None:
        self.options = replace(self.options, **changes)
        prefs, options = self.prefs, self.options
        prefs.audio_format = options.audio_format
        prefs.gain_preset = options.gain_preset
        prefs.custom_focus = options.custom_focus
        prefs.custom_others = options.custom_others
        prefs.mp3_quality = options.mp3_quality
        prefs.keep_stems = options.keep_stems
        prefs.keep_project = options.keep_project
        self.state_changed.emit()

    def set_output_dir(self, folder: str) -> None:
        self.output_dir = folder
        self.prefs.output_dir = folder
        self.state_changed.emit()

    def package_name(self) -> str | None:
        """The folder name the package will get, or ``None`` if the name is unusable."""
        if self.score is None:
            return None
        text = self.options.name.strip() or self.score.path.stem
        try:
            return package_dirname(sanitize_name(text))
        except HandoffError:
            return None

    def expected_location(self) -> Path | None:
        name = self.package_name()
        if not self.output_dir or name is None:
            return None
        return Path(self.output_dir) / name

    def existing_package(self) -> bool:
        location = self.expected_location()
        return location is not None and location.exists()

    # --- validation preview ----------------------------------------------------------------

    def schedule_validation(self) -> None:
        self.validating = True
        self._debounce.start()
        self.state_changed.emit()

    def validate_now(self) -> None:
        self._debounce.stop()
        score, assign = self.score, self.assignments
        if score is None or assign is None:
            self.validating = False
            return
        if not assign.complete:
            self.validating = False
            self.validation = None
            self.validation_changed.emit(None)
            self.state_changed.emit()
            return
        self._validation_serial += 1
        serial = self._validation_serial
        approvals = self.approvals
        assignments = assign.to_role_assignments()
        try:
            config = self.config()
        except PipelineError as problem:
            self.validating = False
            self.validation = ValidationView(
                (Message("error", problem.message),), False, None, None, 0, str(problem)
            )
            self.validation_changed.emit(self.validation)
            self.state_changed.emit()
            return
        identity = SourceIdentity(
            display_name=score.path.name, sha256=score.sha256, title=score.title or None
        )
        # placeholders only: the preview checks the music, not the singer
        refs = {
            role: VoiceEngineRef(
                singer="(not chosen yet)", phonemizer=config.phonemizer, renderer=config.renderer
            )
            for role in VOICE_ORDER
        }

        def work(_emit: Callable[[dict[str, Any]], None]) -> ValidationView:
            def run(given: tuple[LyricApproval, ...]) -> Preparation:
                return prepare(
                    score.parsed, assignments, identity=identity, engine_refs=refs, approvals=given
                )

            effective = run(approvals)
            baseline = effective if not approvals else run(())
            return _view(effective, baseline)

        def done(view: ValidationView) -> None:
            if serial != self._validation_serial:
                return  # a newer check is on its way
            self.validating = False
            self.validation = view
            if view.baseline is not None and self.review is None and view.baseline.review_items:
                self.review = LyricReviewState(view.baseline)
            self.validation_changed.emit(view)
            self.state_changed.emit()

        def failed(error: BaseException) -> None:
            if serial != self._validation_serial:
                return
            self.validating = False
            problem = translate(error)
            self.validation = ValidationView(
                (Message("error", problem.message),), False, None, None, 0, str(problem)
            )
            self.validation_changed.emit(self.validation)
            self.state_changed.emit()

        self.dispatcher.submit(work, done, failed)

    def set_approvals(self, approvals: tuple[LyricApproval, ...]) -> None:
        self.approvals = approvals
        self.schedule_validation()

    # --- readiness for the Generate button -------------------------------------------------

    def blockers(self) -> list[str]:
        out: list[str] = []
        if self.running:
            return ["A generation is already running."]
        if self.loading:
            return ["The score is still loading."]
        if self.score is None:
            return ["Choose a score first."]
        assign = self.assignments
        if assign is not None:
            out.extend(assign.problems())
        if self.validating:
            out.append("Checking the score…")
        elif self.validation is not None:
            if not self.validation.source_ready:
                out.append("The score needs attention (see Lyrics and Validation).")
            elif self.validation.unresolved:
                n = self.validation.unresolved
                out.append(
                    f"{n} note{'s' if n != 1 else ''} still need{'' if n != 1 else 's'} a lyric."
                )
        for role in VOICE_ORDER:
            problem = self.singer_problem(role)
            if problem:
                out.append(problem)
        if not self.output_dir:
            out.append("Choose an output folder.")
        if self.package_name() is None:
            out.append("The package name cannot be used as a folder name.")
        problem = self.gain_problem()
        if problem:
            out.append(problem)
        if self.existing_package() and not self.options.replace:
            out.append("A package with this name already exists: tick “Replace” or rename it.")
        if self.options.audio_format != "wav":
            ffmpeg = self.ffmpeg_path()
            if ffmpeg is None:
                out.append("MP3 needs FFmpeg: choose its location, or pick WAV only.")
        return out

    def ffmpeg_path(self) -> Path | None:
        try:
            config = self.config()
        except PipelineError:
            return None
        ffmpeg = config.ffmpeg
        return ffmpeg if ffmpeg is not None and ffmpeg.is_file() else None

    @property
    def can_generate(self) -> bool:
        return not self.blockers()

    # --- generation ------------------------------------------------------------------------

    def build_request(self) -> GenerateRequest:
        assert self.score is not None
        assert self.assignments is not None
        options = self.options
        config = self.config()
        formats = {
            "wav": frozenset({AudioFormat.WAV}),
            "mp3": frozenset({AudioFormat.MP3}),
            "both": frozenset({AudioFormat.WAV, AudioFormat.MP3}),
        }[options.audio_format]
        name = options.name.strip() or None
        return GenerateRequest(
            score=self.score.path,
            output=Path(self.output_dir),
            assignments=self.assignments.to_role_assignments(),
            engine=EngineChoice(
                singer=None,
                phonemizer=config.phonemizer or DEFAULT_PHONEMIZER,
                renderer=config.renderer or DEFAULT_RENDERER,
                per_voice={role: self.singers[role] for role in VOICE_ORDER},
            ),
            formats=formats,
            name=name,
            approvals=self.approvals,
            replace=options.replace,
            keep_stems=options.keep_stems,
            keep_project=options.keep_project,
            timeout_seconds=float(self.prefs.timeout_minutes * 60),
            mp3_quality=options.mp3_quality,
        )

    def start_generation(self) -> bool:
        """Start in the background; refuses (returns False) if anything still blocks it."""
        if self.running or self.blockers():
            return False
        request = self.build_request()
        config = self.config()
        token = CancelToken()
        self.token = token
        self.running = True
        self.last_result = None
        self.started_at = time.monotonic()
        self.generation_started.emit()
        self.state_changed.emit()

        def work(emit: Callable[[dict[str, Any]], None]) -> GenerateResult:
            return self._generate(request, config, cancel=token, on_event=emit)

        self.dispatcher.submit(
            work, self._generation_done, self._generation_failed, on_event=self._generation_event
        )
        return True

    def _generation_event(self, event: dict[str, Any]) -> None:
        self.generation_event.emit(event)

    def _generation_done(self, result: GenerateResult) -> None:
        self.running = False
        self.token = None
        self.last_result = result
        self.generation_finished.emit(result)
        self.state_changed.emit()

    def _generation_failed(self, error: BaseException) -> None:
        self.running = False
        self.token = None
        self.generation_failed.emit(translate(error))
        self.state_changed.emit()

    def cancel_generation(self) -> None:
        if self.token is not None:
            self.token.cancel()

    def shutdown(self, milliseconds: int = 15_000) -> None:
        self.cancel_generation()
        self.dispatcher.wait(milliseconds)
        self.prefs.sync()


def _view(effective: Preparation, baseline: Preparation) -> ValidationView:
    messages: list[Message] = []
    report = effective.report
    if report is None:
        messages.append(Message("error", "No music could be read from this score."))
        return ValidationView(tuple(messages), False, None, None, 0)
    technical = []
    for finding in report.findings:
        text = finding.issue.message
        technical.append(f"{finding.code}: {text}")
        if finding.disposition.value == "blocking":
            messages.append(Message("error", text))
        elif finding.disposition.value == "advisory":
            messages.append(Message("warning", text))
    unresolved = 0 if effective.plan is None else len(effective.plan.review_items)
    return ValidationView(
        tuple(messages),
        report.ready,
        baseline.plan,
        effective.plan,
        unresolved,
        "\n".join(technical),
    )


__all__ = ["AppController", "LoadedScore", "Message", "OutputOptions", "ValidationView"]
