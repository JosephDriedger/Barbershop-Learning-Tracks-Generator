"""The ``generate`` and ``config`` commands.

``generate SCORE --out DIR --assign ROLE=LINE ... --singer ID`` runs the whole pipeline
(``core.pipeline``) and publishes ``DIR/<name>_learning_tracks/``.

Exit codes of ``generate`` (a public contract):

====  =====================================================================================
0     the package was published
1     the score or the voice mapping is not ready (source problem)
2     invocation, configuration or filesystem problem (singers, host, FFmpeg, output folder)
3     the render host failed (synthesis)
4     the audio did not validate, or mixing/encoding failed
5     a time limit was exceeded
6     lyrics need an explicit decision first (a review report was written)
130   cancelled (Ctrl+C / Ctrl+Break); nothing was published
====  =====================================================================================

Human progress goes to stderr, the summary to stdout. With ``--progress json`` stdout carries one
JSON object per line instead: stage/progress/host/warning events, then a final ``result`` or
``error`` event.
"""

import argparse
import hashlib
import json
import re
import signal
import sys
import threading
from pathlib import Path
from types import FrameType
from typing import Any

from barbershop_tracks.core.melody import MelodyError, MelodyMark
from barbershop_tracks.core.mixing import PRESETS, AudioFormat, find_ffmpeg
from barbershop_tracks.core.pipeline import (
    APPROVALS_SCHEMA,
    DEFAULT_PHONEMIZER,
    DEFAULT_RENDERER,
    OVERRIDES_SCHEMA,
    REVIEW_SCHEMA,
    STAGE_LABELS,
    EngineChoice,
    ErrorCategory,
    GenerateRequest,
    PipelineError,
    ResolvedConfig,
    config_path,
    discover_singers,
    generate,
    load_config_file,
    package_dirname,
    read_approvals,
    read_overrides,
    render_review_text,
    resolve_config,
    template_document,
)
from barbershop_tracks.core.readiness import RoleAssignments
from barbershop_tracks.core.rendering import CancelToken
from barbershop_tracks.core.runtime.host_install import HOST_EXE
from barbershop_tracks.core.synthesis import LyricApproval
from barbershop_tracks.core.synthesis.openutau import PronunciationOverride
from barbershop_tracks.models import VoiceRole

EXIT_OK = 0
EXIT_SOURCE = 1
EXIT_CONFIG = 2
EXIT_SYNTHESIS = 3
EXIT_AUDIO = 4
EXIT_TIMEOUT = 5
EXIT_REVIEW = 6
EXIT_CANCELLED = 130

_EXIT = {
    ErrorCategory.SOURCE: EXIT_SOURCE,
    ErrorCategory.CONFIGURATION: EXIT_CONFIG,
    ErrorCategory.SYNTHESIS: EXIT_SYNTHESIS,
    ErrorCategory.AUDIO: EXIT_AUDIO,
    ErrorCategory.TIMEOUT: EXIT_TIMEOUT,
    ErrorCategory.REVIEW: EXIT_REVIEW,
    ErrorCategory.CANCELLED: EXIT_CANCELLED,
}
_ROLES = {role.value: role for role in VoiceRole}
_LABELS = {k: v.lower() for k, v in STAGE_LABELS.items()}


def _singer(text: str) -> tuple[VoiceRole | None, str]:
    if "=" in text:
        role_text, _, singer = text.partition("=")
        role = _ROLES.get(role_text.strip().lower())
        if role is None or not singer.strip():
            raise argparse.ArgumentTypeError(
                f"{text!r} is not ID or ROLE=ID (roles: {', '.join(_ROLES)})"
            )
        return role, singer.strip()
    if not text.strip():
        raise argparse.ArgumentTypeError("a singer id must not be empty")
    return None, text.strip()


def _melody_mark(text: str) -> MelodyMark:
    """``ROLE=FIRST-LAST`` (or ``ROLE=BAR``): that voice has the melody in those bars.

    A bar may be followed by ``:BEAT``: ``TENOR=30:3-31:2`` is from beat 3 of bar 30 to the end of
    beat 2 of bar 31. Without a beat the whole bar is meant.
    """
    role_text, _, bars = text.partition("=")
    role = _ROLES.get(role_text.strip().lower())
    found = re.fullmatch(r"(\d+)(?::(\d+))?(?:-(\d+)(?::(\d+))?)?", bars.strip())
    if role is None or found is None:
        raise argparse.ArgumentTypeError(
            f"{text!r} is not ROLE=FIRST-LAST or ROLE=BAR, for example LEAD=12-16, TENOR=30 or "
            "TENOR=30:3-31:2 (bars, and beats after a colon)"
        )
    first, first_beat, last, last_beat = found.groups()
    try:
        return MelodyMark(
            role,
            int(first),
            int(last or first),
            int(first_beat or 1),
            int(last_beat) if last_beat else None,
        )
    except MelodyError as error:
        raise argparse.ArgumentTypeError(error.message) from error


def add_config_options(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("configuration (command line > environment > config file)")
    group.add_argument("--config", metavar="FILE", help="a config file (default: per-user file)")
    group.add_argument("--singers-dir", metavar="DIR", help="the folder that holds the voicebanks")
    group.add_argument("--host-dir", metavar="DIR", help="the folder with the render host")
    group.add_argument("--dotnet-root", metavar="DIR", help="the .NET runtime the host needs")
    group.add_argument("--ffmpeg", metavar="PATH", help="the FFmpeg executable (MP3 output only)")
    group.add_argument("--data-dir", metavar="DIR", help="BLT's own working data")


def add_parsers(commands: Any) -> None:
    gen = commands.add_parser(
        "generate",
        help="generate the 13 learning tracks from a score",
        description=(
            "MusicXML to the 13 learning tracks, with no manual OpenUtau step. Exit 0 published, "
            "1 score not ready, 2 invocation/configuration, 3 synthesis failed, 4 audio failed, "
            "5 timeout, 6 lyrics need review, 130 cancelled."
        ),
    )
    gen.add_argument(
        "score",
        help="a .musicxml, .xml, .mxl, .mscz (needs MuseScore) or .pdf (needs Audiveris) file",
    )
    gen.add_argument(
        "--accept-recognition",
        action="store_true",
        help="accept a score recognised from a PDF or image: recognition makes mistakes, so it "
        "only runs when you say so, and the result must be checked against the original",
    )
    gen.add_argument(
        "--no-composed-pronunciations",
        action="store_true",
        help="stop at every word the pronunciation dictionary lacks, so that you decide it; "
        "by default such a word is built from dictionary entries (a spelling such as ev'ry for "
        "every, or pieces of other words) and recorded as BLT's own, not as your decision",
    )
    gen.add_argument(
        "--no-guessed-pronunciations",
        action="store_true",
        help="keep building unknown words from dictionary entries, but stop at a word that "
        "cannot be built that way instead of guessing it from its spelling (a rough guess, "
        "recorded as BLT's and shown as a warning)",
    )
    gen.add_argument("--out", metavar="DIR", help="folder that will hold the package folder")
    gen.add_argument(
        "--assign",
        action="append",
        default=[],
        metavar="ROLE=LINE",
        help="assign a voice to a source line, e.g. TENOR=P1/s1/v1 (all four; see 'lines')",
    )
    gen.add_argument("--ignore", action="append", default=[], metavar="LINE")
    gen.add_argument("--verse", help="the logical verse to use (default: automatic)")
    gen.add_argument(
        "--singer",
        action="append",
        default=[],
        type=_singer,
        metavar="[ROLE=]ID",
        help="the voicebank id (all voices), or ROLE=ID for one voice; never chosen for you",
    )
    gen.add_argument("--phonemizer", help=f"default {DEFAULT_PHONEMIZER}")
    gen.add_argument("--renderer", help=f"default {DEFAULT_RENDERER}")
    gen.add_argument(
        "--audio-format", choices=("wav", "mp3", "both"), default="wav", help="default wav"
    )
    gen.add_argument("--mp3-quality", type=int, default=2, help="LAME VBR quality 0-9 (default 2)")
    gen.add_argument(
        "--gain-profile", choices=sorted(PRESETS), help="mix balance preset (default: default)"
    )
    gen.add_argument("--gain-profile-file", metavar="FILE", help="a JSON gain profile")
    gen.add_argument("--name", help="package name (default: the score's file name)")
    gen.add_argument("--replace", action="store_true", help="replace a previous package of ours")
    gen.add_argument("--approve-lyrics", metavar="FILE", help="an approvals file you filled in")
    gen.add_argument("--review-report", metavar="FILE", help="where to write the lyric review")
    gen.add_argument(
        "--approve-pronunciations",
        metavar="FILE",
        help="your pronunciations for words the dictionary lacks (fill in the template that a "
        "stopped run writes next to the output)",
    )
    gen.add_argument(
        "--no-follow-lead",
        action="store_true",
        help="do not let parts without their own lyrics sing the Lead's words (they go to review)",
    )
    gen.add_argument(
        "--melody",
        action="append",
        default=[],
        type=_melody_mark,
        metavar="ROLE=FIRST-LAST",
        help="that voice has the melody in those bars of the score (repeatable), whatever the "
        "words say, e.g. --melody tenor=30-33; by default the part singing the words has it",
    )
    gen.add_argument(
        "--no-follow-melody",
        action="store_true",
        help="mix the Full Quartet evenly instead of making the voice with the melody louder",
    )
    gen.add_argument("--keep-stems", action="store_true", help="also publish the four stems")
    gen.add_argument("--keep-project", action="store_true", help="also publish the USTX project")
    gen.add_argument(
        "--tune-up",
        action="store_true",
        help="start every track with a three-second note to tune to: the tonic of the score's "
        "first key signature (C or A when the score has no key signature)",
    )
    gen.add_argument(
        "--tune-up-key",
        choices=("major", "minor"),
        default="major",
        help="with --tune-up: the tonic of the major key (the default) or of the relative "
        "minor of the first key signature (G major and E minor share one sharp)",
    )
    gen.add_argument(
        "--count-in",
        action="store_true",
        help="start every track with a bar of metronome clicks at the score's first tempo "
        "and time signature (after the tune-up note, if there is one)",
    )
    gen.add_argument(
        "--timeout", type=float, default=900.0, metavar="SECONDS", help="render time limit (900)"
    )
    gen.add_argument(
        "--progress", choices=("text", "json", "none"), default="text", help="progress style"
    )
    add_config_options(gen)

    conf = commands.add_parser(
        "config",
        help="show where BLT finds singers, the host and FFmpeg",
        description="Show the resolved configuration, where each value came from, what is found.",
    )
    conf.add_argument("--format", choices=("text", "json"), default="text")
    add_config_options(conf)


# --- shared plumbing ---------------------------------------------------------------------------


def _overrides(args: argparse.Namespace) -> dict[str, str | None]:
    return {
        "singers_dir": args.singers_dir,
        "host_dir": args.host_dir,
        "dotnet_root": args.dotnet_root,
        "ffmpeg": args.ffmpeg,
        "data_dir": args.data_dir,
        "output_dir": getattr(args, "out", None),
        "phonemizer": getattr(args, "phonemizer", None),
        "renderer": getattr(args, "renderer", None),
        "gain_profile": getattr(args, "gain_profile", None),
    }


def _resolve(
    args: argparse.Namespace, extra: dict[str, str | None] | None = None
) -> ResolvedConfig:
    environ = None
    path = Path(args.config) if args.config else config_path(environ)
    overrides = {**_overrides(args), **(extra or {})}
    profile_file = getattr(args, "gain_profile_file", None)
    return resolve_config(
        load_config_file(path),
        overrides=overrides,
        profile_file=Path(profile_file) if profile_file else None,
    )


def _print_error(error: PipelineError, *, json_mode: bool) -> None:
    if json_mode:
        payload = {
            "event": "error",
            "category": error.category.value,
            "code": error.code,
            "message": error.message,
            "details": error.details,
        }
        sys.stdout.write(json.dumps(payload) + "\n")
        sys.stdout.flush()
        return
    print(f"error[{error.code}] ({error.category.value}): {error.message}", file=sys.stderr)
    for finding in error.details.get("findings", []):
        where = " ".join(
            str(part)
            for part in (finding.get("voice"), finding.get("line"), finding.get("where"))
            if part
        )
        print(
            f"  - {finding['code']}: {finding['message']}" + (f" ({where})" if where else ""),
            file=sys.stderr,
        )
    if error.category is ErrorCategory.REVIEW:
        print(render_review_text(error.details["review"]), file=sys.stderr)


def _write_json(document: dict[str, Any], path: Path, schema: str) -> str | None:
    """Write a review/approvals document; never over a file that is not one of ours."""
    if path.exists():
        try:
            if json.loads(path.read_text(encoding="utf-8")).get("schema") != schema:
                return f"{path} exists and is not one of our {schema} files; not overwritten"
        except (OSError, ValueError, AttributeError):
            return f"{path} exists and is not one of our {schema} files; not overwritten"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8", newline="\n")
        temporary.replace(path)
    except OSError as error:
        return f"cannot write {path.name}: {error}"
    return None


class _Progress:
    def __init__(self, style: str) -> None:
        self.style = style
        self.last_counted = ""

    def __call__(self, event: dict[str, Any]) -> None:
        if self.style == "json":
            sys.stdout.write(json.dumps(event) + "\n")
            sys.stdout.flush()
        elif self.style == "text":
            self._text(event)

    def _text(self, event: dict[str, Any]) -> None:
        kind = event.get("event")
        if kind == "stage" and event["status"] == "started":
            print(f"-> {_LABELS.get(event['stage'], event['stage'])}...", file=sys.stderr)
        elif kind == "progress":
            print(
                f"   {event['stage'].replace('_', ' ')} {event['completed']}/{event['total']}",
                file=sys.stderr,
            )
        elif kind == "warning":
            print(f"warning[{event['code']}]: {event['message']}", file=sys.stderr)


def _signals(token: CancelToken) -> list[tuple[int, Any]]:
    """Ctrl+C / Ctrl+Break request cancellation once; a second one interrupts immediately."""

    def handler(signum: int, frame: FrameType | None) -> None:
        if token.cancelled:
            raise KeyboardInterrupt
        print("cancelling: stopping the render and cleaning up...", file=sys.stderr)
        token.cancel()

    previous: list[tuple[int, Any]] = []
    if threading.current_thread() is not threading.main_thread():
        return previous  # signal handlers can only be installed from the main thread
    for name in ("SIGINT", "SIGBREAK"):
        number = getattr(signal, name, None)
        if number is not None:
            previous.append((number, signal.signal(number, handler)))
    return previous


def run_generate(args: argparse.Namespace) -> int:
    json_mode = args.progress == "json"
    try:
        return _generate(args, json_mode)
    except PipelineError as error:
        _print_error(error, json_mode=json_mode)
        return _EXIT[error.category]


def _generate(args: argparse.Namespace, json_mode: bool) -> int:
    if not args.assign:
        raise PipelineError(
            ErrorCategory.CONFIGURATION,
            "NO_VOICE_MAPPING",
            "say which source line is which voice: --assign TENOR=LINE --assign LEAD=LINE ... "
            "(list the lines with 'barbershop-tracks lines SCORE')",
        )
    entries: list[tuple[VoiceRole, str]] = []
    for text in args.assign:
        role_text, _, line = text.partition("=")
        role = _ROLES.get(role_text.strip().lower())
        if role is None or not line:
            raise PipelineError(
                ErrorCategory.CONFIGURATION, "BAD_ASSIGN", f"{text!r} is not ROLE=LINE"
            )
        entries.append((role, line))
    default_singer = next((s for r, s in args.singer if r is None), None)
    per_voice = {r: s for r, s in args.singer if r is not None}
    config = _resolve(args, {"singer": default_singer})
    if config.output_dir is None:
        raise PipelineError(
            ErrorCategory.CONFIGURATION,
            "NO_OUTPUT",
            "where should the package go? pass --out DIR (or set BLT_OUTPUT_DIR / output_dir)",
        )
    score = Path(args.score)
    approvals: tuple[LyricApproval, ...] = ()
    pronunciations: tuple[PronunciationOverride, ...] = ()
    if args.approve_lyrics or args.approve_pronunciations:
        digest = _digest(score)
        if args.approve_lyrics:
            approvals = read_approvals(Path(args.approve_lyrics), source_sha256=digest)
        if args.approve_pronunciations:
            pronunciations = read_overrides(Path(args.approve_pronunciations), source_sha256=digest)
    formats = {
        "wav": frozenset({AudioFormat.WAV}),
        "mp3": frozenset({AudioFormat.MP3}),
        "both": frozenset({AudioFormat.WAV, AudioFormat.MP3}),
    }[args.audio_format]
    request = GenerateRequest(
        score=score,
        output=config.output_dir,
        assignments=RoleAssignments(entries=tuple(entries), ignored=tuple(args.ignore)),
        engine=EngineChoice(
            config.singer,
            config.phonemizer,
            config.renderer,
            per_voice,
            automatic="phonemizer" not in config.sources,
        ),
        formats=formats,
        name=args.name,
        verse=args.verse,
        approvals=approvals,
        pronunciations=pronunciations,
        replace=args.replace,
        keep_stems=args.keep_stems,
        keep_project=args.keep_project,
        tune_up=args.tune_up,
        count_in=args.count_in,
        tune_up_minor=args.tune_up_key == "minor",
        timeout_seconds=args.timeout,
        mp3_quality=args.mp3_quality,
        follow_lead=False if args.no_follow_lead else None,
        follow_melody=not args.no_follow_melody,
        melody_marks=tuple(args.melody),
        accept_recognition=args.accept_recognition,
        compose_unknown_words=not args.no_composed_pronunciations,
        guess_by_spelling=not args.no_guessed_pronunciations,
    )
    token = CancelToken()
    previous = _signals(token)
    progress = _Progress(args.progress)
    try:
        result = generate(request, config, cancel=token, on_event=progress)
    except KeyboardInterrupt:
        raise PipelineError(ErrorCategory.CANCELLED, "CANCELLED", "interrupted") from None
    except PipelineError as error:
        if error.category is ErrorCategory.REVIEW:
            _handle_review(error, args, request)
        elif error.code == "PRONUNCIATION_UNKNOWN":
            _handle_pronunciation(error, args, request)
        raise
    finally:
        for number, handler in previous:
            signal.signal(number, handler)
    _print_result(result, json_mode)
    return EXIT_OK


def _digest(score: Path) -> str:
    try:
        return hashlib.sha256(score.read_bytes()).hexdigest()
    except OSError as error:
        raise PipelineError(
            ErrorCategory.SOURCE, "SCORE_UNREADABLE", f"cannot read {score}: {error}"
        ) from error


def _handle_pronunciation(
    error: PipelineError, args: argparse.Namespace, request: GenerateRequest
) -> None:
    """Write a fill-in pronunciations file with one undecided entry per blocked word and voice."""
    name = args.name or Path(args.score).stem
    path = request.output / f"{package_dirname(name)}.pronunciations-template.json"
    template = template_document(error.details.get("unknown_words", []), _digest(request.score))
    problem = _write_json(template, path, OVERRIDES_SCHEMA)
    if problem is None:
        error.details["pronunciations_template"] = str(path)
        if args.progress != "json":
            print(f"pronunciations template written to {path}", file=sys.stderr)
            print(
                "fill in 'symbols' (and 'approved_by') for each place you want to decide, in the "
                "notation named in the entry, delete the places you do not, then rerun with "
                "--approve-pronunciations FILE. The score itself is never changed.",
                file=sys.stderr,
            )
    else:
        error.details["pronunciations_template_error"] = problem
        print(f"warning: {problem}", file=sys.stderr)


def _handle_review(
    error: PipelineError, args: argparse.Namespace, request: GenerateRequest
) -> None:
    """Write the review report and a fill-in approvals template next to it."""
    report = error.details["review"]
    name = args.name or Path(args.score).stem
    path = (
        Path(args.review_report)
        if args.review_report
        else request.output / f"{package_dirname(name)}.lyric-review.json"
    )
    template = path.with_name(path.stem + ".approvals-template.json")
    problem = _write_json(report, path, REVIEW_SCHEMA) or _write_json(
        report["approvals_template"], template, APPROVALS_SCHEMA
    )
    if problem is None:
        error.details["review_report"] = str(path)
        error.details["approvals_template"] = str(template)
        if args.progress != "json":
            print(f"lyric review report written to {path}", file=sys.stderr)
            print(
                f"fill in 'text' and 'approved_by' for each note in {template}, then rerun with "
                "--approve-lyrics FILE",
                file=sys.stderr,
            )
    else:
        error.details["review_report_error"] = problem
        print(f"warning: {problem}", file=sys.stderr)


def _print_result(result: Any, json_mode: bool) -> None:
    manifest = result.package.manifest
    formats = manifest["settings"]["formats"]
    if json_mode:
        payload = {
            "event": "result",
            "status": "ok",
            "package": str(result.destination),
            "tracks": len(manifest["tracks"]),
            "files": len(result.package.files),
            "formats": formats,
            "frames": result.package.frames,
            "duration_seconds": manifest["audio"]["duration_seconds"],
            "elapsed_seconds": round(result.seconds, 2),
            "warnings": list(result.warnings),
        }
        sys.stdout.write(json.dumps(payload) + "\n")
        sys.stdout.flush()
        return
    print(f"Published {result.destination}")
    print(
        f"  13 tracks ({', '.join(formats)}), {manifest['audio']['duration_seconds']} s, "
        f"{result.package.frames} frames; {result.seconds:.1f} s elapsed"
    )
    print("  manifest.json lists every file, its gains and its SHA-256")


def _config_report(args: argparse.Namespace, config: ResolvedConfig) -> dict[str, Any]:
    singers_dir = config.singers_dir
    singers = sorted(discover_singers(singers_dir)) if singers_dir and singers_dir.is_dir() else []
    host = config.host_binaries
    on_path = find_ffmpeg()
    return {
        "config_file": str(Path(args.config) if args.config else config_path()),
        "singers_dir": {
            "path": str(singers_dir) if singers_dir else None,
            "exists": bool(singers_dir and singers_dir.is_dir()),
            "singers": singers,
            "source": config.sources.get("singers_dir"),
        },
        "host": {
            "path": str(host) if host else None,
            "found": bool(host and (host / HOST_EXE).is_file()),
            "source": config.sources.get("host_dir"),
        },
        "dotnet_root": {
            "path": str(config.dotnet_root) if config.dotnet_root else None,
            "source": config.sources.get("dotnet_root"),
        },
        "ffmpeg": {
            "path": str(config.ffmpeg) if config.ffmpeg else None,
            "found": bool(config.ffmpeg and config.ffmpeg.is_file()),
            "source": config.sources.get("ffmpeg"),
            "on_path": str(on_path) if on_path else None,
        },
        "data_dir": {"path": str(config.layout.data), "source": config.sources.get("data_dir")},
        "output_dir": str(config.output_dir) if config.output_dir else None,
        "defaults": {
            "phonemizer": config.phonemizer,
            "renderer": config.renderer,
            "gain_profile": config.gain_profile.name,
            "singer": config.singer,
        },
    }


def _config_text(report: dict[str, Any]) -> str:
    sd, host, ff = report["singers_dir"], report["host"], report["ffmpeg"]
    defaults = report["defaults"]
    lines = [
        f"Config file: {report['config_file']}",
        f"Singers folder: {sd['path']} ({sd['source'] or 'not configured'})",
        "  voicebanks: " + (", ".join(sd["singers"]) if sd["singers"] else "none found"),
        f"Render host: {host['path']} "
        f"({'found' if host['found'] else 'NOT FOUND'}; {host['source'] or 'not configured'})",
        f".NET runtime: {report['dotnet_root']['path'] or 'from the system / DOTNET_ROOT'}",
        f"FFmpeg: {ff['path'] or 'not found'} "
        f"({'found' if ff['found'] else 'needed only for MP3'})",
        f"Data folder: {report['data_dir']['path']}",
        f"Defaults: phonemizer {defaults['phonemizer']}, renderer {defaults['renderer']}, "
        f"gain profile {defaults['gain_profile']}, "
        f"singer {defaults['singer'] or '(none: pass --singer)'}",
    ]
    text: str = "\n".join(lines) + "\n"
    return text


def run_config(args: argparse.Namespace) -> int:
    try:
        config = _resolve(args)
    except PipelineError as error:
        _print_error(error, json_mode=False)
        return _EXIT[error.category]
    report = _config_report(args, config)
    if args.format == "json":
        sys.stdout.write(json.dumps(report, indent=2) + "\n")
    else:
        sys.stdout.write(_config_text(report))
    return EXIT_OK


def dispatch(args: argparse.Namespace) -> int | None:
    if args.command == "generate":
        return run_generate(args)
    if args.command == "config":
        return run_config(args)
    return None


__all__ = ["add_parsers", "dispatch"]
