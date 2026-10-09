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

import dataclasses
import json
import os
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from barbershop_tracks.core.rendering.cancel import CancelToken
from barbershop_tracks.core.rendering.errors import (
    ProjectValidationError,
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
from barbershop_tracks.core.runtime.staging import cleanup_stale, publish_directory, remove_staging
from barbershop_tracks.core.synthesis import PlanNotReadyError, SynthesisPlan
from barbershop_tracks.core.synthesis.openutau import UstxError, write_ustx
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
    ) -> RenderResult:
        """Render ``plan`` and publish ``<destination>/<Role>.wav`` for the four voices."""
        started = time.monotonic()
        token = cancel or CancelToken()
        if token.cancelled:
            raise RenderCancelledError("RENDER_CANCELLED", "cancelled before it started")
        command_prefix, environment = self._host_launch()
        project_text = self._project(plan)
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
            result = self._run(
                plan, area, project_text, command_prefix, environment, token, on_event
            )
            host_result, events = result
            stems_dir = area.path / "stems"
            reports = validate_and_collect(
                plan, area.path / "host-out", stems_dir, self.settings.stem_policy
            )
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

    # --- steps --------------------------------------------------------------------------

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
    def _project(plan: SynthesisPlan) -> str:
        try:
            return write_ustx(plan).text
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
            "--out",
            str(out),
            "--base",
            STEM_BASE,
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
