"""Command-line entry point. The core library is usable without the GUI.

Subcommands:

* ``check SCORE``: assess whether a capability can generate from the score;
* ``lines SCORE``: list the source lines and their identifiers (read-only suggestions, nothing
  is assigned).

Exit codes (the whole public contract): ``0`` ready, ``1`` not ready (a blocking finding, or an
advisory one under ``--strict``), ``2`` invocation, input or load failure. A readiness problem in a
score that loaded fine is a report and exit ``1``, never ``2``.
"""

import argparse
import re
import sys
from collections.abc import Sequence

from barbershop_tracks import __version__
from barbershop_tracks.core.errors import ScoreLoadError
from barbershop_tracks.core.musicxml import ParseResult, parse_musicxml
from barbershop_tracks.core.readiness import CAPABILITIES, RoleAssignments, assess_readiness
from barbershop_tracks.core.readiness.lines import describe_lines
from barbershop_tracks.core.readiness.render import (
    render_json,
    render_lines_json,
    render_lines_text,
    render_text,
)
from barbershop_tracks.models import VoiceRole

EXIT_READY = 0
EXIT_NOT_READY = 1
EXIT_USAGE = 2

_ASSIGN = re.compile(r"^([A-Za-z]+)=(\S.*)$")
_ROLES = {role.name: role for role in VoiceRole} | {role.value: role for role in VoiceRole}


def _assignment(text: str) -> tuple[VoiceRole, str]:
    """``ROLE=LINE``: the syntax and the role are checked here; whether the line exists is not."""
    match = _ASSIGN.match(text)
    if match is None:
        raise argparse.ArgumentTypeError(f"{text!r} is not ROLE=LINE (for example TENOR=P1/s1/v1)")
    role = _ROLES.get(match.group(1).lower()) or _ROLES.get(match.group(1).upper())
    if role is None:
        known = ", ".join(r.value for r in VoiceRole)
        raise argparse.ArgumentTypeError(f"unknown role {match.group(1)!r} (one of: {known})")
    return role, match.group(2)


def _line_id(text: str) -> str:
    if not text.strip():
        raise argparse.ArgumentTypeError("a line identifier must not be empty")
    return text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="barbershop-tracks",
        description="Generate four-part barbershop learning tracks from MusicXML.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")

    check = commands.add_parser(
        "check",
        help="assess whether a capability can generate from a score",
        description="Assess generation readiness. Exit 0 ready, 1 not ready, 2 usage/load error.",
    )
    check.add_argument("score", help="a .musicxml, .xml or .mxl file")
    check.add_argument(
        "--target",
        choices=sorted(CAPABILITIES),
        default="quartet-vocal",
        help="the generation capability to assess (default: quartet-vocal)",
    )
    check.add_argument(
        "--assign",
        action="append",
        default=[],
        type=_assignment,
        metavar="ROLE=LINE",
        help="assign a role to an exact source line, e.g. TENOR=P1/s1/v1 (repeat per role)",
    )
    check.add_argument(
        "--ignore",
        action="append",
        default=[],
        type=_line_id,
        metavar="LINE",
        help="exclude an exact source line on purpose (repeat per line)",
    )
    check.add_argument("--verse", help="the logical verse to analyze (default: automatic)")
    check.add_argument("--format", choices=("text", "json"), default="text")
    check.add_argument(
        "--strict", action="store_true", help="advisory findings also make the result not ready"
    )

    lines = commands.add_parser(
        "lines",
        help="list the source lines and their identifiers",
        description="List source lines. Suggestions are read-only and never applied.",
    )
    lines.add_argument("score", help="a .musicxml, .xml or .mxl file")
    lines.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def _load(path: str) -> ParseResult | None:
    try:
        return parse_musicxml(path)
    except ScoreLoadError as exc:
        print(f"error: {exc}", file=sys.stderr)
    except OSError as exc:
        print(f"error: cannot read {path}: {exc.strerror or exc}", file=sys.stderr)
    return None


def _run_check(args: argparse.Namespace) -> int:
    parsed = _load(args.score)
    if parsed is None:
        return EXIT_USAGE
    assignments = RoleAssignments(entries=tuple(args.assign), ignored=tuple(args.ignore))
    report = assess_readiness(parsed, assignments, CAPABILITIES[args.target], verse=args.verse)
    if args.format == "json":
        sys.stdout.write(render_json(report, strict=args.strict))
    else:
        sys.stdout.write(render_text(report, strict=args.strict))
    passed = report.clean if args.strict else report.ready
    return EXIT_READY if passed else EXIT_NOT_READY


def _run_lines(args: argparse.Namespace) -> int:
    parsed = _load(args.score)
    if parsed is None:
        return EXIT_USAGE
    infos = describe_lines(parsed)
    errors = len(parsed.issues.errors)
    if args.format == "json":
        sys.stdout.write(render_lines_json(infos, error_count=errors))
    else:
        sys.stdout.write(render_lines_text(infos, error_count=errors))
    return EXIT_READY


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)  # a usage error exits with status 2
    if args.command == "check":
        return _run_check(args)
    if args.command == "lines":
        return _run_lines(args)
    parser.print_help()
    return EXIT_READY
