"""Record and check M6 observations (no OpenUtau automation).

    observe.py list
    observe.py template EXPERIMENT_ID [--out FILE]
    observe.py validate FILE... [--allow-template]
    observe.py compare FILE...
    observe.py ustx-summary FILE.ustx

Committed observations live in tests/fixtures/openutau/observations/ as JSON; generated
MIDI/USTX/WAV files never do.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from catalog import BY_ID, CATALOG
from generate import part_a_expected
from observations import compare_events, dumps, load, staleness, template, validate
from recipes_part_a import RECIPES
from recipes_part_b import EXPERIMENTS, build_midi, expected_events
from research_common import sha256_hex
from ustx_summary import UstxReadError, load_yaml, summarize

from barbershop_tracks.core.handoff import prepare_handoff


def _expected_for(experiment_id: str) -> tuple[list[dict[str, Any]], str | None]:
    experiment = BY_ID[experiment_id]
    if experiment.part == "B" and experiment.input_id in EXPERIMENTS:
        source = EXPERIMENTS[experiment.input_id]
        return expected_events(source), sha256_hex(build_midi(source))
    if experiment.part == "A" and experiment.input_id in RECIPES:
        recipe = RECIPES[experiment.input_id]()
        result = prepare_handoff(
            recipe.parsed,
            recipe.assignments,
            name=recipe.artifact_id,
            source_name=f"{recipe.artifact_id}.synthetic",
            source_sha256=sha256_hex(recipe.artifact_id.encode("ascii")),
            ppq=recipe.ppq,
        )
        if result.handoff is None:
            raise SystemExit(f"{experiment_id}: its recipe is not exportable")
        return part_a_expected(result.handoff.midi.plan), result.handoff.manifest["midi"]["sha256"]
    return [], None


def _current_hash(data: Any) -> str | None:
    """The hash of the input this observation's experiment generates now (Part A/B), if known."""
    experiment_id = data.get("experiment_id") if isinstance(data, dict) else None
    if experiment_id not in BY_ID or BY_ID[experiment_id].part == "C":
        return None
    return _expected_for(experiment_id)[1]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M6 observation tooling")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    template_cmd = commands.add_parser("template")
    template_cmd.add_argument("experiment_id")
    template_cmd.add_argument("--out", type=Path)
    validate_cmd = commands.add_parser("validate")
    validate_cmd.add_argument("files", nargs="+", type=Path)
    validate_cmd.add_argument("--allow-template", action="store_true")
    compare_cmd = commands.add_parser("compare")
    compare_cmd.add_argument("files", nargs="+", type=Path)
    ustx_cmd = commands.add_parser("ustx-summary")
    ustx_cmd.add_argument("file", type=Path)
    args = parser.parse_args(argv)

    if args.command == "list":
        for e in CATALOG:
            flags = ("voicebank " if e.requires_voicebank else "") + (
                "manual" if e.requires_manual_openutau else ""
            )
            print(f"{e.experiment_id:28} part {e.part}  {flags.strip():18} {e.title}")
        return 0
    if args.command == "template":
        if args.experiment_id not in BY_ID:
            print(f"unknown experiment {args.experiment_id}", file=sys.stderr)
            return 2
        events, digest = _expected_for(args.experiment_id)
        text = dumps(template(BY_ID[args.experiment_id], events, input_sha256=digest))
        if args.out:
            args.out.write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
        return 0
    if args.command == "validate":
        failed = 0
        for path in args.files:
            data = load(path)
            problems = validate(
                data,
                allow_template=args.allow_template,
                current_input_sha256=_current_hash(data),
            )
            for problem in problems:
                print(f"{path.name}: {problem}", file=sys.stderr)
            failed += bool(problems)
            if not problems:
                print(f"{path.name}: ok")
        return 1 if failed else 0
    if args.command == "compare":
        differing = 0
        for path in args.files:
            data = load(path)
            stale = staleness(data, _current_hash(data))
            if stale:
                print(f"{path.name}: {stale}", file=sys.stderr)
                differing += 1
                continue
            diffs = compare_events(data["expected"]["events"], data["observed"]["events"])
            print(f"{path.name}: {'events agree' if not diffs else f'{len(diffs)} difference(s)'}")
            for diff in diffs:
                print(f"  {diff}")
            differing += bool(diffs)
        return 1 if differing else 0
    try:
        summary = summarize(load_yaml(args.file))
    except UstxReadError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    sys.stdout.write(json.dumps(summary, indent=2, ensure_ascii=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
