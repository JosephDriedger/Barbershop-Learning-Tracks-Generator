"""The OpenUtau render backend: a ready SynthesisPlan in, four validated stems out, or an error.

One call is one transaction:

1. configuration is checked and the host runtime installed (``core.runtime.host_install``);
2. the plan is written as the version-pinned USTX (``core.synthesis.openutau``);
3. an isolated staging directory is created and the host runs there as an owned process tree;
4. the host's structured events are collected, timeouts and cancellation are enforced;
5. the output is validated (``core.rendering.stems``) and only then published atomically.

Whatever happens, the staging directory is removed, and nothing reaches the destination unless the
whole set validated. A previous result at the destination is kept when a new attempt fails.
"""

import contextlib
import dataclasses
import json
import os
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from barbershop_tracks.core.rendering import pronunciation
from barbershop_tracks.core.rendering.cancel import CancelToken
from barbershop_tracks.core.rendering.errors import (
    OutputValidationError,
    ProjectValidationError,
    PronunciationError,
    RenderCancelledError,
    RenderConfigurationError,
    RenderError,
    RenderTimeoutError,
    SynthesisError,
)
from barbershop_tracks.core.rendering.process import OwnedProcess
from barbershop_tracks.core.rendering.stems import (
    STEM_BASE,
    StemPolicy,
    StemReport,
    validate_and_collect,
)
from barbershop_tracks.core.runtime import (
    HostInstallError,
    RuntimeLayout,
    StagingArea,
    StagingError,
    ensure_host_runtime,
)
from barbershop_tracks.core.runtime.filelock import FileLock, LockWaitAbortedError
from barbershop_tracks.core.runtime.staging import cleanup_stale, publish_directory, remove_staging
from barbershop_tracks.core.synthesis import PlanNotReadyError, SynthesisPlan
from barbershop_tracks.core.synthesis.openutau import (
    NO_OVERRIDES,
    ResolvedOverrides,
    UstxError,
    write_ustx,
)
from barbershop_tracks.models import VoiceRole

EventHandler = Callable[[dict[str, Any]], None]


@dataclass(frozen=True, slots=True)
class RenderSettings:
    layout: RuntimeLayout
    singers_dir: Path
    host_binaries: Path | None = None  # directory with blt-render-host.exe; default <binaries>/host
    host_command: tuple[str, ...] | None = None  # replaces the installed host (tests, tooling)
    extra_env: Mapping[str, str] = field(default_factory=dict)
    timeout_seconds: float = 900.0
    phonemize_timeout_ms: int = 60_000
    render_timeout_ms: int = 600_000
    stem_policy: StemPolicy = field(default_factory=StemPolicy)
    poll_seconds: float = 0.05


@dataclass(frozen=True, slots=True)
class RenderResult:
    destination: Path
    stems: Mapping[VoiceRole, StemReport]
    host_result: Mapping[str, Any]
    events: tuple[dict[str, Any], ...]
    job: str
    seconds: float


def _tail(text: str, limit: int = 4000) -> str:
    return text if len(text) <= limit else "…" + text[-limit:]


def with_host_findings(
    error: OutputValidationError, host_result: Mapping[str, Any]
) -> OutputValidationError:
    """Add what the host already knows to a "silent" verdict: which words or sounds have no sound.

    OpenUtau renders a word its dictionary lacks, or an alias the voicebank lacks, as silence
    without an error. The host lists such phonemes (``unsung_phonemes``); the stem check then finds
    the silence. Without this the user is told only that "the voicebank cannot sing those lyrics".
    """
    samples = host_result.get("unsung_phonemes")
    if error.code not in ("STEM_SILENT", "STEM_NOTE_SILENT") or not isinstance(samples, list):
        return error
    words = sorted(
        {
            str(s["lyric"])
            for s in samples
            if s.get("reason") == "lyric_has_no_sound" and s.get("lyric")
        }
    )
    sounds = sorted(
        {
            str(s["alias"])
            for s in samples
            if s.get("reason") == "alias_not_in_voicebank" and s.get("alias")
        }
    )
    failed = sorted(
        {str(s["lyric"]) for s in samples if s.get("reason") == "engine_error" and s.get("lyric")}
    )
    said: list[str] = []
    if failed:
        shown = ", ".join(repr(w) for w in failed[:8]) + (", ..." if len(failed) > 8 else "")
        said.append(
            f"the pronunciation engine failed on the word(s) {shown} (it stopped with an error "
            "there; the voicebank or the word is not one this engine can work with)"
        )
    if words:
        shown = ", ".join(repr(w) for w in words[:8]) + (", ..." if len(words) > 8 else "")
        said.append(
            f"the singing voice has no sound for the word(s) {shown} (a word that is missing from "
            "the pronunciation dictionary, or a lyric this voice cannot sing)"
        )
    if sounds:
        shown = ", ".join(repr(a) for a in sounds[:8]) + (", ..." if len(sounds) > 8 else "")
        said.append(f"the voicebank has no recording named {shown}")
    if not said:
        return error
    details = dict(
        error.details,
        unsung_words=words,
        unsung_sounds=sounds,
        engine_failures=failed,
        host_findings=samples[:60],
    )
    return OutputValidationError(
        error.code, f"{error.message}. The singing engine reported that " + "; ".join(said), details
    )


def _parse_events(lines: list[str]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in lines:
        if line.startswith("{"):
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, dict) and "event" in value:
                events.append(value)
    return events


class OpenUtauRenderBackend:
    def __init__(self, settings: RenderSettings) -> None:
        self.settings = settings

    # --- public -------------------------------------------------------------------------

    def render(
        self,
        plan: SynthesisPlan,
        destination: Path,
        *,
        cancel: CancelToken | None = None,
        on_event: EventHandler | None = None,
        replace: bool = False,
        overrides: ResolvedOverrides = NO_OVERRIDES,
    ) -> RenderResult:
        """Render ``plan`` and publish ``<destination>/<Role>.wav`` for the four voices.

        ``overrides`` are the pronunciations a person decided for particular words of the score;
        they reach the engine only as phonetic hints and are checked by it before anything renders.
        """
        started = time.monotonic()
        token = cancel or CancelToken()
        if token.cancelled:
            raise RenderCancelledError("RENDER_CANCELLED", "cancelled before it started")
        command_prefix, environment = self._host_launch()
        project_text = self._project(plan, overrides)
        layout = self.settings.layout
        try:
            cleanup_stale(layout.staging)  # recover from earlier crashes; never an active job
            job = uuid.uuid4().hex[:12]
            area = StagingArea.create(layout.staging, job)
        except (StagingError, OSError) as error:
            raise RenderConfigurationError(
                "STAGING_UNAVAILABLE", f"cannot create a staging directory: {error}"
            ) from error
        try:
            with self._host_slot(token, on_event):
                try:
                    result = self._run(
                        plan, area, project_text, command_prefix, environment, token, on_event
                    )
                except PronunciationError as unknown:
                    raise pronunciation.with_findings(unknown, plan) from unknown
            host_result, events = result
            stems_dir = area.path / "stems"
            if on_event is not None:
                on_event({"event": "blt_stage", "stage": "stem_validation", "status": "started"})
            try:
                reports = validate_and_collect(
                    plan, area.path / "host-out", stems_dir, self.settings.stem_policy
                )
            except OutputValidationError as invalid:
                raise with_host_findings(invalid, host_result) from invalid
            if on_event is not None:
                on_event({"event": "blt_stage", "stage": "stem_validation", "status": "finished"})
            if token.cancelled:  # cancelled while validating: honour it before publishing
                raise RenderCancelledError("RENDER_CANCELLED", "cancelled before publication")
            try:
                publish_directory(stems_dir, destination, replace=replace)
            except StagingError as error:
                raise RenderConfigurationError(error.code, error.message) from error
            final = {
                role: dataclasses.replace(report, path=destination / report.path.name)
                for role, report in reports.items()
            }
            return RenderResult(
                destination, final, host_result, tuple(events), job, time.monotonic() - started
            )
        finally:
            self._discard(area.path)

    def check_pronunciations(
        self,
        plan: SynthesisPlan,
        overrides: ResolvedOverrides = NO_OVERRIDES,
        *,
        cancel: CancelToken | None = None,
        on_event: EventHandler | None = None,
    ) -> Mapping[str, Any]:
        """Phonemize ``plan`` with the engine and stop: no stem is rendered, nothing is published.

        Raises ``PronunciationError`` (a word the dictionary lacks, or a given pronunciation the
        engine refuses, each placed in the score) exactly as ``render`` would; otherwise returns the
        host's result, whose ``pronunciations`` list the sounds the engine made of each override.
        """
        token = cancel or CancelToken()
        if token.cancelled:
            raise RenderCancelledError("RENDER_CANCELLED", "cancelled before it started")
        command_prefix, environment = self._host_launch()
        project_text = self._project(plan, overrides)
        layout = self.settings.layout
        try:
            cleanup_stale(layout.staging)
            area = StagingArea.create(layout.staging, uuid.uuid4().hex[:12])
        except (StagingError, OSError) as error:
            raise RenderConfigurationError(
                "STAGING_UNAVAILABLE", f"cannot create a staging directory: {error}"
            ) from error
        try:
            with self._host_slot(token, on_event):
                try:
                    host_result, _events = self._run(
                        plan,
                        area,
                        project_text,
                        command_prefix,
                        environment,
                        token,
                        on_event,
                        check_only=True,
                    )
                except PronunciationError as problem:
                    raise pronunciation.with_findings(problem, plan) from problem
            return host_result
        finally:
            self._discard(area.path)

    # --- steps --------------------------------------------------------------------------

    @contextlib.contextmanager
    def _host_slot(self, token: CancelToken, on_event: EventHandler | None) -> Iterator[None]:
        """One host at a time per runtime root: they share OpenUtau's render cache."""
        lock = FileLock(self.settings.layout.runtime / "render.lock")

        def waiting() -> None:
            if on_event is not None:
                on_event({"event": "blt_wait", "reason": "another render is using the host"})

        try:
            lock.acquire(should_stop=lambda: token.cancelled, on_wait=waiting)
        except LockWaitAbortedError:
            raise RenderCancelledError(
                "RENDER_CANCELLED", "cancelled while waiting for another render to finish"
            ) from None
        except OSError as error:
            raise RenderConfigurationError(
                "HOST_LOCK_UNAVAILABLE", f"cannot take the host lock: {error}"
            ) from error
        try:
            yield
        finally:
            lock.release()

    def _host_launch(self) -> tuple[list[str], dict[str, str]]:
        settings = self.settings
        if not settings.singers_dir.is_dir():
            raise RenderConfigurationError(
                "SINGERS_DIR_MISSING", f"singers directory not found: {settings.singers_dir}"
            )
        environment = {**os.environ, **settings.extra_env}
        if settings.host_command is not None:
            return list(settings.host_command), environment
        binaries = settings.host_binaries or settings.layout.binaries / "host"
        try:
            runtime = ensure_host_runtime(binaries, settings.layout.runtime)
        except HostInstallError as error:
            raise RenderConfigurationError(error.code, error.message) from error
        return [str(runtime.exe)], environment

    @staticmethod
    def _project(plan: SynthesisPlan, overrides: ResolvedOverrides = NO_OVERRIDES) -> str:
        try:
            return write_ustx(plan, overrides=overrides).text
        except PlanNotReadyError as error:
            raise ProjectValidationError(error.code, str(error)) from error
        except UstxError as error:
            raise ProjectValidationError(error.code, error.message) from error

    def _run(
        self,
        plan: SynthesisPlan,
        area: StagingArea,
        project_text: str,
        command_prefix: list[str],
        environment: dict[str, str],
        token: CancelToken,
        on_event: EventHandler | None,
        *,
        check_only: bool = False,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        settings = self.settings
        project = area.path / "project.ustx"
        out = area.path / "host-out"
        try:
            project.write_text(project_text, encoding="utf-8", newline="\n")
            out.mkdir()
        except OSError as error:
            raise RenderConfigurationError(
                "STAGING_NOT_WRITABLE", f"cannot write into {area.path}: {error}"
            ) from error
        command = [
            *command_prefix,
            "--project",
            str(project),
            *(["--phonemize-only"] if check_only else ["--out", str(out), "--base", STEM_BASE]),
            "--singers-dir",
            str(settings.singers_dir),
            "--phonemize-timeout-ms",
            str(settings.phonemize_timeout_ms),
            "--render-timeout-ms",
            str(settings.render_timeout_ms),
        ]

        def forward(line: str) -> None:
            if on_event is None or not line.startswith("{"):
                return
            try:
                value = json.loads(line)
            except ValueError:
                return
            if isinstance(value, dict):
                on_event(value)

        try:
            owned = OwnedProcess(command, env=environment, on_stdout_line=forward)
        except OSError as error:
            raise RenderConfigurationError(
                "HOST_LAUNCH_FAILED", f"cannot start the render host: {error}"
            ) from error
        deadline = time.monotonic() + settings.timeout_seconds
        try:
            while owned.poll() is None:
                if token.cancelled:
                    owned.terminate_tree()
                    owned.finish()
                    raise RenderCancelledError(
                        "RENDER_CANCELLED", "cancelled; the render process tree was ended"
                    )
                if time.monotonic() > deadline:
                    owned.terminate_tree()
                    owned.finish()
                    raise RenderTimeoutError(
                        "RENDER_TIMEOUT",
                        f"no result within {settings.timeout_seconds:g} s; the process tree was "
                        "ended",
                        {"stderr": _tail(owned.stderr_text)},
                    )
                time.sleep(settings.poll_seconds)
            code = owned.finish()
        except BaseException:
            owned.terminate_tree()
            owned.finish()
            raise
        events = _parse_events(owned.stdout_lines)
        return self._interpret(code, events, owned.stderr_text), events

    @staticmethod
    def _interpret(code: int, events: list[dict[str, Any]], stderr: str) -> dict[str, Any]:
        last = events[-1] if events and events[-1].get("event") == "result" else None
        details: dict[str, Any] = {
            "exit_code": code,
            "stderr": _tail(stderr),
            "host_result": last,
        }
        message = (last or {}).get("error") or (last or {}).get("status") or "no result"
        if last is None:
            raise SynthesisError(
                "HOST_NO_RESULT",
                f"the render host exited with code {code} without a result ({_tail(stderr, 300)})",
                details,
            )
        if code == 0:
            if last.get("status") != "ok" or last.get("exit_code") != 0:
                raise SynthesisError(
                    "HOST_INCONSISTENT", "exit code 0 but the result is not ok", details
                )
            return last
        if code == 3:
            raise ProjectValidationError("HOST_PROJECT_REJECTED", str(message), details)
        if code == 4:
            raise RenderConfigurationError("HOST_UNRESOLVED", str(message), details)
        if code in (2, 8):
            raise RenderConfigurationError(
                "HOST_USAGE" if code == 2 else "HOST_ENVIRONMENT", str(message), details
            )
        if code == 11:
            raise PronunciationError("PRONUNCIATION_UNKNOWN", str(message), details)
        if code == 12:
            raise PronunciationError("PRONUNCIATION_INVALID", str(message), details)
        if code in (7, 9):
            raise RenderTimeoutError(
                "HOST_PHONEMIZE_TIMEOUT" if code == 7 else "HOST_RENDER_TIMEOUT",
                str(message),
                details,
            )
        raise SynthesisError("HOST_FAILED", f"exit {code}: {message}", details)

    @staticmethod
    def _discard(path: Path) -> None:
        for attempt in range(5):
            try:
                remove_staging(path)
                return
            except FileNotFoundError:
                return
            except OSError:
                time.sleep(0.1 * (attempt + 1))  # a just-killed process may still hold a file


__all__ = ["OpenUtauRenderBackend", "RenderError", "RenderResult", "RenderSettings"]
