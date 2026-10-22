"""The application's behaviour, without widgets.

``AppController`` owns the state of one working session (the loaded score, the user's explicit
voice assignments and singer choices, lyric approvals, output options), runs the slow parts on
background threads, and calls the M10 pipeline for everything musical: ``generate`` does the work,
``prepare`` previews the same readiness and lyric review while the user is still choosing. It
emits Qt signals; the main window only displays them. Everything the user must decide stays
undecided until they decide it: no tempo, meter, lyric, voice assignment or singer is invented.
"""

import os
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from barbershop_tracks.core.handoff import HandoffError, sanitize_name
from barbershop_tracks.core.melody import MelodyError, MelodyMark, MelodySection, melody_of
from barbershop_tracks.core.mixing import (
    PRESETS,
    AudioFormat,
    GainProfile,
    MixConfigurationError,
)
from barbershop_tracks.core.musicxml import ParseResult, opened_score, parse_musicxml
from barbershop_tracks.core.musicxml.fixing import editable_copy
from barbershop_tracks.core.musicxml.opened import parse_opened
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
    check_pronunciations,
    config_path,
    default_follow_lead,
    discover_singers,
    ensure_default_voices_dir,
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
from barbershop_tracks.core.synthesis.openutau import PronunciationOverride
from barbershop_tracks.core.voices import Installed, VoiceInstallError, install_voicebank
from barbershop_tracks.models import VoiceRole
from barbershop_tracks.ui.assignments import AssignmentState, Choice
from barbershop_tracks.ui.background import Dispatcher
from barbershop_tracks.ui.formatting import sentence
from barbershop_tracks.ui.lyric_review import FOLLOWING_STATES, LyricReviewState, has_rows
from barbershop_tracks.ui.preferences import Preferences
from barbershop_tracks.ui.pronunciation_review import PronunciationState

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
    # how it came from a file that is not MusicXML (MuseScore project, recognised PDF), or None
    conversion: dict[str, Any] | None = None
    accepted_recognition: bool = False  # the person accepted a recognised score
    converted_path: Path | None = None  # the MusicXML BLT read, when it converted the file first


@dataclass(frozen=True, slots=True)
class FixTarget:
    """What to put in front of a person who wants to correct the score."""

    path: Path  # the file to open: an editable score, or the picture itself if nothing was read
    compare_with: Path | None  # the original picture of a recognised score, to check it against
    recognised: bool  # the file is music recognised from a picture


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
    following: int = 0  # notes that sing the Lead's words by the barbershop convention

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
    tune_up: bool = False  # a note to tune to before the music
    count_in: bool = False  # a bar of metronome clicks before the music
    tune_up_minor: bool = False  # the tune-up note is the minor key's tonic, not the major's
    follow_melody: bool = True  # the Full Quartet makes the voice with the melody louder
    replace: bool = False


class AppController(QObject):
    score_loaded = Signal(object)  # LoadedScore
    score_failed = Signal(object)  # Explanation-ready PipelineError
    state_changed = Signal()  # anything the window displays may have changed
    validation_changed = Signal(object)  # ValidationView
    voices_changed = Signal(object)  # list[str]
    voice_added = Signal(object)  # list[Installed]
    voice_add_failed = Signal(str)
    generation_started = Signal()
    generation_event = Signal(object)  # dict
    generation_finished = Signal(object)  # GenerateResult
    generation_failed = Signal(object)  # PipelineError
    pronunciation_checked = Signal(object)  # dict (the engine's report) or PipelineError

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
        self.adding_voice = False
        self.review: LyricReviewState | None = None
        self.approvals: tuple[LyricApproval, ...] = ()
        # bars a person marked as having the melody in a part other than the one the words say
        self.melody_marks: tuple[MelodyMark, ...] = ()
        # the words the dictionary lacks (learned when a run stops at them) and what is decided
        self.pronunciation: PronunciationState | None = None
        self.checking = False
        self.validation: ValidationView | None = None
        self.validating = False
        self.loading = False
        self.last_attempt: Path | None = None  # the file most recently chosen, read or not
        self.failed: Path | None = None  # set while the most recent attempt could not be read
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
            tune_up=prefs.tune_up,
            count_in=prefs.count_in,
            tune_up_minor=prefs.tune_up_minor,
            follow_melody=prefs.follow_melody,
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

    def converted_cache(self) -> Path | None:
        try:
            return self.config().layout.cache / "converted"
        except PipelineError:
            return None

    def load_score(self, path: Path, *, accept_recognition: bool = False) -> None:
        self.loading = True
        self.last_attempt = path
        self.state_changed.emit()
        cache = self.converted_cache()

        def work(_emit: Callable[[dict[str, Any]], None]) -> LoadedScore:
            try:
                # a MuseScore project or a PDF is converted first; identity stays the chosen file
                with opened_score(
                    path, accept_recognition=accept_recognition, cache=cache
                ) as opened:
                    parsed, reading = parse_opened(opened, self._parse)
                    digest = opened.sha256
                    conversion = reading.into(
                        None if opened.conversion is None else opened.conversion.as_record()
                    )
                    # only a kept (cached) conversion outlives this block
                    converted_path = (
                        opened.parse_path if conversion is not None and cache is not None else None
                    )
            except OSError as error:
                raise PipelineError(
                    ErrorCategory.SOURCE, "SCORE_UNREADABLE", f"cannot read {path.name}: {error}"
                ) from error
            except BaseException as error:
                raise translate(error) from error
            if parsed.song is None:
                raise PipelineError(
                    ErrorCategory.SOURCE, "SCORE_LOAD_FAILED", "No music was found in this file"
                )
            problems = tuple(issue.message for issue in parsed.issues.errors)
            return LoadedScore(
                path=path,
                sha256=digest,
                title=parsed.song.title or path.stem,
                parsed=parsed,
                lines=describe_lines(parsed),
                problems=problems,
                conversion=conversion,
                accepted_recognition=accept_recognition,
                converted_path=converted_path,
            )

        self.dispatcher.submit(work, self._score_ready, self._score_failed)

    def _score_ready(self, score: LoadedScore) -> None:
        self.loading = False
        previous = self.score
        if previous is not None and self.assignments is not None:
            self._remembered[previous.sha256] = self.assignments.snapshot()
        self.score = score
        self.failed = None
        self.assignments = AssignmentState(score.lines)
        saved = self._remembered.get(score.sha256)
        if saved:  # the same score opened again in this session keeps the user's choices
            self.assignments.restore(saved, [info.line_id for info in score.lines])
        self.review = None
        self.approvals = ()
        self.melody_marks = ()  # marks belong to one score
        self.pronunciation = None  # decisions belong to one score
        self.validation = None
        self.last_result = None
        self.options = replace(self.options, name="", replace=False)
        self.prefs.last_score_dir = str(score.path.parent)
        self.score_loaded.emit(score)
        self.state_changed.emit()
        self.schedule_validation()

    def _score_failed(self, error: BaseException) -> None:
        self.loading = False
        self.failed = self.last_attempt
        self.score_failed.emit(translate(error))
        self.state_changed.emit()

    def fix_target(self) -> FixTarget | None:
        """The file to open so the person can correct the score; None before any score was chosen.

        A score that could not be read is opened as it is. A recognised one is opened as the
        MusicXML BLT read (under the name of the PDF, beside it), together with the picture to check
        it against. Anything else is the person's own file.
        """
        if self.failed is not None:
            return FixTarget(self.failed, None, False)
        score = self.score
        if score is None:
            return None
        recognised = bool(score.conversion and score.conversion.get("recognised"))
        if recognised and score.converted_path is not None and score.converted_path.is_file():
            copy = editable_copy(score.converted_path, score.path, self.converted_cache())
            return FixTarget(copy, score.path, True)
        return FixTarget(score.path, None, False)

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
        self.pronunciation = None  # and to one mapping of lines to voices
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
            ensure_default_voices_dir(folder)
            if folder is None or not folder.is_dir():
                return []
            return sorted(discover_singers(folder), key=str.lower)

        self.dispatcher.submit(work, self._voices_ready, lambda error: self._voices_ready([]))

    def add_voice(self, source: Path) -> None:
        """Copy a voicebank (a folder, or a .zip) into the voices folder, then look again."""
        folder = self.singers_folder()
        if folder is None:
            self.voice_add_failed.emit("Choose the voices folder first.")
            return
        self.adding_voice = True
        self.state_changed.emit()

        def work(_emit: Callable[[dict[str, Any]], None]) -> list[Installed]:
            ensure_default_voices_dir(folder)
            return install_voicebank(source, folder)

        def done(added: list[Installed]) -> None:
            self.adding_voice = False
            self.voice_added.emit(added)
            self.refresh_voices()

        def failed(error: BaseException) -> None:
            self.adding_voice = False
            self.state_changed.emit()
            if isinstance(error, VoiceInstallError):
                self.voice_add_failed.emit(error.message)
            else:
                self.voice_add_failed.emit(f"Could not add {source.name}: {error}")

        self.dispatcher.submit(work, done, failed)

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

    def follow_lead(self) -> bool:
        """Whether parts without lyrics of their own sing the Lead's words (preference and env)."""
        return bool(self.prefs.follow_lead) and default_follow_lead()

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
        prefs.tune_up = options.tune_up
        prefs.count_in = options.count_in
        prefs.tune_up_minor = options.tune_up_minor
        prefs.follow_melody = options.follow_melody
        self.state_changed.emit()

    # --- the melody ------------------------------------------------------------------------

    def melody_plan(self) -> SynthesisPlan | None:
        """The plan the melody is read from: there once voices are chosen."""
        view = self.validation
        if view is None:
            return None
        return view.effective or view.baseline

    def melody_sections(
        self, marks: Sequence[MelodyMark] | None = None
    ) -> tuple[MelodySection, ...]:
        """Who has the melody where, with ``marks`` (default: the person's) laid over the words."""
        plan = self.melody_plan()
        if plan is None:
            return ()
        try:
            return melody_of(plan, self.melody_marks if marks is None else marks)
        except MelodyError:
            return ()

    def set_melody_marks(self, marks: Sequence[MelodyMark]) -> None:
        self.melody_marks = tuple(marks)
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
        self._validation_serial += 1  # whatever is still being checked is now out of date
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
            display_name=score.path.name,
            sha256=score.sha256,
            title=score.title or None,
            conversion=score.conversion,
        )
        # placeholders only: the preview checks the music, not the singer
        refs = {
            role: VoiceEngineRef(
                singer="(not chosen yet)", phonemizer=config.phonemizer, renderer=config.renderer
            )
            for role in VOICE_ORDER
        }

        follow = self.follow_lead()

        def work(_emit: Callable[[dict[str, Any]], None]) -> ValidationView:
            def run(given: tuple[LyricApproval, ...]) -> Preparation:
                return prepare(
                    score.parsed,
                    assignments,
                    identity=identity,
                    engine_refs=refs,
                    approvals=given,
                    follow_lead=follow,
                )

            effective = run(approvals)
            baseline = effective if not approvals else run(())
            return _view(effective, baseline)

        def done(view: ValidationView) -> None:
            if serial != self._validation_serial:
                return  # a newer check is on its way
            self.validating = False
            self.validation = view
            if view.baseline is not None and self.review is None and has_rows(view.baseline):
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

    # --- pronunciations --------------------------------------------------------------------

    def pronunciation_state(self) -> PronunciationState | None:
        """The review of the words the dictionary lacks, once a run or a check has named them."""
        return self.pronunciation

    @property
    def pronunciations(self) -> tuple[PronunciationOverride, ...]:
        return () if self.pronunciation is None else self.pronunciation.overrides()

    def _learn_from_failure(self, error: PipelineError) -> None:
        """Keep what a stopped run says about words and pronunciations for the review."""
        if self.score is None or error.code not in (
            "PRONUNCIATION_UNKNOWN",
            "PRONUNCIATION_INVALID",
        ):
            return
        if self.pronunciation is None:
            self.pronunciation = PronunciationState(self.score.sha256)
        if error.code == "PRONUNCIATION_UNKNOWN":
            self.pronunciation.add_blocked(error.details.get("unknown_words", []))
        else:
            self.pronunciation.mark_refused(error.details.get("invalid_hints", []))

    def start_pronunciation_check(self) -> bool:
        """Ask the engine, in the background, whether the words and pronunciations are accepted."""
        if self.running or self.checking or self.blockers_for_check():
            return False
        request = self.build_request()
        config = self.config()
        token = CancelToken()
        self.token = token
        self.checking = True
        self.state_changed.emit()

        def work(emit: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
            return check_pronunciations(request, config, cancel=token, on_event=emit)

        self.dispatcher.submit(work, self._check_done, self._check_failed)
        return True

    def blockers_for_check(self) -> list[str]:
        """What stops a check: the score, the voices and the singers (not the output options)."""
        if self.running:
            return ["A generation is already running."]
        if self.checking:
            return ["The pronunciations are already being checked."]
        return self._music_blockers()

    def _check_done(self, result: dict[str, Any]) -> None:
        self.checking = False
        self.token = None
        if self.pronunciation is not None:
            self.pronunciation.mark_accepted(result.get("pronunciations", []))
        self.pronunciation_checked.emit(result)
        self.state_changed.emit()

    def _check_failed(self, error: BaseException) -> None:
        self.checking = False
        self.token = None
        problem = translate(error)
        self._learn_from_failure(problem)
        self.pronunciation_checked.emit(problem)
        self.state_changed.emit()

    # --- readiness for the Generate button -------------------------------------------------

    def _music_blockers(self) -> list[str]:
        if self.loading:
            return ["The score is still loading."]
        if self.score is None:
            return ["Choose a score first."]
        out: list[str] = []
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
        return out

    def blockers(self) -> list[str]:
        if self.running:
            return ["A generation is already running."]
        if self.checking:
            return ["The pronunciations are being checked."]
        out = self._music_blockers()
        if self.loading or self.score is None:
            return out
        state = self.pronunciation
        if state is not None and (state.undecided or state.invalid):
            left = state.undecided + state.invalid
            out.append(
                f"{left} place{'s' if left != 1 else ''} with a word the dictionary lacks "
                f"still need{'' if left != 1 else 's'} a pronunciation (open Pronunciations…) "
                "or a different spelling in the score."
            )
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
                automatic="phonemizer" not in config.sources,
            ),
            formats=formats,
            name=name,
            approvals=self.approvals,
            pronunciations=self.pronunciations,
            replace=options.replace,
            keep_stems=options.keep_stems,
            keep_project=options.keep_project,
            tune_up=options.tune_up,
            count_in=options.count_in,
            tune_up_minor=options.tune_up_minor,
            follow_melody=options.follow_melody,
            melody_marks=self.melody_marks,
            timeout_seconds=float(self.prefs.timeout_minutes * 60),
            mp3_quality=options.mp3_quality,
            follow_lead=self.follow_lead(),
            accept_recognition=bool(self.score and self.score.accepted_recognition),
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
        problem = translate(error)
        self._learn_from_failure(problem)
        self.generation_failed.emit(problem)
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
            messages.append(Message("error", sentence(text)))
        elif finding.disposition.value == "advisory":
            messages.append(Message("warning", sentence(text)))
    unresolved = 0 if effective.plan is None else len(effective.plan.review_items)
    following = 0 if effective.plan is None else _following(effective.plan)
    return ValidationView(
        tuple(messages),
        report.ready,
        baseline.plan,
        effective.plan,
        unresolved,
        "\n".join(technical),
        following,
    )


def _following(plan: SynthesisPlan) -> int:
    return sum(1 for v in plan.voices for n in v.notes if n.lyric.state in FOLLOWING_STATES)


__all__ = ["AppController", "LoadedScore", "Message", "OutputOptions", "ValidationView"]
